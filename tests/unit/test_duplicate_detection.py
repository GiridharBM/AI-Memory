"""Tests for duplicate detection in the worker."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.config import (
    AppSettings,
    LoggingSettings,
    ManifestSettings,
    OllamaSettings,
    PathSettings,
    ProcessingSettings,
    Settings,
)
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
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = _settings(tmp_path)
    manager = ManifestManager(settings.manifest.path, project_root=tmp_path)

    source = tmp_path / "inbox" / "notes.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Note", encoding="utf-8")
    digest = manager.hash_for_path(source)
    manager.add_processed_file(path=source, sha256=digest, extension=".md")
    manager.save()

    queue = QueueManager()
    item = QueueItem(path=source, extension=".md", created_at=datetime.now(UTC))
    queue.enqueue(item)
    worker = QueueWorker(queue, settings, manager, workflow=DuplicateWorkflow())

    assert worker.process_next()

    output = capsys.readouterr().out
    assert "Duplicate?" in output
    assert "YES" in output
    assert "Skipping" in output
    assert item.status == QueueStatus.DONE
    assert source.exists()
    assert manager.count() == 1
    assert queue.is_empty()


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app=AppSettings(name="personal-ai-memory", environment="development"),
        paths=PathSettings(
            project_root=tmp_path,
            vault_root=tmp_path / "vault",
            inbox_root=tmp_path / "inbox",
            staging_root=tmp_path / "staging",
            manifest_root=tmp_path / "manifests",
            cache_root=tmp_path / "cache",
            log_root=tmp_path / "logs",
        ),
        ollama=OllamaSettings(),
        logging=LoggingSettings(console_enabled=False, file_enabled=False),
        manifest=ManifestSettings(path=tmp_path / "manifests" / "processed_files.json"),
        processing=ProcessingSettings(
            processed_path=tmp_path / "processed",
            failed_path=tmp_path / "failed",
        ),
    )
