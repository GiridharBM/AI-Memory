"""Tests for watcher service recovery and shutdown polish."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from app.core.config import (
    AppSettings,
    LoggingSettings,
    ManifestSettings,
    OllamaSettings,
    PathSettings,
    ProcessingSettings,
    QueueSettings,
    Settings,
    WatcherSettings,
)
from app.watcher.service import WatchService


class FakeObserver:
    def __init__(self) -> None:
        self.stopped = False
        self.joined = False

    def stop(self) -> None:
        self.stopped = True

    def join(self) -> None:
        self.joined = True


class FakeWorker:
    def __init__(self) -> None:
        self.drain: bool | None = None

    def stop(self, *, drain: bool = False) -> None:
        self.drain = drain


def test_watcher_stop_drains_saves_flushes_and_reports_clean_shutdown(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = WatchService(_settings(tmp_path))
    observer = FakeObserver()
    worker = FakeWorker()
    service._observer = observer
    service.queue_worker = cast(Any, worker)
    service._started = True

    service.stop(drain=True)

    output = capsys.readouterr().out
    assert observer.stopped
    assert observer.joined
    assert worker.drain is True
    assert "Waiting for current task..." in output
    assert "Queue empty." in output
    assert "Logs flushed." in output
    assert "Watcher stopped." in output
    assert "Goodbye." in output
    assert (tmp_path / "manifests" / "queue_state.json").exists()


def test_watcher_creates_missing_runtime_directories(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    service = WatchService(settings)

    service._ensure_runtime_directories()

    for path in [
        settings.paths.inbox_root,
        settings.watcher.inbox_path,
        settings.watcher.processed_path,
        settings.watcher.failed_path,
        settings.processing.processed_path,
        settings.processing.failed_path,
        settings.paths.log_root,
        settings.paths.vault_root,
        settings.paths.cache_root,
        settings.paths.manifest_root,
        settings.queue.state_path.parent,
        settings.manifest.path.parent,
    ]:
        assert path.exists()


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
        watcher=WatcherSettings(
            inbox_path=tmp_path / "inbox",
            processed_path=tmp_path / "processed",
            failed_path=tmp_path / "failed",
        ),
        queue=QueueSettings(state_path=tmp_path / "manifests" / "queue_state.json"),
        manifest=ManifestSettings(path=tmp_path / "manifests" / "processed_files.json"),
        processing=ProcessingSettings(
            processed_path=tmp_path / "processed",
            failed_path=tmp_path / "failed",
        ),
    )
