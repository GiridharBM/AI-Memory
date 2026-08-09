"""Integration tests for Milestone 2.6 code/notebook pipeline (P2-606).

Frozen spec §4.6 / §13 integration row: real ``.py`` and ``.ipynb`` fixtures
through ``IngestionWorkflow`` asserting the attached structures, plus the
rollback contract (``code.enabled=false`` → no structure keys, matching the
pre-M2.6 passthrough). Marked integration so Ollama-free environments are
unaffected.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.application import AIProcessingResult
from app.core.config import Settings
from app.domain.analysis import DocumentAnalysis
from app.domain.documents import SourceDocument
from app.infrastructure.ingestion import DocumentIngestionService
from app.infrastructure.vault import VaultWriter
from app.pipelines import IngestionWorkflow
from app.templates import ObsidianMarkdownGenerator

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "code"


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


def _workflow(settings: Settings, tmp_path: Path) -> IngestionWorkflow:
    return IngestionWorkflow(
        ingestion_service=DocumentIngestionService(settings=settings),
        processor=_RecordingProcessor(),
        note_generator=ObsidianMarkdownGenerator(),
        writer=VaultWriter(tmp_path / "vault"),
        settings=settings,
    )


@pytest.mark.integration
def test_python_file_end_to_end(tmp_settings: Settings, tmp_path: Path) -> None:
    workflow = _workflow(tmp_settings, tmp_path)

    result = workflow.run(FIXTURES / "sample.py", expected_source_type="code")

    structure = result.document.metadata.extra["code_structure"]
    assert [imp["module"] for imp in structure["imports"]] == ["os", "pathlib"]
    assert [fn["name"] for fn in structure["functions"]] == ["greet"]
    assert [cls["name"] for cls in structure["classes"]] == ["Greeter"]


@pytest.mark.integration
def test_notebook_file_end_to_end(tmp_settings: Settings, tmp_path: Path) -> None:
    workflow = _workflow(tmp_settings, tmp_path)

    result = workflow.run(FIXTURES / "sample.ipynb", expected_source_type="notebook")

    structure = result.document.metadata.extra["notebook_structure"]
    assert [cell.type for cell in structure.cells] == ["markdown", "code"]
    assert structure.cells[1].outputs == ["42"]
    assert structure.kernel == "Python 3"
    assert structure.language == "python"


@pytest.mark.integration
def test_rollback_enabled_false(tmp_settings: Settings, tmp_path: Path) -> None:
    tmp_settings.intelligence.code.enabled = False
    workflow = _workflow(tmp_settings, tmp_path)

    code_result = workflow.run(FIXTURES / "sample.py", expected_source_type="code")
    notebook_result = workflow.run(
        FIXTURES / "sample.ipynb", expected_source_type="notebook"
    )

    # Pre-M2.6 passthrough: no structure keys on either document.
    assert "code_structure" not in code_result.document.metadata.extra
    assert "notebook_structure" not in notebook_result.document.metadata.extra


def _analysis() -> DocumentAnalysis:
    return DocumentAnalysis.model_validate(
        {
            "suggested_note_title": "Code Note",
            "summary": {"short": "s", "detailed": "d"},
            "key_concepts": [],
            "definitions": [],
            "important_entities": [],
            "tags": ["code"],
            "related_topics": [],
        }
    )
