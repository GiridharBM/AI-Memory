"""Unit tests for the deterministic document graph query layer (P4-105).

Covers every mandated category: all public query operations, empty graphs,
unknown entities, multiple relationships, cycles, depth/limit boundaries,
and serialization round-trips for the ``extra["knowledge_graph"]`` artifact.
"""

from __future__ import annotations

import json

from app.domain.entity_relationship import Entity, Relationship, SourceReference
from app.domain.knowledge_graph import (
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
)
from app.infrastructure.document_intelligence.graph import (
    DocumentGraphBuilder,
    get_entity,
    graph_from_dict,
    graph_to_dict,
    nodes_by_source,
    query_graph,
    related_entities,
)


def _entity(entity_id: str) -> Entity:
    return Entity(
        id=entity_id,
        label=entity_id.rsplit("::", 1)[-1].replace("_", " "),
        entity_type=entity_id.split("::", 1)[0],
        sources=[SourceReference(source="a.md", start_char=0, end_char=8, snippet="X")],
    )


def _relationship(source_id: str, target_id: str, edge_type: str = "related_to") -> Relationship:
    return Relationship(
        id=Relationship.make_id(source_id, target_id, edge_type),
        source_id=source_id,
        target_id=target_id,
        relationship_type=edge_type,
    )


def _build(entities: list[Entity], relationships: list[Relationship]) -> KnowledgeGraph:
    return DocumentGraphBuilder().build(entities, relationships, "a.md")


def _graph_with_node_types() -> KnowledgeGraph:
    graph = KnowledgeGraph()
    note = KnowledgeNode(id="note::attention", label="Attention", node_type="note", source="a.md")
    concept = KnowledgeNode(id="concept::transformer", label="Transformer", node_type="concept")
    entity = KnowledgeNode(id="person::jane_smith", label="Jane Smith", node_type="entity")
    for node in (note, concept, entity):
        graph.add_node(node)
    graph.add_edge(KnowledgeEdge(source_id="note::attention", target_id="concept::transformer",
                                 edge_type="mentioned_in"))
    return graph


# ── 1. entity lookup ───────────────────────────────────────────────────────


def test_get_entity_returns_node() -> None:
    graph = _build([_entity("person::jane_smith")], [])
    node = get_entity(graph, "person::jane_smith")
    assert node is not None
    assert node.label == "jane smith"
    assert node.node_type == "entity"


def test_get_entity_unknown_id_returns_none() -> None:
    graph = _build([_entity("person::jane_smith")], [])
    assert get_entity(graph, "person::ghost") is None


def test_get_entity_empty_graph_returns_none() -> None:
    assert get_entity(KnowledgeGraph(), "person::jane_smith") is None


# ── 2. relationship lookup (reuses find_relationships; asserted via exports) ─


def test_relationship_lookup_via_find_relationships() -> None:
    from app.infrastructure.document_intelligence.graph import find_relationships

    a = _entity("organization::acme_corporation")
    b = _entity("person::jane_smith")
    graph = _build([a, b], [_relationship(a.id, b.id)])
    edges = find_relationships(graph, source_id=a.id)
    assert [e.target_id for e in edges] == [b.id]


# ── 3. related-entity traversal ────────────────────────────────────────────


def test_related_entities_direct_neighbors() -> None:
    a = _entity("organization::acme_corporation")
    b = _entity("person::jane_smith")
    c = _entity("technology::python_3.12")
    graph = _build([a, b, c], [_relationship(a.id, b.id), _relationship(a.id, c.id)])
    assert [n.id for n in related_entities(graph, a.id)] == [b.id, c.id]


def test_related_entities_returns_empty_for_unknown_id() -> None:
    graph = _build([_entity("person::jane_smith")], [])
    assert related_entities(graph, "person::ghost") == []


def test_related_entities_empty_graph() -> None:
    assert related_entities(KnowledgeGraph(), "person::jane_smith") == []


def test_related_entities_multiple_relationships_all_visited() -> None:
    a = _entity("organization::acme_corporation")
    b = _entity("person::jane_smith")
    c = _entity("technology::python_3.12")
    d = _entity("place::zurich")
    graph = _build(
        [a, b, c, d],
        [_relationship(a.id, b.id), _relationship(b.id, c.id), _relationship(c.id, d.id)],
    )
    assert {n.id for n in related_entities(graph, a.id, max_depth=3)} == {b.id, c.id, d.id}


def test_related_entities_edge_type_filter() -> None:
    a = _entity("organization::acme_corporation")
    b = _entity("person::jane_smith")
    graph = _build(
        [a, b],
        [_relationship(a.id, b.id, "related_to"), _relationship(a.id, b.id, "depends_on")],
    )
    assert [n.id for n in related_entities(graph, a.id, edge_type="depends_on")] == [b.id]


def test_related_entities_depth_boundary() -> None:
    a = _entity("organization::acme_corporation")
    b = _entity("person::jane_smith")
    c = _entity("technology::python_3.12")
    graph = _build([a, b, c], [_relationship(a.id, b.id), _relationship(b.id, c.id)])
    assert related_entities(graph, a.id, max_depth=0) == []
    assert [n.id for n in related_entities(graph, a.id, max_depth=1)] == [b.id]
    assert [n.id for n in related_entities(graph, a.id, max_depth=2)] == [b.id, c.id]


def test_related_entities_cycle_is_safe() -> None:
    a = _entity("organization::acme_corporation")
    b = _entity("person::jane_smith")
    c = _entity("technology::python_3.12")
    graph = _build(
        [a, b, c],
        [_relationship(a.id, b.id), _relationship(b.id, c.id), _relationship(c.id, a.id)],
    )
    # deep traversal over a 3-cycle terminates and visits every node once
    assert [n.id for n in related_entities(graph, a.id, max_depth=10)] == [b.id, c.id]


def test_related_entities_limit_cap() -> None:
    a = _entity("organization::acme_corporation")
    b = _entity("person::jane_smith")
    c = _entity("technology::python_3.12")
    graph = _build([a, b, c], [_relationship(a.id, b.id), _relationship(a.id, c.id)])
    assert [n.id for n in related_entities(graph, a.id, limit=1)] == [b.id]
    assert related_entities(graph, a.id, limit=0) == []


def test_related_entities_deterministic() -> None:
    a = _entity("organization::acme_corporation")
    b = _entity("person::jane_smith")
    c = _entity("technology::python_3.12")
    first = _build([a, b, c], [_relationship(a.id, b.id), _relationship(a.id, c.id)])
    second = _build([c, b, a], [_relationship(a.id, c.id), _relationship(a.id, b.id)])
    assert [n.id for n in related_entities(first, a.id)] == [
        n.id for n in related_entities(second, a.id)
    ]


# ── 4. source/document lookup ──────────────────────────────────────────────


def test_nodes_by_source_returns_matching_nodes() -> None:
    graph = _build([_entity("organization::acme_corporation"), _entity("person::jane_smith")], [])
    assert [n.id for n in nodes_by_source(graph, "a.md")] == [
        "organization::acme_corporation",
        "person::jane_smith",
    ]


def test_nodes_by_source_unknown_source_empty() -> None:
    graph = _build([_entity("person::jane_smith")], [])
    assert nodes_by_source(graph, "missing.md") == []


def test_nodes_by_source_empty_graph() -> None:
    assert nodes_by_source(KnowledgeGraph(), "a.md") == []


# ── 5. basic graph traversal (roadmap §5.2 shape) ──────────────────────────


def test_query_graph_start_node_edge_type_target_type() -> None:
    graph = _graph_with_node_types()
    result = query_graph(
        graph,
        start_node="concept::transformer",
        edge_type="mentioned_in",
        target_type="note",
    )
    assert [n.id for n in result] == ["note::attention"]


def test_query_graph_no_match_returns_empty_not_error() -> None:
    graph = _graph_with_node_types()
    assert query_graph(graph, start_node="concept::transformer", target_type="entity") == []


def test_query_graph_unknown_start_node_returns_empty() -> None:
    graph = _graph_with_node_types()
    assert query_graph(graph, start_node="concept::missing", target_type="note") == []


def test_query_graph_empty_graph_returns_empty() -> None:
    assert query_graph(KnowledgeGraph(), start_node="concept::transformer") == []


def test_query_graph_without_start_node_scans_by_type() -> None:
    graph = _graph_with_node_types()
    assert [n.id for n in query_graph(graph, target_type="concept")] == ["concept::transformer"]
    assert [n.id for n in query_graph(graph)] == [
        "concept::transformer",
        "note::attention",
        "person::jane_smith",
    ]


def test_query_graph_limit() -> None:
    graph = _graph_with_node_types()
    assert [n.id for n in query_graph(graph, limit=2)] == [
        "concept::transformer",
        "note::attention",
    ]


# ── 6. serialization round-trip (produce/consume the artifact) ─────────────


def test_graph_from_dict_round_trips_graph_to_dict() -> None:
    a = _entity("organization::acme_corporation")
    b = _entity("person::jane_smith")
    graph = _build([a, b], [_relationship(a.id, b.id)])
    loaded = graph_from_dict(graph_to_dict(graph))
    assert set(loaded.nodes) == set(graph.nodes)
    assert len(loaded.edges) == 1
    assert get_entity(loaded, a.id).source == "a.md"
    assert [n.id for n in related_entities(loaded, a.id)] == [b.id]


def test_graph_from_dict_accepts_json_round_trip() -> None:
    graph = _graph_with_node_types()
    raw = json.loads(json.dumps(graph_to_dict(graph)))
    loaded = graph_from_dict(raw)
    assert len(loaded.nodes) == 3
    assert len(loaded.edges) == 1


def test_graph_from_dict_empty_and_absent_keys() -> None:
    assert graph_from_dict({}).nodes == {}
    assert graph_from_dict({"nodes": [], "edges": []}).nodes == {}
    assert graph_from_dict({"nodes": []}).edges == []
