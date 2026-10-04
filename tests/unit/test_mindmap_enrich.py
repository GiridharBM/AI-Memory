"""Tests for the V2-F enriched mind map domain model and task handler."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.application.generation_errors import HandlerError
from app.application.mindmap_handler import MindMapEnrichTaskHandler
from app.domain.artifacts import ArtifactKind, ProvenanceRole
from app.domain.generation import GenerationRequest, GenerationTaskType
from app.domain.generation_context import GenerationContext, RetrievedChunk
from app.domain.knowledge_graph import KnowledgeNode
from app.domain.mindmap import EnrichedMindMap
from app.domain.scopes import MemoryScope, resolve_memory_scope


def _node(node_id: str, label: str | None = None) -> dict[str, Any]:
    label = label or f"Label {node_id}"
    return {
        "id": node_id,
        "label": label,
        "node_type": "concept",
        "source": "a.md",
        "description": f"Description of {label}.",
        "key_points": [f"point {node_id}a", f"point {node_id}b"],
    }


def _payload(
    count: int = 2, *, edges: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    nodes = [_node(f"n{i}") for i in range(count)]
    if edges is None:
        edges = [
            {"source_id": "n0", "target_id": f"n{i}", "relationship": "related_to"}
            for i in range(1, count)
        ]
    return {
        "title": "Map",
        "root_node_id": "n0",
        "nodes": nodes,
        "edges": edges,
    }


def _hit(source: str = "a.md") -> RetrievedChunk:
    return RetrievedChunk(source=source, text="body", entry_id=f"{source}::0")


def _context(
    config: dict[str, Any],
    *,
    hits: tuple[RetrievedChunk, ...] | None = None,
    nodes: tuple[KnowledgeNode, ...] = (),
) -> GenerationContext:
    request = GenerationRequest(
        task_type="mindmap_enrich",  # type: ignore[arg-type]
        memory_scope=MemoryScope.documents(["a.md", "b.md"]),
        config=config,  # type: ignore[arg-type]
    )
    resolved_hits = (_hit("a.md"), _hit("b.md")) if hits is None else hits
    return GenerationContext(
        request=request,
        scope=resolve_memory_scope(request.memory_scope),
        hits=resolved_hits,
        nodes=nodes,
    )


class ScriptedGenerate:
    """Fake structured LLM: each call consumes the next scripted response."""

    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self, system_prompt: str, user_prompt: str, model: type[BaseModel]
    ) -> Any:
        self.calls.append((system_prompt, user_prompt))
        if not self._responses:
            raise AssertionError("Fake LLM called more times than scripted.")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return model.model_validate(response)


# ── Domain ────────────────────────────────────────────────────────────


def test_domain_valid_map() -> None:
    mindmap = EnrichedMindMap.model_validate(_payload(3))

    assert mindmap.title == "Map"
    assert mindmap.root_node_id == "n0"
    assert len(mindmap.nodes) == 3
    assert len(mindmap.edges) == 2


def test_domain_normalization() -> None:
    mindmap = EnrichedMindMap.model_validate(
        {
            "title": "  My   Map  ",
            "root_node_id": "  n0 ",
            "nodes": [
                {
                    "id": "  n0 ",
                    "label": "  Root   label ",
                    "node_type": "  concept ",
                    "source": "  a.md  ",
                    "description": "  desc  ",
                    "key_points": ["  p1  ", "   ", "p2"],
                }
            ],
            "edges": [],
        }
    )

    assert mindmap.title == "My Map"
    assert mindmap.root_node_id == "n0"
    assert mindmap.nodes[0].id == "n0"
    assert mindmap.nodes[0].label == "Root label"
    assert mindmap.nodes[0].key_points == ["p1", "p2"]


def test_domain_duplicate_node_ids_rejected() -> None:
    payload = _payload(2)
    nodes = list(payload["nodes"])
    nodes.append(dict(nodes[0]))
    payload["nodes"] = nodes

    with pytest.raises(ValidationError):
        EnrichedMindMap.model_validate(payload)


def test_domain_duplicate_edges_rejected() -> None:
    payload = _payload(2)
    payload["edges"] = [
        {"source_id": "n0", "target_id": "n1", "relationship": "related_to"},
        {"source_id": "n0", "target_id": "n1", "relationship": "related_to"},
    ]

    with pytest.raises(ValidationError):
        EnrichedMindMap.model_validate(payload)


def test_domain_self_edge_rejected() -> None:
    payload = _payload(1, edges=[])
    payload["edges"] = [
        {"source_id": "n0", "target_id": "n0", "relationship": "related_to"}
    ]

    with pytest.raises(ValidationError):
        EnrichedMindMap.model_validate(payload)


def test_domain_dangling_endpoint_rejected() -> None:
    payload = _payload(1, edges=[])
    payload["edges"] = [
        {"source_id": "n0", "target_id": "ghost", "relationship": "related_to"}
    ]

    with pytest.raises(ValidationError):
        EnrichedMindMap.model_validate(payload)


def test_domain_invalid_root_rejected() -> None:
    payload = _payload(2)
    payload["root_node_id"] = "ghost"

    with pytest.raises(ValidationError):
        EnrichedMindMap.model_validate(payload)


def test_domain_empty_map_rejected() -> None:
    with pytest.raises(ValidationError):
        EnrichedMindMap.model_validate(
            {"title": "Map", "root_node_id": "n0", "nodes": [], "edges": []}
        )


def test_domain_node_limit_enforced() -> None:
    payload = _payload(61, edges=[])

    with pytest.raises(ValidationError):
        EnrichedMindMap.model_validate(payload)


def test_domain_edge_limit_enforced() -> None:
    nodes = [_node("n0"), _node("n1")]
    edges = [
        {"source_id": "n0", "target_id": "n1", "relationship": f"rel-{i}"}
        for i in range(121)
    ]
    # Domain caps list length at 120; duplicates are also rejected by structure.
    with pytest.raises(ValidationError):
        EnrichedMindMap.model_validate(
            {"title": "Map", "root_node_id": "n0", "nodes": nodes, "edges": edges}
        )


def test_domain_json_serialization() -> None:
    mindmap = EnrichedMindMap.model_validate(_payload(2))

    raw = mindmap.model_dump_json()
    reloaded = EnrichedMindMap.model_validate_json(raw)

    assert reloaded == mindmap
    assert json.loads(raw)["title"] == "Map"


def test_domain_extra_forbidden() -> None:
    payload = _payload(1, edges=[])
    node = dict(payload["nodes"][0])
    node["unknown"] = "x"
    payload["nodes"] = [node]

    with pytest.raises(ValidationError):
        EnrichedMindMap.model_validate(payload)


# ── Handler ───────────────────────────────────────────────────────────


def test_handler_task_type_and_kind() -> None:
    handler = MindMapEnrichTaskHandler(ScriptedGenerate([_payload(2)]))

    assert handler.task_type is GenerationTaskType.MINDMAP_ENRICH
    result = handler.handle(_context({"node_limit": 2}))

    assert result.kind is ArtifactKind.MINDMAP
    assert result.title == "Map"
    assert result.metadata == {"nodes": "2", "edges": "1"}
    assert result.content is not None
    parsed = EnrichedMindMap.model_validate_json(result.content)
    assert len(parsed.nodes) == 2


def test_handler_successful_structured_generation() -> None:
    handler = MindMapEnrichTaskHandler(ScriptedGenerate([_payload(3)]))

    result = handler.handle(_context({"node_limit": 5}))

    assert result.metadata == {"nodes": "3", "edges": "2"}
    assert result.content is not None


def test_handler_malformed_retries_then_succeeds() -> None:
    malformed = {"title": "Map", "root_node_id": "n0", "nodes": [], "edges": []}
    handler = MindMapEnrichTaskHandler(ScriptedGenerate([malformed, _payload(2)]))

    result = handler.handle(_context({"node_limit": 2}))

    assert result.metadata == {"nodes": "2", "edges": "1"}


def test_handler_second_failure_raises() -> None:
    malformed = {"title": "Map", "root_node_id": "n0", "nodes": [], "edges": []}
    handler = MindMapEnrichTaskHandler(ScriptedGenerate([malformed, malformed]))

    with pytest.raises(HandlerError):
        handler.handle(_context({"node_limit": 2}))


def test_handler_transport_failure_fails_immediately() -> None:
    fake = ScriptedGenerate([RuntimeError("down")])
    handler = MindMapEnrichTaskHandler(fake)

    with pytest.raises(HandlerError):
        handler.handle(_context({"node_limit": 2}))

    assert len(fake.calls) == 1


def test_handler_empty_retrieval_still_generates() -> None:
    handler = MindMapEnrichTaskHandler(ScriptedGenerate([_payload(1, edges=[])]))

    result = handler.handle(_context({"node_limit": 2}, hits=()))

    assert result.metadata == {"nodes": "1", "edges": "0"}
    assert result.provenance == ()


def test_handler_config_validation() -> None:
    handler = MindMapEnrichTaskHandler(ScriptedGenerate([_payload(1, edges=[])]))

    with pytest.raises(HandlerError):
        handler.handle(_context({"node_limit": 0}))
    with pytest.raises(HandlerError):
        handler.handle(_context({"node_limit": 61}))
    with pytest.raises(HandlerError):
        handler.handle(_context({"detail": "huge"}))
    with pytest.raises(HandlerError):
        handler.handle(_context({"title": "  "}))


def test_handler_node_limit_enforced_with_retry() -> None:
    handler = MindMapEnrichTaskHandler(
        ScriptedGenerate([_payload(3), _payload(2)])
    )

    result = handler.handle(_context({"node_limit": 2}))

    assert result.metadata["nodes"] == "2"


def test_handler_node_limit_exceeded_twice_fails() -> None:
    handler = MindMapEnrichTaskHandler(
        ScriptedGenerate([_payload(3), _payload(3)])
    )

    with pytest.raises(HandlerError):
        handler.handle(_context({"node_limit": 2}))


def test_handler_provenance_mapping() -> None:
    handler = MindMapEnrichTaskHandler(ScriptedGenerate([_payload(2)]))

    result = handler.handle(_context({"node_limit": 2}))

    # Every node references every retrieved hit (set-level evidence/lineage).
    assert len(result.provenance) == 2 * 2
    assert {record.source_id for record in result.provenance} == {"a.md", "b.md"}
    assert all(
        record.role is ProvenanceRole.EVIDENCE_CHUNK for record in result.provenance
    )
    assert all(record.kg_node_id is None for record in result.provenance)


def test_handler_provenance_kg_linkage() -> None:
    kg_nodes = (
        KnowledgeNode(id="n0", label="Label n0", node_type="concept", source="a.md"),
    )
    handler = MindMapEnrichTaskHandler(ScriptedGenerate([_payload(2)]))

    result = handler.handle(_context({"node_limit": 2}, nodes=kg_nodes))

    linked = [record for record in result.provenance if record.kg_node_id == "n0"]
    # One record per hit for the matching node.
    assert len(linked) == 2
    assert all(record.chunk_id is not None for record in linked)


def test_handler_deterministic_output() -> None:
    first = MindMapEnrichTaskHandler(ScriptedGenerate([_payload(2)])).handle(
        _context({"node_limit": 2})
    )
    second = MindMapEnrichTaskHandler(ScriptedGenerate([_payload(2)])).handle(
        _context({"node_limit": 2})
    )

    assert first == second


def test_handler_single_generation_call_on_success() -> None:
    fake = ScriptedGenerate([_payload(1, edges=[])])
    handler = MindMapEnrichTaskHandler(fake)

    handler.handle(_context({"node_limit": 5}))

    assert len(fake.calls) == 1
