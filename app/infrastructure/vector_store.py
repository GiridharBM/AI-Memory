"""In-memory vector store with JSON persistence."""

from __future__ import annotations

import json
import math
import operator
import os
from contextlib import suppress
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


def _norm(vector: list[float]) -> float:
    return math.sqrt(sum(x * x for x in vector))


def _matches_filter(entry: VectorEntry, filters: dict[str, object]) -> bool:
    """Exact-match filter against entry fields, then metadata keys.

    Entry fields win over metadata keys of the same name. Structured filter
    syntax (``$in``, ranges) is roadmap 4.5.
    """
    for key, value in filters.items():
        if getattr(entry, key, None) == value:
            continue
        if entry.metadata.get(key) == value:
            continue
        return False
    return True


class VectorStore:
    """In-memory vector store with optional JSON persistence."""

    def __init__(self, persistence_path: Path | None = None) -> None:
        self._entries: dict[str, VectorEntry] = {}
        self._norms: dict[str, float] = {}
        self._version = 0
        self._persistence_path = persistence_path
        if persistence_path and persistence_path.exists():
            self._load()

    @property
    def version(self) -> int:
        """Mutation counter; bumped on every add/remove/load.

        Lets derived caches (e.g. the BM25 index in ``HybridSearch``) detect
        corpus changes and rebuild exactly when needed.
        """
        return self._version

    def add(self, entry: VectorEntry) -> None:
        self._entries[entry.id] = entry
        self._norms[entry.id] = _norm(entry.embedding)
        self._version += 1

    def add_batch(self, entries: list[VectorEntry]) -> None:
        for entry in entries:
            self._entries[entry.id] = entry
            self._norms[entry.id] = _norm(entry.embedding)
        self._version += 1

    def get(self, entry_id: str) -> VectorEntry | None:
        return self._entries.get(entry_id)

    def entries(self) -> list[VectorEntry]:
        """All entries in insertion order (deterministic)."""
        return list(self._entries.values())

    def remove(self, entry_id: str) -> bool:
        if entry_id in self._entries:
            del self._entries[entry_id]
            self._norms.pop(entry_id, None)
            self._version += 1
            return True
        return False

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        min_score: float = 0.0,
        filters: dict[str, object] | None = None,
    ) -> list[SearchResult]:
        if not self._entries:
            return []

        query_norm = math.sqrt(sum(x * x for x in query_embedding))
        query_dim = len(query_embedding)
        scored: list[SearchResult] = []
        for entry in self._entries.values():
            if filters and not _matches_filter(entry, filters):
                continue
            entry_norm = self._norms[entry.id]
            # Matches _cosine_similarity semantics: dim mismatch or a zero
            # vector yields 0.0, which is included when min_score <= 0.0.
            score = 0.0
            if query_dim == len(entry.embedding) and query_norm and entry_norm:
                # map(operator.mul, ...) pushes the multiply to C; bit-identical
                # to the genexpr it replaces.
                dot = sum(map(operator.mul, query_embedding, entry.embedding))
                score = dot / (query_norm * entry_norm)
            if score >= min_score:
                scored.append(SearchResult(entry=entry, score=score))

        scored.sort(key=lambda r: (-r.score, r.entry.id))
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
                    "start_char": e.start_char,
                    "end_char": e.end_char,
                    "metadata": e.metadata,
                }
                for e in self._entries.values()
            ]
        }
        temporary_path = self._persistence_path.with_suffix(
            f"{self._persistence_path.suffix}.tmp",
        )
        try:
            # Compact separators: ~32% smaller files (measured), same semantics.
            temporary_path.write_text(
                json.dumps(data, separators=(",", ":")), encoding="utf-8"
            )
            os.replace(temporary_path, self._persistence_path)
        finally:
            with suppress(FileNotFoundError):
                temporary_path.unlink()
        logger.info("Vector store saved.", extra={"count": len(self._entries)})

    def _load(self) -> None:
        if not self._persistence_path or not self._persistence_path.exists():
            return
        try:
            data = json.loads(self._persistence_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            logger.warning("Failed to load vector store: %s", exc)
            return
        raw_items = data.get("entries", []) if isinstance(data, dict) else []
        if not isinstance(raw_items, list):
            logger.warning("Vector store has no entries list; starting empty.")
            return
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            try:
                entry = VectorEntry(
                    id=item["id"],
                    text=item["text"],
                    embedding=item["embedding"],
                    source=item.get("source", ""),
                    source_type=item.get("source_type", ""),
                    chunk_index=item.get("chunk_index", 0),
                    start_char=item.get("start_char"),
                    end_char=item.get("end_char"),
                    metadata=item.get("metadata", {}),
                )
                # Compute the norm before inserting so a malformed embedding
                # can never leave a norm-less entry behind (search would KeyError).
                norm = _norm(entry.embedding)
                self._entries[entry.id] = entry
                self._norms[entry.id] = norm
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                logger.warning("Skipping malformed vector store entry: %s", exc)
        self._version += 1
        logger.info("Vector store loaded.", extra={"count": len(self._entries)})

    def __len__(self) -> int:
        return len(self._entries)
