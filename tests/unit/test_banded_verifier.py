"""Tests for the banded answerability verifier (Phase 5F experiment)."""

from __future__ import annotations

from app.infrastructure.banded_verifier import BandedGate
from app.infrastructure.llm import (
    OllamaClientError,
    OllamaRequest,
    OllamaResponseError,
    OllamaTimeoutError,
)
from app.infrastructure.search import SearchHit


class FakeOllamaClient:
    """Records requests and returns a configured JSON response or error."""

    def __init__(self, json_response: object | None = None, error: Exception | None = None) -> None:
        self.json_response = json_response
        self.error = error
        self.requests: list[OllamaRequest] = []

    def generate_json(self, request: OllamaRequest, *, response_model=None):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if response_model is not None and self.json_response is not None:
            return response_model.model_validate(self.json_response)
        return self.json_response


def _hit(*, cosine_score: float = 0.5, text: str = "Fact content.") -> SearchHit:
    return SearchHit(
        text=text,
        source="doc.md",
        score=cosine_score,
        entry_id="doc.md::chunk_0",
        cosine_score=cosine_score,
        bm25_score=0.5,
        source_type="markdown",
        metadata={"heading": "Intro"},
    )


def _gate(client: FakeOllamaClient, **kwargs) -> BandedGate:
    return BandedGate(client, **kwargs)


class TestBandedGate:
    def test_band_low_boundary_invokes_verifier(self) -> None:
        client = FakeOllamaClient(json_response={"verdict": "SUPPORTED", "confidence": 0.9})
        gate = _gate(client, enabled=True)

        decision = gate.evaluate("Question?", [_hit(cosine_score=0.45)])

        assert decision.verifier_invoked is True
        assert len(client.requests) == 1

    def test_mid_band_invokes_verifier(self) -> None:
        client = FakeOllamaClient(json_response={"verdict": "SUPPORTED", "confidence": 0.9})
        gate = _gate(client, enabled=True)

        decision = gate.evaluate("Question?", [_hit(cosine_score=0.50)])

        assert decision.verifier_invoked is True
        assert len(client.requests) == 1

    def test_below_band_high_invokes_verifier(self) -> None:
        client = FakeOllamaClient(json_response={"verdict": "SUPPORTED", "confidence": 0.9})
        gate = _gate(client, enabled=True)

        decision = gate.evaluate("Question?", [_hit(cosine_score=0.61)])

        assert decision.verifier_invoked is True
        assert len(client.requests) == 1

    def test_below_band_low_abstains_without_verifier(self) -> None:
        client = FakeOllamaClient(json_response={"verdict": "SUPPORTED", "confidence": 0.9})
        gate = _gate(client, enabled=True)

        decision = gate.evaluate("Question?", [_hit(cosine_score=0.44)])

        assert decision.verifier_invoked is False
        assert decision.abstain is True
        assert decision.abstain_baseline is True
        assert not client.requests

    def test_at_band_high_not_invoked_accepts(self) -> None:
        client = FakeOllamaClient(json_response={"verdict": "SUPPORTED", "confidence": 0.9})
        gate = _gate(client, enabled=True)

        decision = gate.evaluate("Question?", [_hit(cosine_score=0.62)])

        assert decision.verifier_invoked is False
        assert decision.abstain is False
        assert not client.requests

    def test_above_band_high_not_invoked_accepts(self) -> None:
        client = FakeOllamaClient(json_response={"verdict": "SUPPORTED", "confidence": 0.9})
        gate = _gate(client, enabled=True)

        decision = gate.evaluate("Question?", [_hit(cosine_score=0.70)])

        assert decision.verifier_invoked is False
        assert decision.abstain is False
        assert not client.requests

    def test_supported_accepts(self) -> None:
        client = FakeOllamaClient(
            json_response={
                "verdict": "SUPPORTED",
                "confidence": 0.95,
                "supporting_chunk_indices": [2],
                "reason": "chunk 2 contains the fact",
            }
        )
        gate = _gate(client, enabled=True)

        decision = gate.evaluate("Question?", [_hit(cosine_score=0.50)])

        assert decision.verifier_invoked is True
        assert decision.abstain is False
        assert decision.vote == "SUPPORTED"
        assert decision.confidence == 0.95
        assert decision.supporting_chunk_indices == [2]
        assert decision.reason == "chunk 2 contains the fact"
        assert decision.fallback == "none"

    def test_insufficient_abstains(self) -> None:
        client = FakeOllamaClient(
            json_response={
                "verdict": "INSUFFICIENT_EVIDENCE",
                "confidence": 0.8,
                "supporting_chunk_indices": [],
                "reason": "only topic overlap",
            }
        )
        gate = _gate(client, enabled=True)

        decision = gate.evaluate("Question?", [_hit(cosine_score=0.50)])

        assert decision.verifier_invoked is True
        assert decision.abstain is True
        assert decision.vote == "INSUFFICIENT_EVIDENCE"

    def test_timeout_falls_open_to_baseline(self) -> None:
        client = FakeOllamaClient(error=OllamaTimeoutError("timed out"))
        gate = _gate(client, enabled=True)

        decision = gate.evaluate("Question?", [_hit(cosine_score=0.50)])

        assert decision.verifier_invoked is True
        assert decision.abstain is False
        assert decision.fallback == "timeout"

    def test_llm_error_falls_open_to_baseline(self) -> None:
        client = FakeOllamaClient(error=OllamaClientError("connection refused"))
        gate = _gate(client, enabled=True)

        decision = gate.evaluate("Question?", [_hit(cosine_score=0.50)])

        assert decision.verifier_invoked is True
        assert decision.abstain is False
        assert decision.fallback == "error"

    def test_malformed_response_falls_open_to_baseline(self) -> None:
        client = FakeOllamaClient(error=OllamaResponseError("invalid JSON"))
        gate = _gate(client, enabled=True)

        decision = gate.evaluate("Question?", [_hit(cosine_score=0.50)])

        assert decision.verifier_invoked is True
        assert decision.abstain is False
        assert decision.fallback == "malformed"

    def test_schema_violation_falls_open_to_baseline(self) -> None:
        client = FakeOllamaClient(json_response={"verdict": "MAYBE", "confidence": 5.0})
        gate = _gate(client, enabled=True)

        decision = gate.evaluate("Question?", [_hit(cosine_score=0.50)])

        assert decision.verifier_invoked is True
        assert decision.abstain is False
        assert decision.fallback == "malformed"

    def test_disabled_flag_reproduces_baseline(self) -> None:
        client = FakeOllamaClient(json_response={"verdict": "SUPPORTED", "confidence": 0.9})
        gate = _gate(client, enabled=False)

        below = gate.evaluate("Question?", [_hit(cosine_score=0.40)])
        assert below.abstain is True
        assert below.verifier_invoked is False

        in_band = gate.evaluate("Question?", [_hit(cosine_score=0.50)])
        assert in_band.abstain is False
        assert in_band.verifier_invoked is False

        above = gate.evaluate("Question?", [_hit(cosine_score=0.70)])
        assert above.abstain is False
        assert above.verifier_invoked is False

        assert not client.requests  # never calls the LLM when disabled
