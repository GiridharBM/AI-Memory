"""File hashing helpers for manifest duplicate detection."""

from __future__ import annotations

import hashlib
from pathlib import Path

SUPPORTED_HASH_EXTENSIONS = {".md", ".pdf", ".txt"}
CHUNK_SIZE = 8192


def compute_file_hash(path: Path) -> str:
    """Compute a streaming SHA-256 hash for supported files."""

    candidate = Path(path)
    if candidate.suffix.lower() not in SUPPORTED_HASH_EXTENSIONS:
        raise ValueError(f"Unsupported file type for hashing: {candidate.suffix}")

    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)

    return digest.hexdigest()
