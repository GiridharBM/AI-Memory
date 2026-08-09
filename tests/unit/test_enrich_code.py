"""Unit tests for the P2-606 ``_enrich_code()`` enrichment hook (frozen §4.6).

Covers the frozen AC for P2-606: gating by ``intelligence.code.enabled`` and
``kind in {"code", "notebook"}``, structure attachment for code (parsed from
``document.text`` at parse time, capped at ``code.max_code_chars``), and the
notebook passthrough from ``NotebookIngestor`` (P2-605). Tests drive the real
``_run_routed_processor`` shared call site (P2-305) with the passthrough
``CodeProcessor``/``NotebookProcessor`` so the ``metadata.extra`` assertions
match the production flow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from app.core.config import Settings
from app.domain.document_intelligence import NotebookCell, NotebookStructure
from app.domain.documents import DocumentMetadata, SourceDocument
from app.pipelines.ingest_workflow import IngestionWorkflow

PY_SOURCE = (
    "import os\n"
    "\n"
    "\n"
    "def greet(name):\n"
    "    return f'Hello, {name}'\n"
    "\n"
    "\n"
    "class Greeter:\n"
    "    pass\n"
)


def _document(
    *,
    text: str,
    filename: str = "sample.py",
    kind: str = "code",
    extra: dict[str, Any] | None = None,
) -> SourceDocument:
    return SourceDocument(
        source=f"tests/fixtures/{filename}",
        source_path=Path(f"tests/fixtures/{filename}"),
        source_type=kind,
        filename=filename,
        text=text,
        metadata=DocumentMetadata(title="Doc", extra=extra or {}),
    )


def _workflow(settings: Settings | None = None) -> IngestionWorkflow:
    return IngestionWorkflow(
        ingestion_service=MagicMock(),
        ollama_client=MagicMock(),
        note_generator=MagicMock(),
        writer=MagicMock(),
        settings=settings,
    )


def _run_through_hook(
    workflow: IngestionWorkflow,
    document: SourceDocument,
    kind: str,
) -> dict[str, Any]:
    """Run *document* through the P2-305 shared hook and return metadata.extra."""
    processor_name = "CodeProcessor" if kind == "code" else "NotebookProcessor"
    enriched, _, _ = workflow._run_routed_processor(processor_name, document, kind=kind)
    return enriched.metadata.extra


class TestEnrichCodeHook:
    def test_skips_when_disabled(self, tmp_settings: Settings) -> None:
        tmp_settings.intelligence.code.enabled = False
        doc = _document(text=PY_SOURCE)
        workflow = _workflow(tmp_settings)

        assert _run_through_hook(workflow, doc, "code") == {}

    def test_skips_unknown_kind(self, tmp_settings: Settings) -> None:
        doc = _document(text="# not code\n", kind="markdown", filename="notes.md")
        workflow = _workflow(tmp_settings)

        assert _run_through_hook(workflow, doc, "markdown") == {}

    def test_attaches_python_structure(self, tmp_settings: Settings) -> None:
        doc = _document(text=PY_SOURCE, filename="greeter.py")
        workflow = _workflow(tmp_settings)

        extra = _run_through_hook(workflow, doc, "code")
        structure = extra["code_structure"]
        assert [imp["module"] for imp in structure["imports"]] == ["os"]
        assert [fn["name"] for fn in structure["functions"]] == ["greet"]
        assert [cls["name"] for cls in structure["classes"]] == ["Greeter"]

    def test_passes_notebook_structure(self, tmp_settings: Settings) -> None:
        structure = NotebookStructure(
            cells=[
                NotebookCell(
                    id="c0",
                    type="code",
                    source="x = 1",
                    outputs=["1"],
                    execution_count=1,
                )
            ]
        )
        doc = _document(
            text="x = 1\n",
            filename="nb.ipynb",
            kind="notebook",
            extra={"notebook_structure": structure},
        )
        workflow = _workflow(tmp_settings)

        extra = _run_through_hook(workflow, doc, "notebook")
        assert extra["notebook_structure"] is structure

    def test_notebook_rollback_drops_structure_when_disabled(
        self, tmp_settings: Settings
    ) -> None:
        tmp_settings.intelligence.code.enabled = False
        doc = _document(
            text="x = 1\n",
            filename="nb.ipynb",
            kind="notebook",
            extra={"notebook_structure": NotebookStructure(cells=[])},
        )
        workflow = _workflow(tmp_settings)

        assert _run_through_hook(workflow, doc, "notebook") == {}

    def test_max_code_chars_wired_from_config(self, tmp_settings: Settings) -> None:
        tmp_settings.intelligence.code.max_code_chars = 5
        doc = _document(text=PY_SOURCE, filename="greeter.py")
        workflow = _workflow(tmp_settings)

        extra = _run_through_hook(workflow, doc, "code")
        assert extra["code_structure"]["char_end"] == 5
