"""Integration tests for P4-105 graph queries and end-to-end integration.

Chains the real pipeline (``StructureAnalyzer`` → ``EntityExtractor`` →
``RelationshipDetector`` → ``DocumentGraphBuilder``), asserts the query layer
consumes the ``metadata.extra["knowledge_graph"]`` artifact the
``IngestionWorkflow`` produces, and verifies cross-document relationship
queries over a merged graph.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.application import AIProcessingResult
from app.core.config import Settings
from app.domain.analysis import DocumentAnalysis
from app.domain.documents import SourceDocument
from app.infrastructure.document_intelligence.entities import EntityExtractor
from app.infrastructure.document_intelligence.graph import (
    DocumentGraphBuilder,
    get_entity,
    graph_from_dict,
    graph_to_dict,
    nodes_by_source,
    query_graph,
    related_entities,
)
from app.infrastructure.document_intelligence.relationships import RelationshipDetector
from app.infrastructure.document_intelligence.structure.detector import StructureAnalyzer
from app.pipelines import IngestionWorkflow, IngestionWorkflowResult


def _build_graph(text: str, source: str):
    structure = StructureAnalyzer().analyze(text, source)
    entities = EntityExtractor().extract(text, source, "markdown", structure)
    relationships = RelationshipDetector().detect(entities)
    return DocumentGraphBuilder().build(entities, relationships, source)


class _RecordingProcessor:
    def __init__(self) -> None:
        self.documents: list[SourceDocument] = []

    def process(self, document: SourceDocument) -> AIProcessingResult:
        self.documents.append(document)
        return AIProcessingResult(
            document=document,
            analysis=_analysis(),
            attempts=1,
        )


def _production_workflow(settings: Settings) -> IngestionWorkflow:
    workflow = IngestionWorkflow.create_default(settings)
    workflow._processor = _RecordingProcessor()
    workflow._chunker = None
    workflow._embedding_service = None
    workflow._vector_store = None
    workflow._kg_builder = None
    workflow._graph_path = None
    return workflow


def _graph_of(result: IngestionWorkflowResult):
    return result.document.metadata.extra["knowledge_graph"]


def _write_source(tmp_path: Path, filename: str, text: str) -> Path:
    source = tmp_path / filename
    source.write_text(text, encoding="utf-8")
    return source


# ── E2E: ingestion → extraction → detection → construction → query ─────────


@pytest.mark.integration
def test_e2e_query_consumes_workflow_knowledge_graph(
    tmp_settings: Settings,
    tmp_path: Path,
) -> None:
    source = _write_source(
        tmp_path,
        "team.md",
        "# Team\n\nDr. Jane Smith works at Acme Corporation using Python 3.12.\n",
    )
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="markdown")

    raw = _graph_of(result)
    graph = graph_from_dict(raw)

    # entity lookup
    jane = get_entity(graph, "person::jane_smith")
    assert jane is not None and jane.node_type == "entity"

    # related-entity traversal
    related = {n.id for n in related_entities(graph, "person::jane_smith")}
    assert "organization::acme_corporation" in related
    assert "technology::python_3.12" in related

    # source/document lookup
    sources = {n.source for n in nodes_by_source(graph, str(source))}
    assert sources == {str(source)}

    # basic traversal by type
    assert {n.id for n in query_graph(graph, target_type="entity")} == set(graph.nodes)


@pytest.mark.integration
def test_e2e_unknown_entity_and_empty_result_safe(
    tmp_settings: Settings,
    tmp_path: Path,
) -> None:
    source = _write_source(tmp_path, "team.md", "# Team\n\nJane Smith.\n")
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="markdown")

    graph = graph_from_dict(_graph_of(result))
    assert get_entity(graph, "person::ghost") is None
    assert related_entities(graph, "person::ghost") == []
    assert query_graph(graph, start_node="concept::missing") == []


# ── chained pipeline query coverage ────────────────────────────────────────


def test_chained_pipeline_query_multiple_relationships() -> None:
    text = "# Team\n\nDr. Jane Smith works at Acme Corporation and uses Python 3.12.\n"
    graph = _build_graph(text, "team.md")

    related = {n.id for n in related_entities(graph, "person::jane_smith")}
    assert related == {"organization::acme_corporation", "technology::python_3.12"}


def test_chained_pipeline_query_cycle_safe() -> None:
    # all three entities co-occur in one section: complete triangle, no hang
    text = "# Tri\n\nAcme Corporation hired Dr. Jane Smith who builds with Python 3.12.\n"
    graph = _build_graph(text, "tri.md")

    assert len(related_entities(graph, "person::jane_smith", max_depth=10)) == 2


def test_chained_pipeline_query_source_lookup() -> None:
    text = "# Team\n\nJane Smith works at Acme Corporation.\n"
    graph = _build_graph(text, "team.md")

    assert {n.id for n in nodes_by_source(graph, "team.md")} == set(graph.nodes)
    assert nodes_by_source(graph, "other.md") == []


def test_chained_pipeline_artifact_round_trip() -> None:
    text = "# Team\n\nJane Smith works at Acme Corporation.\n"
    graph = _build_graph(text, "team.md")

    loaded = graph_from_dict(graph_to_dict(graph))
    assert set(loaded.nodes) == set(graph.nodes)
    assert len(loaded.edges) == len(graph.edges)


# ── cross-document relationships ───────────────────────────────────────────


def test_cross_document_query_shared_entity() -> None:
    from app.infrastructure.knowledge_graph import KnowledgeGraphBuilder

    graph_a = _build_graph(
        "# A\n\nDr. Jane Smith works at Acme Corporation.\n", "a.md"
    )
    graph_b = _build_graph(
        "# B\n\nDr. Jane Smith uses Python 3.12.\n", "b.md"
    )

    merged = KnowledgeGraphBuilder().merge_graphs(graph_a, graph_b)

    # the shared entity has a single merged node reachable from both documents
    related = {n.id for n in related_entities(merged, "person::jane_smith")}
    assert related == {"organization::acme_corporation", "technology::python_3.12"}
    assert get_entity(merged, "person::jane_smith") is not None


def test_cross_document_query_no_shared_entity() -> None:
    from app.infrastructure.knowledge_graph import KnowledgeGraphBuilder

    graph_a = _build_graph("# A\n\nJane Smith.\n", "a.md")
    graph_b = _build_graph("# B\n\nAcme Corporation.\n", "b.md")

    merged = KnowledgeGraphBuilder().merge_graphs(graph_a, graph_b)
    assert related_entities(merged, "person::jane_smith") == []


def _analysis() -> DocumentAnalysis:
    return DocumentAnalysis.model_validate(
        {
            "suggested_note_title": "Graph Query Test",
            "summary": {
                "short": "Test summary.",
                "detailed": "Test detailed summary.",
            },
            "key_concepts": [],
            "definitions": [],
            "important_entities": [],
            "tags": ["graph"],
            "related_topics": [],
        }
    )
