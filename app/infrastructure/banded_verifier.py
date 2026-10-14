"""Banded post-retrieval answerability verifier (Phase 5F experiment).

Isolated, feature-flagged verifier.  It is NOT wired into the production
pipeline and the Phase 3G-B gate (``app/infrastructure/answerability.py``)
is left untouched.  ``enabled`` defaults to ``False``, so instantiating this
module changes no behavior unless explicitly enabled.

Policy (on the top-1 cosine score):
  - no hits or cosine < band_low        -> abstain (frozen Phase 5D behavior)
  - band_low <= cosine < band_high      -> LLM verifier:
      SUPPORTED -> accept, INSUFFICIENT_EVIDENCE -> abstain
  - cosine >= band_high                 -> accept (frozen Phase 5D behavior)

Fail-open: timeout / LLM error / malformed verdict fall back to the baseline
decision (accept, since in-band implies cosine >= band_low).
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.logging import get_logger
from app.infrastructure.llm import (
    OllamaClient,
    OllamaClientError,
    OllamaRequest,
    OllamaResponseError,
    OllamaTimeoutError,
)
from app.infrastructure.search import SearchHit

logger = get_logger(__name__)

VerifierVote = Literal["SUPPORTED", "INSUFFICIENT_EVIDENCE"]
FallbackKind = Literal["none", "timeout", "error", "malformed"]

_EVIDENCE_SYSTEM_PROMPT = """\
You are an evidence verifier for a retrieval-augmented question-answering \
system. You evaluate whether the provided retrieved chunks, considered \
together, contain the information needed to answer a question.

Rules:
- ONLY use the provided chunks as your knowledge source.
- Do NOT use outside or world knowledge.
- Do NOT invent or assume facts that are not present in the chunks.
- Do NOT require exact wording; the answer may be paraphrased.
- Synthesis across multiple chunks is allowed when the answer is spread \
across them.
- DISTINGUISH "the chunks are about the same topic as the question" from \
"the chunks actually answer the question". Topic overlap alone is NOT \
sufficient; the required fact or information must be present.
- If the required information is present (possibly via synthesis), return \
SUPPORTED.
- If the chunks only mention the topic but do not contain the requested \
fact, return INSUFFICIENT_EVIDENCE.
"""


class BandedVerdict(BaseModel):
    """Structured verdict from the banded verifier LLM."""

    model_config = ConfigDict(extra="forbid")

    verdict: VerifierVote
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_chunk_indices: list[int] = Field(default_factory=list)
    reason: str = ""


@dataclass(slots=True)
class BandedDecision:
    """Final gate decision for a single query."""

    abstain: bool
    abstain_baseline: bool
    verifier_invoked: bool
    vote: VerifierVote | None
    confidence: float | None
    supporting_chunk_indices: list[int]
    reason: str
    fallback: FallbackKind
    latency_ms: float | None


class BandedGate:
    """Banded post-retrieval answerability verifier (Phase 5F experiment)."""

    def __init__(
        self,
        client: OllamaClient,
        *,
        enabled: bool = False,
        band_low: float = 0.45,
        band_high: float = 0.62,
        max_evidence_chunks: int = 5,
        timeout_seconds: float = 10.0,
        model: str | None = None,
    ) -> None:
        self._client = client
        self._enabled = enabled
        self._band_low = band_low
        self._band_high = band_high
        self._max_evidence_chunks = max_evidence_chunks
        self._timeout_seconds = timeout_seconds
        self._model = model

    def evaluate(self, question: str, hits: Sequence[SearchHit]) -> BandedDecision:
        """Apply the banded policy to *hits* for *question*."""

        top = hits[0] if hits else None
        abstain_baseline = top is None or top.cosine_score < self._band_low

        if not self._enabled or abstain_baseline:
            return self._plain(abstain_baseline, "gate disabled or below band")

        if top is None or top.cosine_score >= self._band_high:
            return self._plain(False, "outside band (above band_high)")

        return self._verify(question, hits)

    def _verify(self, question: str, hits: Sequence[SearchHit]) -> BandedDecision:
        evidence_text = self._build_evidence_block(hits)
        user_prompt = (
            f"Question: {question}\n\n"
            f"Retrieved evidence chunks:\n{evidence_text}\n\n"
            "Return a single JSON object:\n"
            '{"verdict": "SUPPORTED" | "INSUFFICIENT_EVIDENCE", '
            '"confidence": 0.0 to 1.0, '
            '"supporting_chunk_indices": [1-based indices, may be empty], '
            '"reason": "one short sentence"}.'
        )
        request = OllamaRequest(
            system_prompt=_EVIDENCE_SYSTEM_PROMPT,
            prompt=user_prompt,
            model=self._model,
            options={"temperature": 0.0},
        )

        t0 = time.perf_counter()
        try:
            verdict: BandedVerdict = self._call_llm(request)
        except OllamaTimeoutError:
            return self._fallback("timeout", t0)
        except OllamaResponseError:
            return self._fallback("malformed", t0)
        except OllamaClientError:
            return self._fallback("error", t0)
        except Exception:
            return self._fallback("malformed", t0)

        if not isinstance(verdict, BandedVerdict):
            return self._fallback("malformed", t0)

        latency_ms = (time.perf_counter() - t0) * 1000
        abstain = verdict.verdict == "INSUFFICIENT_EVIDENCE"
        logger.info(
            "Banded verifier verdict.",
            extra={
                "vote": verdict.verdict,
                "confidence": verdict.confidence,
                "elapsed_ms": round(latency_ms, 1),
            },
        )
        return BandedDecision(
            abstain=abstain,
            abstain_baseline=False,
            verifier_invoked=True,
            vote=verdict.verdict,
            confidence=verdict.confidence,
            supporting_chunk_indices=list(verdict.supporting_chunk_indices),
            reason=verdict.reason,
            fallback="none",
            latency_ms=latency_ms,
        )

    def _call_llm(self, request: OllamaRequest) -> BandedVerdict:
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(self._client.generate_json, request, response_model=BandedVerdict)
        try:
            try:
                result = future.result(timeout=self._timeout_seconds)
            except TimeoutError as exc:
                raise OllamaTimeoutError(
                    f"Banded verifier timed out after {self._timeout_seconds}s"
                ) from exc
        finally:
            pool.shutdown(wait=False)
        if not isinstance(result, BandedVerdict):
            raise OllamaClientError(f"Unexpected verifier response type: {type(result).__name__}")
        return result

    def _plain(self, abstain: bool, reason: str) -> BandedDecision:
        return BandedDecision(
            abstain=abstain,
            abstain_baseline=abstain,
            verifier_invoked=False,
            vote=None,
            confidence=None,
            supporting_chunk_indices=[],
            reason=reason,
            fallback="none",
            latency_ms=None,
        )

    def _fallback(self, kind: FallbackKind, t0: float) -> BandedDecision:
        latency_ms = (time.perf_counter() - t0) * 1000
        logger.warning(
            "Banded verifier %s — failing open to baseline decision.",
            kind,
            extra={"elapsed_ms": round(latency_ms, 1)},
        )
        return BandedDecision(
            abstain=False,
            abstain_baseline=False,
            verifier_invoked=True,
            vote=None,
            confidence=None,
            supporting_chunk_indices=[],
            reason=f"verifier {kind} — baseline accept",
            fallback=kind,
            latency_ms=latency_ms,
        )

    def _build_evidence_block(self, hits: Sequence[SearchHit]) -> str:
        """Format the top-N chunks into a numbered evidence block."""

        blocks: list[str] = []
        for idx, hit in enumerate(hits[: self._max_evidence_chunks], start=1):
            text = " ".join(hit.text.split())
            blocks.append(f"[CHUNK {idx}] Source: {hit.source}\n{text}")
        return "\n\n".join(blocks)
