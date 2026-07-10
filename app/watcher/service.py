"""Long-running watchdog service for the inbox directory."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.core.config import Settings
from app.core.logging import get_logger
from app.queue import QueueItem, QueueManager, QueueStateStore, QueueWorker, RuntimeStats
from app.watcher.events import FileCreatedEvent
from app.watcher.scanner import should_watch_file

logger = get_logger(__name__)


class WatchService:
    """Monitor the inbox directory and report new Markdown files."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.inbox_root = settings.watcher.inbox_path
        self.queue_manager = QueueManager(max_size=settings.queue.max_size)
        self.queue_state_store = QueueStateStore(settings.queue.state_path)
        self.stats = RuntimeStats()
        self.queue_worker = QueueWorker(
            self.queue_manager,
            settings,
            queue_state_store=self.queue_state_store,
            stats=self.stats,
        )
        self._observer: Any | None = None
        self._started = False

    def run(self) -> None:
        """Start watching until interrupted."""

        self.start()
        try:
            while self.is_running:
                time.sleep(self.settings.watcher.interval_seconds)
        except KeyboardInterrupt:
            print("Stopping AI Memory...", flush=True)
        finally:
            self.stop(drain=True)

    def start(self) -> None:
        """Start the watchdog observer."""

        if not self.settings.watcher.enabled:
            logger.info("Watcher disabled")
            return

        self._ensure_runtime_directories()
        recovered = self.queue_state_store.restore_into(self.queue_manager)
        if recovered:
            print("Recovered", flush=True)
            print(f"{recovered} pending files.", flush=True)

        handler = _InboxCreatedHandler(
            supported_extensions=set(self.settings.watcher.supported_extensions),
            queue_manager=self.queue_manager,
            queue_state_store=self.queue_state_store,
            stats=self.stats,
        )
        observer = Observer()
        observer.schedule(
            handler,
            str(self.inbox_root),
            recursive=self.settings.watcher.recursive,
        )

        if self.settings.queue.enabled:
            logger.info("Queue started")
            print("Queue started", flush=True)
            self.queue_worker.start()

        observer.start()
        self._observer = observer
        self._started = True

        logger.info("Watcher started")
        logger.info("Watching %s", self._display_path(self.inbox_root))
        print("Waiting...", flush=True)

    def stop(self, *, drain: bool = False) -> None:
        """Stop the watchdog observer."""

        if not self._started:
            return

        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None

        if drain:
            print("Waiting for current task...", flush=True)
        self.queue_worker.stop(drain=drain)
        print("Queue stopped.", flush=True)
        self.queue_state_store.save(self.queue_manager)
        if self.queue_manager.is_empty():
            print("Queue empty.", flush=True)

        for handler in logging.getLogger().handlers:
            handler.flush()
        print("Logs flushed.", flush=True)
        logger.info("Watcher stopped")
        print("Watcher stopped.", flush=True)
        print("Goodbye.", flush=True)
        self._started = False

    @property
    def is_running(self) -> bool:
        """Return true while the underlying observer is active."""

        return self._observer is not None and self._observer.is_alive()

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.settings.paths.project_root))
        except ValueError:
            return str(path)

    def _ensure_runtime_directories(self) -> None:
        for path in [
            self.settings.paths.inbox_root,
            self.settings.watcher.inbox_path,
            self.settings.watcher.processed_path,
            self.settings.watcher.failed_path,
            self.settings.processing.processed_path,
            self.settings.processing.failed_path,
            self.settings.paths.log_root,
            self.settings.paths.vault_root,
            self.settings.paths.cache_root,
            self.settings.paths.manifest_root,
            self.settings.queue.state_path.parent,
            self.settings.manifest.path.parent,
        ]:
            path.mkdir(parents=True, exist_ok=True)


class _InboxCreatedHandler(FileSystemEventHandler):
    def __init__(
        self,
        *,
        supported_extensions: set[str],
        queue_manager: QueueManager,
        queue_state_store: QueueStateStore,
        stats: RuntimeStats,
    ) -> None:
        self.supported_extensions = supported_extensions
        self.queue_manager = queue_manager
        self.queue_state_store = queue_state_store
        self.stats = stats

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return

        if isinstance(event.src_path, bytes):
            return

        path = Path(event.src_path)
        if not should_watch_file(path, self.supported_extensions):
            return

        created_event = FileCreatedEvent(
            path=path,
            timestamp=datetime.now(UTC),
            extension=path.suffix.lower(),
        )
        logger.info("Markdown detected: %s", created_event.path.name)
        self.stats.record_detection()
        print("New Markdown detected:", flush=True)
        print(created_event.path.name, flush=True)

        queue_item = QueueItem(
            path=created_event.path,
            extension=created_event.extension,
            created_at=created_event.timestamp,
        )
        if self.queue_manager.enqueue(queue_item):
            queue_size = self.queue_manager.size()
            logger.info("Added to queue: %s", created_event.path.name)
            logger.info("Queue size: %s", queue_size)
            self.queue_state_store.save(self.queue_manager)
            print("Added to queue", flush=True)
            print(f"Queue size: {queue_size}", flush=True)
            return

        logger.info("Already queued: %s", created_event.path.name)
        print("Already queued:", flush=True)
        print(created_event.path.name, flush=True)
