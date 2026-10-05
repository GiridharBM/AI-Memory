"""End-to-end V2-H executor runs for image generation (stubbed runtime)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image as PILImage
from pydantic import BaseModel

from app.application.generation_errors import HandlerError
from app.application.generation_executor import GenerationExecutor
from app.application.image_handler import ImageTaskHandler
from app.application.task_handler import register_handlers
from app.core.config import ImageGenerationSettings
from app.domain.artifacts import ArtifactKind, ProvenanceRole
from app.domain.generation import GenerationRequest
from app.domain.jobs import GenerationJobStatus
from app.domain.scopes import MemoryScope
from app.infrastructure.artifacts import ArtifactStore, ProvenanceStore
from app.infrastructure.image_runtime import ImageResult
from app.infrastructure.jobs import GenerationJobStore
from app.infrastructure.search import SearchHit


class StubSearchService:
    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filter: dict[str, object] | None = None,  # noqa: A002 - mirrors service signature
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        return [
            SearchHit(text="body a", source="a.md", score=0.9, entry_id="a.md::0"),
            SearchHit(text="body b", source="b.md", score=0.8, entry_id="b.md::0"),
        ]


class ScriptedPlanner:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)

    def __call__(
        self, system_prompt: str, user_prompt: str, model: type[BaseModel]
    ) -> Any:
        if not self._responses:
            raise AssertionError("Fake planner called more times than scripted.")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return model.model_validate(response)


class StubRuntime:
    def __init__(self, fail: Exception | None = None) -> None:
        self._fail = fail

    def generate(self, **kwargs: object) -> ImageResult:
        if self._fail is not None:
            raise self._fail
        width = kwargs["width"]
        height = kwargs["height"]
        assert isinstance(width, int) and isinstance(height, int)
        return ImageResult(
            image=PILImage.new("RGB", (width, height)),
            width=width,
            height=height,
            seed=7,
            model_id=str(kwargs["model_id"]),
            model_revision=str(kwargs["model_revision"]),
            scheduler="EulerDiscreteScheduler",
            elapsed_seconds=2.0,
        )


def _plan() -> dict[str, object]:
    return {"prompt": "A misty forest.", "negative_prompt": "", "title": "Forest"}


def _executor(
    tmp_path: Path,
    planner: list[object] | None = None,
    runtime_fail: Exception | None = None,
    cancelled: bool = False,
) -> GenerationExecutor:
    return GenerationExecutor(
        job_store=GenerationJobStore(tmp_path / "jobs.json"),
        artifact_store=ArtifactStore(tmp_path / "artifacts.json"),
        provenance_store=ProvenanceStore(tmp_path / "provenance.json"),
        handlers=register_handlers(
            ImageTaskHandler(
                generate_json=ScriptedPlanner(
                    list(planner) if planner is not None else [_plan()]
                ),
                image_runtime=StubRuntime(fail=runtime_fail),
                image_config=ImageGenerationSettings(),
                artifact_root=tmp_path / "artifacts",
                project_root=tmp_path,
            ),
        ),
        search_service=StubSearchService(),
        is_cancelled=(lambda: True) if cancelled else None,
    )


def _request(config: dict[str, object] | None = None) -> GenerationRequest:
    return GenerationRequest(
        task_type="image",  # type: ignore[arg-type]
        memory_scope=MemoryScope.all(),
        config=config or {},  # type: ignore[arg-type]
    )


def test_image_task_accepted_at_submit(tmp_path: Path) -> None:
    executor = _executor(tmp_path)

    job = executor.submit(_request())

    assert job.status is GenerationJobStatus.PENDING
    assert job.request.task_type.value == "image"


def test_image_end_to_end(tmp_path: Path) -> None:
    executor = _executor(tmp_path)

    outcome = executor.run(_request())

    assert outcome.job.status is GenerationJobStatus.DONE
    assert outcome.job.progress == 100
    assert outcome.artifact_id is not None
    artifact = ArtifactStore(tmp_path / "artifacts.json").get(outcome.artifact_id)
    assert artifact is not None
    assert artifact.kind is ArtifactKind.IMAGE
    assert artifact.job_id == outcome.job.job_id
    assert artifact.title == "Forest"
    assert artifact.content is None
    assert artifact.content_ref is not None
    assert artifact.content_ref.endswith(".png")
    assert not Path(artifact.content_ref).is_absolute()
    assert (tmp_path / artifact.content_ref).is_file()
    assert artifact.model_role == outcome.job.request.model_role
    records = ProvenanceStore(tmp_path / "provenance.json").for_artifact(
        outcome.artifact_id
    )
    assert len(records) == 2
    assert all(record.role is ProvenanceRole.EVIDENCE_CHUNK for record in records)
    reloaded = GenerationJobStore(tmp_path / "jobs.json").get(outcome.job.job_id)
    assert reloaded is not None and reloaded.status is GenerationJobStatus.DONE


def test_planner_failure_marks_job_failed(tmp_path: Path) -> None:
    executor = _executor(tmp_path, planner=[RuntimeError("ollama down")])

    with pytest.raises(HandlerError):
        executor.run(_request())

    jobs = GenerationJobStore(tmp_path / "jobs.json").list_jobs()
    assert len(jobs) == 1
    assert jobs[0].status is GenerationJobStatus.FAILED
    assert ArtifactStore(tmp_path / "artifacts.json").list_artifacts() == []


def test_runtime_failure_marks_job_failed(tmp_path: Path) -> None:
    executor = _executor(tmp_path, runtime_fail=RuntimeError("CUDA OOM"))

    with pytest.raises(HandlerError):
        executor.run(_request())

    jobs = GenerationJobStore(tmp_path / "jobs.json").list_jobs()
    assert jobs[0].status is GenerationJobStatus.FAILED
    assert ArtifactStore(tmp_path / "artifacts.json").list_artifacts() == []


def test_cancellation_before_generation(tmp_path: Path) -> None:
    executor = _executor(tmp_path, cancelled=True)

    outcome = executor.run(_request())

    assert outcome.job.status is GenerationJobStatus.CANCELLED
    assert outcome.artifact_id is None
    assert ArtifactStore(tmp_path / "artifacts.json").list_artifacts() == []
