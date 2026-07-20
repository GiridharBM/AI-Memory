"""In-memory vector store with JSON persistence."""

from __future__ import annotations

import json
import math
from pathlib import Path

from app.core.logging import get_logger
from app.domain.vector_store import SearchResult, VectorEntry

logger = get_logger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class VectorStore:
    """In-memory vector store with optional JSON persistence."""

    def __init__(self, persistence_path: Path | None = None) -> None:
        self._entries: dict[str, VectorEntry] = {}
        self._persistence_path = persistence_path
        if persistence_path and persistence_path.exists():
            self._load()

    def add(self, entry: VectorEntry) -> None:
        self._entries[entry.id] = entry

    def add_batch(self, entries: list[VectorEntry]) -> None:
        for entry in entries:
            self._entries[entry.id] = entry

    def get(self, entry_id: str) -> VectorEntry | None:
        return self._entries.get(entry_id)

    def remove(self, entry_id: str) -> bool:
        if entry_id in self._entries:
            del self._entries[entry_id]
            return True
        return False

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        if not self._entries:
            return []

        scored: list[SearchResult] = []
        for entry in self._entries.values():
            score = _cosine_similarity(query_embedding, entry.embedding)
            if score >= min_score:
                scored.append(SearchResult(entry=entry, score=score))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def save(self) -> None:
        if not self._persistence_path:
            return
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "entries": [
                {
                    "id": e.id,
                    "text": e.text,
                    "embedding": e.embedding,
                    "source": e.source,
                    "source_type": e.source_type,
                    "chunk_index": e.chunk_index,
                    "metadata": e.metadata,
                }
                for e in self._entries.values()
            ]
        }
        self._persistence_path.write_text(
            json.dumps(data, indent=2), encoding="utf-8",
        )
        logger.info("Vector store saved.", extra={"count": len(self._entries)})

    def _load(self) -> None:
        if not self._persistence_path or not self._persistence_path.exists():
            return
        try:
            data = json.loads(self._persistence_path.read_text(encoding="utf-8"))
            for item in data.get("entries", []):
                entry = VectorEntry(
                    id=item["id"],
                    text=item["text"],
                    embedding=item["embedding"],
                    source=item.get("source", ""),
                    source_type=item.get("source_type", ""),
                    chunk_index=item.get("chunk_index", 0),
                    metadata=item.get("metadata", {}),
                )
                self._entries[entry.id] = entry
            logger.info("Vector store loaded.", extra={"count": len(self._entries)})
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Failed to load vector store: %s", exc)

    def __len__(self) -> int:
        return len(self._entries)
