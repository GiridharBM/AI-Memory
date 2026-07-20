"""Tests for the queue worker."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

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


def test_worker_processing_returns_false_when_empty(tmp_settings: "Settings") -> None:
    manager = QueueManager()
    worker = QueueWorker(manager, tmp_settings, workflow=EmptyWorkflow())

    assert not worker.process_next()


def test_worker_moves_unsupported_file_to_failed(tmp_settings: "Settings", tmp_path: Path) -> None:
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


def test_worker_handles_missing_source_without_crashing(tmp_settings: "Settings", tmp_path: Path) -> None:
    queue = QueueManager()
    source = tmp_path / "inbox" / "missing.md"
    item = QueueItem(path=source, extension=".md", created_at=datetime.now(UTC))
    queue.enqueue(item)
    worker = QueueWorker(queue, tmp_settings, workflow=EmptyWorkflow())

    assert worker.process_next()
    assert item.status == QueueStatus.FAILED
    assert queue.is_empty()
    assert not queue.is_queued(source)


# _settings removed: tests use shared tmp_settings fixture from conftest.py
