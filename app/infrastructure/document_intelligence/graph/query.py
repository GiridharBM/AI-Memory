"""Deterministic queries over document-level knowledge graphs (P4-105).

Completes the usable Phase 4 knowledge-graph capability: consumers can load
the pipeline's ``metadata.extra["knowledge_graph"]`` artifact back into an
in-memory ``KnowledgeGraph`` (``graph_from_dict``) and then run entity lookup,
relationship lookup, related-entity traversal, source/document lookup, and the
roadmap-style traversal (``query_graph``). Everything operates on the existing
``KnowledgeGraph`` abstraction and reuses the P4-104 ``find_relationships``
for relationship lookup — no new graph store, no duplicated entity/relationship
logic, and no modification of Phase 1-3 modules.

Guarantees:
- Deterministic: every result is sorted by node id (``find_relationships``
  already sorts by the canonical edge order).
- Safe: unknown ids and empty graphs return empty results, never raise.
- Cycle-safe: traversal is BFS with a visited set (requirement 6).
- Bounded: ``max_depth`` and ``limit`` caps are respected (requirement 7).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from app.domain.knowledge_graph import (
    EdgeType,
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
    NodeType,
)

__all__ = [
    "get_entity",
    "graph_from_dict",
    "nodes_by_source",
    "query_graph",
    "related_entities",
]


def get_entity(graph: KnowledgeGraph, entity_id: str) -> KnowledgeNode | None:
    """Return the node for ``entity_id``, or ``None`` if unknown."""
    return graph.nodes.get(entity_id)


def nodes_by_source(graph: KnowledgeGraph, source: str) -> list[KnowledgeNode]:
    """Return all nodes from ``source``, sorted by node id."""
    return sorted(
        (node for node in graph.nodes.values() if node.source == source),
        key=lambda n: n.id,
    )


def related_entities(
    graph: KnowledgeGraph,
    entity_id: str,
    *,
    edge_type: EdgeType | None = None,
    max_depth: int = 1,
    limit: int | None = None,
) -> list[KnowledgeNode]:
    """Return distinct entities reachable from ``entity_id``, sorted by id.

    BFS over the graph's undirected adjacency (reusing ``neighbors``); a
    visited set makes cycles safe. Unknown ids, empty graphs, ``max_depth <= 0``
    and ``limit <= 0`` all return ``[]``.
    """
    if entity_id not in graph.nodes or max_depth <= 0:
        return []
    visited: set[str] = {entity_id}
    frontier: list[str] = [entity_id]
    found: list[KnowledgeNode] = []
    for _ in range(max_depth):
        nxt: list[str] = []
        for current in frontier:
            for neighbor, edge in graph.neighbors(current):
                if edge_type is not None and edge.edge_type != edge_type:
                    continue
                if neighbor.id in visited:
                    continue
                visited.add(neighbor.id)
                found.append(neighbor)
                nxt.append(neighbor.id)
        frontier = sorted(nxt)
        if not frontier:
            break
    found.sort(key=lambda n: n.id)
    return _cap(found, limit)


def query_graph(
    graph: KnowledgeGraph,
    *,
    start_node: str | None = None,
    edge_type: EdgeType | None = None,
    target_type: NodeType | None = None,
    max_depth: int = 1,
    limit: int | None = None,
) -> list[KnowledgeNode]:
    """Traverse from ``start_node`` and return the matched nodes (roadmap §5.2).

    With ``start_node`` given, returns the distinct nodes reachable via edges
    of ``edge_type`` (undirected) within ``max_depth`` hops whose node type is
    ``target_type`` (when given). With ``start_node`` None, returns every node
    matching ``target_type``. No matches — including an unknown ``start_node``
    or an empty graph — return ``[]``, never an error.
    """
    if start_node is None:
        matched = [
            node
            for node in graph.nodes.values()
            if target_type is None or node.node_type == target_type
        ]
        matched.sort(key=lambda n: n.id)
        return _cap(matched, limit)
    reached = related_entities(
        graph,
        start_node,
        edge_type=edge_type,
        max_depth=max_depth,
    )
    matched = [node for node in reached if target_type is None or node.node_type == target_type]
    return _cap(matched, limit)


def graph_from_dict(data: Mapping[str, object]) -> KnowledgeGraph:
    """Load a ``KnowledgeGraph`` from the ``graph_to_dict`` shape (P4-104).

    Inverse of ``graph_to_dict`` so the pipeline's
    ``metadata.extra["knowledge_graph"]`` artifact can be consumed directly
    without a round-trip through ``KnowledgeGraph.save``/``load``.
    """
    graph = KnowledgeGraph()
    for item in cast("list[dict[str, object]]", data.get("nodes", [])):
        graph.add_node(
            KnowledgeNode(
                id=str(item["id"]),
                label=str(item["label"]),
                node_type=cast(NodeType, item["node_type"]),
                source=str(item.get("source", "")),
                metadata=cast("dict[str, str]", item.get("metadata", {})),
            )
        )
    for item in cast("list[dict[str, object]]", data.get("edges", [])):
        raw_weight = item.get("weight", 1.0)
        graph.add_edge(
            KnowledgeEdge(
                source_id=str(item["source_id"]),
                target_id=str(item["target_id"]),
                edge_type=cast(EdgeType, item["edge_type"]),
                weight=cast(float, raw_weight) if isinstance(raw_weight, (int, float))
                else float(cast(str, raw_weight)),
                metadata=cast("dict[str, str]", item.get("metadata", {})),
            )
        )
    return graph


def _cap(results: list[KnowledgeNode], limit: int | None) -> list[KnowledgeNode]:
    if limit is None:
        return results
    if limit <= 0:
        return []
    return results[:limit]
