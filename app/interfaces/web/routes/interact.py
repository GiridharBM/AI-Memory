"""Interactive routes: search, ask, and ingest.

Search and Ask delegate to the exact services the CLI uses
(``SearchService.search``, ``QAWorkflow.ask``), so the GUI cannot diverge from
``pam search`` / ``pam ask`` — including abstention behaviour and citation
validation, which are untouched.

Ingest mirrors the ledger semantics of ``app/cli/entry.py:_run_ingest`` using
``ManifestManager``'s public API. That CLI function is not reusable directly
because it prints Rich panels and raises ``typer.Exit``; the orchestration below
is the only duplicated logic in this package and is covered by
``tests/unit/test_web_routes.py``. If the CLI's ingest semantics change, this
must change with it.
"""

from __future__ import annotations

import time
from contextlib import suppress
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.application import QAError
from app.infrastructure.llm import OllamaClientError
from app.interfaces.web import deps
from app.pipelines import IngestionWorkflow, IngestionWorkflowError

router = APIRouter()

UPLOAD_SUBDIR = "pam-gui-uploads"
# Uploads are staged outside the watched inbox on purpose: if ``pam watch`` is
# running it would otherwise ingest the same file concurrently with this route.
_MAX_UPLOAD_BYTES = 512 * 1024 * 1024


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=0.0)
    source_type: str | None = None
    source: str | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=0.0)


def _hit_payload(hit: Any) -> dict[str, Any]:
    return {
        "entry_id": hit.entry_id,
        "source": hit.source,
        "source_type": hit.source_type or None,
        "text": hit.text,
        "score": hit.score,
        "cosine_score": hit.cosine_score,
        "bm25_score": hit.bm25_score,
        # 0.0 is the documented "reranker disabled or did not score this hit"
        # sentinel, so it is reported as null rather than a fake zero score.
        "rerank_score": hit.rerank_score or None,
        "chunk_index": hit.chunk_index,
        "start_char": hit.start_char,
        "end_char": hit.end_char,
        "parent_section": hit.parent_section,
        "metadata": hit.metadata,
    }


@router.post("/search")
def post_search(request: SearchRequest) -> dict[str, Any]:
    """Ranked retrieval results with the real per-leg scores.

    This is retrieval only: no LLM generation, no abstention gate.
    """

    error = deps.settings_error()
    if error is not None:
        raise HTTPException(status_code=503, detail=error)

    filters: dict[str, object] = {}
    if request.source_type:
        filters["source_type"] = request.source_type
    if request.source:
        filters["source"] = request.source

    try:
        service = deps.get_search_service()
        started = time.perf_counter()
        hits = service.search(
            request.query,
            top_k=request.top_k,
            filter=filters or None,
            min_score=request.min_score,
        )
        latency_seconds = time.perf_counter() - started
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}") from exc

    return {
        "query": request.query,
        "count": len(hits),
        "filters": filters or None,
        "latency_seconds": latency_seconds,
        "results": [_hit_payload(hit) for hit in hits],
    }


@router.post("/ask")
def post_ask(request: AskRequest) -> dict[str, Any]:
    """A grounded answer from the real QA workflow.

    Synchronous by design: ``QAWorkflow.ask`` is fully blocking and enforces its
    own ``qa.timeout_seconds`` deadline. FastAPI runs this route in its
    threadpool, so the event loop stays responsive and the GUI can still render
    a loading state and time out on its own terms.
    """

    error = deps.settings_error()
    if error is not None:
        raise HTTPException(status_code=503, detail=error)

    try:
        result = deps.get_qa_workflow().ask(
            request.question,
            top_k=request.top_k,
            min_score=request.min_score,
        )
    except QAError as exc:
        # QAError covers timeout, unreachable Ollama and empty-answer failures.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except OllamaClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ask failed: {exc}") from exc

    return {
        "question": request.question,
        "answer": result.answer,
        "outcome": result.outcome,
        "abstention_reason": result.abstention_reason,
        "origin": result.origin,
        "model": result.model or None,
        "latency_seconds": result.latency_seconds,
        "citations": [{"number": c.number, **_hit_payload(c.hit)} for c in result.citations],
        "invalid_citations": result.invalid_citations,
        "duplicate_citations": result.duplicate_citations,
        "sources": [_hit_payload(hit) for hit in result.sources],
        "telemetry": (
            {
                "answer_length": result.telemetry.answer_length,
                "source_count": result.telemetry.source_count,
                "citation_count": result.telemetry.citation_count,
                "invalid_citation_count": result.telemetry.invalid_citation_count,
                "duplicate_citation_count": result.telemetry.duplicate_citation_count,
                "answer_has_insufficiency_language": (
                    result.telemetry.answer_has_insufficiency_language
                ),
            }
            if result.telemetry
            else None
        ),
    }


@router.post("/ingest")
async def post_ingest(
    file: Annotated[UploadFile | None, File()] = None,
    url: Annotated[str | None, Form()] = None,
    source_type: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    """Ingest an uploaded file, a GitHub URL, or a YouTube URL.

    Ingestion is synchronous in PAM and reports no progress, so the GUI shows an
    indeterminate indicator rather than a fabricated percentage.
    """

    error = deps.settings_error()
    if error is not None:
        raise HTTPException(status_code=503, detail=error)

    target_url = (url or "").strip()
    if file is None and not target_url:
        raise HTTPException(status_code=400, detail="Provide either a file or a url.")

    if file is not None:
        target = await _stage_upload(file)
        return _run_ingest(target, expected_source_type=source_type or None)

    return _run_ingest(target_url, expected_source_type=source_type or None)


async def _stage_upload(upload: UploadFile) -> Path:
    """Write an uploaded file into the staging directory and return its path."""

    settings = deps.get_settings()
    name = Path(upload.filename or "upload").name
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Missing filename.")

    target_dir = settings.paths.staging_root / UPLOAD_SUBDIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / name

    written = 0
    try:
        with target.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                written += len(chunk)
                if written > _MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File too large.")
                handle.write(chunk)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    except OSError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not store upload: {exc}") from exc
    finally:
        await upload.close()

    if written == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    return target


def _save_ledger(manifest: Any) -> None:
    with suppress(OSError):
        manifest.save()


def _run_ingest(source: str | Path, *, expected_source_type: str | None) -> dict[str, Any]:
    """Run the existing ingestion workflow and record it in the durable ledger.

    Mirrors ``app/cli/entry.py::_run_ingest``: hash-based duplicate detection
    first, then the workflow, then a ledger entry whose status reflects what
    actually happened (processed / skipped_duplicate / failed).
    """

    settings = deps.get_settings()
    from app.infrastructure.state.manifest import ManifestManager

    manifest = ManifestManager(
        settings.manifest.path,
        project_root=settings.paths.project_root,
        enabled=settings.manifest.enabled,
    )

    ledger_path = Path(source)
    digest: str | None
    try:
        digest = manifest.hash_for_path(source) if isinstance(source, Path) else None
    except ValueError:
        digest = None

    if digest is not None and manifest.contains_successful_hash(digest):
        manifest.add_processed_file(
            path=ledger_path,
            sha256=digest,
            extension=ledger_path.suffix,
            status="skipped_duplicate",
        )
        _save_ledger(manifest)
        return {
            "status": "skipped_duplicate",
            "source": str(source),
            "message": (
                "This file was already processed successfully (identical content); "
                "skipping. Existing note, index, and knowledge-graph data was left untouched."
            ),
        }
    if digest is None and manifest.contains_successful_path(ledger_path):
        manifest.add_processed_file(
            path=ledger_path,
            sha256="",
            extension=ledger_path.suffix,
            status="skipped_duplicate",
        )
        _save_ledger(manifest)
        return {
            "status": "skipped_duplicate",
            "source": str(source),
            "message": "This source was already recorded; skipping.",
        }

    try:
        workflow = IngestionWorkflow.create_default(settings)
        result = workflow.run(source, expected_source_type=expected_source_type)
    except (IngestionWorkflowError, OllamaClientError, OSError) as exc:
        manifest.add_failed_file(
            path=ledger_path,
            sha256=digest or "",
            extension=ledger_path.suffix,
            error_reason=f"{type(exc).__name__}: {exc}",
        )
        _save_ledger(manifest)
        raise HTTPException(
            status_code=502,
            detail=f"{exc} (category: {getattr(exc, 'category', 'retryable')})",
        ) from exc
    except Exception as exc:
        manifest.add_failed_file(
            path=ledger_path,
            sha256=digest or "",
            extension=ledger_path.suffix,
            error_reason=f"{type(exc).__name__}: {exc}",
        )
        _save_ledger(manifest)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc

    embedded = bool(getattr(result, "embedding_succeeded", True))
    indexed = bool(getattr(result, "indexing_succeeded", True))
    fully_indexed = embedded and indexed
    engine_error = getattr(result, "engine_error", None)
    graph_succeeded = bool(getattr(result, "graph_succeeded", True))
    chunks_stored = int(getattr(result, "chunks_stored", 0) or 0)

    manifest.add_processed_file(
        path=ledger_path,
        sha256=digest or "",
        extension=ledger_path.suffix,
        generated_note=result.note.filename,
        chunks_stored=chunks_stored,
        embedding_succeeded=embedded,
        indexing_succeeded=indexed,
        status="processed" if fully_indexed else "failed",
        error_reason=None if fully_indexed else (engine_error or "unknown engine failure"),
    )
    _save_ledger(manifest)

    # A new source changed the corpus, so cached BM25/store/QA state is stale.
    deps.invalidate_caches()

    if not fully_indexed:
        raise HTTPException(
            status_code=502,
            detail=(
                f"The note was written, but the source was not fully indexed "
                f"({engine_error or 'unknown engine failure'}). The ledger records "
                f"this attempt as failed; retry ingestion to complete the index."
            ),
        )

    return {
        "status": "processed",
        "source": str(getattr(result.document, "source", ledger_path)),
        "source_type": result.document.source_type,
        "note_title": result.note.title,
        "note_path": str(result.write_result.note_path),
        "created": bool(result.write_result.created),
        "updated": bool(result.write_result.updated),
        "chunks_stored": chunks_stored,
        "embedding_succeeded": embedded,
        "indexing_succeeded": indexed,
        "graph_succeeded": graph_succeeded,
        "graph_warning": (
            None
            if graph_succeeded or not chunks_stored
            else "The note and chunks were indexed, but the knowledge graph could not "
            "be updated for this source. Everything else was saved."
        ),
    }


@router.get("/ingest/capabilities")
def get_ingest_capabilities() -> dict[str, Any]:
    """Source types PAM can actually ingest, from the live ingestor registry."""

    error = deps.settings_error()
    if error is not None:
        return {"available": False, "config_error": error}

    from app.infrastructure.ingestion import DocumentIngestionService

    service = DocumentIngestionService(settings=deps.get_settings())
    extensions = sorted(service.supported_extensions())
    return {
        "available": True,
        "extensions": extensions,
        "extension_count": len(extensions),
        "url_inputs": [
            {"kind": "github", "label": "GitHub repository URL", "source_type": "github_readme"},
            {
                "kind": "youtube",
                "label": "YouTube video URL",
                "source_type": "youtube_transcript",
            },
        ],
    }
