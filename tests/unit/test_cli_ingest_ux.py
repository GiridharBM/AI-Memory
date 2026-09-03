"""Tests for V1.1-A2 CLI ingestion UX hardening.

These tests fake ``IngestionWorkflow`` and drive the Typer ``ingest file``
command with a temp-referenced manifest, so they never touch the real vault,
corpus, Ollama, or vector store.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from app.cli import entry
from app.domain.documents import DocumentMetadata, SourceDocument
from app.domain.notes import ObsidianNote
from app.infrastructure.state.manifest import ManifestManager
from app.infrastructure.vault import WikiUpdateResult

runner = CliRunner()


def _manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "manifests" / "processed.json"
    return manifest_path


def _write_source(tmp_path: Path, name: str = "note.md") -> Path:
    source = tmp_path / name
    source.write_text("# Note", encoding="utf-8")
    return source


def _result(tmp_path: Path, **overrides: object) -> SimpleNamespace:
    generated_at = datetime(2026, 7, 8, tzinfo=UTC)
    document = SourceDocument(
        source="note.md",
        source_type="markdown",
        filename="note.md",
        text="# Note",
        metadata=DocumentMetadata(title="Note"),
    )
    note = ObsidianNote(
        title="Local AI Memory",
        filename="Local AI Memory.md",
        markdown="# Local AI Memory",
        generated_at=generated_at,
        tags=["local-ai"],
        source="note.md",
        source_type="markdown",
    )
    write_result = WikiUpdateResult(
        note_path=tmp_path / "vault" / "Notes" / "Local AI Memory.md",
        created=True,
        updated=False,
        index_path=tmp_path / "vault" / "index.md",
        overview_path=tmp_path / "vault" / "overview.md",
        log_path=tmp_path / "vault" / "log.md",
    )
    ai_result = SimpleNamespace(document=document, analysis=SimpleNamespace(), attempts=1)
    base = SimpleNamespace(
        document=document,
        ai_result=ai_result,
        note=note,
        write_result=write_result,
    )
    return SimpleNamespace(**{**vars(base), **overrides})


def _invoke(source: Path, workflow_cls: type) -> object:
    return runner.invoke(
        entry.cli,
        ["ingest", "file", str(source)],
    )


class _SuccessWorkflow:
    path: Path | None = None

    @classmethod
    def create_default(cls, settings: object, **_: object) -> _SuccessWorkflow:
        return cls()

    def run(self, source_arg: str | Path, **_: object) -> SimpleNamespace:
        cls = type(self)
        return _result(cls.path)


class _DuplicateWorkflow(_SuccessWorkflow):
    def run(self, source_arg: str | Path, **_: object) -> SimpleNamespace:
        raise AssertionError("workflow must not run for a duplicate")


class _FailingWorkflow(_SuccessWorkflow):
    error: Exception | None = None

    def run(self, source_arg: str | Path, **_: object) -> SimpleNamespace:
        raise type(self).error


class _PartialIndexWorkflow(_SuccessWorkflow):
    def run(self, source_arg: str | Path, **_: object) -> SimpleNamespace:
        cls = type(self)
        return _result(
            cls.path,
            embedding_succeeded=False,
            indexing_succeeded=False,
            engine_error="index backend down",
        )


class _KGFailWorkflow(_SuccessWorkflow):
    def run(self, source_arg: str | Path, **_: object) -> SimpleNamespace:
        cls = type(self)
        return _result(cls.path, graph_succeeded=False, chunks_stored=3)


def _set_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAM_MANIFEST__PATH", str(_manifest(tmp_path)))


def test_success_exit_zero_and_truthful_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _write_source(tmp_path)
    monkeypatch.setattr(entry, "IngestionWorkflow", _SuccessWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _SuccessWorkflow.path = tmp_path

    result = _invoke(source, _SuccessWorkflow)

    assert result.exit_code == 0
    out = result.output
    assert "Ingestion Complete" in out
    assert "Source" in out
    assert "Source type" in out
    assert "markdown" in out
    assert "Chunks indexed" in out
    assert "Indexed" in out
    assert "Processing failed" not in out


def test_duplicate_skips_workflow_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _write_source(tmp_path)
    monkeypatch.setattr(entry, "IngestionWorkflow", _DuplicateWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _SuccessWorkflow.path = tmp_path

    # First ingest succeeds so the duplicate hash exists.
    monkeypatch.setattr(entry, "IngestionWorkflow", _SuccessWorkflow)
    first = _invoke(source, _SuccessWorkflow)
    assert first.exit_code == 0

    # Second ingest is a duplicate: workflow must not run.
    monkeypatch.setattr(entry, "IngestionWorkflow", _DuplicateWorkflow)
    second = _invoke(source, _DuplicateWorkflow)

    assert second.exit_code == 0
    assert "Ingest skipped (duplicate)" in second.output
    assert "untouched" in second.output
    assert "Processing failed" not in second.output


def test_duplicate_records_skipped_duplicate_in_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _write_source(tmp_path)
    monkeypatch.setattr(entry, "IngestionWorkflow", _SuccessWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _SuccessWorkflow.path = tmp_path

    _invoke(source, _SuccessWorkflow)
    _invoke(source, _DuplicateWorkflow)

    manager = ManifestManager(_manifest(tmp_path), project_root=tmp_path)
    assert [e.status for e in manager.list_entries()] == ["processed", "skipped_duplicate"]


def test_blocked_secret_surfaces_truthful_panel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _write_source(tmp_path, name=".env")
    monkeypatch.setattr(entry, "IngestionWorkflow", _FailingWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _FailingWorkflow.error = entry.IngestionWorkflowError(
        "Source 'x' is blocked: it appears to be a secret-bearing or credential file.",
        category="blocked",
    )

    result = _invoke(source, _FailingWorkflow)

    assert result.exit_code == 1
    out = result.output
    assert "Ingest blocked (security)" in out
    assert "not read and no contents were indexed" in out
    assert "Processing failed" not in out


def test_unsupported_source_surfaces_panel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _write_source(tmp_path, name="weird.xyz")
    monkeypatch.setattr(entry, "IngestionWorkflow", _FailingWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _FailingWorkflow.error = entry.IngestionWorkflowError(
        "Unsupported source type for 'weird.xyz'.", category="unsupported"
    )

    result = _invoke(source, _FailingWorkflow)

    assert result.exit_code == 1
    assert "Unsupported source" in result.output
    assert "supported file type" in result.output


def test_generic_failure_keeps_processing_failed_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _write_source(tmp_path)
    monkeypatch.setattr(entry, "IngestionWorkflow", _FailingWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _FailingWorkflow.error = entry.IngestionWorkflowError("unsupported content")

    result = _invoke(source, _FailingWorkflow)

    assert result.exit_code == 1
    assert "Processing failed" in result.output
    assert "retry" in result.output


def test_generic_failure_records_ledger_and_error_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _write_source(tmp_path)
    monkeypatch.setattr(entry, "IngestionWorkflow", _FailingWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _FailingWorkflow.error = entry.IngestionWorkflowError("boom", category="ingestion")

    _invoke(source, _FailingWorkflow)

    manager = ManifestManager(_manifest(tmp_path), project_root=tmp_path)
    assert manager.count() == 1
    failed = manager.list_entries()[0]
    assert failed.status == "failed"
    assert "IngestionWorkflowError" in failed.error_reason
    assert "boom" in failed.error_reason


def test_partial_index_failure_exits_one_and_not_complete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _write_source(tmp_path)
    monkeypatch.setattr(entry, "IngestionWorkflow", _PartialIndexWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _PartialIndexWorkflow.path = tmp_path

    result = _invoke(source, _PartialIndexWorkflow)

    assert result.exit_code == 1
    out = result.output
    assert "Ingestion incomplete" in out
    assert "not fully indexed" in out
    assert "retry" in out
    assert "Ingestion Complete" not in out


def test_partial_index_failure_records_failed_in_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _write_source(tmp_path)
    monkeypatch.setattr(entry, "IngestionWorkflow", _PartialIndexWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _PartialIndexWorkflow.path = tmp_path

    _invoke(source, _PartialIndexWorkflow)

    manager = ManifestManager(_manifest(tmp_path), project_root=tmp_path)
    failed = manager.list_entries()[0]
    assert failed.status == "failed"
    assert failed.indexing_succeeded is False
    assert failed.error_reason == "index backend down"


def test_kg_failure_warns_but_exits_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _write_source(tmp_path)
    monkeypatch.setattr(entry, "IngestionWorkflow", _KGFailWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _KGFailWorkflow.path = tmp_path

    result = _invoke(source, _KGFailWorkflow)

    assert result.exit_code == 0
    assert "Knowledge graph warning" in result.output
    assert "Ingestion Complete" in result.output
    assert "Indexed" in result.output


def test_unexpected_exception_has_no_traceback_leak(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _write_source(tmp_path)
    monkeypatch.setattr(entry, "IngestionWorkflow", _FailingWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _FailingWorkflow.error = RuntimeError("internal boom")

    result = _invoke(source, _FailingWorkflow)

    assert result.exit_code == 1
    assert "Processing failed" in result.output
    assert "Traceback" not in result.output
    assert "internal boom" in result.output


def test_missing_source_rejected_by_typer() -> None:
    result = runner.invoke(entry.cli, ["ingest", "file", "C:\\__no_such_a2_file__.md"])
    assert result.exit_code != 0
    assert "does not exist" in result.output
