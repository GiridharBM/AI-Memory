"""Scope-restricted retrieval correctness: fail-closed and recall compensation.

Two confirmed defects are pinned here.

Fail-closed: a restricted scope that resolved to no source must retrieve
nothing. Branching on ``restricted and source_ids`` let an unresolved
topic/node scope fall through to the unrestricted branch and return the whole
corpus as evidence for a narrowly-scoped request.

Recall: the frozen ``SearchService`` fuses and truncates to ``top_k`` *before*
applying its source filter, so a restricted search at top_k=5 could return zero
hits for a source that plainly contained the query. The adapter compensates by
requesting a deeper candidate window and slicing back afterwards.

The recall tests drive the real frozen ``SearchService`` over an in-memory
``VectorStore`` on purpose: the strict pre-filter stub used elsewhere would pass
even without the compensation, which is how the defect survived.
"""

from __future__ import annotations

from app.application.retrieval_adapter import (
    DEFAULT_TOP_K,
    RESTRICTED_MAX_TOP_K,
    RESTRICTED_MIN_TOP_K,
    RESTRICTED_OVERSAMPLE_FACTOR,
    RetrievalPort,
    retrieve_for_request,
)
from app.domain.generation import GenerationRequest, GenerationTaskType
from app.domain.generation_context import RetrievedChunk
from app.domain.scopes import MemoryScope, ResolvedScope, resolve_memory_scope
from app.infrastructure.search import SearchHit, SearchService
from app.infrastructure.vector_store import VectorEntry, VectorStore

_TERM = "transformer"
_TARGET = "target.md"
_DISTRACTOR_SOURCES = 40
_DISTRACTOR_CHUNKS = 2


class RecordingSearchService:
    """Records every call so filter/top_k behavior is assertable."""

    def __init__(self, hits: list[SearchHit] | None = None) -> None:
        self.calls: list[tuple[str, int, dict[str, object] | None]] = []
        self._hits = hits if hits is not None else []

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filter: dict[str, object] | None = None,  # noqa: A002 - mirrors service signature
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        self.calls.append((query, top_k, filter))
        if filter is None:
            return list(self._hits)
        return [hit for hit in self._hits if hit.source == filter.get("source")]


def _hit(source: str, index: int = 0, score: float = 0.9) -> SearchHit:
    return SearchHit(
        text=f"body of {source}",
        source=source,
        score=score,
        entry_id=f"{source}::chunk_{index}",
        chunk_index=index,
    )


def _request(scope: MemoryScope) -> GenerationRequest:
    return GenerationRequest(
        task_type=GenerationTaskType.FLASHCARDS,
        memory_scope=scope,
        config={"query": _TERM},
    )


def _retrieve(
    scope: MemoryScope, service: RetrievalPort, **kwargs: object
) -> tuple[RetrievedChunk, ...]:
    return retrieve_for_request(
        _request(scope),
        resolve_memory_scope(scope),
        service,
        **kwargs,  # type: ignore[arg-type]
    )


def _adversarial_service() -> SearchService:
    """41 sources / 83 chunks where the target is outranked globally.

    Forty distractor sources repeat the query term densely; ``target.md``
    mentions it once per chunk and so falls outside a global top_k=5 window
    even though every one of its chunks is relevant.
    """

    store = VectorStore()
    for index in range(_DISTRACTOR_SOURCES):
        for chunk in range(_DISTRACTOR_CHUNKS):
            store.add(
                VectorEntry(
                    id=f"distract{index}.md::chunk_{chunk}",
                    source=f"distract{index}.md",
                    source_type="markdown",
                    chunk_index=chunk,
                    text=f"{_TERM} " * 25,
                    embedding=[0.0] * 4,
                )
            )
    for chunk in range(3):
        store.add(
            VectorEntry(
                id=f"{_TARGET}::chunk_{chunk}",
                source=_TARGET,
                source_type="markdown",
                chunk_index=chunk,
                text=f"a short note that mentions {_TERM} once",
                embedding=[0.0] * 4,
            )
        )
    # embed=lambda _: None keeps the lexical leg only: no network, no model.
    return SearchService(store, embed=lambda _query: None)


# --- Fail closed -------------------------------------------------------------


def test_restricted_scope_with_zero_sources_retrieves_nothing() -> None:
    service = RecordingSearchService([_hit("a.md"), _hit("b.md")])

    chunks = retrieve_for_request(
        _request(MemoryScope.topics(["topic::ml"])),
        ResolvedScope(restricted=True, node_ids=("topic::ml",)),
        service,
    )

    assert chunks == ()
    assert service.calls == []


def test_topics_scope_never_falls_back_to_whole_corpus() -> None:
    service = RecordingSearchService([_hit("a.md"), _hit("b.md"), _hit("c.md")])
    scope = MemoryScope.topics(["topic::ml"])

    chunks = _retrieve(scope, service)

    assert chunks == ()
    assert service.calls == []
    assert all(call[2] is not None for call in service.calls)


def test_nodes_scope_never_falls_back_to_whole_corpus() -> None:
    service = RecordingSearchService([_hit("a.md"), _hit("b.md"), _hit("c.md")])
    scope = MemoryScope.nodes(["concept::ml"])

    chunks = _retrieve(scope, service)

    assert chunks == ()
    assert service.calls == []
    assert all(call[2] is not None for call in service.calls)


def test_unresolvable_restricted_scope_returns_no_evidence_from_real_service() -> None:
    service = _adversarial_service()

    chunks = _retrieve(MemoryScope.nodes(["concept::does_not_exist"]), service)

    assert chunks == ()


# --- Unrestricted behavior is untouched -------------------------------------


def test_all_scope_keeps_unfiltered_production_call() -> None:
    service = RecordingSearchService([_hit("a.md"), _hit("b.md")])

    chunks = _retrieve(MemoryScope.all(), service)

    assert [chunk.source for chunk in chunks] == ["a.md", "b.md"]
    assert len(service.calls) == 1
    query, top_k, source_filter = service.calls[0]
    assert query == _TERM
    assert top_k == DEFAULT_TOP_K == 5
    assert source_filter is None


def test_all_scope_against_real_service_is_unchanged() -> None:
    service = _adversarial_service()

    chunks = _retrieve(MemoryScope.all(), service)

    assert len(chunks) == DEFAULT_TOP_K
    assert len({chunk.source for chunk in chunks}) > 1


# --- Restricted retrieval semantics ------------------------------------------


def test_documents_scope_passes_raw_source_filters() -> None:
    service = RecordingSearchService([_hit("a.md"), _hit("b.md"), _hit("c.md")])

    _retrieve(MemoryScope.documents(["b.md"]), service)

    assert [call[2] for call in service.calls] == [{"source": "b.md"}]


def test_multiple_sources_get_one_filtered_call_each() -> None:
    service = RecordingSearchService([_hit("a.md"), _hit("b.md")])

    _retrieve(MemoryScope.documents(["a.md", "b.md"]), service)

    assert [call[2] for call in service.calls] == [{"source": "a.md"}, {"source": "b.md"}]


def test_duplicate_sources_produce_no_duplicate_calls() -> None:
    service = RecordingSearchService([_hit("a.md")])
    scope = MemoryScope.documents(["a.md", "a.md", " a.md "])

    _retrieve(scope, service)

    assert [call[2] for call in service.calls] == [{"source": "a.md"}]
    assert len(service.calls) == 1


def test_source_filtering_is_exact() -> None:
    service = RecordingSearchService([_hit("a.md"), _hit("b.md"), _hit("c.md")])

    chunks = _retrieve(MemoryScope.documents(["b.md"]), service)

    assert [chunk.source for chunk in chunks] == ["b.md"]


def test_oversampling_is_bounded_and_deterministic() -> None:
    assert RESTRICTED_MIN_TOP_K <= RESTRICTED_MAX_TOP_K
    assert RESTRICTED_OVERSAMPLE_FACTOR >= 1
    service = RecordingSearchService([_hit("a.md")])

    _retrieve(MemoryScope.documents(["a.md"]), service)

    _, top_k, _ = service.calls[0]
    assert RESTRICTED_MIN_TOP_K <= top_k <= RESTRICTED_MAX_TOP_K


def test_max_hits_is_enforced_after_collection() -> None:
    service = RecordingSearchService([_hit("a.md", index) for index in range(10)])

    chunks = _retrieve(MemoryScope.documents(["a.md"]), service, max_hits=3)

    assert len(chunks) == 3


def test_results_have_no_duplicate_entry_ids_and_are_deterministic() -> None:
    service = RecordingSearchService([_hit("a.md", index) for index in range(6)])
    scope = MemoryScope.documents(["a.md"])

    first = _retrieve(scope, service)
    second = _retrieve(scope, service)

    entry_ids = [chunk.entry_id for chunk in first]
    assert len(entry_ids) == len(set(entry_ids))
    assert first == second


# --- Real SearchService recall regression ------------------------------------


def test_restricted_recall_recovers_target_despite_global_truncation() -> None:
    service = _adversarial_service()

    # The frozen service loses the target outright at the production depth.
    assert service.search(_TERM, top_k=DEFAULT_TOP_K, filter={"source": _TARGET}) == []

    chunks = _retrieve(MemoryScope.documents([_TARGET]), service)

    assert [chunk.source for chunk in chunks] == [_TARGET] * 3
    assert [chunk.entry_id for chunk in chunks] == [f"{_TARGET}::chunk_{n}" for n in range(3)]


def test_restricted_recall_keeps_every_selected_source_represented() -> None:
    service = _adversarial_service()
    selected = [_TARGET, "distract0.md", "distract7.md"]

    chunks = _retrieve(MemoryScope.documents(selected), service)

    assert {chunk.source for chunk in chunks} == set(selected)


def test_restricted_recall_respects_max_hits_with_many_selected_sources() -> None:
    service = _adversarial_service()
    selected = [_TARGET] + [f"distract{index}.md" for index in range(5)]

    chunks = _retrieve(MemoryScope.documents(selected), service, max_hits=4)

    assert len(chunks) == 4
    assert len({chunk.entry_id for chunk in chunks}) == 4
