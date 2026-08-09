"""Unit tests for the deterministic document-level graph builder (P4-104).

Covers the mandated categories: empty/single/multiple nodes and edges,
disconnected components, cycles, duplicate entities and relationships, missing
relationship targets, deterministic construction, entity-id lookup, and
relationship lookup.
"""

from __future__ import annotations

from app.domain.entity_relationship import Entity, Relationship, SourceReference
from app.domain.knowledge_graph import KnowledgeGraph
from app.infrastructure.document_intelligence.graph import (
    DocumentGraphBuilder,
    build_document_graph,
    find_relationships,
    get_default_document_graph_builder,
    graph_to_dict,
)


def _entity(entity_id: str, *, importance: str | None = None) -> Entity:
    kwargs: dict = {
        "id": entity_id,
        "label": entity_id.rsplit("::", 1)[-1].replace("_", " "),
        "entity_type": entity_id.split("::", 1)[0],
        "sources": [SourceReference(source="a.md", start_char=0, end_char=8, snippet="X")],
    }
    if importance is not None:
        from app.domain.entity_relationship import EntityMetadata

        kwargs["metadata"] = EntityMetadata(importance=importance)
    return Entity(**kwargs)


def _relationship(
    source_id: str,
    target_id: str,
    edge_type: str = "related_to",
    *,
    weight: float = 1.0,
) -> Relationship:
    return Relationship(
        id=Relationship.make_id(source_id, target_id, edge_type),
        source_id=source_id,
        target_id=target_id,
        relationship_type=edge_type,
        weight=weight,
    )


def _build(entities: list[Entity], relationships: list[Relationship]) -> KnowledgeGraph:
    return DocumentGraphBuilder().build(entities, relationships, "a.md")


# ── 1. empty graph ─────────────────────────────────────────────────────────


def test_empty_input_yields_empty_graph() -> None:
    graph = _build([], [])
    assert graph.nodes == {}
    assert graph.edges == []


# ── 2. single / multiple nodes ─────────────────────────────────────────────


def test_single_entity_yields_single_node() -> None:
    graph = _build([_entity("organization::acme_corporation")], [])
    assert list(graph.nodes) == ["organization::acme_corporation"]
    node = graph.nodes["organization::acme_corporation"]
    assert node.label == "acme corporation"
    assert node.node_type == "entity"
    assert node.source == "a.md"
    assert node.metadata["entity_type"] == "organization"


def test_multiple_entities_all_present_with_metadata() -> None:
    entities = [
        _entity("organization::acme_corporation"),
        _entity("person::jane_smith", importance="high"),
    ]
    graph = _build(entities, [])
    assert set(graph.nodes) == {"organization::acme_corporation", "person::jane_smith"}
    assert graph.nodes["person::jane_smith"].metadata == {
        "entity_type": "person",
        "importance": "high",
    }


def test_lookup_by_entity_id() -> None:
    graph = _build([_entity("person::jane_smith")], [])
    assert graph.nodes.get("person::jane_smith") is not None
    assert graph.nodes.get("missing") is None


# ── 3. single / multiple edges ─────────────────────────────────────────────


def test_single_relationship_yields_single_edge() -> None:
    acme = _entity("organization::acme_corporation")
    jane = _entity("person::jane_smith")
    graph = _build([acme, jane], [_relationship(acme.id, jane.id)])
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.source_id == acme.id
    assert edge.target_id == jane.id
    assert edge.edge_type == "related_to"
    assert edge.weight == 1.0
    assert edge.metadata["id"] == Relationship.make_id(acme.id, jane.id)
    assert edge.metadata["source"] == "a.md"


def test_multiple_edges_all_present() -> None:
    a, b, c = (_entity("organization::acme_corporation"), _entity("person::jane_smith"),
               _entity("technology::python_3.12"))
    graph = _build([a, b, c], [_relationship(a.id, b.id), _relationship(b.id, c.id)])
    pairs = {(e.source_id, e.target_id) for e in graph.edges}
    assert pairs == {(a.id, b.id), (b.id, c.id)}


# ── 4. disconnected components ─────────────────────────────────────────────


def test_disconnected_entities_yield_isolated_nodes() -> None:
    a = _entity("organization::acme_corporation")
    b = _entity("person::jane_smith")
    c = _entity("technology::python_3.12")
    graph = _build([a, b, c], [_relationship(a.id, b.id)])
    assert set(graph.nodes) == {a.id, b.id, c.id}
    assert len(graph.edges) == 1
    assert graph.neighbors(c.id) == []  # isolated node, no crash


# ── 5. cycles ──────────────────────────────────────────────────────────────


def test_cycle_traversal_is_safe() -> None:
    a, b, c = (_entity("organization::acme_corporation"), _entity("person::jane_smith"),
               _entity("technology::python_3.12"))
    relationships = [
        _relationship(a.id, b.id),
        _relationship(b.id, c.id),
        _relationship(c.id, a.id),
    ]
    graph = _build([a, b, c], relationships)
    assert len(graph.edges) == 3
    # single-hop traversal never loops
    assert len(graph.neighbors(a.id)) == 2
    sub = graph.subgraph(a.id, depth=2)
    assert set(sub.nodes) == {a.id, b.id, c.id}
    assert len(sub.edges) == 3


# ── 6. duplicate entities / relationships ──────────────────────────────────


def test_duplicate_entities_collapse_to_one_node() -> None:
    dup = _entity("organization::acme_corporation")
    graph = _build([_entity("organization::acme_corporation"), dup], [])
    assert list(graph.nodes) == ["organization::acme_corporation"]


def test_duplicate_relationships_collapse_to_one_edge() -> None:
    a = _entity("organization::acme_corporation")
    b = _entity("person::jane_smith")
    graph = _build([a, b], [_relationship(a.id, b.id), _relationship(a.id, b.id)])
    assert len(graph.edges) == 1


# ── 7. missing relationship targets ────────────────────────────────────────


def test_missing_targets_are_skipped_without_crash() -> None:
    a = _entity("organization::acme_corporation")
    graph = _build([a], [_relationship(a.id, "person::ghost")])
    assert graph.edges == []
    assert len(graph.nodes) == 1


# ── 8. deterministic construction ──────────────────────────────────────────


def test_deterministic_across_input_order() -> None:
    a = _entity("organization::acme_corporation")
    b = _entity("person::jane_smith")
    c = _entity("technology::python_3.12")
    rels = [_relationship(a.id, b.id), _relationship(b.id, c.id)]

    forward = graph_to_dict(_build([a, b, c], rels))
    reversed_input = graph_to_dict(_build([c, b, a], list(reversed(rels))))

    assert forward == reversed_input
    assert [e["source_id"] for e in forward["edges"]] == sorted(
        e["source_id"] for e in forward["edges"]
    )


def test_same_input_identical_across_instances() -> None:
    a, b = _entity("organization::acme_corporation"), _entity("person::jane_smith")
    rels = [_relationship(a.id, b.id)]
    first = graph_to_dict(DocumentGraphBuilder().build([a, b], rels, "a.md"))
    second = graph_to_dict(DocumentGraphBuilder().build([a, b], rels, "a.md"))
    assert first == second


# ── 9. relationship lookup ─────────────────────────────────────────────────


def test_find_relationships_filters() -> None:
    a = _entity("organization::acme_corporation")
    b = _entity("person::jane_smith")
    c = _entity("technology::python_3.12")
    graph = _build([a, b, c], [_relationship(a.id, b.id), _relationship(b.id, c.id)])

    assert len(find_relationships(graph)) == 2
    assert [e.target_id for e in find_relationships(graph, source_id=b.id)] == [c.id]
    assert [e.source_id for e in find_relationships(graph, target_id=b.id)] == [a.id]
    assert find_relationships(graph, source_id=a.id, target_id=b.id)[0].edge_type == "related_to"
    assert find_relationships(graph, source_id=c.id, target_id=a.id) == []


def test_find_relationships_edge_type_filter() -> None:
    a = _entity("organization::acme_corporation")
    b = _entity("person::jane_smith")
    graph = _build(
        [a, b],
        [_relationship(a.id, b.id, "related_to"), _relationship(a.id, b.id, "depends_on")],
    )
    assert [e.edge_type for e in find_relationships(graph, edge_type="depends_on")] == [
        "depends_on"
    ]


# ── 10. serialization round-trip ───────────────────────────────────────────


def test_graph_to_dict_round_trips_through_load(tmp_path) -> None:
    a = _entity("organization::acme_corporation")
    b = _entity("person::jane_smith")
    graph = _build([a, b], [_relationship(a.id, b.id)])
    path = tmp_path / "g.json"
    path.write_text(__import__("json").dumps(graph_to_dict(graph)), encoding="utf-8")
    loaded = KnowledgeGraph.load(path)
    assert set(loaded.nodes) == set(graph.nodes)
    assert len(loaded.edges) == 1
    assert loaded.edges[0].metadata == graph.edges[0].metadata


# ── public API ─────────────────────────────────────────────────────────────


def test_module_helpers() -> None:
    assert isinstance(get_default_document_graph_builder(), DocumentGraphBuilder)
    a, b = _entity("organization::acme_corporation"), _entity("person::jane_smith")
    graph = build_document_graph([a, b], [_relationship(a.id, b.id)], "a.md")
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
