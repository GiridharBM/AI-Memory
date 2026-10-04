"""Thin retrieval adapter for V2 generation.

Wraps the frozen ``SearchService`` without modifying it: resolves a
``MemoryScope`` into concrete ``search()`` calls, merges hits
deterministically, caps context size, and projects ``SearchHit`` values
into domain-safe ``RetrievedChunk`` records. No new retrieval system.
"""

from __future__ import annotations

from typing import Protocol

from app.application.generation_errors import RetrievalError, UnsupportedScopeError
from app.domain.generation import GenerationRequest
from app.domain.generation_context import GenerationContext, RetrievedChunk
from app.domain.scopes import (
    MemoryScopeKind,
    ResolvedScope,
    UnsupportedMemoryScopeError,
    resolve_memory_scope,
)
from app.infrastructure.search import SearchHit

# Default per-query depth and total context cap. Deterministic and generous;
# per-task budgets arrive with their features.
DEFAULT_TOP_K = 5
DEFAULT_MAX_HITS = 20

# Adapter-level compensation for post-fusion filtering in the frozen
# SearchService, NOT an exact replacement for pre-ranking filtering.
#
# The frozen stack fuses first and filters second: ``HybridSearch.search``
# returns ``hits[:top_k]`` (app/infrastructure/search.py) and only then does
# ``SearchService.search`` apply ``filter``. A per-source restricted search at
# top_k=5 therefore discards every hit of the very source it was asked about
# whenever other sources outrank it -- on the shipped corpus a source that
# plainly contained the query term returned zero hits. Restricted calls ask for
# a deeper candidate window and slice back to ``top_k`` per source after the
# filter has run.
#
# Bounds are fixed rather than derived from corpus size, so the cost of a
# restricted request stays predictable. Known ceiling while the retrieval stack
# stays frozen: ``VectorStore.search`` filters before scoring, but
# ``SearchService`` never forwards its filter down to the store, so a source
# whose chunks all rank below this window is still invisible.
RESTRICTED_OVERSAMPLE_FACTOR = 20
RESTRICTED_MIN_TOP_K = 200
RESTRICTED_MAX_TOP_K = 1000


class RetrievalPort(Protocol):
    """Structural interface satisfied by ``SearchService`` (no import needed)."""

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filter: dict[str, object] | None = None,
        min_score: float = 0.0,
    ) -> list[SearchHit]: ...


def _queries_for_request(request: GenerationRequest) -> list[str]:
    """Derive retrieval queries for a request.

    V2-B derivation is intentionally naive (explicit config query/topic,
    else the task name); per-task retrieval planning arrives with features.
    """

    config = request.config
    for key in ("query", "topic"):
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return [request.task_type.value]


def _to_chunk(hit: SearchHit) -> RetrievedChunk:
    return RetrievedChunk(
        source=hit.source,
        text=hit.text,
        entry_id=hit.entry_id,
        source_type=hit.source_type,
        score=hit.score,
        cosine_score=hit.cosine_score,
        chunk_index=hit.chunk_index,
        start_char=hit.start_char,
        end_char=hit.end_char,
        metadata=dict(hit.metadata),
    )


def _merge_dedupe(hits: list[SearchHit], max_hits: int) -> list[SearchHit]:
    """Merge per-query hits in query order, dedupe by entry id, truncate."""

    seen: set[str] = set()
    merged: list[SearchHit] = []
    for hit in hits:
        key = hit.entry_id or f"{hit.source}::{hit.chunk_index}"
        if key in seen:
            continue
        seen.add(key)
        merged.append(hit)
        if len(merged) >= max_hits:
            break
    return merged


def retrieve_for_request(
    request: GenerationRequest,
    scope: ResolvedScope,
    search_service: RetrievalPort,
    *,
    top_k: int = DEFAULT_TOP_K,
    max_hits: int = DEFAULT_MAX_HITS,
) -> tuple[RetrievedChunk, ...]:
    """Retrieve evidence chunks for a request within its resolved scope."""

    if request.memory_scope.kind is MemoryScopeKind.PROJECTS:
        # Fail closed even for a hand-built scope: project retrieval is undecided.
        raise UnsupportedScopeError(
            "Project scopes have no supported retrieval yet (project grouping "
            "is undecided); refusing to fall back to unrestricted memory."
        )
    queries = _queries_for_request(request)
    try:
        collected: list[SearchHit] = []
        # Branch on ``restricted`` alone. A restricted scope that resolved to no
        # source matches nothing, so it must return nothing: adding
        # ``and scope.source_ids`` here would let an empty restricted scope fall
        # through to the unrestricted branch and quietly return the whole
        # corpus as evidence for a narrowly-scoped request. Node/topic scopes are
        # representable but unresolved until scope resolution lands, so they fail
        # closed here rather than pretending to be narrower than they are.
        if scope.restricted:
            candidate_top_k = min(
                max(top_k * RESTRICTED_OVERSAMPLE_FACTOR, RESTRICTED_MIN_TOP_K),
                RESTRICTED_MAX_TOP_K,
            )
            for source_id in scope.source_ids:
                for query in queries:
                    # Oversample for the post-fusion filter, then keep at most
                    # ``top_k`` per source so one verbose source cannot crowd
                    # the others out of the context budget.
                    collected.extend(
                        search_service.search(
                            query,
                            top_k=candidate_top_k,
                            filter={"source": source_id},
                            min_score=0.0,
                        )[:top_k]
                    )
        else:
            for query in queries:
                collected.extend(
                    search_service.search(query, top_k=top_k, filter=None, min_score=0.0)
                )
    except Exception as exc:
        raise RetrievalError(f"Memory retrieval failed: {exc}") from exc
    merged = _merge_dedupe(collected, max_hits)
    return tuple(_to_chunk(hit) for hit in merged)


def build_context(
    request: GenerationRequest,
    search_service: RetrievalPort,
    *,
    top_k: int = DEFAULT_TOP_K,
    max_hits: int = DEFAULT_MAX_HITS,
) -> GenerationContext:
    """Resolve scope, retrieve evidence, and bundle the handler input."""

    try:
        scope = resolve_memory_scope(request.memory_scope)
    except UnsupportedMemoryScopeError as exc:
        raise UnsupportedScopeError(str(exc)) from exc
    hits = retrieve_for_request(request, scope, search_service, top_k=top_k, max_hits=max_hits)
    return GenerationContext(request=request, scope=scope, hits=hits, nodes=())
