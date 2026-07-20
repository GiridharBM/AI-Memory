"""Domain models for vector storage."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class VectorEntry:
    """A single vector with its metadata."""

    id: str
    text: str
    embedding: list[float]
    source: str = ""
    source_type: str = ""
    chunk_index: int = 0
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class SearchResult:
    """A search result with similarity score."""

    entry: VectorEntry
    score: float
