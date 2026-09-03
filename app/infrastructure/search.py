"""Semantic and hybrid search over the knowledge base."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.vector_store import SearchResult, VectorEntry
from app.infrastructure.bm25 import BM25Index
from app.infrastructure.vector_store import VectorStore

if TYPE_CHECKING:
    from app.infrastructure.hyde import HyDETransform

logger = get_logger(__name__)


@dataclass(slots=True)
class SearchHit:
    """A unified search hit with chunk/document provenance.

    ``parent_section`` is the roadmap 4.6 parent-section context slot; it stays
    ``None`` until parent-child retrieval is implemented (chunks already carry
    ``parent_heading``/``heading_path`` in ``metadata``).

    ``cosine_score`` and ``bm25_score`` carry the raw per-leg retrieval scores
    that RRF fuses into ``score``.  They default to 0.0 so existing callers
    that construct SearchHit without them continue to work.
    """

    text: str
    source: str
    score: float
    entry_id: str
    cosine_score: float = 0.0
    bm25_score: float = 0.0
    rerank_score: float = 0.0
    parent_section: str | None = None
    source_type: str = ""
    chunk_index: int = 0
    start_char: int | None = None
    end_char: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)


def _to_hit(result: SearchResult) -> SearchHit:
    entry: VectorEntry = result.entry
    return SearchHit(
        text=entry.text,
        source=entry.source,
        score=result.score,
        entry_id=entry.id,
        parent_section=entry.metadata.get("parent_section_id"),
        source_type=entry.source_type,
        chunk_index=entry.chunk_index,
        start_char=entry.start_char,
        end_char=entry.end_char,
        metadata=dict(entry.metadata),
    )


def _rrf_fuse(
    *ranked_lists: list[str],
    k: int = 60,
    score_maps: tuple[dict[str, float], ...] | None = None,
) -> list[tuple[str, float, float, float]]:
    """Reciprocal rank fusion (roadmap 4.2).

    Each argument is a list of entry ids in descending rank order. A doc
    present in multiple lists accumulates ``1/(k + rank)`` per list; ids in no
    list score zero and are excluded. Ties resolve by id, so the output is
    deterministic regardless of input order.

    When *score_maps* is provided it must have one ``{entry_id: raw_score}``
    dict per ranked list.  The returned tuples carry the per-leg raw scores
    as ``(entry_id, rrf_score, leg0_score, leg1_score)`` so callers can use
    them for abstention gating without re-querying the individual engines.
    """
    scores: dict[str, float] = {}
    leg_scores: dict[str, tuple[float, float]] = {}
    for list_idx, ranked in enumerate(ranked_lists):
        for rank, entry_id in enumerate(ranked, start=1):
            scores[entry_id] = scores.get(entry_id, 0.0) + 1.0 / (k + rank)
            if score_maps and list_idx < len(score_maps):
                raw = score_maps[list_idx].get(entry_id, 0.0)
                prev = leg_scores.get(entry_id, (0.0, 0.0))
                if list_idx == 0:
                    leg_scores[entry_id] = (raw, prev[1])
                else:
                    leg_scores[entry_id] = (prev[0], raw)
    result = []
    for entry_id, rrf_score in sorted(scores.items(), key=lambda item: (-item[1], item[0])):
        leg0, leg1 = leg_scores.get(entry_id, (0.0, 0.0))
        result.append((entry_id, rrf_score, leg0, leg1))
    return result


def _hit_matches_filter(hit: SearchHit, filters: dict[str, object]) -> bool:
    """Exact-match filter against hit fields, then metadata keys.

    Structured ``$in``/range syntax is roadmap 4.5.
    """
    for key, value in filters.items():
        if getattr(hit, key, None) == value:
            continue
        if hit.metadata.get(key) == value:
            continue
        return False
    return True


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
        hits = [_to_hit(r) for r in results]
        logger.debug(
            "Semantic search completed.",
            extra={"hits": len(hits), "top_score": hits[0].score if hits else 0},
        )
        return hits


class HybridSearch:
    """Fuse dense vector retrieval with BM25 sparse retrieval via RRF.

    Candidate pools are capped at ``max(top_k * 5, 50)`` per leg so large
    corpora stay bounded. A leg that yields nothing (empty embedding, no
    lexical matches, or a BM25 failure) simply contributes no ranks; the other
    leg still produces results (roadmap 4.1 fallback).

    The BM25 index is built once per corpus snapshot and rebuilt only when the
    store mutates (tracked by ``VectorStore.version``); rebuilding the whole
    index on every query was the dominant measured cost on large corpora
    (P5-105).
    """

    def __init__(self, store: VectorStore, *, rrf_k: int = 60) -> None:
        self._store = store
        self._rrf_k = rrf_k
        self._bm25_index: BM25Index | None = None
        self._bm25_version: int | None = None
        self._bm25_ids: list[str] = []

    def _lexical(
        self,
    ) -> tuple[BM25Index, list[str]] | None:
        """Return the (index, entry-id ordering) for the current corpus."""
        if self._bm25_index is None or self._bm25_version != self._store.version:
            try:
                entries = self._store.entries()
                index = BM25Index([e.text for e in entries])
            except Exception:
                logger.warning(
                    "HybridSearch: BM25 build failed; using dense results only.",
                    exc_info=True,
                )
                self._bm25_index = None
                return None
            self._bm25_index = index
            self._bm25_ids = [e.id for e in entries]
            self._bm25_version = self._store.version
        return self._bm25_index, self._bm25_ids

    def search(
        self,
        query: str,
        query_embedding: list[float] | None,
        *,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        if top_k <= 0:
            return []
        pool_size = max(top_k * 5, 50)

        dense = (
            self._store.search(query_embedding, top_k=pool_size, min_score=0.0)
            if query_embedding
            else []
        )

        lexical: list[tuple[int, float]] = []
        if query.strip():
            built = self._lexical()
            if built is not None:
                index, ids = built
                try:
                    lexical = index.search(query, top_k=pool_size)
                except Exception:
                    logger.warning(
                        "HybridSearch: BM25 search failed; using dense results only.",
                        exc_info=True,
                    )
                fused_ids = [ids[i] for i, _score in lexical]
            else:
                fused_ids = []
        else:
            fused_ids = []

        vector_score_map = {r.entry.id: r.score for r in dense}
        bm25_score_map = {
            ids[i]: score for i, (doc_idx, score) in enumerate(lexical) if doc_idx < len(ids)
        }

        fused = _rrf_fuse(
            [r.entry.id for r in dense],
            fused_ids,
            k=self._rrf_k,
            score_maps=(vector_score_map, bm25_score_map),
        )

        hits: list[SearchHit] = []
        for entry_id, score, cosine_score, bm25_score in fused:
            entry = self._store.get(entry_id)
            assert entry is not None
            hit = _to_hit(SearchResult(entry=entry, score=score))
            hit.cosine_score = cosine_score
            hit.bm25_score = bm25_score
            if hit.score >= min_score:
                hits.append(hit)
        return hits[:top_k]


class SearchService:
    """Spec-facing retrieval facade (MEDD §7.6) — hybrid (dense + BM25 + RRF).

    Embeds the query text via the injected callable, then fuses dense and BM25
    candidates with reciprocal rank fusion (roadmap 4.2, k=60). ``filter``
    applies exact-match on hit fields then metadata keys after fusion;
    structured ``$in`` syntax is roadmap 4.5.

    Fallback: if the embedder raises or returns an empty/``None`` embedding,
    search degrades to lexical-only (BM25) instead of failing, so a broken or
    disabled embedding service never crashes the query path (roadmap §4.1
    success criterion: keyword-exact matches still rank).
    """

    def __init__(
        self,
        store: VectorStore,
        embed: Callable[[str], list[float] | None],
        *,
        hyde: HyDETransform | None = None,
    ) -> None:
        self._store = store
        self._embed = embed
        self._hybrid = HybridSearch(store)
        self._hyde = hyde

    @classmethod
    def create_default(
        cls,
        settings: Settings,
        *,
        embed: Callable[[str], list[float] | None] | None = None,
    ) -> SearchService:
        """Build the production service from application settings.

        Mirrors ``IngestionWorkflow.create_default``: the vector store reads the
        same persisted file (``manifest_root/vector_store.json``) the ingest
        pipeline writes, and queries embed via the configured embedding model.
        ``embed`` may be injected for tests; when omitted, an embedder failure
        degrades to lexical-only via ``_embed_query`` (roadmap 4.1 fallback).
        """
        store = VectorStore(
            persistence_path=settings.paths.manifest_root / "vector_store.json",
        )
        if embed is None:
            from app.infrastructure.embeddings import EmbeddingService

            embeddings = EmbeddingService(settings.ollama, model=settings.models.embeddings)

            def _embed(query: str) -> list[float]:
                return embeddings.embed(query).embedding

            embed = _embed
        hyde = None
        if getattr(settings, "hyde", None) and settings.hyde.enabled:
            from app.infrastructure.hyde import HyDETransform
            from app.infrastructure.llm import OllamaClient, OllamaRequest

            ollama = OllamaClient(settings.ollama)

            def _hyde_generate(system_prompt: str, user_prompt: str) -> str | None:
                try:
                    req = OllamaRequest(
                        prompt=user_prompt,
                        system_prompt=system_prompt,
                    )
                    resp = ollama.generate_text(req)
                    return resp.response
                except Exception:
                    return None

            hyde = HyDETransform(_hyde_generate, max_length=settings.hyde.max_length)
        return cls(store, embed=embed, hyde=hyde)

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filter: dict[str, object] | None = None,
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        if not query or not query.strip():
            return []
        embed_text = query
        if self._hyde is not None:
            hyde_text = self._hyde.transform(query)
            if hyde_text:
                embed_text = hyde_text
        embedding = self._embed_query(embed_text)
        hits = self._hybrid.search(query, embedding, top_k=top_k, min_score=min_score)
        if filter:
            hits = [h for h in hits if _hit_matches_filter(h, filter)]
        return hits

    def _embed_query(self, query: str) -> list[float] | None:
        try:
            return self._embed(query)
        except Exception:
            logger.warning(
                "SearchService: embedder failed; falling back to lexical-only.",
                exc_info=True,
            )
            return None
