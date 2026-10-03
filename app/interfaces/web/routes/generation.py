"""Generation routes: submit generation jobs, poll them, cancel them.

Long-running work never blocks the request: POST /generation persists a
PENDING job and starts a daemon thread running it to completion. The
GenerationJobStore is the single source of truth both sides observe, and
the thread's cancellation predicate re-reads it so a cancel request is
always honored at the next checkpoint.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar, cast

from fastapi import APIRouter, HTTPException

from app.application.flashcard_handler import FlashcardTaskHandler
from app.application.generation_errors import UnsupportedTaskError
from app.application.generation_executor import GenerationExecutor
from app.application.presentation_handler import PresentationTaskHandler
from app.application.quiz_handler import QuizTaskHandler
from app.application.report_handler import ReportTaskHandler
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.generation import GenerationRequest
from app.domain.jobs import (
    GenerationJob,
    GenerationJobStatus,
    InvalidJobTransitionError,
    cancel,
)
from app.infrastructure.artifacts import ArtifactStore, ProvenanceStore
from app.infrastructure.jobs import GenerationJobStore
from app.infrastructure.llm import OllamaClient, OllamaRequest
from app.infrastructure.search import SearchService
from app.interfaces.web import deps

router = APIRouter()

logger = get_logger(__name__)

ResponseModelT = TypeVar("ResponseModelT")


def _stores(
    settings: Settings,
) -> tuple[GenerationJobStore, ArtifactStore, ProvenanceStore]:
    """Build the three generation stores under the manifest root."""

    root = settings.paths.manifest_root
    return (
        GenerationJobStore(root / "generation_jobs.json"),
        ArtifactStore(root / "artifacts.json"),
        ProvenanceStore(root / "provenance.json"),
    )


def _job_payload(job: GenerationJob) -> dict[str, Any]:
    """Project a job to its stable API representation."""

    return {
        "job_id": job.job_id,
        "task_type": job.request.task_type.value,
        "status": job.status.value,
        "progress": job.progress,
        "stage": job.stage,
        "message": job.message,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "error": job.error,
    }


def _generate_json_factory(
    client: OllamaClient, model: str
) -> Callable[[str, str, type[ResponseModelT]], ResponseModelT]:
    """Bind a structured-output callable for one model (handler seam)."""

    def generate(
        system_prompt: str, user_prompt: str, response_model: type[ResponseModelT]
    ) -> ResponseModelT:
        return cast(
            ResponseModelT,
            client.generate_json(
                OllamaRequest(
                    prompt=user_prompt, system_prompt=system_prompt, model=model
                ),
                response_model=response_model,
            ),
        )

    return generate


def _build_executor(
    settings: Settings,
    *,
    model_role: str = "general_text",
    is_cancelled: Callable[[], bool] | None = None,
) -> GenerationExecutor:
    """Wire real handlers, stores, and search for one execution context."""

    job_store, artifact_store, provenance_store = _stores(settings)
    client = OllamaClient(settings.ollama)
    model = settings.models.model_for(model_role)
    generate = _generate_json_factory(client, model)
    handlers = {}
    for handler in (
        FlashcardTaskHandler(generate_json=generate),
        QuizTaskHandler(generate_json=generate),
        ReportTaskHandler(generate_json=generate),
        PresentationTaskHandler(
            generate_json=generate,
            artifact_root=settings.paths.artifact_root,
            project_root=settings.paths.project_root,
        ),
    ):
        handlers[handler.task_type] = handler
    return GenerationExecutor(
        job_store=job_store,
        artifact_store=artifact_store,
        provenance_store=provenance_store,
        handlers=handlers,
        search_service=SearchService.create_default(settings),
        is_cancelled=is_cancelled,
    )


def _is_cancelled(store_path: Path, job_id: str) -> bool:
    """Fresh store read so a cancel request is never missed by stale cache."""

    current = GenerationJobStore(store_path).get(job_id)
    return current is not None and current.status == GenerationJobStatus.CANCELLED


def _run_job(settings: Settings, job_id: str) -> None:
    """Background entry: execute a submitted job; failures stay FAILED."""

    store_path = settings.paths.manifest_root / "generation_jobs.json"

    def cancelled() -> bool:
        return _is_cancelled(store_path, job_id)

    executor = _build_executor(settings, is_cancelled=cancelled)
    try:
        executor.execute_job(job_id)
    except Exception:
        logger.exception("Background generation failed.", extra={"job_id": job_id})


def _launch(target: Callable[..., None], args: tuple[object, ...] = ()) -> None:
    """Start a daemon thread; patched to run inline in tests."""

    thread = threading.Thread(target=target, args=args, daemon=True)
    thread.start()


def _require_settings() -> Settings:
    error = deps.settings_error()
    if error is not None:
        raise HTTPException(status_code=503, detail=error)
    return deps.get_settings()


@router.post("/generation", status_code=202)
def post_generation(request: GenerationRequest) -> dict[str, Any]:
    """Submit a generation request; returns the PENDING job immediately."""

    settings = _require_settings()
    executor = _build_executor(settings, model_role=request.model_role)
    try:
        job = executor.submit(request)
    except UnsupportedTaskError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _launch(_run_job, (settings, job.job_id))
    return _job_payload(job)


@router.get("/jobs")
def list_jobs() -> dict[str, Any]:
    """All generation jobs in deterministic creation order."""

    settings = _require_settings()
    job_store, _, _ = _stores(settings)
    jobs = job_store.list_jobs()
    return {"jobs": [_job_payload(job) for job in jobs], "total": len(jobs)}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    """One generation job, or 404 when unknown."""

    settings = _require_settings()
    job_store, _, _ = _stores(settings)
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Generation job not found.")
    return _job_payload(job)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    """Cancel a PENDING or PROCESSING job; terminal states 409."""

    settings = _require_settings()
    job_store, _, _ = _stores(settings)
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Generation job not found.")
    try:
        cancelled = cancel(job)
    except InvalidJobTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    job_store.update(cancelled)
    return _job_payload(cancelled)
