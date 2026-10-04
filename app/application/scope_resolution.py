"""Application-layer resolution of topic/node scopes to source identifiers.

Maps requested knowledge-graph node IDs to the vector ``source`` values
their nodes carry, so TOPICS/NODES scopes can reuse the existing
P0 restricted retrieval path (per-source filtered ``SearchService``
calls). Pure and read-only: no filesystem access, no graph mutation,
no persistence, no retrieval calls. The caller supplies an already
loaded ``KnowledgeGraph``; loading belongs at the application boundary.

Resolution is exact node-ID lookup only: no prefix enforcement, no
neighbor/subgraph expansion, no label matching. One node contributes at
most its own single persisted ``source`` (the current data model keeps
only the last writer's source per label-derived ID); multi-source
history would require a KG identity redesign, which is out of scope.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.application.generation_errors import UnsupportedScopeError
from app.domain.knowledge_graph import KnowledgeGraph


def resolve_sources_for_nodes(
    graph: KnowledgeGraph,
    node_ids: Sequence[str],
) -> tuple[str, ...]:
    """Resolve KG node IDs to a deterministic sorted tuple of source IDs.

    Nodes with a blank source contribute nothing. Any unknown ID poisons
    the whole request with :class:`UnsupportedScopeError` naming every
    unknown ID, so a topic/node scope can never silently narrow to a
    known subset — and, downstream of P0, never widen to whole-corpus
    retrieval.
    """

    wanted = [node_id for node_id in node_ids if isinstance(node_id, str) and node_id.strip()]
    unknown = sorted({node_id for node_id in wanted if node_id not in graph.nodes})
    if unknown:
        listed = ", ".join(repr(node_id) for node_id in unknown)
        raise UnsupportedScopeError(
            f"Unknown knowledge-graph node identifier(s): {listed}."
        )
    sources: set[str] = set()
    for node_id in wanted:
        source = graph.nodes[node_id].source
        if isinstance(source, str) and source.strip():
            sources.add(source.strip())
    return tuple(sorted(sources))
