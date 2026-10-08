"""Shared, cached access to PAM's existing services for the GUI transport.

Every accessor here delegates to the same application/infrastructure objects
the CLI uses. The caches exist for one reason: ``HybridSearch`` rebuilds the
entire BM25 index whenever ``VectorStore.version`` changes
(``app/infrastructure/search.py``), so constructing a fresh
``SearchService`` per request would pay a full-corpus rebuild on every click.
``invalidate_caches()`` drops them after an ingest so the GUI never serves a
stale corpus.

Read paths use the CLI's explicitly read-only manifest reader rather than
``ManifestManager``, because constructing a ``ManifestManager`` creates
directories and can rewrite/quarantine the manifest — a side effect a
status view must never have.
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Any

from app.application import QAWorkflow
from app.core.config import ConfigurationError, Settings, load_settings
from app.infrastructure.llm import OllamaClient
from app.infrastructure.search import SearchService
from app.infrastructure.vector_store import VectorStore

# How long an Ollama reachability probe stays fresh. The dashboard polls, so
# without this every render would hit the model server.
_HEALTH_TTL_SECONDS = 10.0
_health_cache: tuple[float, dict[str, Any]] | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the resolved application settings (authoritative, backend-side)."""

    return load_settings()


def settings_error() -> str | None:
    """Return why configuration is unusable, or ``None`` when it loads.

    The GUI renders ``STATUS UNKNOWN`` rather than fabricating health when this
    is set; it must never crash the whole UI on a config problem.
    """

    try:
        get_settings()
    except ConfigurationError as exc:
        return str(exc)
    except Exception as exc:  # defensive: a GUI must survive odd config states
        return f"{type(exc).__name__}: {exc}"
    return None


@lru_cache(maxsize=1)
def get_search_service() -> SearchService:
    """Return the cached hybrid search service (dense + BM25 + RRF)."""

    return SearchService.create_default(get_effective_settings())


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    """Return the cached persisted vector store, for read-only detail views.

    ``SearchService`` keeps its own instance; this one serves the chunk-level
    reads the memory-detail view needs. It is cached because the store is a
    single JSON document that is fully materialised on construction.
    """

    return VectorStore(
        persistence_path=get_settings().paths.manifest_root / "vector_store.json",
    )


@lru_cache(maxsize=1)
def get_qa_workflow() -> QAWorkflow:
    """Return the cached QA workflow.

    Building this constructs the search service, two Ollama clients and the
    system-facts layer, so it is cached for the same reason as the search
    service. ``QAWorkflow.ask`` is fully blocking and already enforces its own
    wall-clock deadline; the route runs it in FastAPI's threadpool.
    """

    return QAWorkflow.create_default(get_effective_settings())


def invalidate_caches() -> None:
    """Drop cached corpora so the next query sees a just-ingested source."""

    get_search_service.cache_clear()
    get_qa_workflow.cache_clear()
    get_vector_store.cache_clear()


# Experimental retrieval stages the GUI may toggle at runtime (HyDE query
# expansion, cross-encoder reranking, answerability gating). These are
# process-runtime overrides over the YAML-loaded settings: they affect
# future searches served by this process only and are never written back
# to configuration files. Fresh processes and the CLI keep file defaults
# (all three disabled) until explicitly toggled here.
RETRIEVAL_TOGGLES = ("hyde_enabled", "reranker_enabled", "answerability_enabled")

_retrieval_overrides: dict[str, bool] = {}


def get_retrieval_flags() -> dict[str, bool]:
    """Canonical runtime state of the three experimental retrieval stages."""

    settings = get_settings()
    base = {
        "hyde_enabled": settings.hyde.enabled,
        "reranker_enabled": settings.reranker.enabled,
        "answerability_enabled": settings.answerability.enabled,
    }
    return {name: _retrieval_overrides.get(name, value) for name, value in base.items()}


def set_retrieval_flag(name: str, enabled: bool) -> dict[str, bool]:
    """Set one experimental stage flag; rebuild services so future searches observe it.

    Only one flag changes per call — the other two are never touched.
    Raises ``ValueError`` for unknown names or non-boolean values, leaving
    all state (including caches) exactly as it was.
    """

    if name not in RETRIEVAL_TOGGLES:
        raise ValueError(f"Unknown retrieval stage: {name}.")
    if not isinstance(enabled, bool):
        raise ValueError("Retrieval stage state must be a boolean.")
    _retrieval_overrides[name] = enabled
    invalidate_caches()
    return get_retrieval_flags()


def clear_retrieval_overrides() -> None:
    """Drop all runtime overrides (used by tests to isolate flag state)."""

    _retrieval_overrides.clear()
    invalidate_caches()


def get_effective_settings() -> Settings:
    """File-loaded settings with runtime retrieval overrides applied.

    Identical to :func:`get_settings` when nothing was toggled; the cached
    search/QA services are built from this so toggles take effect for
    future searches after :func:`invalidate_caches`.
    """

    base = get_settings()
    flags = get_retrieval_flags()
    return base.model_copy(
        update={
            "hyde": base.hyde.model_copy(update={"enabled": flags["hyde_enabled"]}),
            "reranker": base.reranker.model_copy(update={"enabled": flags["reranker_enabled"]}),
            "answerability": base.answerability.model_copy(
                update={"enabled": flags["answerability_enabled"]}
            ),
        }
    )


def read_ledger() -> list[dict[str, Any]] | None:
    """Return durable ledger entries read-only, or ``None`` when unreadable.

    Delegates to the CLI's reader, which never creates directories, writes a
    fresh manifest, or quarantines a recreated one. ``[]`` means a genuinely
    empty ledger; ``None`` means present-but-unreadable, which the GUI shows as
    ``Not available`` rather than a fabricated zero.
    """

    from app.cli.entry import _read_manifest_entries

    return _read_manifest_entries(get_settings())


def ollama_health(*, force: bool = False) -> dict[str, Any]:
    """Probe the local Ollama runtime, cached briefly to avoid hammering it.

    Returns a dict with ``reachable`` (bool), ``model_present`` (bool | None),
    ``model`` and ``detail``. ``model_present`` is ``None`` when the client
    cannot answer the question, which the UI must not render as "Ready".
    """

    global _health_cache

    if not force and _health_cache is not None:
        stamp, cached_payload = _health_cache
        if time.monotonic() - stamp < _HEALTH_TTL_SECONDS:
            return cached_payload

    settings = get_settings()
    model = settings.ollama.model
    payload: dict[str, Any] = {
        "reachable": False,
        "model_present": None,
        "model": model,
        "detail": "",
    }
    try:
        client = OllamaClient(settings.ollama)
        if client.is_available():
            payload["reachable"] = True
            payload["detail"] = str(settings.ollama.host)
            if not hasattr(client, "model_exists"):
                payload["detail"] = "model check unavailable"
            else:
                try:
                    present = bool(client.model_exists(model))
                except Exception as exc:  # a probe failure is not a "missing model"
                    payload["detail"] = f"model check failed: {exc}"
                else:
                    payload["model_present"] = present
                    if not present:
                        payload["detail"] = f"model not listed: {model}"
        else:
            payload["detail"] = f"could not reach {settings.ollama.host}"
    except Exception as exc:
        payload["detail"] = f"{type(exc).__name__}: {exc}"

    _health_cache = (time.monotonic(), payload)
    return payload
