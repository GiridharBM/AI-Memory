"""Integration tests for P4-103 relationship detection pipeline wiring.

Chains the real ``StructureAnalyzer`` (M2.3) → ``EntityExtractor`` (P4-102) →
``RelationshipDetector`` (P4-103). Entities are extracted against the original
document offsets, and the detector consumes those entities, so co-occurrence
edges reflect the actual section structure. Also asserts the full
``IngestionWorkflow`` attaches ``metadata.extra["relationships"]``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.application import AIProcessingResult
from app.core.config import Settings
from app.domain.analysis import DocumentAnalysis
from app.domain.documents import SourceDocument
from app.infrastructure.document_intelligence.entities import EntityExtractor
from app.infrastructure.document_intelligence.relationships import (
    RelationshipDetector,
    get_default_relationship_detector,
)
from app.infrastructure.document_intelligence.structure.detector import StructureAnalyzer
from app.pipelines import IngestionWorkflow, IngestionWorkflowResult


def _detect(text: str, source: str = "team.md") -> list:
    structure = StructureAnalyzer().analyze(text, source)
    entities = EntityExtractor().extract(text, source, "markdown", structure)
    return RelationshipDetector().detect(entities)


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


def _relationships_of(result: IngestionWorkflowResult) -> list[dict]:
    return result.document.metadata.extra["relationships"]


def _write_source(tmp_path: Path, filename: str, text: str) -> Path:
    source = tmp_path / filename
    source.write_text(text, encoding="utf-8")
    return source


def test_relationships_between_section_cooccurring_entities() -> None:
    text = (
        "# Team\n\n"
        "Dr. Jane Smith works at Acme Corporation using Python 3.12.\n\n"
        "## Tooling\n\n"
        "We run production on Kubernetes.\n"
    )
    rels = _detect(text)

    pairs = {(r.source_id, r.target_id) for r in rels}
    assert pairs == {
        ("organization::acme_corporation", "person::jane_smith"),
        ("organization::acme_corporation", "technology::python_3.12"),
        ("person::jane_smith", "technology::python_3.12"),
    }
    assert all(r.relationship_type == "related_to" for r in rels)
    # evidence offsets point into the original document
    for rel in rels:
        for ref in rel.sources:
            assert text[ref.start_char : ref.end_char] == ref.snippet


def test_no_relationships_across_sections_via_pipeline() -> None:
    text = "# One\n\nAcme Corporation.\n\n# Two\n\nJane Smith.\n"
    assert _detect(text) == []


def test_code_block_content_is_excluded_from_relationships() -> None:
    text = "# Team\n\nJane Smith.\n\n```\nAcme Corporation\n```\n"
    # only Jane Smith survives extraction, so no co-occurrence edge can form
    assert _detect(text) == []


@pytest.mark.integration
def test_workflow_enriches_markdown_with_relationships(
    tmp_settings: Settings,
    tmp_path: Path,
) -> None:
    text = "# Team\n\nJane Smith works at Acme Corporation.\n"
    source = _write_source(tmp_path, "team.md", text)
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="markdown")

    rels = _relationships_of(result)
    assert len(rels) == 1
    rel = rels[0]
    assert rel["relationship_type"] == "related_to"
    assert {rel["source_id"], rel["target_id"]} == {
        "concept::jane_smith",
        "organization::acme_corporation",
    }
    assert len(rel["sources"]) == 2
    for ref in rel["sources"]:
        assert ref["source"].endswith("team.md")
        assert ref["source_type"] == "markdown"
        assert ref["section_id"] == "s-1"
        assert text[ref["start_char"] : ref["end_char"]] == ref["snippet"]


@pytest.mark.integration
def test_relationships_absent_when_disabled(tmp_settings: Settings, tmp_path: Path) -> None:
    tmp_settings.intelligence.relationships.enabled = False
    source = _write_source(tmp_path, "team.md", "# Team\n\nJane Smith.\n")
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="markdown")

    assert "relationships" not in result.document.metadata.extra


@pytest.mark.integration
def test_relationships_absent_for_non_text_kind(tmp_settings: Settings, tmp_path: Path) -> None:
    source = _write_source(tmp_path, "data.csv", "a,b\n1,2\n")
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="csv")

    assert "relationships" not in result.document.metadata.extra


@pytest.mark.integration
def test_detector_failure_contained_and_ingestion_continues(
    tmp_settings: Settings,
    tmp_path: Path,
) -> None:
    class _RaisingDetector:
        def detect(self, entities: list) -> list:
            raise RuntimeError("boom")

    source = _write_source(tmp_path, "team.md", "# Team\n\nJane Smith.\n")
    workflow = _production_workflow(tmp_settings)
    workflow._relationship_detector = _RaisingDetector()

    result = workflow.run(source, expected_source_type="markdown")

    assert "relationships" not in result.document.metadata.extra
    assert result.note is not None


@pytest.mark.integration
def test_create_default_wires_relationship_detector(tmp_settings: Settings) -> None:
    workflow = IngestionWorkflow.create_default(tmp_settings)

    detector = get_default_relationship_detector()
    assert isinstance(workflow._relationship_detector, type(detector))
    assert workflow._relationships().enabled is True


@pytest.mark.integration
def test_create_default_disabled_still_wires_detector(tmp_settings: Settings) -> None:
    tmp_settings.intelligence.relationships.enabled = False
    workflow = IngestionWorkflow.create_default(tmp_settings)

    assert workflow._relationship_detector is not None
    assert workflow._relationships().enabled is False


def _analysis() -> DocumentAnalysis:
    return DocumentAnalysis.model_validate(
        {
            "suggested_note_title": "Relationship Test",
            "summary": {
                "short": "Test summary.",
                "detailed": "Test detailed summary.",
            },
            "key_concepts": [],
            "definitions": [],
            "important_entities": [],
            "tags": ["relationships"],
            "related_topics": [],
        }
    )
