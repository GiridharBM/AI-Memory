"""Tests for the V2 retrieval adapter (stubbed search service)."""

from __future__ import annotations

import pytest

from app.application.generation_errors import RetrievalError, UnsupportedScopeError
from app.application.retrieval_adapter import build_context, retrieve_for_request
from app.domain.generation import GenerationRequest
from app.domain.scopes import MemoryScope, resolve_memory_scope
from app.infrastructure.search import SearchHit


def _hit(source: str, text: str = "body", score: float = 0.9) -> SearchHit:
    return SearchHit(
        text=text,
        source=source,
        score=score,
        entry_id=f"{source}::0",
        cosine_score=score,
        chunk_index=0,
    )


class StubSearchService:
    """Deterministic stand-in for the frozen SearchService."""

    def __init__(self, hits: list[SearchHit] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, object] | None]] = []
        self._hits = hits if hits is not None else [_hit("a.md"), _hit("b.md")]

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filter: dict[str, object] | None = None,  # noqa: A002 - mirrors service signature
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        self.calls.append((query, filter))
        if filter is None:
            return list(self._hits)
        return [hit for hit in self._hits if hit.source == filter.get("source")]


def _request(**overrides: object) -> GenerationRequest:
    values: dict[str, object] = {"task_type": "flashcards", "memory_scope": MemoryScope.all()}
    values.update(overrides)
    return GenerationRequest(**values)  # type: ignore[arg-type]


def test_all_scope_searches_unfiltered() -> None:
    service = StubSearchService()

    chunks = retrieve_for_request(
        _request(), resolve_memory_scope(MemoryScope.all()), service
    )

    assert [hit.source for hit in chunks] == ["a.md", "b.md"]
    assert service.calls[0][1] is None


def test_documents_scope_filters_exact_sources() -> None:
    service = StubSearchService()
    request = _request(memory_scope=MemoryScope.documents(["b.md"]))

    chunks = retrieve_for_request(
        request,
        resolve_memory_scope(request.memory_scope),
        service,
    )

    assert [hit.source for hit in chunks] == ["b.md"]
    assert all(call[1] == {"source": "b.md"} for call in service.calls)


def test_project_scope_fails_closed() -> None:
    service = StubSearchService()

    with pytest.raises(UnsupportedScopeError):
        build_context(_request(memory_scope=MemoryScope.projects(["p1"])), service)


def test_deterministic_ordering_and_deduplication() -> None:
    service = StubSearchService(hits=[_hit("a.md"), _hit("a.md"), _hit("b.md")])

    first = retrieve_for_request(
        _request(), resolve_memory_scope(MemoryScope.all()), service
    )
    second = retrieve_for_request(
        _request(), resolve_memory_scope(MemoryScope.all()), service
    )

    assert [hit.source for hit in first] == ["a.md", "b.md"]
    assert first == second


def test_context_cap_truncates() -> None:
    service = StubSearchService(hits=[_hit(f"{index}.md") for index in range(10)])

    chunks = retrieve_for_request(
        _request(), resolve_memory_scope(MemoryScope.all()), service, max_hits=3
    )

    assert len(chunks) == 3


def test_search_hit_fields_preserved() -> None:
    service = StubSearchService(
        hits=[
            SearchHit(
                text="body",
                source="a.md",
                score=0.7,
                entry_id="a.md::2",
                cosine_score=0.65,
                chunk_index=2,
                start_char=10,
                end_char=42,
            )
        ]
    )

    (chunk,) = retrieve_for_request(
        _request(), resolve_memory_scope(MemoryScope.all()), service
    )

    assert chunk.source == "a.md"
    assert chunk.text == "body"
    assert chunk.entry_id == "a.md::2"
    assert chunk.cosine_score == 0.65
    assert chunk.chunk_index == 2
    assert (chunk.start_char, chunk.end_char) == (10, 42)


def test_retrieval_failure_is_typed() -> None:
    class BrokenService:
        def search(self, query: str, **kwargs: object) -> list[SearchHit]:
            raise RuntimeError("backend down")

    with pytest.raises(RetrievalError):
        build_context(_request(), BrokenService())  # type: ignore[arg-type]
