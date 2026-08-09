"""Integration tests for P4-104 document-level knowledge graph construction.

Chains the real ``StructureAnalyzer`` (M2.3) → ``EntityExtractor`` (P4-102) →
``RelationshipDetector`` (P4-103) → ``DocumentGraphBuilder`` (P4-104), and
asserts the full ``IngestionWorkflow`` attaches
``metadata.extra["knowledge_graph"]``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.application import AIProcessingResult
from app.core.config import Settings
from app.domain.analysis import DocumentAnalysis
from app.domain.documents import SourceDocument
from app.domain.knowledge_graph import KnowledgeGraph
from app.infrastructure.document_intelligence.entities import EntityExtractor
from app.infrastructure.document_intelligence.graph import (
    DocumentGraphBuilder,
    get_default_document_graph_builder,
    graph_to_dict,
)
from app.infrastructure.document_intelligence.relationships import RelationshipDetector
from app.infrastructure.document_intelligence.structure.detector import StructureAnalyzer
from app.pipelines import IngestionWorkflow, IngestionWorkflowResult


def _build_graph(text: str, source: str = "team.md") -> KnowledgeGraph:
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


def _graph_of(result: IngestionWorkflowResult) -> dict:
    return result.document.metadata.extra["knowledge_graph"]


def _write_source(tmp_path: Path, filename: str, text: str) -> Path:
    source = tmp_path / filename
    source.write_text(text, encoding="utf-8")
    return source


def test_pipeline_builds_graph_with_nodes_and_edges() -> None:
    text = (
        "# Team\n\n"
        "Dr. Jane Smith works at Acme Corporation using Python 3.12.\n\n"
        "## Tooling\n\n"
        "We run production on Kubernetes.\n"
    )
    graph = _build_graph(text)

    assert set(graph.nodes) == {
        "organization::acme_corporation",
        "person::jane_smith",
        "technology::python_3.12",
    }
    pairs = {(e.source_id, e.target_id) for e in graph.edges}
    assert pairs == {
        ("organization::acme_corporation", "person::jane_smith"),
        ("organization::acme_corporation", "technology::python_3.12"),
        ("person::jane_smith", "technology::python_3.12"),
    }
    for node in graph.nodes.values():
        assert node.source == "team.md"
        assert node.node_type == "entity"
        assert "entity_type" in node.metadata


def test_pipeline_graph_preserves_section_connectivity() -> None:
    text = "# One\n\nAcme Corporation.\n\n# Two\n\nDr. Jane Smith.\n"
    graph = _build_graph(text)
    # both entities present but in different sections: no edge (disconnected)
    assert set(graph.nodes) == {"organization::acme_corporation", "person::jane_smith"}
    assert graph.edges == []


def test_pipeline_graph_serialization_round_trips_through_load(tmp_path: Path) -> None:
    import json

    text = "# Team\n\nJane Smith works at Acme Corporation.\n"
    graph = _build_graph(text)
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(graph_to_dict(graph)), encoding="utf-8")
    loaded = KnowledgeGraph.load(path)
    assert set(loaded.nodes) == set(graph.nodes)
    assert len(loaded.edges) == len(graph.edges)


@pytest.mark.integration
def test_workflow_enriches_markdown_with_knowledge_graph(
    tmp_settings: Settings,
    tmp_path: Path,
) -> None:
    source = _write_source(tmp_path, "team.md", "# Team\n\nJane Smith works at Acme Corporation.\n")
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="markdown")

    raw = _graph_of(result)
    node_ids = {n["id"] for n in raw["nodes"]}
    assert node_ids == {"concept::jane_smith", "organization::acme_corporation"}
    assert all(n["node_type"] == "entity" for n in raw["nodes"])
    assert len(raw["edges"]) == 1
    edge = raw["edges"][0]
    assert edge["edge_type"] == "related_to"
    assert edge["metadata"]["source"].endswith("team.md")
    assert edge["source_id"] in node_ids and edge["target_id"] in node_ids


@pytest.mark.integration
def test_workflow_graph_nodes_only_when_relationships_disabled(
    tmp_settings: Settings,
    tmp_path: Path,
) -> None:
    tmp_settings.intelligence.relationships.enabled = False
    source = _write_source(tmp_path, "team.md", "# Team\n\nJane Smith works at Acme Corporation.\n")
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="markdown")

    raw = _graph_of(result)
    assert len(raw["nodes"]) == 2
    assert raw["edges"] == []


@pytest.mark.integration
def test_knowledge_graph_absent_when_disabled(
    tmp_settings: Settings,
    tmp_path: Path,
) -> None:
    tmp_settings.intelligence.graph.enabled = False
    source = _write_source(tmp_path, "team.md", "# Team\n\nJane Smith.\n")
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="markdown")

    assert "knowledge_graph" not in result.document.metadata.extra


@pytest.mark.integration
def test_graph_absent_for_non_text_kind(tmp_settings: Settings, tmp_path: Path) -> None:
    source = _write_source(tmp_path, "data.csv", "a,b\n1,2\n")
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="csv")

    assert "knowledge_graph" not in result.document.metadata.extra


@pytest.mark.integration
def test_builder_failure_contained_and_ingestion_continues(
    tmp_settings: Settings,
    tmp_path: Path,
) -> None:
    class _RaisingBuilder:
        def build(self, entities, relationships, source):
            raise RuntimeError("boom")

    source = _write_source(tmp_path, "team.md", "# Team\n\nJane Smith.\n")
    workflow = _production_workflow(tmp_settings)
    workflow._document_graph_builder = _RaisingBuilder()

    result = workflow.run(source, expected_source_type="markdown")

    assert "knowledge_graph" not in result.document.metadata.extra
    assert result.note is not None


@pytest.mark.integration
def test_create_default_wires_document_graph_builder(tmp_settings: Settings) -> None:
    workflow = IngestionWorkflow.create_default(tmp_settings)

    builder = get_default_document_graph_builder()
    assert isinstance(workflow._document_graph_builder, type(builder))
    assert workflow._graph().enabled is True


@pytest.mark.integration
def test_create_default_disabled_still_wires_builder(tmp_settings: Settings) -> None:
    tmp_settings.intelligence.graph.enabled = False
    workflow = IngestionWorkflow.create_default(tmp_settings)

    assert workflow._document_graph_builder is not None
    assert workflow._graph().enabled is False


def _analysis() -> DocumentAnalysis:
    return DocumentAnalysis.model_validate(
        {
            "suggested_note_title": "Graph Test",
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
