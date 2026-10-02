"""Domain models for V2 generation jobs.

A generation job tracks one asynchronous generation request through an
explicit lifecycle. It is a pure value object: the lifecycle functions here
perform no filesystem access, no network access, and no mutation — every
state change returns a new job. Persistence lives in
``app.infrastructure.jobs``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.generation import GenerationRequest


class GenerationJobStatus(StrEnum):
    """Lifecycle states for a generation job."""

    PENDING = "pending"
    PROCESSING = "processing"
    VALIDATING = "validating"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


_ALLOWED_TRANSITIONS: dict[GenerationJobStatus, frozenset[GenerationJobStatus]] = {
    GenerationJobStatus.PENDING: frozenset(
        {GenerationJobStatus.PROCESSING, GenerationJobStatus.CANCELLED}
    ),
    GenerationJobStatus.PROCESSING: frozenset(
        {
            GenerationJobStatus.VALIDATING,
            GenerationJobStatus.DONE,
            GenerationJobStatus.FAILED,
            GenerationJobStatus.CANCELLED,
        }
    ),
    GenerationJobStatus.VALIDATING: frozenset(
        {GenerationJobStatus.DONE, GenerationJobStatus.FAILED}
    ),
    GenerationJobStatus.DONE: frozenset(),
    GenerationJobStatus.FAILED: frozenset(),
    GenerationJobStatus.CANCELLED: frozenset(),
}


class InvalidJobTransitionError(ValueError):
    """An explicit lifecycle violation (never a silent state change)."""


class GenerationJob(BaseModel):
    """One tracked generation request and its lifecycle state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    request: GenerationRequest
    status: GenerationJobStatus = GenerationJobStatus.PENDING
    progress: int = Field(default=0, ge=0, le=100)
    stage: str = ""
    message: str = ""
    created_at: datetime
    updated_at: datetime
    error: str | None = None

    @classmethod
    def create(cls, request: GenerationRequest) -> GenerationJob:
        """Create a new job in PENDING state with a stable unique id."""

        now = datetime.now(UTC)
        return cls(
            job_id=uuid4().hex,
            request=request,
            status=GenerationJobStatus.PENDING,
            progress=0,
            stage="",
            message="",
            created_at=now,
            updated_at=now,
            error=None,
        )


def transition(job: GenerationJob, to_status: GenerationJobStatus) -> GenerationJob:
    """Move a job to a new lifecycle state, rejecting invalid transitions."""

    if to_status not in _ALLOWED_TRANSITIONS[job.status]:
        raise InvalidJobTransitionError(
            f"Cannot transition job {job.job_id} from "
            f"'{job.status.value}' to '{to_status.value}'."
        )
    return job.model_copy(
        update={"status": to_status, "updated_at": datetime.now(UTC)}
    )


def set_progress(
    job: GenerationJob, progress: int, *, stage: str = "", message: str = ""
) -> GenerationJob:
    """Record bounded progress (0-100) with an optional stage/message."""

    if not 0 <= progress <= 100:
        raise ValueError(f"Job progress must be within 0-100, got {progress}.")
    return job.model_copy(
        update={
            "progress": progress,
            "stage": stage,
            "message": message,
            "updated_at": datetime.now(UTC),
        }
    )


def fail(job: GenerationJob, error: str) -> GenerationJob:
    """Move a job to FAILED, preserving the failure reason."""

    reason = error.strip()
    if not reason:
        raise ValueError("A failed job must carry a non-empty error.")
    moved = transition(job, GenerationJobStatus.FAILED)
    return moved.model_copy(update={"error": reason, "updated_at": datetime.now(UTC)})


def cancel(job: GenerationJob) -> GenerationJob:
    """Move a job to CANCELLED, keeping its last progress and stage."""

    return transition(job, GenerationJobStatus.CANCELLED)
