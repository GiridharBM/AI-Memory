"""End-to-end V2-F executor runs for AI-enriched mind maps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from app.application.generation_errors import HandlerError
from app.application.generation_executor import GenerationExecutor
from app.application.mindmap_handler import MindMapEnrichTaskHandler
from app.application.task_handler import register_handlers
from app.core.config import Settings
from app.domain.artifacts import ArtifactKind
from app.domain.generation import GenerationRequest
from app.domain.jobs import GenerationJobStatus
from app.domain.mindmap import EnrichedMindMap
from app.domain.scopes import MemoryScope
from app.infrastructure.artifacts import ArtifactStore, ProvenanceStore
from app.infrastructure.jobs import GenerationJobStore
from app.infrastructure.search import SearchHit
from app.interfaces.web.routes import generation as generation_routes


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


def _node(node_id: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "label": f"Label {node_id}",
        "node_type": "concept",
        "source": "a.md",
        "description": f"Description of {node_id}.",
        "key_points": [f"point {node_id}"],
    }


def _mindmap_payload(count: int = 2) -> dict[str, Any]:
    return {
        "title": "Map",
        "root_node_id": "n0",
        "nodes": [_node(f"n{i}") for i in range(count)],
        "edges": [
            {"source_id": "n0", "target_id": f"n{i}", "relationship": "related_to"}
            for i in range(1, count)
        ],
    }


class ScriptedGenerate:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)

    def __call__(
        self, system_prompt: str, user_prompt: str, model: type[BaseModel]
    ) -> Any:
        if not self._responses:
            raise AssertionError("Fake LLM called more times than scripted.")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return model.model_validate(response)


def _executor(tmp_path: Path, responses: list[object] | None = None) -> GenerationExecutor:
    scripted: list[object] = (
        list(responses) if responses is not None else [_mindmap_payload(2)]
    )
    return GenerationExecutor(
        job_store=GenerationJobStore(tmp_path / "jobs.json"),
        artifact_store=ArtifactStore(tmp_path / "artifacts.json"),
        provenance_store=ProvenanceStore(tmp_path / "provenance.json"),
        handlers=register_handlers(
            MindMapEnrichTaskHandler(ScriptedGenerate(scripted)),
        ),
        search_service=StubSearchService(),
    )


def _request(config: dict[str, Any] | None = None) -> GenerationRequest:
    return GenerationRequest(
        task_type="mindmap_enrich",  # type: ignore[arg-type]
        memory_scope=MemoryScope.all(),
        config=config or {"node_limit": 2},  # type: ignore[arg-type]
    )


def test_mindmap_end_to_end(tmp_path: Path) -> None:
    executor = _executor(tmp_path)

    outcome = executor.run(_request())

    assert outcome.job.status is GenerationJobStatus.DONE
    assert outcome.job.progress == 100
    assert outcome.artifact_id is not None
    artifact = ArtifactStore(tmp_path / "artifacts.json").get(outcome.artifact_id)
    assert artifact is not None
    assert artifact.kind is ArtifactKind.MINDMAP
    assert artifact.job_id == outcome.job.job_id
    assert artifact.title == "Map"
    assert artifact.content is not None
    parsed = EnrichedMindMap.model_validate_json(artifact.content)
    assert len(parsed.nodes) == 2
    assert artifact.metadata == {"nodes": "2", "edges": "1"}
    assert artifact.content_ref is None
    assert artifact.model_role == outcome.job.request.model_role
    records = ProvenanceStore(tmp_path / "provenance.json").for_artifact(
        outcome.artifact_id
    )
    assert len(records) == 2 * 2
    reloaded = GenerationJobStore(tmp_path / "jobs.json").get(outcome.job.job_id)
    assert reloaded is not None and reloaded.status is GenerationJobStatus.DONE


def test_mindmap_artifact_content_validity(tmp_path: Path) -> None:
    executor = _executor(tmp_path)

    outcome = executor.run(_request())
    assert outcome.artifact_id is not None

    artifact = ArtifactStore(tmp_path / "artifacts.json").get(outcome.artifact_id)
    assert artifact is not None and artifact.content is not None
    raw = json.loads(artifact.content)
    assert raw["root_node_id"] == "n0"
    assert len(raw["nodes"]) == 2


def test_mindmap_provenance_persistence(tmp_path: Path) -> None:
    executor = _executor(tmp_path)

    outcome = executor.run(_request())
    assert outcome.artifact_id is not None

    records = ProvenanceStore(tmp_path / "provenance.json").for_artifact(
        outcome.artifact_id
    )
    assert {record.source_id for record in records} == {"a.md", "b.md"}
    assert all(record.artifact_id == outcome.artifact_id for record in records)


def test_failed_generation_marks_job_failed(tmp_path: Path) -> None:
    executor = _executor(tmp_path, responses=[ValueError("bad"), ValueError("bad")])

    with pytest.raises(HandlerError):
        executor.run(_request())

    jobs = GenerationJobStore(tmp_path / "jobs.json").list_jobs()
    assert len(jobs) == 1
    assert jobs[0].status is GenerationJobStatus.FAILED
    assert ArtifactStore(tmp_path / "artifacts.json").list_artifacts() == []


def test_cancellation_before_generation(tmp_path: Path) -> None:
    executor = GenerationExecutor(
        job_store=GenerationJobStore(tmp_path / "jobs.json"),
        artifact_store=ArtifactStore(tmp_path / "artifacts.json"),
        provenance_store=ProvenanceStore(tmp_path / "provenance.json"),
        handlers=register_handlers(
            MindMapEnrichTaskHandler(ScriptedGenerate([_mindmap_payload(2)])),
        ),
        search_service=StubSearchService(),
        is_cancelled=lambda: True,
    )

    outcome = executor.run(_request())

    assert outcome.job.status is GenerationJobStatus.CANCELLED
    assert outcome.artifact_id is None
    assert ArtifactStore(tmp_path / "artifacts.json").list_artifacts() == []


def test_job_artifact_linkage_and_reload(tmp_path: Path) -> None:
    executor = _executor(tmp_path)

    outcome = executor.run(_request())

    assert outcome.artifact_id is not None
    artifact = ArtifactStore(tmp_path / "artifacts.json").get(outcome.artifact_id)
    assert artifact is not None
    assert artifact.job_id == outcome.job.job_id
    assert artifact.request.task_type.value == "mindmap_enrich"
    reloaded_job = GenerationJobStore(tmp_path / "jobs.json").get(outcome.job.job_id)
    assert reloaded_job is not None
    assert reloaded_job.status is GenerationJobStatus.DONE
    # Terminal jobs return as-is without re-running.
    again = executor.execute_job(outcome.job.job_id)
    assert again.job.status is GenerationJobStatus.DONE
    assert again.artifact_id is None


def test_run_job_preserves_model_role(
    tmp_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: background _run_job must reuse the submitted model_role."""

    job_store = GenerationJobStore(
        tmp_settings.paths.manifest_root / "generation_jobs.json"
    )
    request = GenerationRequest(
        task_type="mindmap_enrich",  # type: ignore[arg-type]
        memory_scope=MemoryScope.all(),
        config={"node_limit": 2},  # type: ignore[arg-type]
        model_role="summarizer",
    )
    job = job_store.create(request)
    seen: dict[str, object] = {}
    executed: dict[str, str] = {}

    class _Probe:
        def execute_job(self, job_id: str) -> None:
            executed["job_id"] = job_id

    def _probe_build(settings: Settings, **kwargs: object) -> Any:
        seen.update(kwargs)
        return _Probe()

    monkeypatch.setattr(generation_routes, "_build_executor", _probe_build)
    generation_routes._run_job(tmp_settings, job.job_id)

    assert seen.get("model_role") == "summarizer"
    assert executed.get("job_id") == job.job_id


def test_run_job_missing_job_returns_safely(
    tmp_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING"):
        generation_routes._run_job(tmp_settings, "does-not-exist")

    jobs = GenerationJobStore(
        tmp_settings.paths.manifest_root / "generation_jobs.json"
    ).list_jobs()
    assert jobs == []
