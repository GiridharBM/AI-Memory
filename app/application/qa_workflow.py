"""RAG question-answering use case over the knowledge base."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.core.config import Settings
from app.core.logging import get_logger
from app.infrastructure.llm import OllamaClient, OllamaClientError, OllamaRequest
from app.infrastructure.reranker import CrossEncoderReranker, RerankerConfig
from app.infrastructure.search import SearchHit, SearchService
from app.prompts.qa import QA_SYSTEM_PROMPT, build_qa_user_prompt

logger = get_logger(__name__)

MAX_CONTEXT_CHUNKS = 8
MAX_CONTEXT_CHARS = 12_000

ABSTENTION_MESSAGE = (
    "I don't have enough relevant information in the knowledge base "
    "to answer this question."
)


class QAError(RuntimeError):
    """Raised when the QA workflow cannot produce an answer."""


@dataclass(slots=True)
class QAAnswer:
    """A generated answer together with the retrieved sources it is grounded on."""

    answer: str
    sources: list[SearchHit] = field(default_factory=list)
    model: str = ""


@dataclass(slots=True)
class AbstentionResult:
    """Outcome of the retrieval-confidence gate."""

    abstain: bool
    reason: str | None = None


class AbstentionGate:
    """Decide whether retrieved evidence is sufficient to ground an answer.

    Uses the raw per-leg scores (cosine similarity, BM25) that RRF fuses
    into ``SearchHit.score``.  When a cross-encoder reranker is active, its
    score (``rerank_score``) serves as the primary relevance signal.

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
       a. High rerank_score (>= *min_rerank_score*) → accept.
       b. Low rerank_score BUT cosine OR BM25 evidence exists → accept
          (reranker may under-score documents that are genuinely relevant
          to the query; raw retrieval evidence overrides a low reranker
          score when the reranker is not confident).
       c. Low rerank_score AND no raw evidence → abstain.
    3. Reranker-inactive path (``rerank_score == 0``, Phase 3B fallback):
       a. No evidence from either leg (both raw scores are 0.0) → abstain.
       b. Top-1 cosine similarity below *min_cosine* AND no BM25 evidence
          → abstain.  BM25-only results (cosine=0.0, bm25>0) pass.
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
            # High reranker confidence → accept
            if self._min_rerank_score > 0.0 and top.rerank_score >= self._min_rerank_score:
                return AbstentionResult(False)
            # Low reranker confidence BUT raw evidence exists → accept
            # (reranker may under-score genuinely relevant documents;
            #  raw retrieval evidence overrides when the reranker is uncertain)
            if top.cosine_score > 0.0 or top.bm25_score > 0.0:
                return AbstentionResult(False)
            # Low reranker confidence AND no raw evidence → abstain
            return AbstentionResult(
                True,
                f"low_rerank_no_evidence (rerank={top.rerank_score:.4f})",
            )

        # Reranker-inactive path: fall back to Phase 3B cosine + BM25 logic
        if top.cosine_score == 0.0 and top.bm25_score == 0.0:
            return AbstentionResult(True, "no_evidence")
        if top.cosine_score < self._min_cosine and top.bm25_score == 0.0:
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
    ) -> None:
        self._search_service = search_service
        self._ollama_client = ollama_client
        self._model = model
        self._reranker = reranker
        self._abstention_gate = AbstentionGate(
            min_cosine=min_cosine,
            min_rerank_score=min_rerank_score,
        )

    @classmethod
    def create_default(cls, settings: Settings, *, model: str | None = None) -> QAWorkflow:
        """Build the production workflow from application settings."""

        search_service = SearchService.create_default(settings)
        ollama_client = OllamaClient(settings.ollama)

        reranker: CrossEncoderReranker | None = None
        min_rerank_score = 0.0
        if settings.reranker.enabled:
            reranker = CrossEncoderReranker(settings.reranker)
            min_rerank_score = settings.reranker.min_score

        return cls(
            search_service,
            ollama_client,
            model=model,
            min_cosine=0.25,
            reranker=reranker,
            min_rerank_score=min_rerank_score,
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
            return QAAnswer(answer=ABSTENTION_MESSAGE, sources=[], model="")

        context = build_context(hits)
        prompt = build_qa_user_prompt(question, context)
        try:
            response = self._ollama_client.generate_text(
                OllamaRequest(
                    system_prompt=QA_SYSTEM_PROMPT,
                    prompt=prompt,
                    model=self._model,
                )
            )
        except OllamaClientError as exc:
            logger.warning("QA generation failed: Ollama unavailable or errored.", exc_info=True)
            raise QAError(
                "Unable to generate an answer because the Ollama server is "
                "unavailable or returned an error."
            ) from exc

        return QAAnswer(answer=response.response, sources=list(hits), model=response.model)
