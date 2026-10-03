"""End-to-end V2-D executor runs for reports and presentations."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.application.generation_errors import HandlerError
from app.application.generation_executor import GenerationExecutor
from app.application.presentation_handler import PresentationTaskHandler
from app.application.report_handler import ReportTaskHandler
from app.application.task_handler import register_handlers
from app.domain.artifacts import ArtifactKind
from app.domain.generation import GenerationRequest
from app.domain.jobs import GenerationJobStatus
from app.domain.scopes import MemoryScope
from app.infrastructure.artifacts import ArtifactStore, ProvenanceStore
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


def _report_payload(count: int) -> dict[str, object]:
    return {
        "title": "Report",
        "summary": "Summary.",
        "sections": [
            {
                "heading": f"Section {i}",
                "paragraphs": [f"Paragraph {i}."],
                "bullets": [f"point {i}"],
                "references": ["a.md"],
            }
            for i in range(count)
        ],
    }


def _presentation_payload(count: int) -> dict[str, object]:
    return {
        "title": "Deck",
        "slides": [
            {
                "title": f"Slide {i}",
                "bullets": [f"bullet {i}a", f"bullet {i}b"],
                "speaker_notes": f"notes {i}",
            }
            for i in range(count)
        ],
    }


class ScriptedGenerate:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)

    def __call__(self, system_prompt: str, user_prompt: str, model: type) -> object:
        if not self._responses:
            raise AssertionError("Fake LLM called more times than scripted.")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return model.model_validate(response)


def _executor(
    tmp_path: Path, report: object = None, presentation: object = None
) -> GenerationExecutor:
    report_responses = (
        report if isinstance(report, list) else [_report_payload(2) if report is None else report]
    )
    presentation_responses = (
        presentation
        if isinstance(presentation, list)
        else [_presentation_payload(2) if presentation is None else presentation]
    )
    return GenerationExecutor(
        job_store=GenerationJobStore(tmp_path / "jobs.json"),
        artifact_store=ArtifactStore(tmp_path / "artifacts.json"),
        provenance_store=ProvenanceStore(tmp_path / "provenance.json"),
        handlers=register_handlers(
            ReportTaskHandler(ScriptedGenerate(report_responses)),
            PresentationTaskHandler(
                ScriptedGenerate(presentation_responses),
                artifact_root=tmp_path / "artifacts",
                project_root=tmp_path,
            ),
        ),
        search_service=StubSearchService(),
    )


def _request(task: str, config: dict[str, object]) -> GenerationRequest:
    return GenerationRequest(
        task_type=task,  # type: ignore[arg-type]
        memory_scope=MemoryScope.all(),
        config=config,  # type: ignore[arg-type]
    )


def test_report_end_to_end(tmp_path: Path) -> None:
    executor = _executor(tmp_path)

    outcome = executor.run(_request("report", {"section_count": 2}))

    assert outcome.job.status is GenerationJobStatus.DONE
    assert outcome.job.progress == 100
    assert outcome.artifact_id is not None
    artifact = ArtifactStore(tmp_path / "artifacts.json").get(outcome.artifact_id)
    assert artifact is not None
    assert artifact.kind is ArtifactKind.REPORT
    assert artifact.job_id == outcome.job.job_id
    assert artifact.content is not None and artifact.content.startswith("# Report")
    records = ProvenanceStore(tmp_path / "provenance.json").for_artifact(
        outcome.artifact_id
    )
    assert len(records) == 2 * 2
    reloaded = GenerationJobStore(tmp_path / "jobs.json").get(outcome.job.job_id)
    assert reloaded is not None and reloaded.status is GenerationJobStatus.DONE


def test_presentation_end_to_end(tmp_path: Path) -> None:
    executor = _executor(tmp_path)

    outcome = executor.run(_request("ppt", {"slide_count": 2}))

    assert outcome.job.status is GenerationJobStatus.DONE
    assert outcome.artifact_id is not None
    artifact = ArtifactStore(tmp_path / "artifacts.json").get(outcome.artifact_id)
    assert artifact is not None
    assert artifact.kind is ArtifactKind.PPT
    assert artifact.content_ref is not None
    assert artifact.content_ref.endswith(".pptx")
    assert not Path(artifact.content_ref).is_absolute()
    assert (tmp_path / artifact.content_ref).exists()
    records = ProvenanceStore(tmp_path / "provenance.json").for_artifact(
        outcome.artifact_id
    )
    assert len(records) == 2 * 2


def test_failed_generation_marks_job_failed(tmp_path: Path) -> None:
    executor = _executor(tmp_path, report=[ValueError("bad"), ValueError("bad")])

    with pytest.raises(HandlerError):
        executor.run(_request("report", {"section_count": 2}))

    jobs = GenerationJobStore(tmp_path / "jobs.json").list_jobs()
    assert len(jobs) == 1
    assert jobs[0].status is GenerationJobStatus.FAILED
    assert ArtifactStore(tmp_path / "artifacts.json").list_artifacts() == []


def test_renderer_failure_marks_job_failed(tmp_path: Path) -> None:
    (tmp_path / "artifacts").mkdir()
    blocker = tmp_path / "artifacts" / "blocked.pptx"
    blocker.write_text("not a directory", encoding="utf-8")
    executor = GenerationExecutor(
        job_store=GenerationJobStore(tmp_path / "jobs.json"),
        artifact_store=ArtifactStore(tmp_path / "artifacts.json"),
        provenance_store=ProvenanceStore(tmp_path / "provenance.json"),
        handlers=register_handlers(
            ReportTaskHandler(ScriptedGenerate([_report_payload(2)])),
            PresentationTaskHandler(
                ScriptedGenerate([_presentation_payload(1)]),
                artifact_root=blocker,
                project_root=tmp_path,
            ),
        ),
        search_service=StubSearchService(),
    )

    with pytest.raises(HandlerError):
        executor.run(_request("ppt", {"slide_count": 1}))

    jobs = GenerationJobStore(tmp_path / "jobs.json").list_jobs()
    assert jobs[0].status is GenerationJobStatus.FAILED


def test_cancellation_before_generation(tmp_path: Path) -> None:
    executor = GenerationExecutor(
        job_store=GenerationJobStore(tmp_path / "jobs.json"),
        artifact_store=ArtifactStore(tmp_path / "artifacts.json"),
        provenance_store=ProvenanceStore(tmp_path / "provenance.json"),
        handlers=register_handlers(
            ReportTaskHandler(ScriptedGenerate([_report_payload(2)])),
            PresentationTaskHandler(
                ScriptedGenerate([_presentation_payload(2)]),
                artifact_root=tmp_path / "artifacts",
                project_root=tmp_path,
            ),
        ),
        search_service=StubSearchService(),
        is_cancelled=lambda: True,
    )

    outcome = executor.run(_request("report", {"section_count": 2}))

    assert outcome.job.status is GenerationJobStatus.CANCELLED
    assert outcome.artifact_id is None
    assert ArtifactStore(tmp_path / "artifacts.json").list_artifacts() == []
