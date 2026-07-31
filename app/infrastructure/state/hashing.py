"""File hashing helpers for manifest duplicate detection."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.core.extensions import (
    AUDIO_EXTENSIONS,
    CODE_EXTENSIONS,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
)

SUPPORTED_HASH_EXTENSIONS = (
    {".md", ".pdf", ".txt", ".csv", ".xlsx"}
    | CODE_EXTENSIONS | IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
)
CHUNK_SIZE = 8192


def compute_file_hash(path: Path) -> str:
    """Compute a streaming SHA-256 hash for supported files."""

    if path.suffix.lower() not in SUPPORTED_HASH_EXTENSIONS:
        raise ValueError(f"Unsupported file type for hashing: {path.suffix}")

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)

    return digest.hexdigest()
