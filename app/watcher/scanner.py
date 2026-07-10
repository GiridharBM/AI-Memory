"""File scanning helpers for the watcher."""

from __future__ import annotations

from pathlib import Path

from app.watcher.filters import is_supported_file, should_ignore


def should_watch_file(
    path: str | Path,
    supported_extensions: set[str] | None = None,
) -> bool:
    """Return true when the watcher should report a file."""

    candidate = Path(path)
    return not should_ignore(candidate) and is_supported_file(candidate, supported_extensions)
