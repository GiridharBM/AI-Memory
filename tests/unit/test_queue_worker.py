"""Tests for the queue worker."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.domain.documents import DocumentMetadata, SourceDocument
from app.domain.notes import ObsidianNote
from app.infrastructure.state.manifest import ManifestManager
from app.infrastructure.vault.wiki_manager import WikiUpdateResult
from app.pipelines import IngestionWorkflowResult
from app.queue import QueueItem, QueueManager, QueueStatus, QueueWorker


class EmptyWorkflow:
    def run(
        self,
        source: str | Path,
        *,
        expected_source_type: str | None = None,
    ) -> IngestionWorkflowResult:
        raise AssertionError("Workflow should not run for this test.")


class SuccessfulWorkflow:
    def run(
        self,
        source: str | Path,
        *,
        expected_source_type: str | None = None,
    ) -> IngestionWorkflowResult:
        return IngestionWorkflowResult(
            document=SourceDocument(
                source=str(source),
                source_path=None,
                source_type="markdown",
                filename=Path(source).name,
                text="x",
                metadata=DocumentMetadata(),
            ),
            ai_result=MagicMock(),
            note=ObsidianNote(
                title="Note",
                filename="note.md",
                source=str(source),
                markdown="# Note",
                generated_at=datetime.now(UTC),
                source_type="markdown",
            ),
            write_result=WikiUpdateResult(
                note_path=Path("note.md"),
                created=True,
                updated=False,
                index_path=Path("index.md"),
                overview_path=Path("overview.md"),
                log_path=Path("log.md"),
            ),
        )


def test_worker_processing_returns_false_when_empty(tmp_settings: Settings) -> None:
    manager = QueueManager()
    worker = QueueWorker(manager, tmp_settings, workflow=EmptyWorkflow())

    assert not worker.process_next()


def test_worker_moves_unsupported_file_to_failed(tmp_settings: Settings, tmp_path: Path) -> None:
    queue = QueueManager()
    source = tmp_path / "inbox" / "data.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("a,b", encoding="utf-8")
    item = QueueItem(path=source, extension=".csv", created_at=datetime.now(UTC))
    queue.enqueue(item)

    worker = QueueWorker(queue, tmp_settings, workflow=EmptyWorkflow())

    assert worker.process_next()
    assert item.status == QueueStatus.FAILED
    assert not source.exists()
    assert (tmp_path / "failed" / "data.csv").exists()
    assert queue.is_empty()


def test_worker_handles_missing_source_without_crashing(
    tmp_settings: Settings, tmp_path: Path
) -> None:
    queue = QueueManager()
    source = tmp_path / "inbox" / "missing.md"
    item = QueueItem(path=source, extension=".md", created_at=datetime.now(UTC))
    queue.enqueue(item)
    worker = QueueWorker(queue, tmp_settings, workflow=EmptyWorkflow())

    assert worker.process_next()
    assert item.status == QueueStatus.FAILED
    assert queue.is_empty()
    assert not queue.is_queued(source)


def test_worker_rejects_unsupported_extension(tmp_settings: Settings, tmp_path: Path) -> None:
    queue = QueueManager()
    source = tmp_path / "inbox" / "data.xyz"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("unexpected", encoding="utf-8")
    item = QueueItem(path=source, extension=".xyz", created_at=datetime.now(UTC))
    queue.enqueue(item)

    worker = QueueWorker(queue, tmp_settings, workflow=EmptyWorkflow())

    assert worker.process_next()
    assert item.status == QueueStatus.FAILED
    assert not source.exists()
    assert (tmp_path / "failed" / "data.xyz").exists()
    assert queue.is_empty()


def test_worker_manifest_save_failure_keeps_item_done(
    tmp_settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = QueueManager()
    source = tmp_path / "inbox" / "note.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Note", encoding="utf-8")
    item = QueueItem(path=source, extension=".md", created_at=datetime.now(UTC))
    queue.enqueue(item)

    worker = QueueWorker(queue, tmp_settings, workflow=SuccessfulWorkflow())

    def fail_save() -> None:
        raise OSError("disk full")

    monkeypatch.setattr(worker.manifest_manager, "save", fail_save)

    assert worker.process_next()
    # A failed manifest write must not strand the file: it is already in
    # processed/ and the note is written, so the item stays DONE and the
    # in-memory record keeps dedup working for the session.
    assert item.status == QueueStatus.DONE
    assert worker.manifest_manager.count() == 1
    assert not source.exists()
    assert (tmp_path / "processed" / "note.md").exists()
    assert queue.is_empty()


def test_worker_move_failure_does_not_record_manifest(
    tmp_settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = QueueManager()
    source = tmp_path / "inbox" / "note.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Note", encoding="utf-8")
    item = QueueItem(path=source, extension=".md", created_at=datetime.now(UTC))
    queue.enqueue(item)

    worker = QueueWorker(queue, tmp_settings, workflow=SuccessfulWorkflow())

    def fail_move(_source_path: Path) -> Path:
        raise OSError("move failed")

    monkeypatch.setattr(worker, "_move_to_processed", fail_move)

    assert worker.process_next()
    # The file must be recorded as processed only after a successful move; a
    # failed move must leave the manifest untouched so the file can be retried.
    assert item.status == QueueStatus.FAILED
    assert worker.manifest_manager.count() == 0
    assert (tmp_path / "failed" / "note.md").exists()
    assert queue.is_empty()


# ── Phase 6A: durable ledger + retry semantics ─────────────────────────


def test_worker_retries_file_after_failed_ledger_entry(
    tmp_settings: Settings, tmp_path: Path,
) -> None:
    """A failed ledger entry must not block re-processing the same file."""
    queue = QueueManager()
    source = tmp_path / "inbox" / "note.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Note", encoding="utf-8")

    seeded = ManifestManager(tmp_settings.manifest.path, project_root=tmp_path)
    digest = seeded.hash_for_path(source)
    seeded.add_failed_file(path=source, sha256=digest, extension=".md", error_reason="previous")
    seeded.save()

    item = QueueItem(path=source, extension=".md", created_at=datetime.now(UTC))
    queue.enqueue(item)
    runs: list[str | Path] = []

    class RetryWorkflow(SuccessfulWorkflow):
        def run(
            self,
            source_arg: str | Path,
            *,
            expected_source_type: str | None = None,
        ) -> IngestionWorkflowResult:
            runs.append(source_arg)
            return super().run(source_arg, expected_source_type=expected_source_type)

    worker = QueueWorker(queue, tmp_settings, workflow=RetryWorkflow())

    assert worker.process_next()
    assert len(runs) == 1  # workflow ran despite the failed ledger entry
    assert item.status == QueueStatus.DONE
    assert (tmp_path / "processed" / "note.md").exists()
    assert worker.manifest_manager.count() == 2  # previous failure + new success


def test_worker_records_skipped_duplicate_in_ledger(
    tmp_settings: Settings, tmp_path: Path,
) -> None:
    """A re-dropped, already-processed file is skipped and recorded as such."""
    queue = QueueManager()
    source = tmp_path / "inbox" / "note.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Note", encoding="utf-8")

    seeded = ManifestManager(tmp_settings.manifest.path, project_root=tmp_path)
    digest = seeded.hash_for_path(source)
    seeded.add_processed_file(path=source, sha256=digest, extension=".md")
    seeded.save()

    item = QueueItem(path=source, extension=".md", created_at=datetime.now(UTC))
    queue.enqueue(item)
    worker = QueueWorker(queue, tmp_settings, workflow=EmptyWorkflow())

    assert worker.process_next()
    assert item.status == QueueStatus.DONE
    entries = worker.manifest_manager.list_entries()
    assert len(entries) == 2
    assert entries[1].status == "skipped_duplicate"
    assert worker.manifest_manager.contains_successful_hash(digest)


def test_worker_fails_item_when_note_written_but_not_indexed(
    tmp_settings: Settings, tmp_path: Path,
) -> None:
    """A note written without embedding/indexing is a retryable failure."""
    queue = QueueManager()
    source = tmp_path / "inbox" / "note.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Note", encoding="utf-8")
    item = QueueItem(path=source, extension=".md", created_at=datetime.now(UTC))
    queue.enqueue(item)

    class NotIndexedWorkflow(SuccessfulWorkflow):
        def run(
            self,
            source_arg: str | Path,
            *,
            expected_source_type: str | None = None,
        ) -> IngestionWorkflowResult:
            result = super().run(source_arg, expected_source_type=expected_source_type)
            return replace(
                result,
                embedding_succeeded=False,
                indexing_succeeded=False,
                engine_error="embedding failed",
            )

    worker = QueueWorker(queue, tmp_settings, workflow=NotIndexedWorkflow())

    assert worker.process_next()
    assert item.status == QueueStatus.FAILED
    assert (tmp_path / "failed" / "note.md").exists()
    assert not (tmp_path / "processed" / "note.md").exists()
    entry = worker.manifest_manager.list_entries()[0]
    assert entry.status == "failed"
    assert "EMBEDDING/INDEXING FAILURE" in entry.error_reason
    assert not worker.manifest_manager.contains_successful_hash(entry.sha256)


# _settings removed: tests use shared tmp_settings fixture from conftest.py
