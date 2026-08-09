"""Deterministic document-level knowledge graph construction (P4-104).

Consumes the P4-101 ``Entity`` and ``Relationship`` objects produced by the
pipeline (P4-102 extraction, P4-103 detection) and builds an in-memory
``KnowledgeGraph`` (``app/domain/knowledge_graph.py`` — the smallest graph
abstraction the existing architecture already provides). This milestone adds
no graph storage or retrieval: the graph is a document-level, in-memory
construction; requirement 10 forbids persistent graph-database infrastructure.

Mapping:
- ``Entity``      → ``KnowledgeNode`` (``node_type="entity"``, ``source`` set,
  ``entity_type`` and ``importance`` preserved in node metadata).
- ``Relationship`` → ``KnowledgeEdge`` (``edge_type``/``weight`` carried
  directly; the relationship ``id`` and the document ``source`` preserved in
  edge metadata).

Guarantees:
- Deterministic by construction: nodes and edges are sorted by id, so the
  built graph is a pure function of the inputs regardless of input list order.
- No duplicate nodes (dedup by ``Entity.id``) and no duplicate edges (dedup by
  ``(source_id, target_id, edge_type)``).
- Missing/invalid relationship targets never raise: an edge whose endpoints are
  not in the entity set is skipped with a logged warning.
- Disconnected entities produce an isolated-nodes graph (valid: requirement 6).
- Cycles are safe: traversal is single-hop ``neighbors`` (no recursion) and
  ``KnowledgeGraph.subgraph`` uses a visited set.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.logging import get_logger
from app.domain.entity_relationship import Entity, Relationship
from app.domain.knowledge_graph import (
    EdgeType,
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
)

logger = get_logger(__name__)


class DocumentGraphBuilder:
    """Deterministic builder of a document-level ``KnowledgeGraph`` (P4-104).

    Stateless and reentrant-safe: a fresh instance is equivalent to any other.
    ``build`` never raises for empty or malformed input, and every node and
    edge id in the output comes from the input entities/relationships.
    """

    def build(
        self,
        entities: Sequence[Entity],
        relationships: Sequence[Relationship],
        source: str,
    ) -> KnowledgeGraph:
        """Build a ``KnowledgeGraph`` from entities and relationships."""
        nodes: dict[str, KnowledgeNode] = {}
        for entity in sorted(entities, key=lambda e: e.id):
            nodes[entity.id] = KnowledgeNode(
                id=entity.id,
                label=entity.label,
                node_type="entity",
                source=source,
                metadata=_node_metadata(entity),
            )

        edges: dict[tuple[str, str, str], KnowledgeEdge] = {}
        for relationship in sorted(relationships, key=lambda r: r.id):
            if relationship.source_id not in nodes or relationship.target_id not in nodes:
                logger.warning(
                    "Skipping document graph edge with missing endpoints.",
                    extra={
                        "source_id": relationship.source_id,
                        "target_id": relationship.target_id,
                        "edge_type": relationship.relationship_type,
                    },
                )
                continue
            key = (relationship.source_id, relationship.target_id, relationship.relationship_type)
            if key in edges:
                continue  # duplicate edge: keep the first (deterministic after sort)
            edges[key] = KnowledgeEdge(
                source_id=relationship.source_id,
                target_id=relationship.target_id,
                edge_type=relationship.relationship_type,
                weight=relationship.weight,
                metadata={"id": relationship.id, "source": source},
            )

        graph = KnowledgeGraph()
        for node in nodes.values():
            graph.add_node(node)
        graph.edges = sorted(edges.values(), key=lambda e: (e.source_id, e.target_id, e.edge_type))
        return graph


def _node_metadata(entity: Entity) -> dict[str, str]:
    """Node metadata from entity type/importance (both JSON-safe strings)."""
    metadata = {"entity_type": entity.entity_type}
    if entity.metadata.importance is not None:
        metadata["importance"] = entity.metadata.importance
    return metadata


def find_relationships(
    graph: KnowledgeGraph,
    *,
    source_id: str | None = None,
    target_id: str | None = None,
    edge_type: EdgeType | None = None,
) -> list[KnowledgeEdge]:
    """Return edges matching the given filters, in deterministic order (P4-104).

    Relationship lookup over the built graph. ``None`` filters are wildcards:
    ``find_relationships(graph)`` returns every edge; ``source_id`` selects
    edges leaving that node; ``target_id`` selects edges entering it; combined
    filters are applied conjunctively.
    """
    matches = [
        edge
        for edge in graph.edges
        if (source_id is None or edge.source_id == source_id)
        and (target_id is None or edge.target_id == target_id)
        and (edge_type is None or edge.edge_type == edge_type)
    ]
    return sorted(matches, key=lambda e: (e.source_id, e.target_id, e.edge_type))


def get_default_document_graph_builder() -> DocumentGraphBuilder:
    """Return a DocumentGraphBuilder (P4-104 composition root)."""
    return DocumentGraphBuilder()  # stateless; fresh instance is reentrant-safe


def build_document_graph(
    entities: Sequence[Entity],
    relationships: Sequence[Relationship],
    source: str,
) -> KnowledgeGraph:
    """Build a document-level ``KnowledgeGraph`` (P4-104 public API)."""
    return DocumentGraphBuilder().build(entities, relationships, source)


def graph_to_dict(graph: KnowledgeGraph) -> dict[str, object]:
    """Serialize a ``KnowledgeGraph`` to the ``KnowledgeGraph.save`` shape.

    Mirrors ``app.domain.knowledge_graph.KnowledgeGraph.save`` so the
    ``metadata.extra["knowledge_graph"]`` artifact round-trips with
    ``KnowledgeGraph.load`` and the existing M4 graph persistence.
    """
    return {
        "nodes": [
            {
                "id": node.id,
                "label": node.label,
                "node_type": node.node_type,
                "source": node.source,
                "metadata": node.metadata,
            }
            for node in graph.nodes.values()
        ],
        "edges": [
            {
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "edge_type": edge.edge_type,
                "weight": edge.weight,
                "metadata": edge.metadata,
            }
            for edge in graph.edges
        ],
    }
