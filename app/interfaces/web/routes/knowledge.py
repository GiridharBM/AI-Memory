"""Memory library routes: indexed sources and per-source chunk detail.

Source rows come from the persisted vector store (the authority on what is
indexable), annotated with durable ledger state. Both projections are the same
ones ``pam sources`` renders, so the GUI cannot disagree with the CLI.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, HTTPException

from app.interfaces.web import deps

router = APIRouter()

# A source is a filesystem path or a URL, so it cannot be a path parameter.
# The id is a stable digest of the source string: deterministic, opaque, and
# safe in a URL.
_MAX_CHUNKS_IN_DETAIL = 200


def source_id(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]


def _rows() -> list[Any] | None:
    """Return ledger-annotated source rows, or ``None`` when the store is unreadable."""

    from app.cli.entry import _annotate_source_ledger, _read_vector_store_sources
    from app.infrastructure.state.manifest import ManifestManager

    settings = deps.get_settings()
    rows = _read_vector_store_sources(settings)
    if rows is None:
        return None
    manifest = ManifestManager(
        settings.manifest.path,
        project_root=settings.paths.project_root,
        enabled=settings.manifest.enabled,
    )
    _annotate_source_ledger(rows, manifest, settings.paths.project_root)
    return rows


@router.get("/sources")
def get_sources() -> dict[str, Any]:
    """Every indexed source with its type, chunk count and ledger status."""

    error = deps.settings_error()
    if error is not None:
        return {"available": False, "config_error": error, "sources": [], "total_chunks": None}

    rows = _rows()
    if rows is None:
        return {
            "available": False,
            "config_error": "The vector store could not be read; source listing is unavailable.",
            "sources": [],
            "total_chunks": None,
        }

    sources = [
        {
            "id": source_id(row.source),
            "source": row.source,
            "name": row.source.rsplit("/", 1)[-1] or row.source,
            "type": row.type or None,
            "chunks": row.chunks,
            "status": row.status,
            "last_ingested": row.last_ingested,
        }
        for row in rows
    ]

    by_type: dict[str, int] = {}
    for source in sources:
        key = source["type"] or "unknown"
        by_type[key] = by_type.get(key, 0) + source["chunks"]

    return {
        "available": True,
        "total": len(sources),
        "total_chunks": sum(s["chunks"] for s in sources),
        "by_type": sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0])),
        "sources": sources,
    }


@router.get("/sources/{identifier}")
def get_source(identifier: str, limit: int = _MAX_CHUNKS_IN_DETAIL) -> dict[str, Any]:
    """One source with its indexed chunks, when chunk text is safely exposed."""

    error = deps.settings_error()
    if error is not None:
        raise HTTPException(status_code=503, detail=error)

    rows = _rows() or []
    match = next((row for row in rows if source_id(row.source) == identifier), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Source not found.")

    settings = deps.get_settings()
    store = deps.get_vector_store()
    chunks: list[dict[str, Any]] = []
    for entry in store.entries():
        if entry.source != match.source:
            continue
        chunks.append(
            {
                "entry_id": entry.id,
                "chunk_index": entry.chunk_index,
                "text": entry.text,
                "start_char": entry.start_char,
                "end_char": entry.end_char,
                "metadata": entry.metadata,
            }
        )
    chunks.sort(key=lambda c: int(c["chunk_index"] or 0))

    return {
        "available": True,
        "id": identifier,
        "source": match.source,
        "name": match.source.rsplit("/", 1)[-1] or match.source,
        "type": match.type or None,
        "status": match.status,
        "last_ingested": match.last_ingested,
        "chunk_count": match.chunks,
        "store_path": str(settings.paths.manifest_root / "vector_store.json"),
        "chunks_truncated": len(chunks) > max(1, limit),
        "chunks": chunks[: max(1, limit)],
    }
