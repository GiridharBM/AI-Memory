"""Post-retrieval answerability/evidence gate (Phase 3G-B).

Evaluates whether the retrieved chunks collectively contain enough evidence
to answer the question.  Operates AFTER the existing AbstentionGate and
before QA generation — a second-pass filter that targets topic-adjacent
false positives (high cosine, no answerable evidence).

When ``enabled=false`` the gate is never instantiated; the system behaves
byte-identically to the frozen Phase 3E baseline.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

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

_EVIDENCE_SYSTEM_PROMPT = """\
You are a strict evidence verifier. You evaluate whether the provided \
retrieved chunks contain the information needed to answer a question.

Rules:
- ONLY use the provided chunks as your knowledge source.
- Do NOT use any outside/world knowledge.
- Do NOT infer, guess, or assume information not explicitly present.
- Return SUPPORTED ONLY if the chunks explicitly contain the answer.
- When in doubt, return INSUFFICIENT_EVIDENCE.
- Be conservative: prefer INSUFFICIENT_EVIDENCE over SUPPORTED.
"""


class EvidenceVerdict(BaseModel):
    """Structured output from the evidence verifier LLM."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["SUPPORTED", "INSUFFICIENT_EVIDENCE"]


@dataclass(slots=True)
class AnswerabilityResult:
    """Outcome of the evidence verification gate."""

    sufficient: bool
    reason: str | None = None


class AnswerabilityGate:
    """Post-retrieval gate that verifies evidence supports the question.

    Uses the project's existing LLM (OllamaClient + generate_json) with a
    structured pydantic response model to enforce schema compliance.  The
    gate is fail-open: any LLM error, timeout, or parse failure results in
    ``AnswerabilityResult(sufficient=True)`` so the system falls through to
    the existing QA path unchanged.
    """

    def __init__(
        self,
        client: OllamaClient,
        *,
        model: str | None = None,
        timeout_seconds: float = 10.0,
        max_evidence_chunks: int = 5,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_evidence_chunks = max_evidence_chunks

    def verify(self, question: str, hits: Sequence[SearchHit]) -> AnswerabilityResult:
        """Verify whether *hits* contain answerable evidence for *question*.

        Returns ``AnswerabilityResult(sufficient=True)`` on any LLM failure
        (fail-open) so the existing QA path proceeds unchanged.
        """

        if not hits:
            return AnswerabilityResult(False, "no_results")

        evidence_text = self._build_evidence_block(hits)
        user_prompt = (
            f"Question: {question}\n\n"
            f"Retrieved evidence chunks:\n{evidence_text}\n\n"
            "Answer: {"
        )

        t0 = time.perf_counter()
        try:
            verdict: EvidenceVerdict = self._client.generate_json(  # type: ignore[assignment]
                OllamaRequest(
                    system_prompt=_EVIDENCE_SYSTEM_PROMPT,
                    prompt=user_prompt,
                    model=self._model,
                    options={"temperature": 0.0},
                ),
                response_model=EvidenceVerdict,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "Answerability gate verdict.",
                extra={
                    "verdict": verdict.verdict,
                    "elapsed_ms": round(elapsed_ms, 1),
                    "chunks": len(hits[: self._max_evidence_chunks]),
                },
            )
            if verdict.verdict == "INSUFFICIENT_EVIDENCE":
                return AnswerabilityResult(False, "answerability_insufficient_evidence")
            return AnswerabilityResult(True)

        except (OllamaClientError, OllamaTimeoutError, OllamaResponseError) as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.warning(
                "Answerability gate LLM failure — falling through (fail-open).",
                extra={"error": str(exc), "elapsed_ms": round(elapsed_ms, 1)},
            )
            return AnswerabilityResult(True)

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.warning(
                "Answerability gate unexpected error — falling through (fail-open).",
                extra={"error": str(exc), "elapsed_ms": round(elapsed_ms, 1)},
            )
            return AnswerabilityResult(True)

    def _build_evidence_block(self, hits: Sequence[SearchHit]) -> str:
        """Format the top-N chunks into a numbered evidence block."""

        blocks: list[str] = []
        for idx, hit in enumerate(hits[: self._max_evidence_chunks], start=1):
            text = " ".join(hit.text.split())
            blocks.append(f"[CHUNK {idx}] Source: {hit.source}\n{text}")
        return "\n\n".join(blocks)
