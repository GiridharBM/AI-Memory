"""FIFO queue management for watcher events."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from threading import Lock

from app.queue.models import QueueItem, QueueStatus


class QueueManager:
    """Thread-safe in-memory FIFO queue with duplicate protection."""

    def __init__(self, *, max_size: int = 1000) -> None:
        self.max_size = max_size
        self._items: deque[QueueItem] = deque()
        self._queued_paths: set[Path] = set()
        self._processing_paths: set[Path] = set()
        self._processing_items: dict[Path, QueueItem] = {}
        self._lock = Lock()

    def enqueue(self, item: QueueItem) -> bool:
        """Add an item to the queue unless its path is already queued."""

        queue_path = self._queue_path(item.path)
        with self._lock:
            if (
                queue_path in self._queued_paths
                or queue_path in self._processing_paths
                or len(self._items) >= self.max_size
            ):
                return False

            item.status = QueueStatus.PENDING
            self._items.append(item)
            self._queued_paths.add(queue_path)
            return True

    def dequeue(self) -> QueueItem | None:
        """Remove and return the oldest queued item."""

        with self._lock:
            if not self._items:
                return None

            item = self._items.popleft()
            queue_path = self._queue_path(item.path)
            self._queued_paths.discard(queue_path)
            self._processing_paths.add(queue_path)
            self._processing_items[queue_path] = item
            item.status = QueueStatus.PROCESSING
            return item

    def complete(self, item: QueueItem) -> None:
        """Mark a dequeued item complete so the same path may be queued again."""

        with self._lock:
            queue_path = self._queue_path(item.path)
            self._processing_paths.discard(queue_path)
            self._processing_items.pop(queue_path, None)

    def is_empty(self) -> bool:
        """Return true when the queue has no pending items."""

        return self.size() == 0

    def size(self) -> int:
        """Return the number of pending items."""

        with self._lock:
            return len(self._items)

    def peek(self) -> QueueItem | None:
        """Return the next pending item without removing it."""

        with self._lock:
            return self._items[0] if self._items else None

    def list_items(self) -> list[QueueItem]:
        """Return pending items in FIFO order."""

        with self._lock:
            return list(self._items)

    def list_recoverable_items(self) -> list[QueueItem]:
        """Return pending and in-flight items for durable recovery.

        In-flight items are retained in the persisted state until their worker
        finishes, preventing a process crash from silently losing a file.
        """

        with self._lock:
            return [*self._processing_items.values(), *self._items]

    def restore(self, items: list[QueueItem]) -> int:
        """Restore pending items, preserving FIFO order and duplicate protection."""

        restored = 0
        for item in items:
            if self.enqueue(item):
                restored += 1
        return restored

    def is_queued(self, path: Path) -> bool:
        """Return true when a path is pending or currently being processed."""

        with self._lock:
            queue_path = self._queue_path(path)
            return queue_path in self._queued_paths or queue_path in self._processing_paths

    def _queue_path(self, path: Path) -> Path:
        return path.resolve()
