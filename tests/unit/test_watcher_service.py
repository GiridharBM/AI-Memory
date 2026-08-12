"""Tests for watcher service recovery and shutdown polish."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import (
    AppSettings,
    LoggingSettings,
    ManifestSettings,
    ModelRoutingSettings,
    OllamaSettings,
    PathSettings,
    ProcessingSettings,
    QueueSettings,
    Settings,
    WatcherSettings,
)
from app.queue import QueueItem, QueueManager
from app.watcher.service import WatchService, _InboxCreatedHandler, _wait_for_stable_file


class FakeObserver:
    def __init__(self, alive: bool = True) -> None:
        self.stopped = False
        self.joined = False
        self._alive = alive

    def start(self) -> None:
        pass

    def stop(self) -> None:
        self.stopped = True

    def join(self) -> None:
        self.joined = True

    def is_alive(self) -> bool:
        return self._alive

    def schedule(self, *args: Any, **kwargs: Any) -> None:
        pass


class FakeWorker:
    def __init__(self) -> None:
        self.drain: bool | None = None
        self.started = False

    def stop(self, *, drain: bool = False) -> None:
        self.drain = drain

    def start(self) -> None:
        self.started = True


def test_watcher_stop_drains_saves_flushes_and_reports_clean_shutdown(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = WatchService(_settings(tmp_path))
    observer = FakeObserver()
    worker = FakeWorker()
    service._observer = observer
    service.queue_worker = cast(Any, worker)
    service._started = True

    with caplog.at_level("INFO"):
        service.stop(drain=True)

    assert observer.stopped
    assert observer.joined
    assert worker.drain is True
    assert "Waiting for current task..." in caplog.text
    assert "Queue empty." in caplog.text
    assert "Watcher stopped" in caplog.text
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


def test_watcher_start_disabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.watcher.enabled = False
    service = WatchService(settings)
    service.start()
    assert service._observer is None
    assert service._started is False


def test_watcher_start_creates_observer(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    service = WatchService(settings)
    fake_observer = FakeObserver()
    with patch("app.watcher.service.Observer", return_value=fake_observer):
        service.start()
    assert service._observer is fake_observer
    assert service._started is True


def test_watcher_start_queue_worker_started(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    service = WatchService(settings)
    fake_worker = FakeWorker()
    fake_observer = FakeObserver()
    service.queue_worker = cast(Any, fake_worker)
    with patch("app.watcher.service.Observer", return_value=fake_observer):
        service.start()
    assert fake_worker.started is True


def test_watcher_stop_not_started_returns_early(tmp_path: Path) -> None:
    service = WatchService(_settings(tmp_path))
    service._started = False
    service.stop()
    assert service._started is False


def test_watcher_stop_without_drain(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    service = WatchService(_settings(tmp_path))
    observer = FakeObserver()
    worker = FakeWorker()
    service._observer = observer
    service.queue_worker = cast(Any, worker)
    service._started = True
    service.stop(drain=False)
    assert worker.drain is False
    assert "Waiting for current task..." not in capsys.readouterr().out


def test_watcher_is_running_property(tmp_path: Path) -> None:
    service = WatchService(_settings(tmp_path))
    assert service.is_running is False
    service._observer = FakeObserver(alive=True)
    assert service.is_running is True
    service._observer = FakeObserver(alive=False)
    assert service.is_running is False


def test_watcher_display_path_relative(tmp_path: Path) -> None:
    service = WatchService(_settings(tmp_path))
    result = service._display_path(tmp_path / "inbox" / "test.md")
    assert "inbox" in result


def test_watcher_display_path_absolute(tmp_path: Path) -> None:
    service = WatchService(_settings(tmp_path))
    foreign = Path("C:/other/dir/file.md") if Path("C:/").exists() else Path("/tmp/file.md")
    result = service._display_path(foreign)
    assert "file.md" in result


def test_display_path_outside_project_root(tmp_path: Path) -> None:
    service = WatchService(_settings(tmp_path))
    outside = tmp_path.parent / "outside" / "note.md"
    assert service._display_path(outside) == str(outside)


def test_display_path_cross_drive_no_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = WatchService(_settings(tmp_path))
    path = tmp_path / "inbox" / "note.md"

    def _raise(*args: object, **kwargs: object) -> Path:
        raise OSError("cross-drive path")

    monkeypatch.setattr(Path, "relative_to", _raise)
    assert service._display_path(path) == str(path)


def test_watcher_stop_flushes_handlers(tmp_path: Path) -> None:
    service = WatchService(_settings(tmp_path))
    observer = FakeObserver()
    worker = FakeWorker()
    service._observer = observer
    service.queue_worker = cast(Any, worker)
    service._started = True
    handler = MagicMock(spec=logging.Handler)
    with patch("app.watcher.service.logging.getLogger") as mock_get_logger:
        mock_root = MagicMock()
        mock_root.handlers = [handler]
        mock_get_logger.return_value = mock_root
        service.stop()
    handler.flush.assert_called()


def test_handler_skips_directories(tmp_path: Path) -> None:
    handler = _InboxCreatedHandler(
        supported_extensions={".md"},
        queue_manager=QueueManager(),
        queue_state_store=MagicMock(),
        stats=MagicMock(),
    )
    event = MagicMock()
    event.is_directory = True
    event.src_path = str(tmp_path / "subdir")
    handler.on_created(event)


def test_handler_skips_unsupported_extensions(tmp_path: Path) -> None:
    handler = _InboxCreatedHandler(
        supported_extensions={".md"},
        queue_manager=QueueManager(),
        queue_state_store=MagicMock(),
        stats=MagicMock(),
    )
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(tmp_path / "image.png")
    handler.on_created(event)


def test_handler_skips_bytes_path() -> None:
    handler = _InboxCreatedHandler(
        supported_extensions={".md"},
        queue_manager=QueueManager(),
        queue_state_store=MagicMock(),
        stats=MagicMock(),
    )
    event = MagicMock()
    event.is_directory = False
    event.src_path = b"/some/path/file.md"
    handler.on_created(event)


def test_handler_enqueues_markdown_file(tmp_path: Path) -> None:
    qm = QueueManager()
    stats = MagicMock()
    handler = _InboxCreatedHandler(
        supported_extensions={".md"},
        queue_manager=qm,
        queue_state_store=MagicMock(),
        stats=stats,
    )
    md_file = tmp_path / "note.md"
    md_file.write_text("# Test", encoding="utf-8")
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(md_file)
    handler.on_created(event)
    stats.record_detection.assert_called_once()
    assert qm.size() == 1


def test_wait_for_stable_file_retries_until_size_is_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "note.md"
    target.write_text("# Test", encoding="utf-8")

    sizes = iter([1, 2, 2])
    real_stat = Path.stat

    def fake_stat(self: Path, *args: object, **kwargs: object) -> Any:
        if self != target:
            return real_stat(self, *args, **kwargs)
        return SimpleNamespace(st_size=next(sizes))

    monkeypatch.setattr("app.watcher.service.time.sleep", lambda *_: None)
    monkeypatch.setattr(Path, "stat", fake_stat)

    assert _wait_for_stable_file(target, delay=0.1, checks=2) is True


def test_handler_waits_for_stable_file_before_enqueue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qm = QueueManager()
    stats = MagicMock()
    handler = _InboxCreatedHandler(
        supported_extensions={".md"},
        queue_manager=qm,
        queue_state_store=MagicMock(),
        stats=stats,
    )
    md_file = tmp_path / "note.md"
    md_file.write_text("# Test", encoding="utf-8")
    monkeypatch.setattr("app.watcher.service._wait_for_stable_file", lambda *args, **kwargs: True)

    event = MagicMock()
    event.is_directory = False
    event.src_path = str(md_file)
    handler.on_created(event)

    assert qm.size() == 1


def test_handler_rejects_duplicate_enqueue(tmp_path: Path) -> None:
    qm = QueueManager()
    stats = MagicMock()
    handler = _InboxCreatedHandler(
        supported_extensions={".md"},
        queue_manager=qm,
        queue_state_store=MagicMock(),
        stats=stats,
    )
    md_file = tmp_path / "note.md"
    md_file.write_text("# Test", encoding="utf-8")
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(md_file)
    handler.on_created(event)
    handler.on_created(event)
    assert qm.size() == 1


def test_start_scans_inbox_enqueues_existing_files(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.watcher.inbox_path.mkdir(parents=True, exist_ok=True)
    (settings.watcher.inbox_path / "note.md").write_text("# Note", encoding="utf-8")
    nested = settings.watcher.inbox_path / "sub"
    nested.mkdir(parents=True)
    (nested / "other.md").write_text("# Other", encoding="utf-8")
    service = WatchService(settings)
    service.queue_worker = cast(Any, FakeWorker())
    with patch("app.watcher.service.Observer", return_value=FakeObserver()):
        service.start()
    assert service.queue_manager.size() == 2


def test_inbox_scan_skips_hidden_files(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.watcher.inbox_path.mkdir(parents=True, exist_ok=True)
    (settings.watcher.inbox_path / ".hidden.md").write_text("hidden", encoding="utf-8")
    (settings.watcher.inbox_path / "note.md").write_text("# Note", encoding="utf-8")
    service = WatchService(settings)
    service.queue_worker = cast(Any, FakeWorker())
    with patch("app.watcher.service.Observer", return_value=FakeObserver()):
        service.start()
    assert service.queue_manager.size() == 1


def test_inbox_scan_skips_unsupported_extensions(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.watcher.inbox_path.mkdir(parents=True, exist_ok=True)
    (settings.watcher.inbox_path / "data.xyz").write_text("x", encoding="utf-8")
    (settings.watcher.inbox_path / "note.md").write_text("# Note", encoding="utf-8")
    service = WatchService(settings)
    service.queue_worker = cast(Any, FakeWorker())
    with patch("app.watcher.service.Observer", return_value=FakeObserver()):
        service.start()
    assert service.queue_manager.size() == 1


def test_inbox_scan_skips_directories(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    (settings.watcher.inbox_path / "notes").mkdir(parents=True)
    service = WatchService(settings)
    service.queue_worker = cast(Any, FakeWorker())
    with patch("app.watcher.service.Observer", return_value=FakeObserver()):
        service.start()
    assert service.queue_manager.size() == 0


def test_supported_extensions_always_include_canonical_set(tmp_path: Path) -> None:
    from app.core.extensions import PROCESSABLE_EXTENSIONS

    settings = _settings(tmp_path)
    service = WatchService(settings)
    assert PROCESSABLE_EXTENSIONS <= service._supported_extensions()
    assert service._supported_extensions() >= set(settings.watcher.supported_extensions)


def test_inbox_scan_does_not_double_enqueue_restored_files(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.watcher.inbox_path.mkdir(parents=True, exist_ok=True)
    md_file = settings.watcher.inbox_path / "note.md"
    md_file.write_text("# Note", encoding="utf-8")
    service = WatchService(settings)
    service.queue_manager.enqueue(
        QueueItem(path=md_file, extension=".md", created_at=datetime.now(UTC))
    )
    service.queue_worker = cast(Any, FakeWorker())
    with patch("app.watcher.service.Observer", return_value=FakeObserver()):
        service.start()
    assert service.queue_manager.size() == 1


def test_watcher_run_calls_start_and_stop(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    service = WatchService(settings)
    fake_observer = FakeObserver(alive=False)
    with patch.object(service, "start") as mock_start, \
         patch.object(service, "stop") as mock_stop, \
         patch("app.watcher.service.Observer", return_value=fake_observer), \
         patch("app.watcher.service.time"):
        service.run()
    mock_start.assert_called_once()
    mock_stop.assert_called_once_with(drain=True)


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
        models=ModelRoutingSettings(),
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
