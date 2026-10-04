"""Topic/node scope resolution: KG node IDs to retrievable source IDs.

Covers the pure resolver (exact lookup, unknown IDs fail closed,
sourceless nodes contribute nothing, deterministic union) and its
integration through ``build_context``/``GenerationExecutor`` into the
existing P0 restricted retrieval path (no leakage, no widening,
oversampling and caps intact, provenance still source/chunk-only).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.application.flashcard_handler import FlashcardTaskHandler
from app.application.generation_errors import HandlerError, UnsupportedScopeError
from app.application.generation_executor import GenerationExecutor
from app.application.retrieval_adapter import (
    RESTRICTED_MIN_TOP_K,
    build_context,
    retrieve_for_request,
)
from app.application.scope_resolution import resolve_sources_for_nodes
from app.application.task_handler import register_handlers
from app.core.config import Settings
from app.domain.artifacts import ProvenanceRole
from app.domain.generation import GenerationRequest, GenerationTaskType
from app.domain.jobs import GenerationJobStatus
from app.domain.knowledge_graph import KnowledgeEdge, KnowledgeGraph, KnowledgeNode
from app.domain.scopes import MemoryScope, ResolvedScope
from app.infrastructure.artifacts import ArtifactStore, ProvenanceStore
from app.infrastructure.jobs import GenerationJobStore
from app.infrastructure.search import SearchHit


def _node(node_id: str, source: str, label: str | None = None) -> KnowledgeNode:
    return KnowledgeNode(
        id=node_id,
        label=label or node_id,
        node_type="concept",
        source=source,
    )


def _graph() -> KnowledgeGraph:
    graph = KnowledgeGraph()
    graph.add_node(_node("topic::rag", "a.md", label="RAG"))
    graph.add_node(_node("concept::chunking", "a.md", label="Chunking"))
    graph.add_node(_node("entity::acme", "b.md", label="Acme"))
    graph.add_node(_node("concept::orphan", "", label="Orphan"))
    graph.add_edge(
        KnowledgeEdge(source_id="topic::rag", target_id="concept::chunking", edge_type="related_to")
    )
    return graph


def _snapshot(graph: KnowledgeGraph) -> dict[str, object]:
    return {
        "nodes": sorted(
            (node.id, node.label, node.node_type, node.source)
            for node in graph.nodes.values()
        ),
        "edges": sorted(
            (edge.source_id, edge.target_id, edge.edge_type)
            for edge in graph.edges
        ),
    }


# ── Resolver unit tests ───────────────────────────────────────────────


def test_resolve_single_topic_to_source() -> None:
    assert resolve_sources_for_nodes(_graph(), ["topic::rag"]) == ("a.md",)


def test_resolve_single_node_to_source() -> None:
    assert resolve_sources_for_nodes(_graph(), ["entity::acme"]) == ("b.md",)


def test_resolve_unknown_topic_raises_naming_id() -> None:
    with pytest.raises(UnsupportedScopeError, match="topic::ghost"):
        resolve_sources_for_nodes(_graph(), ["topic::ghost"])


def test_resolve_unknown_node_raises_naming_id() -> None:
    with pytest.raises(UnsupportedScopeError, match="node::ghost"):
        resolve_sources_for_nodes(_graph(), ["node::ghost"])


def test_resolve_unknown_poison_names_every_unknown_id() -> None:
    with pytest.raises(UnsupportedScopeError) as excinfo:
        resolve_sources_for_nodes(_graph(), ["topic::rag", "nope::a", "nope::b"])

    message = str(excinfo.value)
    assert "nope::a" in message and "nope::b" in message


def test_resolve_sourceless_node_contributes_nothing() -> None:
    assert resolve_sources_for_nodes(_graph(), ["concept::orphan"]) == ()


def test_resolve_multiple_nodes_deterministic_sorted_union() -> None:
    first = resolve_sources_for_nodes(
        _graph(), ["entity::acme", "topic::rag", "concept::chunking"]
    )
    second = resolve_sources_for_nodes(
        _graph(), ["concept::chunking", "entity::acme", "topic::rag"]
    )

    assert first == second == ("a.md", "b.md")


def test_resolve_duplicate_sources_deduplicated() -> None:
    assert resolve_sources_for_nodes(
        _graph(), ["topic::rag", "concept::chunking"]
    ) == ("a.md",)


def test_resolve_duplicate_requested_ids_deterministic() -> None:
    assert resolve_sources_for_nodes(
        _graph(), ["entity::acme", "entity::acme"]
    ) == ("b.md",)


def test_resolve_does_not_mutate_graph() -> None:
    graph = _graph()
    before = _snapshot(graph)

    resolve_sources_for_nodes(graph, ["topic::rag", "entity::acme"])
    resolve_sources_for_nodes(graph, ["concept::orphan"])

    assert _snapshot(graph) == before


def test_resolve_empty_ids_resolves_empty() -> None:
    assert resolve_sources_for_nodes(_graph(), []) == ()


# ── Adapter/executor integration ──────────────────────────────────────


class RecordingSearchService:
    """Strict pre-filter stub that records every call."""

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


def _hit(source: str, index: int = 0) -> SearchHit:
    return SearchHit(
        text=f"body of {source}",
        source=source,
        score=0.9,
        entry_id=f"{source}::chunk_{index}",
        chunk_index=index,
    )


def _request(scope: MemoryScope) -> GenerationRequest:
    return GenerationRequest(
        task_type=GenerationTaskType.FLASHCARDS,
        memory_scope=scope,
        config={"query": "retrieval", "count": 1},
    )


def _cards() -> dict[str, object]:
    return {"cards": [{"front": "term?", "back": "definition"}]}


class ScriptedGenerate:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)

    def __call__(self, system_prompt: str, user_prompt: str, model: type) -> Any:
        if not self._responses:
            raise AssertionError("Fake LLM called more times than scripted.")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return model.model_validate(response)


def _executor(tmp_path: Path, responses: list[object] | None = None) -> GenerationExecutor:
    return GenerationExecutor(
        job_store=GenerationJobStore(tmp_path / "jobs.json"),
        artifact_store=ArtifactStore(tmp_path / "artifacts.json"),
        provenance_store=ProvenanceStore(tmp_path / "provenance.json"),
        handlers=register_handlers(
            FlashcardTaskHandler(ScriptedGenerate(list(responses) if responses else [_cards()])),
        ),
        search_service=RecordingSearchService([_hit("a.md"), _hit("evil.md")]),
        graph_loader=_graph,
    )


def test_topic_scope_retrieves_only_resolved_source() -> None:
    service = RecordingSearchService([_hit("a.md"), _hit("evil.md")])
    request = _request(MemoryScope.topics(["topic::rag"]))

    context = build_context(request, service, graph_loader=_graph)

    assert context.scope.restricted is True
    assert context.scope.source_ids == ("a.md",)
    assert {hit.source for hit in context.hits} == {"a.md"}
    assert service.calls and all(call[2] == {"source": "a.md"} for call in service.calls)


def test_node_scope_retrieves_only_resolved_source() -> None:
    service = RecordingSearchService([_hit("b.md"), _hit("evil.md")])
    request = _request(MemoryScope.nodes(["entity::acme"]))

    context = build_context(request, service, graph_loader=_graph)

    assert context.scope.source_ids == ("b.md",)
    assert {hit.source for hit in context.hits} == {"b.md"}


def test_unknown_topic_fails_closed_before_retrieval() -> None:
    service = RecordingSearchService([_hit("a.md")])
    request = _request(MemoryScope.topics(["topic::ghost"]))

    with pytest.raises(UnsupportedScopeError, match="topic::ghost"):
        build_context(request, service, graph_loader=_graph)

    assert service.calls == []


def test_unknown_node_fails_closed_before_retrieval() -> None:
    service = RecordingSearchService([_hit("a.md")])
    request = _request(MemoryScope.nodes(["node::ghost"]))

    with pytest.raises(UnsupportedScopeError, match="node::ghost"):
        build_context(request, service, graph_loader=_graph)

    assert service.calls == []


def test_sourceless_node_never_widens_to_all() -> None:
    """Mutation guard: weakening the P0 ``restricted`` branch would leak the corpus here."""

    service = RecordingSearchService([_hit("a.md"), _hit("evil.md")])
    request = _request(MemoryScope.topics(["concept::orphan"]))

    context = build_context(request, service, graph_loader=_graph)

    assert context.scope.restricted is True
    assert context.scope.source_ids == ()
    assert context.hits == ()
    assert service.calls == []


def test_restricted_empty_sources_never_calls_search() -> None:
    """Direct P0 non-vacuous pin: restricted + zero sources retrieves nothing."""

    service = RecordingSearchService([_hit("a.md")])
    scope = ResolvedScope(restricted=True, source_ids=())
    request = _request(MemoryScope.documents(["a.md"]))

    hits = retrieve_for_request(request, scope, service)

    assert hits == ()
    assert service.calls == []


def test_topic_scope_without_loader_fails_closed() -> None:
    service = RecordingSearchService([_hit("a.md")])

    with pytest.raises(UnsupportedScopeError):
        build_context(_request(MemoryScope.topics(["topic::rag"])), service)

    assert service.calls == []


def test_all_scope_unchanged_with_loader_present() -> None:
    service = RecordingSearchService([_hit("a.md"), _hit("evil.md")])

    context = build_context(_request(MemoryScope.all()), service, graph_loader=_graph)

    assert context.scope.restricted is False
    assert {hit.source for hit in context.hits} == {"a.md", "evil.md"}
    assert all(call[2] is None for call in service.calls)


def test_documents_scope_unchanged_with_loader_present() -> None:
    service = RecordingSearchService([_hit("a.md"), _hit("evil.md")])

    context = build_context(
        _request(MemoryScope.documents(["a.md"])), service, graph_loader=_graph
    )

    assert context.scope.source_ids == ("a.md",)
    assert {hit.source for hit in context.hits} == {"a.md"}


def test_projects_scope_still_fails_closed() -> None:
    service = RecordingSearchService([_hit("a.md")])

    with pytest.raises(UnsupportedScopeError):
        build_context(_request(MemoryScope.projects(["p1"])), service, graph_loader=_graph)

    assert service.calls == []


def test_p0_oversampling_still_applies_to_resolved_sources() -> None:
    service = RecordingSearchService([_hit("a.md")])

    build_context(_request(MemoryScope.topics(["topic::rag"])), service, graph_loader=_graph)

    assert service.calls and all(call[1] >= RESTRICTED_MIN_TOP_K for call in service.calls)


def test_max_hits_still_enforced_for_topic_scope() -> None:
    service = RecordingSearchService([_hit("a.md", index=i) for i in range(50)])

    context = build_context(
        _request(MemoryScope.topics(["topic::rag"])),
        service,
        graph_loader=_graph,
        max_hits=3,
    )

    assert len(context.hits) == 3


def test_unknown_topic_fails_job_without_artifact(tmp_path: Path) -> None:
    executor = _executor(tmp_path)

    with pytest.raises(UnsupportedScopeError):
        executor.run(_request(MemoryScope.topics(["topic::ghost"])))

    jobs = GenerationJobStore(tmp_path / "jobs.json").list_jobs()
    assert len(jobs) == 1
    assert jobs[0].status is GenerationJobStatus.FAILED
    assert ArtifactStore(tmp_path / "artifacts.json").list_artifacts() == []


def test_topic_executor_end_to_end_with_source_provenance(tmp_path: Path) -> None:
    executor = _executor(tmp_path)

    outcome = executor.run(_request(MemoryScope.topics(["topic::rag"])))

    assert outcome.job.status is GenerationJobStatus.DONE
    assert outcome.artifact_id is not None
    records = ProvenanceStore(tmp_path / "provenance.json").for_artifact(outcome.artifact_id)
    assert records
    assert {record.source_id for record in records} == {"a.md"}
    assert all(record.role is ProvenanceRole.EVIDENCE_CHUNK for record in records)
    assert all(record.kg_node_id is None for record in records)


def test_kg_file_unchanged_during_retrieval(tmp_path: Path) -> None:
    from app.domain.knowledge_graph import KnowledgeGraph as DomainGraph

    path = tmp_path / "knowledge_graph.json"
    _graph().save(path)
    before = path.read_bytes()

    def file_loader() -> DomainGraph:
        return DomainGraph.load(path)

    service = RecordingSearchService([_hit("a.md")])
    build_context(
        _request(MemoryScope.topics(["topic::rag"])), service, graph_loader=file_loader
    )

    assert path.read_bytes() == before


def test_route_loader_missing_file_is_empty_graph(tmp_settings: Settings) -> None:
    from app.interfaces.web.routes import generation as generation_routes

    graph = generation_routes._knowledge_graph_loader(tmp_settings)()

    assert graph.nodes == {}


def test_route_loader_corrupt_file_fails_safely(tmp_settings: Settings) -> None:
    from app.application.generation_errors import RetrievalError
    from app.interfaces.web.routes import generation as generation_routes

    tmp_settings.paths.manifest_root.mkdir(parents=True, exist_ok=True)
    (tmp_settings.paths.manifest_root / "knowledge_graph.json").write_text(
        "not json{{{", encoding="utf-8"
    )

    with pytest.raises(RetrievalError):
        generation_routes._knowledge_graph_loader(tmp_settings)()


def test_handler_error_still_wraps_downstream(tmp_path: Path) -> None:
    executor = GenerationExecutor(
        job_store=GenerationJobStore(tmp_path / "jobs.json"),
        artifact_store=ArtifactStore(tmp_path / "artifacts.json"),
        provenance_store=ProvenanceStore(tmp_path / "provenance.json"),
        handlers=register_handlers(
            FlashcardTaskHandler(ScriptedGenerate([HandlerError("boom")])),
        ),
        search_service=RecordingSearchService([_hit("a.md")]),
        graph_loader=_graph,
    )

    with pytest.raises(HandlerError):
        executor.run(_request(MemoryScope.topics(["topic::rag"])))

    jobs = GenerationJobStore(tmp_path / "jobs.json").list_jobs()
    assert len(jobs) == 1
    assert jobs[0].status is GenerationJobStatus.FAILED
