"""Reusable file filters for watcher events."""

from __future__ import annotations

from pathlib import Path

SUPPORTED_EXTENSIONS = {".md"}


def is_supported_file(
    path: str | Path,
    supported_extensions: set[str] | None = None,
) -> bool:
    """Return true when a path points to a supported Markdown file."""

    candidate = Path(path)
    extensions = supported_extensions or SUPPORTED_EXTENSIONS
    return candidate.is_file() and candidate.suffix.lower() in extensions


def is_hidden(path: str | Path) -> bool:
    """Return true when the file or any parent segment is hidden."""

    return any(part.startswith(".") for part in Path(path).parts)


def should_ignore(path: str | Path) -> bool:
    """Return true when a file should be ignored by the watcher."""

    candidate = Path(path)
    name = candidate.name
    return is_hidden(candidate) or name.endswith("~") or name.endswith(".tmp")
