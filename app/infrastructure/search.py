"""Semantic and hybrid search over the knowledge base."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.vector_store import VectorEntry, SearchResult
from app.infrastructure.vector_store import VectorStore


@dataclass(slots=True)
class SearchHit:
    """A unified search hit."""

    text: str
    source: str
    score: float
    entry_id: str


class SemanticSearch:
    """Search using vector embeddings."""

    def __init__(self, store: VectorStore) -> None:
        self._store = store

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        results = self._store.search(
            query_embedding, top_k=top_k, min_score=min_score,
        )
        return [
            SearchHit(
                text=r.entry.text,
                source=r.entry.source,
                score=r.score,
                entry_id=r.entry.id,
            )
            for r in results
        ]


class HybridSearch:
    """Combine keyword matching with semantic search."""

    def __init__(self, store: VectorStore) -> None:
        self._store = store
        self._keyword_weight = 0.3
        self._semantic_weight = 0.7

    def search(
        self,
        query: str,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        semantic_results = self._store.search(
            query_embedding, top_k=top_k * 2, min_score=0.0,
        )
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored: list[SearchHit] = []
        for result in semantic_results:
            text_lower = result.entry.text.lower()
            keyword_hits = sum(1 for w in query_words if w in text_lower)
            keyword_score = keyword_hits / max(len(query_words), 1)
            combined = (
                self._semantic_weight * result.score
                + self._keyword_weight * keyword_score
            )
            if combined >= min_score:
                scored.append(SearchHit(
                    text=result.entry.text,
                    source=result.entry.source,
                    score=combined,
                    entry_id=result.entry.id,
                ))

        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]
