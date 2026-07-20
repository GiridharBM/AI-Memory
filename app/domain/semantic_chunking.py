"""Domain models for semantic text chunking."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DocumentChunk:
    """A semantic chunk of text from a source document."""

    chunk_id: str
    text: str
    source: str
    source_type: str
    chunk_index: int
    start_char: int
    end_char: int
    metadata: dict[str, str] = field(default_factory=dict)
