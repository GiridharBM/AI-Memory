"""RAG question-answering use case over the knowledge base.

The QA outcome contract (Phase 6B):

- ANSWERED  — generation succeeded; ``answer`` text (verbatim), ``sources``
  (full retrieved hits), ``citations`` (validated [SOURCE N] references that
  resolve to real retrieved hits, deduplicated), ``invalid_citations``
  (out-of-range / SOURCE 0 numbers, never silently remapped).
- ABSTAINED — the retrieval-confidence (or answerability) gate rejected the
  query; ``answer`` is the fixed abstention message, ``sources`` is empty and
  the LLM is never invoked.  ``outcome == "abstained"`` plus
  ``abstention_reason`` carries the gate diagnostic.
- FAILED    — a technical failure; represented by raised ``QAError`` /
  ``QATimeoutError``, never by a ``QAAnswer``.  A failure is therefore always
  distinguishable from a legitimate abstention.  Phase 6C: an empty or
  whitespace-only model response is also FAILED (``QAEmptyAnswerError``).

An ANSWERED result may optionally carry ``latency_seconds`` (generation wall
time) and ``telemetry`` (observational statistics) for future evaluation.  These
never influence the outcome.
"""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from app.core.config import Settings
from app.core.logging import get_logger
from app.application.system_facts import SystemFactsRouter, SystemFactsService
from app.infrastructure.answerability import AnswerabilityGate, AnswerabilityResult
from app.infrastructure.llm import (
    OllamaClient,
    OllamaClientError,
    OllamaRequest,
    OllamaTextResponse,
    OllamaTimeoutError,
)
from app.infrastructure.reranker import CrossEncoderReranker
from app.infrastructure.search import SearchHit, SearchService
from app.prompts.qa import QA_SYSTEM_PROMPT, build_qa_user_prompt

logger = get_logger(__name__)

MAX_CONTEXT_CHUNKS = 8
MAX_CONTEXT_CHARS = 12_000

ABSTENTION_MESSAGE = (
    "I don't have enough relevant information in the knowledge base "
    "to answer this question."
)

OUTCOME_ANSWERED = "answered"
OUTCOME_ABSTAINED = "abstained"

ORIGIN_RETRIEVAL = "retrieval"
ORIGIN_SYSTEM = "system"

_SOURCE_CITATION_PATTERN = re.compile(r"\[SOURCE\s+(\d+)\]", re.IGNORECASE)

_INSUFFICIENCY_LANGUAGE_PATTERN = re.compile(
    r"don.?t have enough|do not have enough|enough (?:relevant )?information|"
    r"insufficient (?:evidence|information)|cannot (?:determine|answer)|"
    r"can.?t (?:determine|answer)|not enough information|unable to (?:answer|determine)|"
    r"no (?:relevant )?information|does not (?:contain|provide)|"
    r"not (?:found|present) (?:in|within)",
    re.IGNORECASE,
)


def has_insufficiency_language(text: str) -> bool:
    """Measurement-only heuristic: obvious insufficiency/abstention phrasing.

    Observational telemetry only.  The result is recorded in the QA outcome's
    telemetry and NEVER influences the ANSWERED / ABSTAINED / FAILED decision.
    """

    return bool(_INSUFFICIENCY_LANGUAGE_PATTERN.search(text or ""))


class QAError(RuntimeError):
    """Raised when the QA workflow cannot produce an answer."""


class QAEmptyAnswerError(QAError):
    """Raised when the model returns an empty or whitespace-only response.

    Phase 6C: distinct from ``QATimeoutError`` (the server hung) and from a
    plain ``QAError`` (the server is unreachable).  Still a FAILED-style
    failure, never an ABSTAINED answer.
    """


class QATimeoutError(QAError):
    """Raised when QA generation exceeds the configured ``qa.timeout_seconds``.

    Distinct from a plain QAError so the CLI can tell "the model hung" apart
    from "the Ollama server is unreachable".
    """


@dataclass(slots=True)
class ObservationTelemetry:
    """Observational evaluation metadata attached to a QAAnswer (Phase 6C).

    Computed on the success path; values never feed back into the
    ANSWERED / ABSTAINED decision.
    """

    question: str
    answer_length: int
    answer_has_insufficiency_language: bool
    source_count: int
    citation_count: int
    invalid_citation_count: int
    duplicate_citation_count: int
    latency_seconds: float

    @classmethod
    def answered(
        cls,
        *,
        question: str,
        answer: str,
        hits: int,
        citations: int,
        invalid_citations: int,
        duplicate_citations: int,
        latency_seconds: float,
    ) -> ObservationTelemetry:
        """Build telemetry for an ANSWERED outcome (measurement-only)."""

        return cls(
            question=question,
            answer_length=len(answer),
            answer_has_insufficiency_language=has_insufficiency_language(answer),
            source_count=hits,
            citation_count=citations,
            invalid_citation_count=invalid_citations,
            duplicate_citation_count=duplicate_citations,
            latency_seconds=latency_seconds,
        )


def _abstention_answer(question: str, reason: str | None) -> QAAnswer:
    """Build an ABSTAINED QAAnswer with measurement-only telemetry attached."""

    return QAAnswer(
        answer=ABSTENTION_MESSAGE,
        sources=[],
        model="",
        outcome=OUTCOME_ABSTAINED,
        abstention_reason=reason,
        telemetry=ObservationTelemetry.answered(
            question=question,
            answer=ABSTENTION_MESSAGE,
            hits=0,
            citations=0,
            invalid_citations=0,
            duplicate_citations=0,
            latency_seconds=0.0,
        ),
    )


@dataclass(slots=True)
class SourceCitation:
    """A citation the model produced that resolves to a retrieved source.

    ``number`` is the ``[SOURCE N]`` number exactly as the model cited it;
    ``hit`` is the retrieved source it maps to (``sources[number - 1]``).
    """

    number: int
    hit: SearchHit


@dataclass(slots=True)
class QAAnswer:
    """A generated answer together with the retrieved sources it is grounded on.

    ``outcome`` is ``answered`` or ``abstained``; an ANSWERED answer carries
    the validated ``citations``, while ``invalid_citations`` (numbers outside
    the retrieved context, e.g. SOURCE 0 or SOURCE 9 with 3 sources) are
    reported but never silently remapped.
    """

    answer: str
    sources: list[SearchHit] = field(default_factory=list)
    model: str = ""
    outcome: str = OUTCOME_ANSWERED
    abstention_reason: str | None = None
    citations: list[SourceCitation] = field(default_factory=list)
    invalid_citations: list[int] = field(default_factory=list)
    duplicate_citations: int = 0
    latency_seconds: float | None = None
    telemetry: ObservationTelemetry | None = None
    origin: str = ORIGIN_RETRIEVAL


@dataclass(slots=True)
class AbstentionResult:
    """Outcome of the retrieval-confidence gate."""

    abstain: bool
    reason: str | None = None


def extract_citations(answer: str) -> list[int]:
    """Return every ``[SOURCE N]`` citation number in order of appearance.

    Duplicates are preserved.  Malformed tokens that do not match the pattern
    (e.g. ``[SOURCE x]``, ``SOURCE 1`` without brackets) are plain text and
    are neither treated as citations nor reported as invalid.
    """

    return [int(number) for number in _SOURCE_CITATION_PATTERN.findall(answer)]


def resolve_citations(
    answer: str,
    hits: Sequence[SearchHit],
) -> tuple[list[SourceCitation], list[int], int]:
    """Validate the citations in ``answer`` against the retrieved ``hits``.

    Returns ``(citations, invalid_numbers, duplicate_count)``:

    - ``citations``: valid references (``1 <= N <= len(hits)``), deduplicated,
      in citation order of first use.
    - ``invalid_numbers``: out-of-range numbers (including 0), each listed
      once, in order of first use.  They are never mapped to another source.
    - ``duplicate_count``: how many times a valid number was cited again.

    The answer text itself is never altered.
    """

    citations: list[SourceCitation] = []
    invalid_numbers: list[int] = []
    seen: set[int] = set()
    invalid_seen: set[int] = set()
    duplicates = 0
    for number in extract_citations(answer):
        if 1 <= number <= len(hits):
            if number in seen:
                duplicates += 1
            else:
                seen.add(number)
                citations.append(SourceCitation(number=number, hit=hits[number - 1]))
        elif number not in invalid_seen:
            invalid_seen.add(number)
            invalid_numbers.append(number)
    return citations, invalid_numbers, duplicates


class AbstentionGate:
    """Decide whether retrieved evidence is sufficient to ground an answer.

    Uses the raw per-leg scores (cosine similarity, BM25) that RRF fuses
    into ``SearchHit.score``.  When a cross-encoder reranker is active, its
    score (``rerank_score``) serves as a SECONDARY ABSTENTION signal.

    Score semantics:
    - ``rerank_score``: cross-encoder relevance score [0.0, 1.0].
      Higher = more relevant.  0.0 means reranker was disabled or failed.
    - ``cosine_score``: raw cosine similarity from the vector leg.
      0.0 means either the embedding failed or the vector store found no results.
    - ``bm25_score``: raw Okapi BM25 score from the lexical leg.
      0.0 means BM25 found no matching terms.

    Signals (checked in order):
    1. No results at all → abstain.
    2. Reranker-active path (``rerank_score > 0``):
       a. cosine >= min_cosine AND rerank_score >= min_rerank_score → accept.
       b. Any threshold below minimum → abstain (AND gate).
       BM25 does NOT bypass either threshold.
    3. Reranker-inactive path (``rerank_score == 0``, Phase 3B/3E fallback):
       a. No evidence from either leg (both raw scores are 0.0) → abstain.
       b. Top-1 cosine similarity below *min_cosine* → abstain.
          BM25 is a retrieval signal, not an acceptance override.
    """

    def __init__(
        self,
        min_cosine: float = 0.25,
        min_rerank_score: float = 0.0,
    ) -> None:
        self._min_cosine = min_cosine
        self._min_rerank_score = min_rerank_score

    def evaluate(self, hits: list[SearchHit]) -> AbstentionResult:
        if not hits:
            return AbstentionResult(True, "no_results")
        top = hits[0]

        # Reranker-active path: rerank_score > 0 means the reranker ran
        if top.rerank_score > 0.0:
            # AND gate: both cosine and reranker must pass
            cosine_ok = top.cosine_score >= self._min_cosine
            rerank_ok = (
                self._min_rerank_score <= 0.0
                or top.rerank_score >= self._min_rerank_score
            )
            if cosine_ok and rerank_ok:
                return AbstentionResult(False)
            # One or both thresholds failed → abstain
            reasons = []
            if not cosine_ok:
                reasons.append(
                    f"cosine_below_threshold ({top.cosine_score:.4f} < {self._min_cosine})"
                )
            if not rerank_ok:
                reasons.append(
                    f"rerank_below_threshold ({top.rerank_score:.4f} < {self._min_rerank_score})"
                )
            return AbstentionResult(True, " AND ".join(reasons))

        # Reranker-inactive path: cosine is the primary gate signal
        if top.cosine_score == 0.0 and top.bm25_score == 0.0:
            return AbstentionResult(True, "no_evidence")
        if top.cosine_score < self._min_cosine:
            return AbstentionResult(
                True,
                f"cosine_below_threshold ({top.cosine_score:.4f} < {self._min_cosine})",
            )
        return AbstentionResult(False)


def build_context(hits: Sequence[SearchHit]) -> str:
    """Build a bounded, deterministic context block from ranked hits.

    Chunks are bounded by ``MAX_CONTEXT_CHUNKS`` and a total character budget
    so excessive retrieval results cannot create an uncontrolled prompt.
    """

    blocks: list[str] = []
    used = 0
    for index, hit in enumerate(hits[:MAX_CONTEXT_CHUNKS], start=1):
        remaining = MAX_CONTEXT_CHARS - used
        if remaining <= 0:
            break
        text = " ".join(hit.text.split())
        if len(text) > remaining:
            text = text[:remaining]

        section = hit.metadata.get("heading") or hit.metadata.get("parent_heading")
        block = f"[SOURCE {index}]\nSource: {hit.source}\n"
        if section:
            block += f"Section: {section}\n"
        if hit.rerank_score > 0.0:
            block += f"Rerank: {hit.rerank_score:.4f}\n"
        block += f"Score: {hit.score:.4f}\nContent:\n{text}"

        blocks.append(block)
        used += len(text)
    return "\n\n".join(blocks)


class QAWorkflow:
    """Answer a question grounded in retrieved knowledge base context.

    Retrieval goes through the existing ``SearchService`` hybrid pipeline;
    generation goes through the existing ``OllamaClient``.  Neither the vector
    store nor the retrieved documents are ever modified.

    When *min_cosine* is provided (default 0.25), an ``AbstentionGate`` rejects
    queries whose top-1 cosine similarity is below the threshold, returning a
    clear "insufficient evidence" answer without invoking the LLM.

    When a *reranker* is provided and enabled, an additional cross-encoder
    reranking step runs between RRF candidate generation and the abstention
    gate.  The gate then uses the reranker's relevance score as the primary
    acceptance signal (falling back to cosine+BM25 when the reranker is
    unavailable).
    """

    def __init__(
        self,
        search_service: SearchService,
        ollama_client: OllamaClient,
        *,
        model: str | None = None,
        min_cosine: float = 0.25,
        reranker: CrossEncoderReranker | None = None,
        min_rerank_score: float = 0.0,
        answerability_gate: AnswerabilityGate | None = None,
        generation_timeout_seconds: float | None = None,
        system_facts: SystemFactsService | None = None,
    ) -> None:
        self._search_service = search_service
        self._ollama_client = ollama_client
        self._model = model
        self._reranker = reranker
        self._answerability_gate = answerability_gate
        self._generation_timeout_seconds = generation_timeout_seconds
        self._system_facts = system_facts
        self._system_facts_router = SystemFactsRouter()
        self._abstention_gate = AbstentionGate(
            min_cosine=min_cosine,
            min_rerank_score=min_rerank_score,
        )

    @classmethod
    def create_default(cls, settings: Settings, *, model: str | None = None) -> QAWorkflow:
        """Build the production workflow from application settings."""

        search_service = SearchService.create_default(settings)
        # The QA generation client gets the dedicated QA timeout.  The
        # answerability gate keeps the default ollama timeout (its own
        # `answerability.timeout_seconds` governs the request), so only the
        # generation step is bounded by `qa.timeout_seconds`.
        generation_client = OllamaClient(
            settings.ollama.model_copy(update={"timeout_seconds": settings.qa.timeout_seconds}),
        )
        gate_client = OllamaClient(settings.ollama)

        reranker: CrossEncoderReranker | None = None
        min_rerank_score = 0.0
        if settings.reranker.enabled:
            reranker = CrossEncoderReranker(settings.reranker)
            min_rerank_score = settings.reranker.min_score

        answerability_gate: AnswerabilityGate | None = None
        if settings.answerability.enabled:
            answerability_gate = AnswerabilityGate(
                gate_client,
                model=settings.answerability.model,
                timeout_seconds=settings.answerability.timeout_seconds,
                max_evidence_chunks=settings.answerability.max_evidence_chunks,
            )

        return cls(
            search_service,
            generation_client,
            model=model,
            min_cosine=0.25,
            reranker=reranker,
            min_rerank_score=min_rerank_score,
            answerability_gate=answerability_gate,
            generation_timeout_seconds=settings.qa.timeout_seconds,
            system_facts=SystemFactsService(settings),
        )

    def ask(
        self,
        question: str,
        *,
        top_k: int = 5,
        min_score: float = 0.0,
        filter: dict[str, object] | None = None,
    ) -> QAAnswer:
        """Answer ``question`` using the top retrieved sources."""

        question = question.strip() if question else ""
        if not question:
            raise QAError("Question must not be empty.")

        if self._system_facts is not None:
            intent = self._system_facts_router.route(question)
            if intent is not None:
                fact = self._system_facts.resolve(intent)
                logger.info(
                    "Answering from System Facts.",
                    extra={"intent": intent, "question": question},
                )
                return QAAnswer(
                    answer=fact.answer,
                    sources=[],
                    model="",
                    outcome=OUTCOME_ANSWERED,
                    origin=ORIGIN_SYSTEM,
                )

        # When reranker is active, retrieve extra candidates for reranking
        rerank_top_n = 0
        if self._reranker and self._reranker.is_available:
            rerank_top_n = getattr(self._reranker, '_config', None)
            rerank_top_n = rerank_top_n.top_n if rerank_top_n else 20

        search_top_k = max(top_k, rerank_top_n) if rerank_top_n else top_k
        hits = self._search_service.search(
            question, top_k=search_top_k, min_score=min_score, filter=filter,
        )
        logger.info(
            "QA retrieval completed.",
            extra={"question": question, "hits": len(hits), "top_k": top_k},
        )

        # Rerank if available
        if self._reranker and self._reranker.is_available and hits:
            hits = self._reranker.rerank(question, hits, top_k=top_k)
            logger.info(
                "Reranking completed.",
                extra={
                    "question": question,
                    "reranked": len(hits),
                    "top_rerank_score": hits[0].rerank_score if hits else 0.0,
                },
            )

        # Truncate to top_k after reranking
        hits = hits[:top_k]

        abstention = self._abstention_gate.evaluate(hits)
        if abstention.abstain:
            logger.info(
                "Abstaining from answer.",
                extra={"reason": abstention.reason, "question": question},
            )
            return _abstention_answer(question, abstention.reason)

        # Post-retrieval answerability gate (Phase 3G-B): verify evidence supports
        # the question before invoking the QA generation LLM.
        if self._answerability_gate is not None:
            evidence_result: AnswerabilityResult = self._answerability_gate.verify(question, hits)
            if not evidence_result.sufficient:
                logger.info(
                    "Answerability gate: abstaining.",
                    extra={"reason": evidence_result.reason, "question": question},
                )
                return _abstention_answer(question, str(evidence_result.reason))

        context = build_context(hits)
        prompt = build_qa_user_prompt(question, context)
        start_time = time.perf_counter()
        request = OllamaRequest(
            system_prompt=QA_SYSTEM_PROMPT,
            prompt=prompt,
            model=self._model,
        )
        try:
            if self._generation_timeout_seconds is not None:
                response = self._generate_with_deadline(
                    request, self._generation_timeout_seconds
                )
            else:
                response = self._ollama_client.generate_text(request)
        except OllamaTimeoutError as exc:
            logger.warning("QA generation timed out.", exc_info=True)
            raise QATimeoutError(
                "Unable to generate an answer: the request timed out after "
                "the configured QA timeout (qa.timeout_seconds)."
            ) from exc
        except OllamaClientError as exc:
            logger.warning("QA generation failed: Ollama unavailable or errored.", exc_info=True)
            raise QAError(
                "Unable to generate an answer because the Ollama server is "
                "unavailable or returned an error."
            ) from exc
        except Exception as exc:
            # Phase 6C: any unexpected provider/model exception is surfaced
            # through the QA failure hierarchy rather than leaking a raw
            # traceback to the normal CLI failure path.
            logger.warning("QA generation raised an unexpected error.", exc_info=True)
            raise QAError(
                "Unable to generate an answer: the model produced an unexpected error."
            ) from exc
        finally:
            generation_latency_s = time.perf_counter() - start_time

        if not response.response.strip():
            logger.warning(
                "QA generation returned an empty response (treated as failure).",
                extra={"question": question},
            )
            raise QAEmptyAnswerError(
                "Unable to generate an answer: the model returned an empty response."
            )

        citations, invalid_numbers, duplicates = resolve_citations(response.response, hits)
        if invalid_numbers:
            logger.warning(
                "QA answer cites source numbers outside the retrieved context.",
                extra={"invalid": invalid_numbers, "question": question},
            )

        return QAAnswer(
            answer=response.response,
            sources=list(hits),
            model=response.model,
            outcome=OUTCOME_ANSWERED,
            citations=citations,
            invalid_citations=invalid_numbers,
            duplicate_citations=duplicates,
            latency_seconds=generation_latency_s,
            telemetry=ObservationTelemetry.answered(
                question=question,
                answer=response.response,
                hits=len(hits),
                citations=len(citations),
                invalid_citations=len(invalid_numbers),
                duplicate_citations=duplicates,
                latency_seconds=generation_latency_s,
            ),
        )

    def _generate_with_deadline(
        self, request: OllamaRequest, timeout_seconds: float
    ) -> OllamaTextResponse:
        """Run generation under a true wall-clock deadline (Phase 6F-A).

        Mirrors the BandedVerifier pattern: the model call runs on a worker
        thread and ``future.result(timeout=...)`` enforces the wall-clock
        budget.  An expired deadline surfaces as ``OllamaTimeoutError`` so the
        existing ``ask()`` error mapping applies.  The worker is left to finish
        after an expiry (matches BandedVerifier); it owns no shared mutable
        state.
        """

        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(self._ollama_client.generate_text, request)
        try:
            try:
                return future.result(timeout=timeout_seconds)
            except TimeoutError as exc:
                raise OllamaTimeoutError(
                    f"QA generation exceeded the wall-clock timeout of "
                    f"{timeout_seconds:g} seconds."
                ) from exc
        finally:
            pool.shutdown(wait=False)
