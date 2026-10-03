"""Central V2-B generation coordinator.

Owns the full request lifecycle: validate and accept the request, create
and transition the job, resolve scope, retrieve memory, invoke the
registered handler, validate the result, persist artifact and provenance,
and mark the job DONE (or FAILED/CANCELLED with its state preserved).

Progress is deterministic and monotonic within a run:
PENDING 0 → PROCESSING (5 resolving_scope, 10 retrieving, 40 generating)
→ VALIDATING (70) → persisting (85) → DONE 100.

Cancellation is observed at stage boundaries (before retrieval, before
generation, before the validate/persist phase) via an injectable
predicate. State-level only: no thread or process interruption. The third
checkpoint sits before the VALIDATING transition so ``cancel()`` stays
within the Part 2 transition table.

Failure policy for split persistence: artifact and provenance writes are
separate JSON operations with no transaction. If provenance persistence
fails after the artifact was stored, the artifact is PRESERVED (never
compensating-deleted — generated content is not silently destroyed) and
the job is marked FAILED naming the provenance failure. The resulting
state (FAILED job + persisted artifact + missing/incomplete provenance)
stays fully queryable, so recovery is deterministic and auditable.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from pydantic import BaseModel, ConfigDict

from app.application.generation_errors import (
    ArtifactPersistError,
    HandlerError,
    JobCancelled,
    ProvenancePersistError,
    RetrievalError,
    UnsupportedScopeError,
    UnsupportedTaskError,
)
from app.application.generation_validation import validate_result
from app.application.retrieval_adapter import RetrievalPort, build_context
from app.application.task_handler import TaskHandler
from app.domain.artifacts import Artifact, ProvenanceRecord
from app.domain.generation import GenerationRequest, GenerationTaskType
from app.domain.jobs import (
    GenerationJob,
    GenerationJobStatus,
    cancel,
    fail,
    set_progress,
    transition,
)
from app.infrastructure.artifacts import ArtifactStore, ProvenanceStore
from app.infrastructure.jobs import GenerationJobStore

# Stages reported on the job as the pipeline advances.
_STAGE_RESOLVING = "resolving_scope"
_STAGE_RETRIEVING = "retrieving"
_STAGE_GENERATING = "generating"
_STAGE_VALIDATING = "validating"
_STAGE_PERSISTING = "persisting"
_STAGE_DONE = "done"


class ExecutionOutcome(BaseModel):
    """The completed run: final job state plus the artifact it produced, if any."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job: GenerationJob
    artifact_id: str | None = None


class GenerationExecutor:
    """Coordinate one generation request end to end (synchronous)."""

    def __init__(
        self,
        *,
        job_store: GenerationJobStore,
        artifact_store: ArtifactStore,
        provenance_store: ProvenanceStore,
        handlers: Mapping[GenerationTaskType, TaskHandler],
        search_service: RetrievalPort,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> None:
        self._job_store = job_store
        self._artifact_store = artifact_store
        self._provenance_store = provenance_store
        self._handlers = dict(handlers)
        self._search_service = search_service
        self._is_cancelled = is_cancelled or (lambda: False)

    def _save(self, job: GenerationJob) -> GenerationJob:
        self._job_store.update(job)
        return job

    def submit(self, request: GenerationRequest) -> GenerationJob:
        """Create and persist a PENDING job without executing it.

        Lets API callers return a job id immediately and run execution on a
        background thread. The handler check mirrors :meth:`run` so
        unsupported tasks fail before any job exists.
        """

        handler = self._handlers.get(request.task_type)
        if handler is None:
            # No job exists yet: report the unsupported task without one.
            raise UnsupportedTaskError(
                f"No handler registered for task '{request.task_type.value}'."
            )
        return self._job_store.create(request)

    def execute_job(self, job_id: str) -> ExecutionOutcome:
        """Execute a previously submitted job to completion.

        Terminal jobs (DONE/FAILED/CANCELLED) return as-is without
        re-running, so a retried background launch can never duplicate work.
        """

        job = self._job_store.get(job_id)
        if job is None:
            raise KeyError(f"Unknown generation job: {job_id}")
        if job.status in (
            GenerationJobStatus.DONE,
            GenerationJobStatus.FAILED,
            GenerationJobStatus.CANCELLED,
        ):
            return ExecutionOutcome(job=job, artifact_id=None)
        handler = self._handlers.get(job.request.task_type)
        if handler is None:
            raise UnsupportedTaskError(
                f"No handler registered for task '{job.request.task_type.value}'."
            )
        return self._execute(job, handler)

    def run(self, request: GenerationRequest) -> ExecutionOutcome:
        """Execute the full pipeline for one request."""

        return self.execute_job(self.submit(request).job_id)

    def _execute(self, job: GenerationJob, handler: TaskHandler) -> ExecutionOutcome:
        try:
            job = self._save(
                set_progress(
                    transition(job, GenerationJobStatus.PROCESSING),
                    5,
                    stage=_STAGE_RESOLVING,
                )
            )
            if self._is_cancelled():
                raise JobCancelled("Cancelled before retrieval.")

            job = self._save(set_progress(job, 10, stage=_STAGE_RETRIEVING))
            try:
                context = build_context(
                    request=job.request, search_service=self._search_service
                )
            except (UnsupportedScopeError, RetrievalError):
                raise
            except Exception as exc:
                raise RetrievalError(f"Memory retrieval failed: {exc}") from exc

            job = self._save(set_progress(job, 40, stage=_STAGE_GENERATING))
            if self._is_cancelled():
                raise JobCancelled("Cancelled before generation.")
            try:
                result = handler.handle(context)
            except Exception as exc:
                raise HandlerError(f"Task handler failed: {exc}") from exc

            if self._is_cancelled():
                raise JobCancelled("Cancelled before validation and persistence.")
            job = self._save(
                set_progress(
                    transition(job, GenerationJobStatus.VALIDATING),
                    70,
                    stage=_STAGE_VALIDATING,
                )
            )
            validate_result(job.request, result)

            job = self._save(set_progress(job, 85, stage=_STAGE_PERSISTING))
            try:
                artifact = Artifact.create(
                    kind=result.kind,
                    title=result.title,
                    job_id=job.job_id,
                    request=job.request,
                    content=result.content,
                    content_ref=result.content_ref,
                    metadata=dict(result.metadata),
                )
                self._artifact_store.create(artifact)
            except Exception as exc:
                raise ArtifactPersistError(f"Artifact persistence failed: {exc}") from exc
            try:
                for candidate in result.provenance:
                    self._provenance_store.add(
                        ProvenanceRecord(
                            artifact_id=artifact.artifact_id,
                            source_id=candidate.source_id,
                            role=candidate.role,
                            source_type=candidate.source_type,
                            chunk_id=candidate.chunk_id,
                            chunk_index=candidate.chunk_index,
                            start_char=candidate.start_char,
                            end_char=candidate.end_char,
                            kg_node_id=candidate.kg_node_id,
                            quote=candidate.quote,
                        )
                    )
            except Exception as exc:
                raise ProvenancePersistError(
                    f"Provenance persistence failed: {exc}"
                ) from exc

            done = self._save(
                set_progress(
                    transition(job, GenerationJobStatus.DONE), 100, stage=_STAGE_DONE
                )
            )
            return ExecutionOutcome(job=done, artifact_id=artifact.artifact_id)
        except JobCancelled:
            finished = self._save(cancel(job))
            return ExecutionOutcome(job=finished, artifact_id=None)
        except Exception as exc:
            self._save(fail(job, f"{type(exc).__name__}: {exc}"))
            raise
