"""Tests for V1.1-A2 CLI ingestion UX hardening.

These tests fake ``IngestionWorkflow`` and drive the Typer ``ingest file``
command with a temp-referenced manifest, so they never touch the real vault,
corpus, Ollama, or vector store.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from app.cli import entry
from app.domain.documents import DocumentMetadata, SourceDocument
from app.domain.notes import ObsidianNote
from app.infrastructure.state.manifest import ManifestManager
from app.infrastructure.vault import WikiUpdateResult
from app.infrastructure.vector_store import VectorStore
from app.pipelines.ingest_workflow import IngestionWorkflow

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


class _ReRunWorkflow(_SuccessWorkflow):
    """Counts runs so a re-ingest cannot silently skip the workflow."""

    calls = 0

    def run(self, source_arg: str | Path, **_: object) -> SimpleNamespace:
        type(self).calls += 1
        return super().run(source_arg)


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


# ── V1.1.1 D5: unreadable index fails closed with a truthful panel ─────────


def test_unreadable_index_panel_is_not_a_security_or_retry_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _write_source(tmp_path)
    monkeypatch.setattr(entry, "IngestionWorkflow", _FailingWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _FailingWorkflow.error = entry.IngestionWorkflowError(
        "The existing index could not be read.", category="unreadable_state"
    )

    result = _invoke(source, _FailingWorkflow)

    assert result.exit_code == 1
    out = result.output
    assert "Index unreadable" in out
    assert "nothing ingested" in out
    # must not be mislabelled as a security block or a transient retry failure
    assert "Ingest blocked" not in out
    assert "Ollama offline" not in out
    assert "Traceback" not in out


def test_corrupt_vector_store_exits_one_and_preserves_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end through the real IngestionWorkflow guard: a corrupt store
    must abort before any write and leave the file byte-identical."""
    source = _write_source(tmp_path)
    _set_manifest(tmp_path, monkeypatch)
    vpath = tmp_path / "vector_store.json"
    corrupt = b'{"entries": [ broken'
    vpath.write_bytes(corrupt)

    workflow = IngestionWorkflow(
        ingestion_service=MagicMock(),
        processor=MagicMock(),
        ollama_client=MagicMock(),
        note_generator=MagicMock(),
        writer=MagicMock(),
        chunker=MagicMock(),
        embedding_service=MagicMock(),
        vector_store=VectorStore(persistence_path=vpath),
        knowledge_graph_builder=MagicMock(),
    )
    monkeypatch.setattr(
        entry, "IngestionWorkflow", MagicMock(create_default=MagicMock(return_value=workflow))
    )

    result = _invoke(source, entry.IngestionWorkflow)

    assert result.exit_code == 1
    assert "Index unreadable" in result.output
    assert "Traceback" not in result.output
    assert vpath.read_bytes() == corrupt
    assert list(tmp_path.glob("*.tmp")) == []
    workflow._writer.save.assert_not_called()
    workflow._writer.create_placeholder.assert_not_called()
    workflow._ingestion_service.ingest.assert_not_called()


# -- V1.1.1 D3: a failed non-hashable source stays retryable ---------------
# A previous failed entry must not turn a re-drop into ``skipped_duplicate``.


def test_failed_url_retries_instead_of_duplicate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    url = "https://github.com/example/pam"
    monkeypatch.setattr(entry, "IngestionWorkflow", _FailingWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _FailingWorkflow.error = OSError("host unreachable")

    first = runner.invoke(entry.cli, ["ingest", "github", url])
    assert first.exit_code == 1
    assert "skipped" not in first.output.lower()

    monkeypatch.setattr(entry, "IngestionWorkflow", _SuccessWorkflow)
    _SuccessWorkflow.path = tmp_path
    second = runner.invoke(entry.cli, ["ingest", "github", url])

    assert second.exit_code == 0
    assert "Ingest skipped (duplicate)" not in second.output
    assert "Ingestion Complete" in second.output


def test_failed_unsupported_source_retries_instead_of_duplicate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _write_source(tmp_path, name="weird.xyz")
    monkeypatch.setattr(entry, "IngestionWorkflow", _FailingWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _FailingWorkflow.error = entry.IngestionWorkflowError(
        "Unsupported source type for 'weird.xyz'.", category="unsupported"
    )

    first = _invoke(source, _FailingWorkflow)
    assert first.exit_code == 1
    assert "Ingest skipped (duplicate)" not in first.output

    monkeypatch.setattr(entry, "IngestionWorkflow", _SuccessWorkflow)
    _SuccessWorkflow.path = tmp_path
    second = _invoke(source, _SuccessWorkflow)

    assert second.exit_code == 0
    assert "Ingest skipped (duplicate)" not in second.output
    assert "Ingestion Complete" in second.output


def test_retry_after_failure_stays_append_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The old failed row survives; the retry adds a new row beside it."""
    source = _write_source(tmp_path, name="weird.xyz")
    monkeypatch.setattr(entry, "IngestionWorkflow", _FailingWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _FailingWorkflow.error = entry.IngestionWorkflowError(
        "Unsupported source type for 'weird.xyz'.", category="unsupported"
    )
    assert _invoke(source, _FailingWorkflow).exit_code == 1

    monkeypatch.setattr(entry, "IngestionWorkflow", _SuccessWorkflow)
    _SuccessWorkflow.path = tmp_path
    assert _invoke(source, _SuccessWorkflow).exit_code == 0

    manager = ManifestManager(_manifest(tmp_path), project_root=tmp_path)
    entries = manager.list_entries()
    assert [e.status for e in entries] == ["failed", "processed"]
    # The original failure is neither rewritten nor superseded.
    assert entries[0].error_reason == (
        "IngestionWorkflowError: Unsupported source type for 'weird.xyz'."
    )


def test_processed_non_hashable_source_still_duplicate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Successful duplicate protection must be unchanged by the D3 fix."""
    source = _write_source(tmp_path, name="weird.xyz")
    monkeypatch.setattr(entry, "IngestionWorkflow", _SuccessWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _SuccessWorkflow.path = tmp_path
    assert _invoke(source, _SuccessWorkflow).exit_code == 0

    monkeypatch.setattr(entry, "IngestionWorkflow", _DuplicateWorkflow)
    second = _invoke(source, _DuplicateWorkflow)

    assert second.exit_code == 0
    assert "Ingest skipped (duplicate)" in second.output
    assert "already recorded" in second.output


def test_skipped_duplicate_non_hashable_source_stays_duplicate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A prior ``skipped_duplicate`` path is a successful status: still protected."""
    source = _write_source(tmp_path, name="weird.xyz")
    monkeypatch.setattr(entry, "IngestionWorkflow", _SuccessWorkflow)
    _set_manifest(tmp_path, monkeypatch)
    _SuccessWorkflow.path = tmp_path
    assert _invoke(source, _SuccessWorkflow).exit_code == 0

    monkeypatch.setattr(entry, "IngestionWorkflow", _DuplicateWorkflow)
    assert _invoke(source, _DuplicateWorkflow).exit_code == 0

    manager = ManifestManager(_manifest(tmp_path), project_root=tmp_path)
    assert [e.status for e in manager.list_entries()] == ["processed", "skipped_duplicate"]

    # A third drop short-circuits on the successful path entry, not the failed one.
    third = _invoke(source, _DuplicateWorkflow)

    assert third.exit_code == 0
    assert "Ingest skipped (duplicate)" in third.output


# ── V1.1.1 D3-C: exact URLs are CWD-independent ──────────────────────────


def _legacy_url_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, url: str, *, status: str
) -> str:
    """Seed a historical CWD-mangled URL row without rewriting it later."""
    legacy_directory = tmp_path / "legacy-cwd"
    legacy_directory.mkdir(exist_ok=True)
    manager = ManifestManager(_manifest(tmp_path), project_root=tmp_path)
    monkeypatch.chdir(legacy_directory)
    if status == "failed":
        manager.add_failed_file(
            path=Path(url), sha256="", extension="", error_reason="OSError: old failure"
        )
    else:
        manager.add_processed_file(path=Path(url), sha256="", extension="", status=status)
    manager.save()
    return manager.list_entries()[-1].original_path


def test_successful_url_from_another_cwd_is_duplicate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    url = "https://github.com/example/pam"
    _set_manifest(tmp_path, monkeypatch)
    legacy_path = _legacy_url_row(tmp_path, monkeypatch, url, status="processed")
    retry_directory = tmp_path / "retry-cwd"
    retry_directory.mkdir()

    monkeypatch.chdir(retry_directory)
    monkeypatch.setattr(entry, "IngestionWorkflow", _DuplicateWorkflow)
    result = runner.invoke(entry.cli, ["ingest", "github", url])

    assert result.exit_code == 0
    assert "Ingest skipped (duplicate)" in result.output
    manager = ManifestManager(_manifest(tmp_path), project_root=tmp_path)
    entries = manager.list_entries()
    assert [entry.status for entry in entries] == ["processed", "skipped_duplicate"]
    assert entries[0].original_path == legacy_path
    assert entries[1].original_path == url


def test_failed_url_retry_from_another_cwd_uses_exact_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    url = "https://github.com/example/pam"
    _set_manifest(tmp_path, monkeypatch)
    _legacy_url_row(tmp_path, monkeypatch, url, status="failed")
    retry_directory = tmp_path / "retry-cwd"
    retry_directory.mkdir()
    monkeypatch.setenv("COLUMNS", "220")

    monkeypatch.chdir(retry_directory)
    monkeypatch.setattr(entry, "IngestionWorkflow", _FailingWorkflow)
    _FailingWorkflow.error = OSError("host unreachable")
    result = runner.invoke(entry.cli, ["ingest", "github", url])

    assert result.exit_code == 1
    assert "Ingest skipped (duplicate)" not in result.output
    manager = ManifestManager(_manifest(tmp_path), project_root=tmp_path)
    entries = manager.list_entries()
    assert [entry.status for entry in entries] == ["failed", "failed"]
    assert entries[1].original_path == url

    failed_listing = runner.invoke(entry.cli, ["sources", "--failed"])
    assert failed_listing.exit_code == 0
    assert failed_listing.output.count(url) == 1


def test_url_variants_remain_distinct_identities(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base_url = "https://github.com/o/r"
    slashed_url = "https://github.com/o/r/"
    watch_url = "https://www.youtube.com/watch?v=ID"
    short_url = "https://youtu.be/ID"
    _set_manifest(tmp_path, monkeypatch)
    monkeypatch.setattr(entry, "IngestionWorkflow", _SuccessWorkflow)
    _SuccessWorkflow.path = tmp_path

    assert runner.invoke(entry.cli, ["ingest", "github", base_url]).exit_code == 0
    assert runner.invoke(entry.cli, ["ingest", "github", slashed_url]).exit_code == 0

    manager = ManifestManager(_manifest(tmp_path), project_root=tmp_path)
    assert [entry.status for entry in manager.list_entries()] == ["processed", "processed"]
    assert [entry.original_path for entry in manager.list_entries()] == [
        base_url,
        slashed_url,
    ]
    assert manager.contains_successful_url(base_url) is True
    assert manager.contains_successful_url(slashed_url) is True
    assert manager.contains_successful_url(watch_url) is False
    assert manager.contains_successful_url(short_url) is False


def test_url_ingest_remove_reingest_runs_ingestion_again(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    url = "https://github.com/o/r"
    _set_manifest(tmp_path, monkeypatch)
    # Point remove at the same isolated stores: it must never read or write
    # the real vector store or knowledge graph.
    monkeypatch.setattr(entry, "setup_logging", lambda _settings: None)
    monkeypatch.setattr(
        entry,
        "_load_configured_settings",
        lambda **_: SimpleNamespace(
            paths=SimpleNamespace(
                manifest_root=tmp_path / "manifests",
                project_root=tmp_path,
            ),
            manifest=SimpleNamespace(path=_manifest(tmp_path), enabled=True),
        ),
    )
    monkeypatch.setattr(entry, "IngestionWorkflow", _SuccessWorkflow)
    _SuccessWorkflow.path = tmp_path

    assert runner.invoke(entry.cli, ["ingest", "github", url]).exit_code == 0
    assert runner.invoke(entry.cli, ["remove", url]).exit_code == 0
    manager = ManifestManager(_manifest(tmp_path), project_root=tmp_path)
    assert manager.contains_successful_url(url) is False

    # The removed URL is no longer a duplicate, so a fresh ingest must run.
    monkeypatch.setattr(entry, "IngestionWorkflow", _ReRunWorkflow)
    reingest = runner.invoke(entry.cli, ["ingest", "github", url])

    assert reingest.exit_code == 0
    assert _ReRunWorkflow.calls == 1


def test_url_identity_ignores_surrounding_whitespace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    url = "https://github.com/o/r"
    _set_manifest(tmp_path, monkeypatch)
    _SuccessWorkflow.path = tmp_path

    monkeypatch.setattr(entry, "IngestionWorkflow", _SuccessWorkflow)
    assert runner.invoke(entry.cli, ["ingest", "github", f"  {url}  "]).exit_code == 0
    monkeypatch.setattr(entry, "IngestionWorkflow", _DuplicateWorkflow)
    second = runner.invoke(entry.cli, ["ingest", "github", url])

    assert second.exit_code == 0
    assert "Ingest skipped (duplicate)" in second.output
    manager = ManifestManager(_manifest(tmp_path), project_root=tmp_path)
    assert manager.list_entries()
    assert {entry.original_path for entry in manager.list_entries()} == {url}
    assert manager.contains_successful_url(url) is True


def test_same_absolute_local_file_from_another_cwd_is_duplicate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _write_source(tmp_path)
    first_directory = tmp_path / "first-cwd"
    second_directory = tmp_path / "second-cwd"
    first_directory.mkdir()
    second_directory.mkdir()
    _set_manifest(tmp_path, monkeypatch)

    monkeypatch.chdir(first_directory)
    monkeypatch.setattr(entry, "IngestionWorkflow", _SuccessWorkflow)
    _SuccessWorkflow.path = tmp_path
    assert _invoke(source, _SuccessWorkflow).exit_code == 0

    monkeypatch.chdir(second_directory)
    monkeypatch.setattr(entry, "IngestionWorkflow", _DuplicateWorkflow)
    second = _invoke(source, _DuplicateWorkflow)

    assert second.exit_code == 0
    assert "Ingest skipped (duplicate)" in second.output
