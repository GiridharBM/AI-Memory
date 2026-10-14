"""Tests for the post-retrieval answerability/evidence gate (Phase 3G-B)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.application.qa_workflow import (
    ABSTENTION_MESSAGE,
    QAWorkflow,
)
from app.infrastructure.answerability import AnswerabilityGate, EvidenceVerdict
from app.infrastructure.llm import (
    OllamaClientError,
    OllamaRequest,
    OllamaResponseError,
    OllamaTextResponse,
)
from app.infrastructure.search import SearchHit

# ── Fakes ──────────────────────────────────────────────────────────────


class FakeSearchService:
    def __init__(self, hits: list[SearchHit] | None = None) -> None:
        self.hits = hits or []
        self.last: dict[str, object] = {}

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filter: dict[str, object] | None = None,
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        self.last = {"query": query, "top_k": top_k, "filter": filter, "min_score": min_score}
        return self.hits


class FakeOllamaClient:
    """Dual-purpose fake: supports both generate_text and generate_json."""

    def __init__(
        self,
        text_response: OllamaTextResponse | None = None,
        json_response: object | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.text_response = text_response
        self.json_response = json_response
        self.error = error
        self.requests: list[OllamaRequest] = []

    def generate_text(self, request: OllamaRequest) -> OllamaTextResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        assert self.text_response is not None
        return self.text_response

    def generate_json(
        self,
        request: OllamaRequest,
        *,
        response_model=None,
    ):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if response_model is not None and self.json_response is not None:
            return response_model.model_validate(self.json_response)
        return self.json_response


def _hit(
    text: str = "Python is a programming language.",
    *,
    source: str = "doc.md",
    score: float = 0.5,
    cosine_score: float = 0.5,
    bm25_score: float = 0.5,
) -> SearchHit:
    return SearchHit(
        text=text,
        source=source,
        score=score,
        entry_id="doc.md::chunk_0",
        cosine_score=cosine_score,
        bm25_score=bm25_score,
        source_type="markdown",
        metadata={"heading": "Intro"},
    )


def _response(text: str = "Python is a language.") -> OllamaTextResponse:
    return OllamaTextResponse(model="qwen3:8b", response=text, raw={})


def _gate(client: FakeOllamaClient, **kwargs) -> AnswerabilityGate:
    return AnswerabilityGate(client, **kwargs)


# ── EvidenceVerdict schema tests ───────────────────────────────────────


class TestEvidenceVerdict:
    def test_supported_verdict(self) -> None:
        v = EvidenceVerdict(verdict="SUPPORTED")
        assert v.verdict == "SUPPORTED"

    def test_insufficient_verdict(self) -> None:
        v = EvidenceVerdict(verdict="INSUFFICIENT_EVIDENCE")
        assert v.verdict == "INSUFFICIENT_EVIDENCE"

    def test_invalid_verdict_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceVerdict(verdict="INVALID")


# ── AnswerabilityGate unit tests ───────────────────────────────────────


class TestAnswerabilityGate:
    """Unit tests for the evidence verification gate."""

    def test_no_hits_returns_insufficient(self) -> None:
        client = FakeOllamaClient()
        gate = _gate(client)

        result = gate.verify("What is Python?", [])

        assert result.sufficient is False
        assert result.reason == "no_results"
        assert not client.requests  # LLM not called

    def test_supported_is_sufficient(self) -> None:
        client = FakeOllamaClient(json_response={"verdict": "SUPPORTED"})
        gate = _gate(client)
        hits = [_hit()]

        result = gate.verify("What is Python?", hits)

        assert result.sufficient is True
        assert result.reason is None
        assert len(client.requests) == 1

    def test_insufficient_is_not_sufficient(self) -> None:
        client = FakeOllamaClient(json_response={"verdict": "INSUFFICIENT_EVIDENCE"})
        gate = _gate(client)
        hits = [_hit()]

        result = gate.verify("What is quantum computing?", hits)

        assert result.sufficient is False
        assert result.reason == "answerability_insufficient_evidence"

    def test_llm_error_failopen(self) -> None:
        client = FakeOllamaClient(error=OllamaClientError("connection refused"))
        gate = _gate(client)
        hits = [_hit()]

        result = gate.verify("What is Python?", hits)

        assert result.sufficient is True  # fail-open

    def test_timeout_failopen(self) -> None:
        from app.infrastructure.llm import OllamaTimeoutError

        client = FakeOllamaClient(error=OllamaTimeoutError("timed out"))
        gate = _gate(client)
        hits = [_hit()]

        result = gate.verify("What is Python?", hits)

        assert result.sufficient is True  # fail-open

    def test_response_parse_error_failopen(self) -> None:
        client = FakeOllamaClient(error=OllamaResponseError("invalid JSON"))
        gate = _gate(client)
        hits = [_hit()]

        result = gate.verify("What is Python?", hits)

        assert result.sufficient is True  # fail-open

    def test_evidence_block_contains_chunk_texts(self) -> None:
        client = FakeOllamaClient(json_response={"verdict": "SUPPORTED"})
        gate = _gate(client, max_evidence_chunks=3)
        hits = [_hit(text="Chunk A text"), _hit(text="Chunk B text"), _hit(text="Chunk C text")]

        gate.verify("test query", hits)

        prompt = client.requests[0].prompt
        assert "Chunk A text" in prompt
        assert "Chunk B text" in prompt
        assert "Chunk C text" in prompt
        assert "[CHUNK 1]" in prompt
        assert "[CHUNK 2]" in prompt
        assert "[CHUNK 3]" in prompt

    def test_max_evidence_chunks_respected(self) -> None:
        client = FakeOllamaClient(json_response={"verdict": "SUPPORTED"})
        gate = _gate(client, max_evidence_chunks=2)
        hits = [_hit(text=f"Chunk {i}") for i in range(5)]

        gate.verify("test query", hits)

        prompt = client.requests[0].prompt
        assert "Chunk 0" in prompt
        assert "Chunk 1" in prompt
        assert "Chunk 2" not in prompt  # beyond max_evidence_chunks

    def test_temperature_zero(self) -> None:
        client = FakeOllamaClient(json_response={"verdict": "SUPPORTED"})
        gate = _gate(client)
        hits = [_hit()]

        gate.verify("test query", hits)

        assert client.requests[0].options.get("temperature") == 0.0


# ── Integration with QAWorkflow ────────────────────────────────────────


class TestAnswerabilityInWorkflow:
    """Verify the answerability gate slots into QAWorkflow correctly."""

    def test_gate_off_by_default_no_llm_judge_call(self) -> None:
        """When answerability_gate is None, no evidence verification happens."""
        hits = [_hit(cosine_score=0.6, bm25_score=2.0)]
        search = FakeSearchService(hits)
        client = FakeOllamaClient(text_response=_response("Python is a language."))
        workflow = QAWorkflow(search, client, min_cosine=0.25)

        result = workflow.ask("What is Python?")

        assert result.answer == "Python is a language."
        assert result.sources == hits

    def test_gate_supported_proceeds_to_qa(self) -> None:
        hits = [_hit(cosine_score=0.6, bm25_score=2.0)]
        search = FakeSearchService(hits)
        judge_client = FakeOllamaClient(json_response={"verdict": "SUPPORTED"})
        qa_client = FakeOllamaClient(text_response=_response("Python is a language."))
        gate = _gate(judge_client)
        workflow = QAWorkflow(search, qa_client, min_cosine=0.25, answerability_gate=gate)

        result = workflow.ask("What is Python?")

        assert result.answer == "Python is a language."
        assert result.sources == hits
        assert len(judge_client.requests) == 1  # judge was called
        assert len(qa_client.requests) == 1  # QA LLM was called

    def test_gate_insufficient_abstains(self) -> None:
        hits = [_hit(cosine_score=0.6, bm25_score=2.0)]
        search = FakeSearchService(hits)
        judge_client = FakeOllamaClient(json_response={"verdict": "INSUFFICIENT_EVIDENCE"})
        qa_client = FakeOllamaClient(text_response=_response("Should not be called."))
        gate = _gate(judge_client)
        workflow = QAWorkflow(search, qa_client, min_cosine=0.25, answerability_gate=gate)

        result = workflow.ask("What is quantum computing?")

        assert result.answer == ABSTENTION_MESSAGE
        assert result.sources == []
        assert len(judge_client.requests) == 1  # judge was called
        assert not qa_client.requests  # QA LLM was NOT called

    def test_gate_failopen_proceeds_to_qa(self) -> None:
        hits = [_hit(cosine_score=0.6, bm25_score=2.0)]
        search = FakeSearchService(hits)
        judge_client = FakeOllamaClient(error=OllamaClientError("connection refused"))
        qa_client = FakeOllamaClient(text_response=_response("Python is a language."))
        gate = _gate(judge_client)
        workflow = QAWorkflow(search, qa_client, min_cosine=0.25, answerability_gate=gate)

        result = workflow.ask("What is Python?")

        assert result.answer == "Python is a language."
        assert result.sources == hits

    def test_abstention_gate_blocks_before_answerability(self) -> None:
        """If abstention gate rejects, answerability gate is never called."""
        hits = [_hit(cosine_score=0.1, bm25_score=0.0)]
        search = FakeSearchService(hits)
        judge_client = FakeOllamaClient(json_response={"verdict": "SUPPORTED"})
        qa_client = FakeOllamaClient(text_response=_response("Should not be called."))
        gate = _gate(judge_client)
        workflow = QAWorkflow(search, qa_client, min_cosine=0.25, answerability_gate=gate)

        result = workflow.ask("What is Python?")

        assert result.answer == ABSTENTION_MESSAGE
        assert not judge_client.requests  # answerability gate was NOT called
        assert not qa_client.requests
