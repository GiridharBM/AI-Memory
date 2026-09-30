"""System, diagnostics, configuration, storage, activity and retrieval routes.

Everything reported here is derived from authoritative durable state (the
vector store, the processed-files manifest, the resolved ``Settings``) or from
a live probe. Unreadable state is reported as ``null`` and rendered by the UI
as "Not available"; it is never replaced with a fabricated zero.
"""

from __future__ import annotations

import json
import platform
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from app.application.system_facts import OLLAMA_NUM_CTX, SUPPORTED_INGESTION_TYPES
from app.interfaces.web import deps

router = APIRouter()

# RRF's k is a module-level default in app/infrastructure/search.py, not a
# config key, so it is surfaced as a constant of the retrieval implementation
# rather than pretended to be configurable.
RRF_K = 60


def _count(raw: str) -> int | None:
    """Convert a CLI count string to an int, mapping "unavailable" to ``None``."""

    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


@router.get("/system")
def get_system() -> dict[str, Any]:
    """Dashboard payload: live counts, runtime health and retrieval config."""

    from app.cli.entry import _indexed_chunks, _indexed_sources, _queue_waiting

    config_error = deps.settings_error()
    if config_error is not None:
        return {
            "state": "unknown",
            "config_ok": False,
            "config_error": config_error,
            "metrics": {},
            "health": {},
            "retrieval": None,
            "activity": None,
        }

    settings = deps.get_settings()
    health = deps.ollama_health()
    sources = _count(_indexed_sources(settings))
    chunks = _count(_indexed_chunks(settings))
    ledger = deps.read_ledger()
    ledger_available = ledger is not None
    entries = ledger or []

    processed = sum(1 for e in entries if e.get("status") == "processed")
    skipped = sum(1 for e in entries if e.get("status") == "skipped_duplicate")
    failed = sum(1 for e in entries if e.get("status") == "failed")

    # "Healthy" is a claim, so it is only made when both the configuration
    # loads and the model runtime actually answers.
    if not health["reachable"]:
        state = "degraded"
    elif health["model_present"] is False:
        state = "degraded"
    else:
        state = "healthy"

    return {
        "state": state,
        "config_ok": True,
        "config_error": None,
        "metrics": {
            "sources": sources,
            "chunks": chunks,
            "ledger_entries": len(entries) if ledger_available else None,
            "processed": processed if ledger_available else None,
            "skipped_duplicates": skipped if ledger_available else None,
            "failed": failed if ledger_available else None,
            "queue_waiting": _count(_queue_waiting(settings)),
        },
        "health": {
            "llm": {
                "label": "LLM",
                "value": settings.ollama.model,
                "status": "ready" if health["reachable"] else "unavailable",
                "detail": health["detail"] or None,
            },
            "embeddings": {
                "label": "Embeddings",
                "value": settings.models.embeddings,
                # Reachability is shared: both models are served by the same
                # local Ollama runtime.
                "status": "ready" if health["reachable"] else "unavailable",
                "detail": None if health["reachable"] else health["detail"],
            },
            "vector_store": {
                "label": "Vector Store",
                "value": "Local JSON store",
                "status": "ready" if chunks is not None else "unavailable",
                "detail": None if chunks is not None else "vector_store.json could not be read",
            },
            "bm25": {
                "label": "BM25",
                "value": "Okapi BM25",
                "status": "ready" if chunks else "unavailable",
                "detail": None if chunks else "no indexed chunks to index",
            },
            "rrf": {
                "label": "RRF Fusion",
                "value": f"k = {RRF_K}",
                "status": "ready",
                "detail": None,
            },
        },
        "retrieval": _retrieval_config(settings),
        "activity": {
            "available": ledger_available,
            "total": len(entries) if ledger_available else None,
            "latest": _latest_ingest(entries) if ledger_available else None,
        },
        "capabilities": SUPPORTED_INGESTION_TYPES,
        "version": _app_version(settings),
        "environment": settings.app.environment,
    }


def _app_version(settings: Any) -> str | None:
    try:
        return package_version("personal-ai-memory")
    except PackageNotFoundError:
        return None


def _latest_ingest(entries: list[dict[str, Any]]) -> str | None:
    """Most recent successful ingestion timestamp, derived only from the ledger."""

    latest: str | None = None
    for entry in entries:
        if entry.get("status") not in {"processed", "skipped_duplicate"}:
            continue
        stamp = entry.get("processed_at")
        if not isinstance(stamp, str) or not stamp:
            continue
        if latest is None or stamp > latest:
            latest = stamp
    return latest


def _retrieval_config(settings: Any) -> dict[str, Any]:
    """Describe the retrieval pipeline from the running configuration only.

    Stage availability is what the GUI's pipeline diagram renders, so a stage
    disabled in config can never be drawn as active.
    """

    return {
        "top_k_default": 5,
        "rrf_k": RRF_K,
        "min_cosine": 0.25,
        "qa_timeout_seconds": settings.qa.timeout_seconds,
        "ollama_num_ctx": OLLAMA_NUM_CTX,
        "stages": [
            {"id": "query_processing", "label": "Query Processing", "active": True},
            {
                "id": "semantic",
                "label": "Semantic Search",
                "active": True,
                "detail": settings.models.embeddings,
            },
            {"id": "bm25", "label": "BM25 Search", "active": True, "detail": "Okapi BM25"},
            {
                "id": "hyde",
                "label": "HyDE Expansion",
                "active": settings.hyde.enabled,
                "detail": None if settings.hyde.enabled else "disabled",
            },
            {
                "id": "rerank",
                "label": "Cross-Encoder Rerank",
                "active": settings.reranker.enabled,
                "detail": None if settings.reranker.enabled else "disabled",
            },
            {"id": "rrf", "label": "RRF Fusion", "active": True, "detail": f"k = {RRF_K}"},
            {
                "id": "answerability",
                "label": "Answerability Gate",
                "active": settings.answerability.enabled,
                "detail": None if settings.answerability.enabled else "disabled",
            },
            {"id": "qa", "label": "QA Generation", "active": True, "detail": settings.ollama.model},
        ],
    }


@router.get("/retrieval")
def get_retrieval() -> dict[str, Any]:
    """Retrieval pipeline description for the Retrieval page."""

    if deps.settings_error() is not None:
        return {"available": False, "config_error": deps.settings_error()}
    return {"available": True, **deps_retrieval()}


def deps_retrieval() -> dict[str, Any]:
    return _retrieval_config(deps.get_settings())


@router.get("/activity")
def get_activity(limit: int = 50) -> dict[str, Any]:
    """Ingestion activity from the durable manifest ledger.

    PAM records ingest events only. Searches, QA queries, configuration changes
    and diagnostic runs are not persisted anywhere, so they are absent here
    rather than synthesised.
    """

    ledger = deps.read_ledger()
    if ledger is None:
        return {"available": False, "scope": "ingestion", "events": []}

    events = [
        {
            "at": entry.get("processed_at"),
            "status": entry.get("status"),
            "filename": entry.get("original_filename"),
            "source": entry.get("original_path"),
            "extension": entry.get("extension"),
            "chunks_stored": entry.get("chunks_stored"),
            "note": entry.get("generated_note"),
            "error_reason": entry.get("error_reason"),
            "embedding_succeeded": entry.get("embedding_succeeded"),
            "indexing_succeeded": entry.get("indexing_succeeded"),
        }
        for entry in ledger
    ]
    events.sort(key=lambda e: e.get("at") or "", reverse=True)
    return {
        "available": True,
        "scope": "ingestion",
        "total": len(events),
        "events": events[: max(1, min(limit, 500))],
    }


@router.get("/config")
def get_config() -> dict[str, Any]:
    """Resolved configuration, straight from the authoritative Settings model.

    Read-only by design: PAM configuration stays backend-authoritative and is
    never round-tripped through the browser.
    """

    error = deps.settings_error()
    if error is not None:
        return {"available": False, "config_error": error, "config": None}
    return {"available": True, "config": json.loads(deps.get_settings().model_dump_json())}


@router.get("/storage")
def get_storage() -> dict[str, Any]:
    """Storage locations, artifact sizes and persistence state."""

    error = deps.settings_error()
    if error is not None:
        return {"available": False, "config_error": error}

    settings = deps.get_settings()
    root = settings.paths.manifest_root
    store_path = root / "vector_store.json"
    graph_path = root / "knowledge_graph.json"
    notes_root = settings.paths.vault_root / "Notes"

    ledger = deps.read_ledger()
    from app.cli.entry import _indexed_chunks, _indexed_sources

    notes = len(list(notes_root.glob("*.md"))) if notes_root.exists() else 0
    return {
        "available": True,
        "vector_store": {
            "type": "Local JSON store",
            "path": str(store_path),
            "exists": store_path.exists(),
            "size_bytes": _file_size(store_path),
            "sources": _count(_indexed_sources(settings)),
            "chunks": _count(_indexed_chunks(settings)),
        },
        "knowledge_graph": {
            "path": str(graph_path),
            "exists": graph_path.exists(),
            "size_bytes": _file_size(graph_path),
        },
        "manifest": {
            "path": str(settings.manifest.path),
            "enabled": settings.manifest.enabled,
            "entries": len(ledger) if ledger is not None else None,
        },
        "vault": {
            "notes_root": str(notes_root),
            "notes": notes,
        },
        "paths": {
            key: str(getattr(settings.paths, key))
            for key in (
                "project_root",
                "vault_root",
                "inbox_root",
                "staging_root",
                "manifest_root",
                "cache_root",
                "log_root",
            )
        },
    }


@router.get("/diagnostics")
def get_diagnostics() -> dict[str, Any]:
    """Engineering diagnostics: environment, models, retrieval, storage."""

    error = deps.settings_error()
    if error is not None:
        return {"available": False, "config_error": error}

    settings = deps.get_settings()
    health = deps.ollama_health(force=True)
    from app.cli.entry import _check_writable_directory, _indexed_chunks, _indexed_sources

    directories = []
    for label, path in (
        ("Project root", settings.paths.project_root),
        ("Vault root", settings.paths.vault_root),
        ("Inbox", settings.paths.inbox_root),
        ("Manifest root", settings.paths.manifest_root),
        ("Log root", settings.paths.log_root),
        ("Cache root", settings.paths.cache_root),
    ):
        ok, detail = _check_writable_directory(path)
        directories.append({"label": label, "ok": ok, "detail": detail})

    ocr = settings.intelligence.ocr
    return {
        "available": True,
        "environment": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "platform": platform.platform(),
            "pam_version": _app_version(settings),
            "environment": settings.app.environment,
            "config_file": str(settings.paths.project_root / "config" / "default.yaml"),
        },
        "models": {
            "llm": settings.ollama.model,
            "embeddings": settings.models.embeddings,
            "vision": settings.models.vision,
            "audio": settings.models.audio,
            "ollama_host": str(settings.ollama.host),
            "ollama_reachable": health["reachable"],
            "ollama_model_present": health["model_present"],
            "ollama_detail": health["detail"],
            "ollama_num_ctx": OLLAMA_NUM_CTX,
        },
        "retrieval": {
            **_retrieval_config(settings),
            "reranker_enabled": settings.reranker.enabled,
            "reranker_model": settings.reranker.model,
            "hyde_enabled": settings.hyde.enabled,
            "answerability_enabled": settings.answerability.enabled,
            "qa_timeout_seconds": settings.qa.timeout_seconds,
        },
        "ingestion": {
            "ocr_enabled": ocr.enabled,
            "ocr_engine": ocr.engine,
            "ocr_page_limit": ocr.page_limit,
            "metadata_enabled": settings.intelligence.metadata.enabled,
            "watcher_enabled": settings.watcher.enabled,
            "watcher_extensions": settings.watcher.supported_extensions,
        },
        "storage": {
            "sources": _count(_indexed_sources(settings)),
            "chunks": _count(_indexed_chunks(settings)),
            "directories": directories,
        },
    }


@router.get("/evaluation")
def get_evaluation() -> dict[str, Any]:
    """Inventory of the offline evaluation artifacts in ``eval/results``.

    PAM's evaluation runs offline against frozen corpora; there is no runtime
    evaluation service. This lists real files on disk with their size and
    modification time. Headline metrics are deliberately not parsed here: the
    schemas differ per experiment, so the UI shows the inventory and reports
    metrics as "Not available" rather than inventing them.
    """

    error = deps.settings_error()
    if error is not None:
        return {"available": False, "config_error": error}

    results_dir = deps.get_settings().paths.project_root / "eval" / "results"
    artifacts: list[dict[str, Any]] = []
    if results_dir.exists():
        for path in sorted(results_dir.iterdir()):
            if not path.is_file():
                continue
            stat = path.stat()
            artifacts.append(
                {
                    "name": path.name,
                    "size_bytes": stat.st_size,
                    "modified": int(stat.st_mtime),
                    "kind": path.suffix.lstrip("."),
                }
            )
    return {
        "available": True,
        "results_dir": str(results_dir),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "runtime_metrics_available": False,
    }
