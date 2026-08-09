"""Integration tests for Milestone 2.3 structure enrichment (P2-305/306).

Frozen spec §13 integration row: markdown + text files through
``IngestionWorkflow`` asserting ``result.document.metadata.extra["structure"]``
deserializes to a non-empty ``DocumentStructure`` with stable section IDs across
repeated runs; ``enabled: false`` path -> key absent; kinds outside
``TEXT_BEARING_KINDS`` -> key absent; CLI and worker paths both reach the
analyzer (both construct via ``IngestionWorkflow.create_default``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.application import AIProcessingResult
from app.core.config import Settings
from app.domain.analysis import DocumentAnalysis
from app.domain.document_intelligence import DocumentStructure
from app.domain.documents import SourceDocument
from app.infrastructure.document_intelligence.structure.detector import (
    StructureAnalyzer,
    max_structure_text_bytes,
)
from app.pipelines import IngestionWorkflow, IngestionWorkflowResult


class _RecordingProcessor:
    """Fake AI processor used to exercise the real pipeline without Ollama."""

    def __init__(self) -> None:
        self.documents: list[SourceDocument] = []

    def process(self, document: SourceDocument) -> AIProcessingResult:
        self.documents.append(document)
        return AIProcessingResult(
            document=document,
            analysis=_analysis(),
            attempts=1,
        )


class _RaisingAnalyzer:
    """Structure analyzer that always raises, for the L4 containment test."""

    def analyze(self, text: str, source: str) -> DocumentStructure:
        raise RuntimeError("boom")


def _production_workflow(settings: Settings) -> IngestionWorkflow:
    """Build via ``create_default`` (production wiring) with network steps off."""
    workflow = IngestionWorkflow.create_default(settings)
    workflow._processor = _RecordingProcessor()
    workflow._chunker = None
    workflow._embedding_service = None
    workflow._vector_store = None
    workflow._kg_builder = None
    workflow._graph_path = None
    return workflow


def _structure_of(result: IngestionWorkflowResult) -> DocumentStructure:
    raw = result.document.metadata.extra["structure"]
    return DocumentStructure.model_validate(raw)


def _fixture(name: str) -> str:
    return (Path(__file__).resolve().parents[1] / "fixtures" / "structure" / name).read_text(
        encoding="utf-8"
    )


def _write_source(tmp_path: Path, filename: str, text: str) -> Path:
    source = tmp_path / filename
    source.write_text(text, encoding="utf-8")
    return source


@pytest.mark.integration
def test_markdown_file_enriched_with_structure(tmp_settings: Settings, tmp_path: Path) -> None:
    source = _write_source(tmp_path, "input.md", _fixture("nested_headings.md"))
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="markdown")

    structure = _structure_of(result)
    assert structure.sections
    assert structure.sections[0].id == "s-1"
    assert [s.title for s in structure.sections[:2]] == ["Project Notes", "Installation"]


@pytest.mark.integration
def test_text_file_enriched_with_structure(tmp_settings: Settings, tmp_path: Path) -> None:
    text = "# Alpha\n\nBody.\n\n## Beta\n\nMore.\n"
    source = _write_source(tmp_path, "plain.txt", text)
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="text")

    structure = _structure_of(result)
    assert [s.title for s in structure.sections] == ["Alpha", "Beta"]


@pytest.mark.integration
def test_structure_stable_across_repeated_runs(tmp_settings: Settings, tmp_path: Path) -> None:
    source = _write_source(tmp_path, "input.md", _fixture("nested_headings.md"))
    workflow = _production_workflow(tmp_settings)

    first = _structure_of(workflow.run(source, expected_source_type="markdown"))
    second = _structure_of(workflow.run(source, expected_source_type="markdown"))

    assert first == second
    assert [s.id for s in first.sections] == [s.id for s in second.sections]


@pytest.mark.integration
def test_structure_absent_when_disabled(tmp_settings: Settings, tmp_path: Path) -> None:
    tmp_settings.intelligence.structure.enabled = False
    source = _write_source(tmp_path, "input.md", _fixture("nested_headings.md"))
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="markdown")

    assert "structure" not in result.document.metadata.extra


@pytest.mark.integration
def test_structure_absent_for_non_text_kind(tmp_settings: Settings, tmp_path: Path) -> None:
    source = _write_source(tmp_path, "data.csv", "a,b\n1,2\n")
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="csv")

    assert "structure" not in result.document.metadata.extra


@pytest.mark.integration
def test_analyzer_failure_contained_and_ingestion_continues(
    tmp_settings: Settings,
    tmp_path: Path,
) -> None:
    source = _write_source(tmp_path, "input.md", _fixture("nested_headings.md"))
    workflow = _production_workflow(tmp_settings)
    workflow._structure_analyzer = _RaisingAnalyzer()

    result = workflow.run(source, expected_source_type="markdown")

    assert "structure" not in result.document.metadata.extra
    assert result.note is not None


@pytest.mark.integration
def test_oversize_text_skipped_without_structure_key(
    tmp_settings: Settings,
    tmp_path: Path,
) -> None:
    source = _write_source(
        tmp_path,
        "big.md",
        "# Heading\n\n" + ("body line text\n" * (max_structure_text_bytes // 14 + 1)),
    )
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="markdown")

    assert len(result.document.text.encode("utf-8")) > max_structure_text_bytes
    assert "structure" not in result.document.metadata.extra


@pytest.mark.integration
def test_create_default_wires_structure_analyzer(tmp_settings: Settings) -> None:
    workflow = IngestionWorkflow.create_default(tmp_settings)

    assert isinstance(workflow._structure_analyzer, StructureAnalyzer)
    assert workflow._structure().enabled is True


@pytest.mark.integration
def test_create_default_disabled_still_wires_analyzer(tmp_settings: Settings) -> None:
    tmp_settings.intelligence.structure.enabled = False
    workflow = IngestionWorkflow.create_default(tmp_settings)

    assert isinstance(workflow._structure_analyzer, StructureAnalyzer)
    assert workflow._structure().enabled is False


def _analysis() -> DocumentAnalysis:
    return DocumentAnalysis.model_validate(
        {
            "suggested_note_title": "Structure Test",
            "summary": {
                "short": "Test summary.",
                "detailed": "Test detailed summary.",
            },
            "key_concepts": [
                {
                    "name": "Structure",
                    "explanation": "Test concept.",
                    "importance": "medium",
                }
            ],
            "definitions": [],
            "important_entities": [],
            "tags": ["structure"],
            "related_topics": [],
        }
    )
