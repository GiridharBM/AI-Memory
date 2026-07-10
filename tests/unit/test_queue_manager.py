"""Tests for the in-memory queue manager."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.queue import QueueItem, QueueManager, QueueStatus


def test_enqueue_adds_item(tmp_path: Path) -> None:
    manager = QueueManager()
    item = _item(tmp_path / "notes.md")

    assert manager.enqueue(item)
    assert manager.peek() == item
    assert item.status == QueueStatus.PENDING


def test_dequeue_returns_item(tmp_path: Path) -> None:
    manager = QueueManager()
    item = _item(tmp_path / "notes.md")
    manager.enqueue(item)

    dequeued = manager.dequeue()

    assert dequeued == item
    assert item.status == QueueStatus.PROCESSING
    assert manager.is_empty()


def test_fifo_order(tmp_path: Path) -> None:
    manager = QueueManager()
    first = _item(tmp_path / "first.md")
    second = _item(tmp_path / "second.md")
    third = _item(tmp_path / "third.md")

    manager.enqueue(first)
    manager.enqueue(second)
    manager.enqueue(third)

    assert manager.dequeue() == first
    assert manager.dequeue() == second
    assert manager.dequeue() == third


def test_duplicate_rejection(tmp_path: Path) -> None:
    manager = QueueManager()
    first = _item(tmp_path / "notes.md")
    duplicate = _item(tmp_path / "notes.md")

    assert manager.enqueue(first)
    assert not manager.enqueue(duplicate)
    assert manager.size() == 1


def test_duplicate_rejection_while_item_is_processing(tmp_path: Path) -> None:
    manager = QueueManager()
    first = _item(tmp_path / "notes.md")

    assert manager.enqueue(first)
    assert manager.dequeue() == first
    assert not manager.enqueue(_item(tmp_path / "notes.md"))

    manager.complete(first)

    assert manager.enqueue(_item(tmp_path / "notes.md"))


def test_queue_size(tmp_path: Path) -> None:
    manager = QueueManager()

    manager.enqueue(_item(tmp_path / "one.md"))
    manager.enqueue(_item(tmp_path / "two.md"))

    assert manager.size() == 2


def test_empty_queue() -> None:
    manager = QueueManager()

    assert manager.is_empty()
    assert manager.peek() is None
    assert manager.dequeue() is None


def _item(path: Path) -> QueueItem:
    return QueueItem(path=path, extension=path.suffix, created_at=datetime.now(UTC))
