"""Tests for persisted queue state recovery."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.queue import QueueItem, QueueManager, QueueStateStore


def test_queue_state_store_restores_pending_items(tmp_path: Path) -> None:
    first = tmp_path / "inbox" / "first.md"
    second = tmp_path / "inbox" / "second.md"
    first.parent.mkdir(parents=True)
    first.write_text("# First", encoding="utf-8")
    second.write_text("# Second", encoding="utf-8")

    original_queue = QueueManager()
    original_queue.enqueue(QueueItem(path=first, extension=".md", created_at=datetime.now(UTC)))
    original_queue.enqueue(QueueItem(path=second, extension=".md", created_at=datetime.now(UTC)))

    store = QueueStateStore(tmp_path / "manifests" / "queue_state.json")
    store.save(original_queue)

    restored_queue = QueueManager()
    restored = store.restore_into(restored_queue)

    assert restored == 2
    assert restored_queue.size() == 2
    restored_first = restored_queue.dequeue()
    restored_second = restored_queue.dequeue()
    assert restored_first is not None
    assert restored_second is not None
    assert restored_first.path == first
    assert restored_second.path == second


def test_queue_state_store_ignores_invalid_json(tmp_path: Path) -> None:
    state_path = tmp_path / "manifests" / "queue_state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text("{not json", encoding="utf-8")

    assert QueueStateStore(state_path).load() == []


def test_queue_state_store_persists_in_flight_item_for_recovery(tmp_path: Path) -> None:
    source = tmp_path / "inbox" / "notes.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Notes", encoding="utf-8")
    queue = QueueManager()
    item = QueueItem(path=source, extension=".md", created_at=datetime.now(UTC))
    queue.enqueue(item)
    assert queue.dequeue() == item

    store = QueueStateStore(tmp_path / "manifests" / "queue_state.json")
    store.save(queue)

    restored = QueueManager()
    assert store.restore_into(restored) == 1
    restored_item = restored.dequeue()
    assert restored_item is not None
    assert restored_item.path == source
