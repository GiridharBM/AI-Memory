"""Persistence for unfinished queue items."""

from __future__ import annotations

import json
import os
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.queue.manager import QueueManager
from app.queue.models import QueueItem, QueueStatus

logger = get_logger(__name__)


class QueueStateStore:
    """Persist pending queue items for restart recovery."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def restore_into(self, queue_manager: QueueManager) -> int:
        """Restore queue items into a manager and return the count restored."""

        items = self.load()
        restored = queue_manager.restore(items)
        if restored:
            logger.info("Recovered pending queue items.", extra={"count": restored})
        return restored

    def load(self) -> list[QueueItem]:
        """Load pending queue items from disk."""

        if not self.path.exists():
            return []

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Queue state was invalid JSON and will be ignored.")
            return []

        raw_items = payload.get("items", []) if isinstance(payload, dict) else []
        if not isinstance(raw_items, list):
            return []

        items: list[QueueItem] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            item = _item_from_payload(raw_item)
            if item is not None and item.path.exists():
                items.append(item)
        return items

    def save(self, queue_manager: QueueManager) -> None:
        """Save current pending queue items."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "items": [
                _item_to_payload(item) for item in queue_manager.list_recoverable_items()
            ],
        }
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        try:
            temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(temporary_path, self.path)
        finally:
            with suppress(FileNotFoundError):
                temporary_path.unlink()


def _item_to_payload(item: QueueItem) -> dict[str, Any]:
    return {
        "path": str(item.path),
        "extension": item.extension,
        "created_at": item.created_at.isoformat(),
        "status": QueueStatus.PENDING.value,
    }


def _item_from_payload(payload: dict[str, Any]) -> QueueItem | None:
    try:
        return QueueItem(
            path=Path(str(payload["path"])),
            extension=str(payload["extension"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            status=QueueStatus.PENDING,
        )
    except (KeyError, ValueError, TypeError):
        return None
