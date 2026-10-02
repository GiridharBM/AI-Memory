"""Tests for the V2 generation executor (deterministic fake handler)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from app.application.generation_errors import UnsupportedTaskError
from app.application.generation_executor import GenerationExecutor
from app.application.retrieval_adapter import RetrievalPort
from app.application.task_handler import register_handlers
from app.domain.artifacts import ArtifactKind, ProvenanceRecord, ProvenanceRole
from app.domain.generation import GenerationRequest, GenerationTaskType
from app.domain.generation_context import GenerationContext
from app.domain.generation_result import GenerationResult
from app.domain.jobs import GenerationJobStatus
from app.domain.scopes import MemoryScope
from app.infrastructure.artifacts import ArtifactStore, ProvenanceStore
from app.infrastructure.jobs import GenerationJobStore
from app.infrastructure.search import SearchHit


class DeterministicFakeHandler:
    """Test-only handler: fixed output derived from task type and hits."""

    task_type = GenerationTaskType.FLASHCARDS

    def __init__(self) -> None:
        self.calls: list[GenerationContext] = []

    def handle(self, context: GenerationContext) -> GenerationResult:
        self.calls.append(context)
        lines = [f"Q: {hit.source}" for hit in context.hits] or ["Q: empty"]
        return GenerationResult(
            kind=ArtifactKind.FLASHCARDS,
            title=f"Cards for {context.request.task_type.value}",
            content="\n".join(lines),
            metadata={"hits": str(len(context.hits))},
            provenance=tuple(
                ProvenanceRecord(
                    artifact_id="pending",
                    source_id=hit.source,
                    role=ProvenanceRole.EVIDENCE_CHUNK,
                    chunk_id=hit.entry_id,
                )
                for hit in context.hits
            ),
        )


class StubSearchService:
    def __init__(self, sources: tuple[str, ...] = ("a.md", "b.md")) -> None:
        self._sources = sources

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filter: dict[str, object] | None = None,  # noqa: A002 - mirrors service signature
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        sources = self._sources
        if filter is not None and "source" in filter:
            wanted = str(filter["source"])
            sources = tuple(source for source in sources if source == wanted)
        return [
            SearchHit(text="body", source=source, score=0.9, entry_id=f"{source}::0")
            for source in sources
        ]


def _request(**overrides: object) -> GenerationRequest:
    values: dict[str, object] = {
        "task_type": "flashcards",
        "memory_scope": MemoryScope.documents(["a.md", "b.md"]),
    }
    values.update(overrides)
    return GenerationRequest(**values)  # type: ignore[arg-type]


def _executor(
    tmp_path: Path,
    handler: DeterministicFakeHandler | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    search_service: RetrievalPort | None = None,
) -> tuple[GenerationExecutor, DeterministicFakeHandler]:
    fake = handler or DeterministicFakeHandler()
    executor = GenerationExecutor(
        job_store=GenerationJobStore(tmp_path / "jobs.json"),
        artifact_store=ArtifactStore(tmp_path / "artifacts.json"),
        provenance_store=ProvenanceStore(tmp_path / "provenance.json"),
        handlers=register_handlers(fake),
        search_service=search_service or StubSearchService(),
        is_cancelled=is_cancelled,
    )
    return executor, fake


def test_complete_happy_path(tmp_path: Path) -> None:
    executor, fake = _executor(tmp_path)

    outcome = executor.run(_request())

    assert outcome.job.status is GenerationJobStatus.DONE
    assert outcome.job.progress == 100
    assert outcome.artifact_id is not None
    assert len(fake.calls) == 1


def test_job_lifecycle_transitions(tmp_path: Path) -> None:
    executor, _ = _executor(tmp_path)
    seen: list[GenerationJobStatus] = []
    store = executor._job_store
    original_update = store.update

    def tracking_update(job):  # type: ignore[no-untyped-def]
        seen.append(job.status)
        return original_update(job)

    store.update = tracking_update  # type: ignore[method-assign]
    executor.run(_request())

    assert seen[0] is GenerationJobStatus.PROCESSING
    assert GenerationJobStatus.VALIDATING in seen
    assert seen[-1] is GenerationJobStatus.DONE


def test_scope_resolution_retrieval_and_handler_invocation(tmp_path: Path) -> None:
    executor, fake = _executor(tmp_path)

    executor.run(_request())

    assert [hit.source for hit in fake.calls[0].hits] == ["a.md", "b.md"]
    assert fake.calls[0].scope.restricted is True


def test_validation_artifact_and_provenance_persisted(tmp_path: Path) -> None:
    executor, _ = _executor(tmp_path)

    outcome = executor.run(_request())
    assert outcome.artifact_id is not None

    artifact_store = ArtifactStore(tmp_path / "artifacts.json")
    provenance_store = ProvenanceStore(tmp_path / "provenance.json")
    artifact = artifact_store.get(outcome.artifact_id)
    assert artifact is not None
    assert artifact.kind is ArtifactKind.FLASHCARDS
    records = provenance_store.for_artifact(outcome.artifact_id)
    assert {record.source_id for record in records} == {"a.md", "b.md"}


def test_job_artifact_linkage_and_request_preservation(tmp_path: Path) -> None:
    executor, _ = _executor(tmp_path)
    request = _request(config={"count": 3}, model_role="vision")

    outcome = executor.run(request)

    artifact_store = ArtifactStore(tmp_path / "artifacts.json")
    artifacts = artifact_store.list_for_job(outcome.job.job_id)
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.request == request
    assert artifact.memory_scope == request.memory_scope
    assert artifact.model_role == "vision"
    assert artifact.request.config == {"count": 3}


def test_failure_marks_job_failed(tmp_path: Path) -> None:
    class BrokenHandler(DeterministicFakeHandler):
        def handle(self, context: GenerationContext) -> GenerationResult:
            raise RuntimeError("model exploded")

    executor, _ = _executor(tmp_path, handler=BrokenHandler())

    with pytest.raises(Exception, match="model exploded"):
        executor.run(_request())

    jobs = GenerationJobStore(tmp_path / "jobs.json").list_jobs()
    assert len(jobs) == 1
    assert jobs[0].status is GenerationJobStatus.FAILED
    assert "model exploded" in (jobs[0].error or "")


def test_unsupported_task_fails_without_job(tmp_path: Path) -> None:
    executor, _ = _executor(tmp_path)

    with pytest.raises(UnsupportedTaskError):
        executor.run(_request(task_type="quiz"))

    assert GenerationJobStore(tmp_path / "jobs.json").list_jobs() == []


def test_cancellation_before_retrieval(tmp_path: Path) -> None:
    executor, _ = _executor(tmp_path, is_cancelled=lambda: True)

    outcome = executor.run(_request())

    assert outcome.job.status is GenerationJobStatus.CANCELLED
    assert outcome.job.progress == 5
    assert outcome.artifact_id is None


def test_cancellation_before_generation(tmp_path: Path) -> None:
    calls = 0

    def cancel_late() -> bool:
        nonlocal calls
        calls += 1
        return calls > 1

    executor, fake = _executor(tmp_path, is_cancelled=cancel_late)

    outcome = executor.run(_request())

    assert outcome.job.status is GenerationJobStatus.CANCELLED
    assert outcome.job.progress == 40
    assert outcome.job.stage == "generating"
    assert fake.calls == []


def test_cancellation_before_persistence(tmp_path: Path) -> None:
    calls = 0

    def cancel_last() -> bool:
        nonlocal calls
        calls += 1
        return calls > 2

    executor, fake = _executor(tmp_path, is_cancelled=cancel_last)

    outcome = executor.run(_request())

    assert outcome.job.status is GenerationJobStatus.CANCELLED
    assert len(fake.calls) == 1
    assert outcome.artifact_id is None
    assert ArtifactStore(tmp_path / "artifacts.json").list_artifacts() == []


def test_deterministic_output(tmp_path: Path) -> None:
    first_executor, _ = _executor(tmp_path / "one")
    second_executor, _ = _executor(tmp_path / "two")

    first = first_executor.run(_request())
    second = second_executor.run(_request())

    first_store = ArtifactStore(tmp_path / "one" / "artifacts.json")
    second_store = ArtifactStore(tmp_path / "two" / "artifacts.json")
    assert first_store.get(first.artifact_id) is not None
    first_artifact = first_store.get(first.artifact_id)
    second_artifact = second_store.get(second.artifact_id)
    assert first_artifact is not None and second_artifact is not None
    assert first_artifact.content == second_artifact.content
    assert first_artifact.title == second_artifact.title
    assert first_artifact.artifact_id != second_artifact.artifact_id


def test_multiple_jobs_independent(tmp_path: Path) -> None:
    executor, _ = _executor(tmp_path)

    first = executor.run(_request())
    second = executor.run(_request(task_type="flashcards"))

    assert first.job.job_id != second.job.job_id
    assert first.artifact_id != second.artifact_id
    assert len(GenerationJobStore(tmp_path / "jobs.json").list_jobs()) == 2
    assert len(ArtifactStore(tmp_path / "artifacts.json").list_artifacts()) == 2


def test_persistence_integration_after_reload(tmp_path: Path) -> None:
    executor, _ = _executor(tmp_path)
    outcome = executor.run(_request())
    assert outcome.artifact_id is not None

    job = GenerationJobStore(tmp_path / "jobs.json").get(outcome.job.job_id)
    artifact = ArtifactStore(tmp_path / "artifacts.json").get(outcome.artifact_id)
    records = ProvenanceStore(tmp_path / "provenance.json").for_artifact(
        outcome.artifact_id
    )

    assert job is not None and job.status is GenerationJobStatus.DONE
    assert artifact is not None and artifact.job_id == job.job_id
    assert artifact.request.memory_scope == MemoryScope.documents(["a.md", "b.md"])
    assert {record.source_id for record in records} == {"a.md", "b.md"}


class FailingProvenanceStore(ProvenanceStore):
    """Provenance store that fails after a fixed number of successful adds."""

    def __init__(self, path: Path, succeed: int = 0) -> None:
        super().__init__(path)
        self._remaining = succeed

    def add(self, record: ProvenanceRecord) -> ProvenanceRecord:
        if self._remaining <= 0:
            raise OSError("simulated provenance write failure")
        self._remaining -= 1
        return super().add(record)


def _executor_with_provenance(
    tmp_path: Path, succeed: int
) -> tuple[GenerationExecutor, DeterministicFakeHandler]:
    store = GenerationJobStore(tmp_path / "jobs.json")
    artifact_store = ArtifactStore(tmp_path / "artifacts.json")
    provenance_store = FailingProvenanceStore(tmp_path / "provenance.json", succeed)
    fake = DeterministicFakeHandler()
    executor = GenerationExecutor(
        job_store=store,
        artifact_store=artifact_store,
        provenance_store=provenance_store,
        handlers=register_handlers(fake),
        search_service=StubSearchService(),
    )
    return executor, fake


def test_provenance_failure_preserves_artifact_and_fails_job(tmp_path: Path) -> None:
    executor, _ = _executor_with_provenance(tmp_path, succeed=0)

    with pytest.raises(Exception, match="Provenance persistence failed"):
        executor.run(_request())

    jobs = GenerationJobStore(tmp_path / "jobs.json").list_jobs()
    assert len(jobs) == 1
    assert jobs[0].status is GenerationJobStatus.FAILED
    assert "Provenance persistence failed" in (jobs[0].error or "")

    artifacts = ArtifactStore(tmp_path / "artifacts.json").list_for_job(jobs[0].job_id)
    assert len(artifacts) == 1
    assert ProvenanceStore(tmp_path / "provenance.json").for_artifact(
        artifacts[0].artifact_id
    ) == []
    assert GenerationJobStore(tmp_path / "jobs.json").list_jobs()[0].status is not (
        GenerationJobStatus.DONE
    )


def test_partial_provenance_failure_keeps_written_records(tmp_path: Path) -> None:
    executor, _ = _executor_with_provenance(tmp_path, succeed=1)

    with pytest.raises(Exception, match="Provenance persistence failed"):
        executor.run(_request())

    jobs = GenerationJobStore(tmp_path / "jobs.json").list_jobs()
    assert jobs[0].status is GenerationJobStatus.FAILED
    artifacts = ArtifactStore(tmp_path / "artifacts.json").list_for_job(jobs[0].job_id)
    assert len(artifacts) == 1
    records = ProvenanceStore(tmp_path / "provenance.json").for_artifact(
        artifacts[0].artifact_id
    )
    assert [record.source_id for record in records] == ["a.md"]
