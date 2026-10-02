"""Tests for the V2 generation-job lifecycle and persistence."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.generation import GenerationRequest
from app.domain.jobs import (
    GenerationJob,
    GenerationJobStatus,
    InvalidJobTransitionError,
    cancel,
    fail,
    set_progress,
    transition,
)
from app.domain.scopes import MemoryScope
from app.infrastructure.jobs import GenerationJobStore


def _request() -> GenerationRequest:
    return GenerationRequest(task_type="flashcards", memory_scope=MemoryScope.all())


def _store(tmp_path: Path) -> GenerationJobStore:
    return GenerationJobStore(tmp_path / "jobs" / "generation_jobs.json")


def test_job_creation_starts_pending() -> None:
    job = GenerationJob.create(_request())

    assert job.job_id
    assert job.status is GenerationJobStatus.PENDING
    assert job.progress == 0
    assert job.error is None
    assert job.created_at <= job.updated_at


def test_valid_lifecycle_transitions() -> None:
    job = GenerationJob.create(_request())

    processing = transition(job, GenerationJobStatus.PROCESSING)
    assert processing.status is GenerationJobStatus.PROCESSING

    validating = transition(processing, GenerationJobStatus.VALIDATING)
    assert validating.status is GenerationJobStatus.VALIDATING

    done = transition(validating, GenerationJobStatus.DONE)
    assert done.status is GenerationJobStatus.DONE

    direct = transition(transition(job, GenerationJobStatus.PROCESSING), GenerationJobStatus.DONE)
    assert direct.status is GenerationJobStatus.DONE

    failed = fail(transition(job, GenerationJobStatus.PROCESSING), "boom")
    assert failed.status is GenerationJobStatus.FAILED
    assert failed.error == "boom"

    cancelled = cancel(job)
    assert cancelled.status is GenerationJobStatus.CANCELLED


def test_transitions_are_immutable_snapshots() -> None:
    job = GenerationJob.create(_request())

    moved = transition(job, GenerationJobStatus.PROCESSING)

    assert job.status is GenerationJobStatus.PENDING
    assert moved.status is GenerationJobStatus.PROCESSING
    assert moved.job_id == job.job_id
    assert moved.updated_at >= job.updated_at


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        (GenerationJobStatus.PENDING, GenerationJobStatus.VALIDATING),
        (GenerationJobStatus.PENDING, GenerationJobStatus.DONE),
        (GenerationJobStatus.PENDING, GenerationJobStatus.FAILED),
        (GenerationJobStatus.VALIDATING, GenerationJobStatus.PROCESSING),
        (GenerationJobStatus.VALIDATING, GenerationJobStatus.CANCELLED),
        (GenerationJobStatus.DONE, GenerationJobStatus.PROCESSING),
        (GenerationJobStatus.FAILED, GenerationJobStatus.PENDING),
        (GenerationJobStatus.CANCELLED, GenerationJobStatus.PENDING),
    ],
)
def test_invalid_lifecycle_transitions_fail_explicitly(
    from_status: GenerationJobStatus, to_status: GenerationJobStatus
) -> None:
    job = GenerationJob.create(_request()).model_copy(update={"status": from_status})

    with pytest.raises(InvalidJobTransitionError):
        transition(job, to_status)


def test_progress_validation() -> None:
    job = GenerationJob.create(_request())

    assert set_progress(job, 0).progress == 0
    assert set_progress(job, 57).progress == 57
    assert set_progress(job, 100).progress == 100
    with pytest.raises(ValueError):
        set_progress(job, -1)
    with pytest.raises(ValueError):
        set_progress(job, 101)
    with pytest.raises(ValidationError):
        GenerationJob.model_validate({**job.model_dump(), "progress": 101})


def test_stage_and_message_updates() -> None:
    job = GenerationJob.create(_request())

    updated = set_progress(job, 40, stage="rendering", message="slide 4 of 10")

    assert updated.progress == 40
    assert updated.stage == "rendering"
    assert updated.message == "slide 4 of 10"
    assert job.stage == ""


def test_failure_requires_an_error() -> None:
    job = transition(GenerationJob.create(_request()), GenerationJobStatus.PROCESSING)

    with pytest.raises(ValueError):
        fail(job, "   ")


def test_cancellation_rules() -> None:
    pending = GenerationJob.create(_request())
    processing = transition(pending, GenerationJobStatus.PROCESSING)
    done = transition(processing, GenerationJobStatus.DONE)

    assert cancel(pending).status is GenerationJobStatus.CANCELLED
    kept = set_progress(processing, 63, stage="rendering", message="halfway")
    assert cancel(kept).progress == 63
    assert cancel(kept).stage == "rendering"
    with pytest.raises(InvalidJobTransitionError):
        cancel(done)


def test_store_save_load_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)

    job = store.create(_request())

    assert store.get(job.job_id) == job


def test_store_update_persists_status_progress_and_error(tmp_path: Path) -> None:
    store = _store(tmp_path)
    job = store.create(_request())

    moved = set_progress(
        fail(transition(job, GenerationJobStatus.PROCESSING), "nope"), 12
    )
    store.update(moved)

    reloaded = store.get(job.job_id)
    assert reloaded == moved
    assert reloaded is not None
    assert reloaded.status is GenerationJobStatus.FAILED
    assert reloaded.error == "nope"


def test_store_update_unknown_job_fails_explicitly(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with pytest.raises(KeyError):
        store.update(GenerationJob.create(_request()))


def test_store_lists_multiple_jobs_deterministically(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.create(_request())
    second = store.create(_request())

    listed = store.list_jobs()

    assert {job.job_id for job in listed} == {first.job_id, second.job_id}
    assert [job.job_id for job in store.list_jobs()] == [job.job_id for job in listed]


def test_store_survives_new_instance(tmp_path: Path) -> None:
    store = _store(tmp_path)
    job = store.create(_request())
    store.update(transition(job, GenerationJobStatus.PROCESSING))

    fresh = _store(tmp_path)

    assert fresh.get(job.job_id) == store.get(job.job_id)


def test_inflight_states_survive_reload_unchanged(tmp_path: Path) -> None:
    store = _store(tmp_path)
    processing = store.create(_request())
    store.update(transition(processing, GenerationJobStatus.PROCESSING))
    validating = store.create(_request())
    started = transition(validating, GenerationJobStatus.PROCESSING)
    store.update(transition(started, GenerationJobStatus.VALIDATING))

    fresh = _store(tmp_path)
    reloaded_processing = fresh.get(processing.job_id)
    reloaded_validating = fresh.get(validating.job_id)

    assert reloaded_processing is not None
    assert reloaded_processing.status is GenerationJobStatus.PROCESSING
    assert reloaded_validating is not None
    assert reloaded_validating.status is GenerationJobStatus.VALIDATING


def test_request_preserved_through_serialization(tmp_path: Path) -> None:
    request = GenerationRequest(
        task_type="quiz",
        memory_scope=MemoryScope.documents(["b.md", "a.md"]),
        config={"count": 5},
        provenance="strict",
    )
    store = _store(tmp_path)

    job = store.create(request)

    assert store.get(job.job_id) is not None
    assert store.get(job.job_id).request == request  # type: ignore[union-attr]


def test_store_deterministic_serialization(tmp_path: Path) -> None:
    store = _store(tmp_path)
    job = store.create(_request())

    first = (tmp_path / "jobs" / "generation_jobs.json").read_text(encoding="utf-8")
    fresh = _store(tmp_path)
    fresh.update(job)
    second = (tmp_path / "jobs" / "generation_jobs.json").read_text(encoding="utf-8")

    assert first == second
