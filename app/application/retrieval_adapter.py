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
        # Branch on the resolved scope data (not the request spelling) so the
        # behavior follows what was actually resolved. For consistent callers
        # both agree; node-only scopes retrieve broad evidence a handler
        # narrows by nodes, never inventing retrieval semantics.
        if scope.restricted and scope.source_ids:
            for source_id in scope.source_ids:
                for query in queries:
                    collected.extend(
                        search_service.search(
                            query, top_k=top_k, filter={"source": source_id}, min_score=0.0
                        )
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
