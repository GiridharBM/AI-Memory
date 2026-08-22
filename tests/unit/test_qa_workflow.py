"""Tests for the RAG question-answering workflow."""

from __future__ import annotations

import pytest

from app.application.qa_workflow import (
    ABSTENTION_MESSAGE,
    MAX_CONTEXT_CHARS,
    MAX_CONTEXT_CHUNKS,
    QAAnswer,
    QAError,
    QAWorkflow,
    AbstentionGate,
    AbstentionResult,
    build_context,
)
from app.infrastructure.llm import OllamaClientError, OllamaRequest, OllamaTextResponse
from app.infrastructure.search import SearchHit


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
    def __init__(
        self,
        response: OllamaTextResponse | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.requests: list[OllamaRequest] = []

    def generate_text(self, request: OllamaRequest) -> OllamaTextResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


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


def _workflow(search: FakeSearchService, client: FakeOllamaClient) -> QAWorkflow:
    return QAWorkflow(search, client)


def test_ask_returns_answer_and_sources() -> None:
    hits = [_hit()]
    search = FakeSearchService(hits)
    client = FakeOllamaClient(_response("Python is a language."))
    workflow = _workflow(search, client)

    result = workflow.ask("What is Python?")

    assert isinstance(result, QAAnswer)
    assert result.answer == "Python is a language."
    assert result.sources == hits
    assert result.model == "qwen3:8b"


def test_ask_places_question_in_prompt() -> None:
    search = FakeSearchService([_hit()])
    client = FakeOllamaClient(_response())
    workflow = _workflow(search, client)

    workflow.ask("What is Python?")

    prompt = client.requests[0].prompt
    assert "What is Python?" in prompt
    assert client.requests[0].system_prompt is not None


def test_ask_places_retrieved_context_in_prompt() -> None:
    search = FakeSearchService([_hit(text="Guido wrote CPython in 1991.")])
    client = FakeOllamaClient(_response())
    workflow = _workflow(search, client)

    workflow.ask("Who wrote Python?")

    prompt = client.requests[0].prompt
    assert "Guido wrote CPython in 1991." in prompt
    assert "doc.md" in prompt
    assert "[SOURCE 1]" in prompt


def test_ask_forwards_top_k() -> None:
    search = FakeSearchService([_hit()])
    client = FakeOllamaClient(_response())
    workflow = _workflow(search, client)

    workflow.ask("What is Python?", top_k=3)

    assert search.last["top_k"] == 3


def test_ask_forwards_min_score() -> None:
    search = FakeSearchService([_hit()])
    client = FakeOllamaClient(_response())
    workflow = _workflow(search, client)

    workflow.ask("What is Python?", min_score=0.1)

    assert search.last["min_score"] == 0.1


def test_ask_forwards_filter() -> None:
    search = FakeSearchService([_hit()])
    client = FakeOllamaClient(_response())
    workflow = _workflow(search, client)

    workflow.ask("What is Python?", filter={"heading": "Intro"})

    assert search.last["filter"] == {"heading": "Intro"}


@pytest.mark.parametrize("question", ["", "   ", None])
def test_ask_rejects_invalid_question(question: str | None) -> None:
    search = FakeSearchService([_hit()])
    client = FakeOllamaClient(_response())
    workflow = _workflow(search, client)

    with pytest.raises(QAError, match="must not be empty"):
        workflow.ask(question)  # type: ignore[arg-type]


def test_ask_handles_empty_retrieval_safely() -> None:
    search = FakeSearchService([])
    client = FakeOllamaClient(_response("No relevant context was retrieved."))
    workflow = _workflow(search, client)

    result = workflow.ask("What is Python?")

    assert result.answer == ABSTENTION_MESSAGE
    assert result.sources == []
    assert not client.requests  # LLM not invoked when gate abstains on empty hits


def test_ask_wraps_ollama_failure() -> None:
    search = FakeSearchService([_hit()])
    client = FakeOllamaClient(error=OllamaClientError("connection refused"))
    workflow = _workflow(search, client)

    with pytest.raises(QAError, match="Ollama server is unavailable"):
        workflow.ask("What is Python?")


def test_build_context_is_bounded() -> None:
    huge_text = "x" * 5_000
    hits = [_hit(text=huge_text, source=f"doc{i}.md") for i in range(100)]

    context = build_context(hits)

    assert len(context) < 100 * len(huge_text)
    assert context.count("[SOURCE") <= MAX_CONTEXT_CHUNKS
    assert len(context) <= MAX_CONTEXT_CHARS + 1_000


def test_build_context_preserves_ranking() -> None:
    hits = [_hit(source="first.md"), _hit(source="second.md")]

    context = build_context(hits)

    assert context.index("first.md") < context.index("second.md")


# ── Abstention gate tests ──────────────────────────────────────────────


class TestAbstentionGate:
    """Unit tests for the retrieval-confidence abstention gate."""

    def test_strong_relevant_retrieval_accepted(self) -> None:
        gate = AbstentionGate(min_cosine=0.25)
        hits = [_hit(cosine_score=0.6, bm25_score=2.0)]

        result = gate.evaluate(hits)

        assert result.abstain is False
        assert result.reason is None

    def test_weak_retrieval_rejected(self) -> None:
        gate = AbstentionGate(min_cosine=0.25)
        hits = [_hit(cosine_score=0.1, bm25_score=0.0)]

        result = gate.evaluate(hits)

        assert result.abstain is True
        assert "cosine_below_threshold" in result.reason

    def test_negative_query_no_results_rejected(self) -> None:
        gate = AbstentionGate(min_cosine=0.25)

        result = gate.evaluate([])

        assert result.abstain is True
        assert result.reason == "no_results"

    def test_borderline_score_deterministic(self) -> None:
        gate = AbstentionGate(min_cosine=0.25)
        hits_exact = [_hit(cosine_score=0.25, bm25_score=0.0)]
        hits_below = [_hit(cosine_score=0.2499, bm25_score=0.0)]

        assert gate.evaluate(hits_exact).abstain is False
        assert gate.evaluate(hits_below).abstain is True

    def test_accepted_query_context_built_normally(self) -> None:
        hits = [_hit(cosine_score=0.6, bm25_score=2.0, text="Guido wrote CPython.")]
        search = FakeSearchService(hits)
        client = FakeOllamaClient(_response("Python is a language."))
        workflow = QAWorkflow(search, client, min_cosine=0.25)

        result = workflow.ask("What is Python?")

        assert result.answer == "Python is a language."
        assert result.sources == hits
        assert client.requests  # LLM was invoked

    def test_rejected_query_llm_not_invoked(self) -> None:
        hits = [_hit(cosine_score=0.1, bm25_score=0.0)]
        search = FakeSearchService(hits)
        client = FakeOllamaClient(_response("This should not be called."))
        workflow = QAWorkflow(search, client, min_cosine=0.25)

        result = workflow.ask("What is quantum computing?")

        assert result.answer == ABSTENTION_MESSAGE
        assert result.sources == []
        assert result.model == ""
        assert not client.requests  # LLM was NOT invoked

    def test_existing_behavior_unchanged_when_gate_accepts(self) -> None:
        hits = [_hit(cosine_score=0.6, bm25_score=2.0)]
        search = FakeSearchService(hits)
        client = FakeOllamaClient(_response("Python is a language."))
        workflow = QAWorkflow(search, client, min_cosine=0.25)

        result = workflow.ask("What is Python?", top_k=3, filter={"heading": "Intro"})

        assert search.last["top_k"] == 3
        assert search.last["filter"] == {"heading": "Intro"}
        assert result.answer == "Python is a language."
        assert "[SOURCE 1]" in client.requests[0].prompt

    def test_bm25_below_cosine_threshold_rejected(self) -> None:
        gate = AbstentionGate(min_cosine=0.25)
        hits = [_hit(cosine_score=0.0, bm25_score=3.0)]

        result = gate.evaluate(hits)

        assert result.abstain is True
        assert "cosine_below_threshold" in result.reason

    def test_no_evidence_both_scores_zero_rejected(self) -> None:
        gate = AbstentionGate(min_cosine=0.25)
        hits = [_hit(cosine_score=0.0, bm25_score=0.0)]

        result = gate.evaluate(hits)

        assert result.abstain is True
        assert result.reason == "no_evidence"

    def test_bm25_only_with_zero_cosine_above_threshold_accepted(self) -> None:
        gate = AbstentionGate(min_cosine=0.0)
        hits = [_hit(cosine_score=0.0, bm25_score=3.0)]

        result = gate.evaluate(hits)

        assert result.abstain is False

    # ── BM25 override regression tests (Phase 3E) ───────────────────

    def test_bm25_override_rejected_cosine_below_threshold(self) -> None:
        gate = AbstentionGate(min_cosine=0.45)
        hits = [_hit(cosine_score=0.30, bm25_score=5.0)]

        result = gate.evaluate(hits)

        assert result.abstain is True
        assert "cosine_below_threshold" in result.reason

    def test_bm25_override_rejected_even_with_strong_bm25(self) -> None:
        gate = AbstentionGate(min_cosine=0.45)
        hits = [_hit(cosine_score=0.40, bm25_score=10.0)]

        result = gate.evaluate(hits)

        assert result.abstain is True

    def test_cosine_above_threshold_accepted_with_zero_bm25(self) -> None:
        gate = AbstentionGate(min_cosine=0.45)
        hits = [_hit(cosine_score=0.60, bm25_score=0.0)]

        result = gate.evaluate(hits)

        assert result.abstain is False

    def test_cosine_above_threshold_accepted_with_bm25(self) -> None:
        gate = AbstentionGate(min_cosine=0.45)
        hits = [_hit(cosine_score=0.60, bm25_score=3.0)]

        result = gate.evaluate(hits)

        assert result.abstain is False

    def test_no_results_always_abstains(self) -> None:
        gate = AbstentionGate(min_cosine=0.45)
        result = gate.evaluate([])
        assert result.abstain is True
        assert result.reason == "no_results"

    def test_both_zero_scores_abstains(self) -> None:
        gate = AbstentionGate(min_cosine=0.45)
        hits = [_hit(cosine_score=0.0, bm25_score=0.0)]
        result = gate.evaluate(hits)
        assert result.abstain is True
        assert result.reason == "no_evidence"
