"""Knowledge graph builder from document analysis."""

from __future__ import annotations

from app.core.logging import get_logger
from app.domain.analysis import DocumentAnalysis
from app.domain.knowledge_graph import (
    GraphBuildResult,
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
)

logger = get_logger(__name__)


def _make_id(label: str, node_type: str) -> str:
    return f"{node_type}::{label.lower().strip().replace(' ', '_')}"


class KnowledgeGraphBuilder:
    """Build a knowledge graph from document analysis results."""

    def build_from_analysis(
        self,
        analysis: DocumentAnalysis,
        source: str,
    ) -> GraphBuildResult:
        graph = KnowledgeGraph()
        nodes_added = 0
        edges_added = 0
        note_id = _make_id(analysis.suggested_note_title, "note")
        graph.add_node(KnowledgeNode(
            id=note_id,
            label=analysis.suggested_note_title,
            node_type="note",
            source=source,
        ))
        nodes_added += 1

        for concept in analysis.key_concepts:
            nid = _make_id(concept.name, "concept")
            graph.add_node(KnowledgeNode(
                id=nid,
                label=concept.name,
                node_type="concept",
                source=source,
                metadata={"importance": concept.importance},
            ))
            nodes_added += 1
            graph.add_edge(KnowledgeEdge(
                source_id=note_id,
                target_id=nid,
                edge_type="mentioned_in",
            ))
            edges_added += 1

        for definition in analysis.definitions:
            nid = _make_id(definition.term, "definition")
            graph.add_node(KnowledgeNode(
                id=nid,
                label=definition.term,
                node_type="definition",
                source=source,
                metadata={"definition": definition.definition[:200]},
            ))
            nodes_added += 1
            graph.add_edge(KnowledgeEdge(
                source_id=note_id,
                target_id=nid,
                edge_type="defined_in",
            ))
            edges_added += 1

        for entity in analysis.important_entities:
            nid = _make_id(entity.name, "entity")
            graph.add_node(KnowledgeNode(
                id=nid,
                label=entity.name,
                node_type="entity",
                source=source,
                metadata={"entity_type": entity.type},
            ))
            nodes_added += 1
            graph.add_edge(KnowledgeEdge(
                source_id=note_id,
                target_id=nid,
                edge_type="mentioned_in",
            ))
            edges_added += 1

        for topic in analysis.related_topics:
            nid = _make_id(topic.topic, "topic")
            graph.add_node(KnowledgeNode(
                id=nid,
                label=topic.topic,
                node_type="topic",
                source=source,
            ))
            nodes_added += 1
            graph.add_edge(KnowledgeEdge(
                source_id=note_id,
                target_id=nid,
                edge_type="related_to",
            ))
            edges_added += 1

        for concept in analysis.key_concepts:
            for entity in analysis.important_entities:
                cid = _make_id(concept.name, "concept")
                eid = _make_id(entity.name, "entity")
                if graph.nodes.get(cid) and graph.nodes.get(eid):
                    graph.add_edge(KnowledgeEdge(
                        source_id=cid,
                        target_id=eid,
                        edge_type="related_to",
                        weight=0.5,
                    ))
                    edges_added += 1

        result = GraphBuildResult(
            graph=graph,
            nodes_added=nodes_added,
            edges_added=edges_added,
        )
        logger.info(
            "Knowledge graph built.",
            extra={"source": source, "nodes": nodes_added, "edges": edges_added},
        )
        return result

    def merge_graphs(self, *graphs: KnowledgeGraph) -> KnowledgeGraph:
        merged = KnowledgeGraph()
        for graph in graphs:
            for node in graph.nodes.values():
                merged.add_node(node)
            for edge in graph.edges:
                merged.add_edge(edge)
        logger.debug(
            "Graphs merged.",
            extra={"total_nodes": len(merged.nodes), "total_edges": len(merged.edges)},
        )
        return merged
