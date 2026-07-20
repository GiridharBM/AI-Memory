"""Domain models for knowledge graph representation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

NodeType = Literal["entity", "concept", "topic", "note", "definition"]
EdgeType = Literal["related_to", "defined_in", "mentioned_in", "part_of", "depends_on"]


@dataclass(slots=True)
class KnowledgeNode:
    """A node in the knowledge graph."""

    id: str
    label: str
    node_type: NodeType
    source: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class KnowledgeEdge:
    """A directed edge in the knowledge graph."""

    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class KnowledgeGraph:
    """A simple in-memory knowledge graph."""

    nodes: dict[str, KnowledgeNode] = field(default_factory=dict)
    edges: list[KnowledgeEdge] = field(default_factory=list)

    def add_node(self, node: KnowledgeNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: KnowledgeEdge) -> None:
        if edge.source_id in self.nodes and edge.target_id in self.nodes:
            self.edges.append(edge)

    def neighbors(self, node_id: str) -> list[tuple[KnowledgeNode, KnowledgeEdge]]:
        results: list[tuple[KnowledgeNode, KnowledgeEdge]] = []
        for edge in self.edges:
            neighbor_id = None
            if edge.source_id == node_id:
                neighbor_id = edge.target_id
            elif edge.target_id == node_id:
                neighbor_id = edge.source_id
            if neighbor_id and neighbor_id in self.nodes:
                results.append((self.nodes[neighbor_id], edge))
        return results

    def subgraph(self, node_id: str, depth: int = 1) -> KnowledgeGraph:
        visited: set[str] = set()
        queue = [(node_id, 0)]
        graph = KnowledgeGraph()
        while queue:
            current, d = queue.pop(0)
            if current in visited or d > depth:
                continue
            visited.add(current)
            if current in self.nodes:
                graph.add_node(self.nodes[current])
            if d == depth:
                continue
            for neighbor, edge in self.neighbors(current):
                if neighbor.id not in visited:
                    graph.add_node(neighbor)
                    graph.add_edge(edge)
                    queue.append((neighbor.id, d + 1))
        return graph


@dataclass(slots=True)
class GraphBuildResult:
    """Result of building a knowledge graph from analysis."""

    graph: KnowledgeGraph
    nodes_added: int = 0
    edges_added: int = 0
