"""Tests for the RAG question-answering workflow."""

from __future__ import annotations

import pytest

from app.application.qa_workflow import (
    MAX_CONTEXT_CHARS,
    MAX_CONTEXT_CHUNKS,
    QAAnswer,
    QAError,
    QAWorkflow,
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


def _hit(text: str = "Python is a programming language.", *, source: str = "doc.md") -> SearchHit:
    return SearchHit(
        text=text,
        source=source,
        score=0.5,
        entry_id="doc.md::chunk_0",
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

    assert result.answer == "No relevant context was retrieved."
    assert result.sources == []
    assert "No relevant context" in client.requests[0].prompt


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
