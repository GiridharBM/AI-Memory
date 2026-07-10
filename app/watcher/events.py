"""Watcher event models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class FileCreatedEvent:
    """Represents a supported file creation event."""

    path: Path
    timestamp: datetime
    extension: str
