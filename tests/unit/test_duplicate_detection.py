"""Tests for duplicate detection in the worker."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.infrastructure.state.manifest import ManifestManager
from app.pipelines import IngestionWorkflowResult
from app.queue import QueueItem, QueueManager, QueueStatus, QueueWorker


class DuplicateWorkflow:
    def run(
        self,
        source: str | Path,
        *,
        expected_source_type: str | None = None,
    ) -> IngestionWorkflowResult:
        raise AssertionError("Duplicate files must not reach the workflow.")


def test_duplicate_skip(
    tmp_settings: Settings,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager = ManifestManager(tmp_settings.manifest.path, project_root=tmp_path)

    source = tmp_path / "inbox" / "notes.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Note", encoding="utf-8")
    digest = manager.hash_for_path(source)
    manager.add_processed_file(path=source, sha256=digest, extension=".md")
    manager.save()

    queue = QueueManager()
    item = QueueItem(path=source, extension=".md", created_at=datetime.now(UTC))
    queue.enqueue(item)
    worker = QueueWorker(queue, tmp_settings, manager, workflow=DuplicateWorkflow())

    with caplog.at_level("INFO"):
        assert worker.process_next()

    assert "Duplicate detected" in caplog.text
    assert item.status == QueueStatus.DONE
    assert source.exists()
    assert manager.count() == 1
    assert queue.is_empty()


# _settings removed: tests use shared tmp_settings fixture from conftest.py
