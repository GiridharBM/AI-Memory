"""Mind-map route: deterministic read-only knowledge-graph projection.

No LLM, no job, no artifact, no mutation. A node id projects that node's
bounded neighborhood; without one the route returns a bounded,
deterministically ordered slice of the graph. A missing graph file is a
genuinely empty projection; an unreadable one is a 503.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core.config import Settings
from app.domain.knowledge_graph import KnowledgeGraph
from app.interfaces.web import deps

router = APIRouter()

_MAX_DEPTH = 3
_MAX_NODES = 100


def _node_payload(node: Any) -> dict[str, Any]:
    return {
        "id": node.id,
        "label": node.label,
        "node_type": node.node_type,
        "source": node.source,
    }


def _edge_payload(edge: Any) -> dict[str, Any]:
    return {
        "source_id": edge.source_id,
        "target_id": edge.target_id,
        "edge_type": edge.edge_type,
    }


def _project(graph: KnowledgeGraph, node_ids: set[str]) -> dict[str, Any]:
    """Project a node set with its internal edges, deterministically ordered."""

    ordered = sorted(node_ids)
    nodes = [_node_payload(graph.nodes[node_id]) for node_id in ordered]
    edges = sorted(
        (
            _edge_payload(edge)
            for edge in graph.edges
            if edge.source_id in node_ids and edge.target_id in node_ids
        ),
        key=lambda edge: (edge["source_id"], edge["target_id"], edge["edge_type"]),
    )
    return {"available": True, "nodes": nodes, "edges": edges}


def _load_graph(settings: Settings) -> KnowledgeGraph | None:
    """Load the persisted graph; ``None`` only when it cannot be read."""

    path = settings.paths.manifest_root / "knowledge_graph.json"
    if not path.exists():
        return KnowledgeGraph()
    try:
        return KnowledgeGraph.load(path)
    except (ValueError, OSError, KeyError, TypeError):
        return None


@router.get("/mindmap")
def get_mindmap(
    node_id: str | None = Query(default=None),
    depth: int = Query(default=1, ge=0, le=_MAX_DEPTH),
) -> dict[str, Any]:
    """Bounded deterministic projection of the knowledge graph."""

    error = deps.settings_error()
    if error is not None:
        raise HTTPException(status_code=503, detail=error)
    settings = deps.get_settings()
    graph = _load_graph(settings)
    if graph is None:
        raise HTTPException(
            status_code=503,
            detail="The knowledge graph could not be read; mind map is unavailable.",
        )
    if node_id is not None:
        if node_id not in graph.nodes:
            raise HTTPException(status_code=404, detail="Mind-map node not found.")
        projected = graph.subgraph(node_id, depth=depth)
        rest = sorted(set(projected.nodes) - {node_id})
        node_ids = {node_id} | set(rest[: max(0, _MAX_NODES - 1)])
    else:
        node_ids = set(sorted(graph.nodes)[:_MAX_NODES])
    return _project(graph, node_ids) | {"root": node_id}
