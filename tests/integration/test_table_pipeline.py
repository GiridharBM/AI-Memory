"""Integration tests for Milestone 2.4 table enrichment (P2-406).

Frozen spec §13 integration row: a CSV file through ``IngestionWorkflow``
asserting ``result.document.metadata.extra["tables"]`` deserializes to a
non-empty ``Table`` whose rendered Markdown lands in the note body;
``tables.enabled: false`` -> key absent; kinds outside the table-bearing set
(markdown/text) -> key absent; note body matches the golden CSV fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.application import AIProcessingResult
from app.core.config import Settings
from app.domain.analysis import DocumentAnalysis
from app.domain.document_intelligence import Table
from app.domain.documents import SourceDocument
from app.infrastructure.document_intelligence.tables.render import MarkdownTableRenderer
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


def _fixture(name: str) -> str:
    return (Path(__file__).resolve().parents[1] / "fixtures" / "tables" / name).read_text(
        encoding="utf-8"
    )


def _write_source(tmp_path: Path, filename: str, text: str) -> Path:
    source = tmp_path / filename
    source.write_text(text, encoding="utf-8")
    return source


def _tables_of(result: IngestionWorkflowResult) -> list[Table]:
    raw = result.document.metadata.extra["tables"]
    return [Table.model_validate(item) for item in raw]


def _expected_golden_markdown() -> str:
    table = Table.model_validate(
        {
            "title": "people.csv",
            "header": {
                "cells": [
                    {"value": "name"},
                    {"value": "age"},
                    {"value": "city"},
                ]
            },
            "rows": [
                {
                    "cells": [
                        {"value": "Alice"},
                        {"value": "30"},
                        {"value": "Springfield"},
                    ]
                },
                {
                    "cells": [
                        {"value": "Bob"},
                        {"value": "25"},
                        {"value": "Shelbyville"},
                    ]
                },
                {
                    "cells": [
                        {"value": "Carol"},
                        {"value": "40"},
                        {"value": "Capital City"},
                    ]
                },
            ],
            "source_position": "line 1",
        }
    )
    return MarkdownTableRenderer().to_markdown(table)


@pytest.mark.integration
def test_csv_file_enriched_with_tables(tmp_settings: Settings, tmp_path: Path) -> None:
    source = _write_source(tmp_path, "people.csv", _fixture("people.csv"))
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="csv")

    tables = _tables_of(result)
    assert len(tables) == 1
    assert tables[0].title == "people.csv"
    assert [c.value for c in tables[0].header.cells] == ["name", "age", "city"]
    assert tables[0].source_position == "line 1"


@pytest.mark.integration
def test_csv_tables_render_into_note_body(tmp_settings: Settings, tmp_path: Path) -> None:
    source = _write_source(tmp_path, "people.csv", _fixture("people.csv"))
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="csv")

    expected = _expected_golden_markdown()
    assert result.note is not None
    assert "## Tables" in result.note.markdown
    assert expected in result.note.markdown


@pytest.mark.integration
def test_tables_absent_when_disabled(tmp_settings: Settings, tmp_path: Path) -> None:
    tmp_settings.intelligence.tables.enabled = False
    source = _write_source(tmp_path, "people.csv", _fixture("people.csv"))
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="csv")

    assert "tables" not in result.document.metadata.extra
    assert result.note is not None
    assert "## Tables" not in result.note.markdown


@pytest.mark.integration
def test_tables_absent_for_non_table_kind(tmp_settings: Settings, tmp_path: Path) -> None:
    source = _write_source(tmp_path, "plain.md", "# Heading\n\nBody.\n")
    workflow = _production_workflow(tmp_settings)

    result = workflow.run(source, expected_source_type="markdown")

    assert "tables" not in result.document.metadata.extra
    assert result.note is not None
    assert "## Tables" not in result.note.markdown


@pytest.mark.integration
def test_create_default_wires_table_extractor(tmp_settings: Settings) -> None:
    workflow = IngestionWorkflow.create_default(tmp_settings)

    assert workflow._tables().enabled is True


@pytest.mark.integration
def test_create_default_disabled_still_wires_extractor(tmp_settings: Settings) -> None:
    tmp_settings.intelligence.tables.enabled = False
    workflow = IngestionWorkflow.create_default(tmp_settings)

    assert workflow._tables().enabled is False


def _analysis() -> DocumentAnalysis:
    return DocumentAnalysis.model_validate(
        {
            "suggested_note_title": "People Table",
            "summary": {
                "short": "A table of people.",
                "detailed": "A table of people with name, age, and city.",
            },
            "key_concepts": [],
            "definitions": [],
            "important_entities": [],
            "tags": ["table"],
            "related_topics": [],
        }
    )
