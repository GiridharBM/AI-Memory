"""Queue data models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class QueueStatus(StrEnum):
    """Lifecycle status for queued files."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass
class QueueItem:
    """A file waiting for future processing."""

    path: Path
    extension: str
    created_at: datetime
    status: QueueStatus = QueueStatus.PENDING
