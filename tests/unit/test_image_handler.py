"""Tests for the V2-H image task handler (stubbed planner + runtime)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image as PILImage
from pydantic import BaseModel

from app.application.generation_errors import HandlerError
from app.application.image_handler import ImageTaskHandler
from app.core.config import ImageGenerationSettings
from app.domain.artifacts import ArtifactKind, ProvenanceRole
from app.domain.generation import GenerationRequest
from app.domain.generation_context import GenerationContext, RetrievedChunk
from app.domain.scopes import MemoryScope, resolve_memory_scope
from app.infrastructure.image_runtime import ImageResult


def _hit(source: str = "a.md") -> RetrievedChunk:
    return RetrievedChunk(source=source, text="body", entry_id=f"{source}::0")


def _context(config: dict[str, object]) -> GenerationContext:
    request = GenerationRequest(
        task_type="image",  # type: ignore[arg-type]
        memory_scope=MemoryScope.all(),
        config=config,  # type: ignore[arg-type]
    )
    return GenerationContext(
        request=request,
        scope=resolve_memory_scope(request.memory_scope),
        hits=(_hit("a.md"), _hit("b.md")),
    )


def _plan() -> dict[str, object]:
    return {"prompt": "A misty forest.", "negative_prompt": "blurry", "title": "Forest"}


class ScriptedPlanner:
    """Fake structured LLM: each call consumes the next scripted response."""

    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self, system_prompt: str, user_prompt: str, model: type[BaseModel]
    ) -> Any:
        self.calls.append((system_prompt, user_prompt))
        if not self._responses:
            raise AssertionError("Fake planner called more times than scripted.")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return model.model_validate(response)


class StubRuntime:
    """Deterministic image runtime: renders a solid PIL image at spec size."""

    def __init__(self, size_override: tuple[int, int] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._size_override = size_override

    def generate(self, **kwargs: object) -> ImageResult:
        self.calls.append(dict(kwargs))
        width = kwargs["width"]
        height = kwargs["height"]
        seed = kwargs["seed"]
        assert isinstance(width, int) and isinstance(height, int)
        assert isinstance(seed, int)
        size = self._size_override or (width, height)
        return ImageResult(
            image=PILImage.new("RGB", size, color=(10, 20, 30)),
            width=width,
            height=height,
            seed=seed,
            model_id=str(kwargs["model_id"]),
            model_revision=str(kwargs["model_revision"]),
            scheduler="EulerDiscreteScheduler",
            elapsed_seconds=1.0,
        )


def _handler(
    tmp_path: Path,
    planner: ScriptedPlanner,
    runtime: StubRuntime | None = None,
) -> ImageTaskHandler:
    return ImageTaskHandler(
        generate_json=planner,
        image_runtime=runtime or StubRuntime(),
        image_config=ImageGenerationSettings(),
        artifact_root=tmp_path / "artifacts",
        project_root=tmp_path,
    )


# ── Success paths ───────────────────────────────────────────────────


def test_task_type_and_kind(tmp_path: Path) -> None:
    from app.domain.generation import GenerationTaskType

    handler = _handler(tmp_path, ScriptedPlanner([_plan()]))

    assert handler.task_type is GenerationTaskType.IMAGE
    result = handler.handle(_context({}))

    assert result.kind is ArtifactKind.IMAGE
    assert result.content is None
    assert result.content_ref is not None and result.content_ref.endswith(".png")
    assert (tmp_path / result.content_ref).is_file()


def test_metadata_and_title(tmp_path: Path) -> None:
    handler = _handler(tmp_path, ScriptedPlanner([_plan()]))

    result = handler.handle(_context({}))

    assert result.title == "Forest"
    assert result.metadata["mode"] == "standard"
    assert result.metadata["width"] == "768"
    assert result.metadata["height"] == "768"
    assert result.metadata["steps"] == "20"
    assert result.metadata["seed"] != ""
    assert result.metadata["model_id"] == "stabilityai/stable-diffusion-xl-base-1.0"
    assert result.metadata["scheduler"] == "EulerDiscreteScheduler"
    assert len(result.metadata["prompt_sha256"]) == 64
    assert result.metadata["evidence_chunks"] == "2"


def test_fast_mode_uses_turbo_defaults(tmp_path: Path) -> None:
    runtime = StubRuntime()
    handler = _handler(tmp_path, ScriptedPlanner([_plan()]), runtime)

    result = handler.handle(_context({"mode": "fast"}))

    assert result.metadata["mode"] == "fast"
    assert result.metadata["model_id"] == "stabilityai/sdxl-turbo"
    assert result.metadata["steps"] == "4"
    assert runtime.calls[0]["guidance_scale"] == 0.0


def test_explicit_prompt_bypasses_planner(tmp_path: Path) -> None:
    planner = ScriptedPlanner([])
    runtime = StubRuntime()
    handler = _handler(tmp_path, planner, runtime)

    result = handler.handle(_context({"prompt": "A lighthouse."}))

    assert planner.calls == []
    assert runtime.calls[0]["prompt"] == "A lighthouse."
    assert result.title == "Image (768x768)"


def test_provenance_per_hit(tmp_path: Path) -> None:
    handler = _handler(tmp_path, ScriptedPlanner([_plan()]))

    result = handler.handle(_context({}))

    assert len(result.provenance) == 2
    assert {record.source_id for record in result.provenance} == {"a.md", "b.md"}
    assert all(record.role is ProvenanceRole.EVIDENCE_CHUNK for record in result.provenance)
    assert all(record.kg_node_id is None for record in result.provenance)


def test_empty_retrieval_still_generates(tmp_path: Path) -> None:
    handler = _handler(tmp_path, ScriptedPlanner([_plan()]))
    request = GenerationRequest(
        task_type="image",  # type: ignore[arg-type]
        memory_scope=MemoryScope.all(),
        config={},  # type: ignore[arg-type]
    )
    context = GenerationContext(
        request=request,
        scope=resolve_memory_scope(request.memory_scope),
        hits=(),
    )

    result = handler.handle(context)

    assert result.metadata["evidence_chunks"] == "0"
    assert result.provenance == ()


def test_seed_zero_randomizes_but_records(tmp_path: Path) -> None:
    runtime = StubRuntime()
    handler = _handler(tmp_path, ScriptedPlanner([_plan()]), runtime)

    handler.handle(_context({"seed": 0}))

    assert isinstance(runtime.calls[0]["seed"], int)


def test_explicit_seed_passed_through(tmp_path: Path) -> None:
    runtime = StubRuntime()
    handler = _handler(tmp_path, ScriptedPlanner([_plan()]), runtime)

    result = handler.handle(_context({"seed": 1234}))

    assert runtime.calls[0]["seed"] == 1234
    assert result.metadata["seed"] == "1234"


# ── Failure paths ───────────────────────────────────────────────────


def test_planner_malformed_retries_then_succeeds(tmp_path: Path) -> None:
    malformed = {"prompt": "", "negative_prompt": "", "title": ""}
    planner = ScriptedPlanner([malformed, _plan()])
    handler = _handler(tmp_path, planner)

    result = handler.handle(_context({}))

    assert result.kind is ArtifactKind.IMAGE
    assert len(planner.calls) == 2


def test_planner_second_failure_raises(tmp_path: Path) -> None:
    malformed = {"prompt": "", "negative_prompt": "", "title": ""}
    handler = _handler(tmp_path, ScriptedPlanner([malformed, malformed]))

    with pytest.raises(HandlerError):
        handler.handle(_context({}))


def test_planner_transport_failure_fails_immediately(tmp_path: Path) -> None:
    runtime = StubRuntime()
    planner = ScriptedPlanner([RuntimeError("ollama down")])
    handler = _handler(tmp_path, planner, runtime)

    with pytest.raises(HandlerError):
        handler.handle(_context({}))

    assert len(planner.calls) == 1
    assert runtime.calls == []


def test_runtime_failure_fails_without_artifact(tmp_path: Path) -> None:
    class FailingRuntime:
        def generate(self, **kwargs: object) -> Any:
            raise RuntimeError("CUDA OOM")

    handler = ImageTaskHandler(
        generate_json=ScriptedPlanner([_plan()]),
        image_runtime=FailingRuntime(),  # type: ignore[arg-type]
        image_config=ImageGenerationSettings(),
        artifact_root=tmp_path / "artifacts",
        project_root=tmp_path,
    )

    with pytest.raises(HandlerError):
        handler.handle(_context({}))

    artifacts_dir = tmp_path / "artifacts"
    assert not artifacts_dir.exists() or list(artifacts_dir.glob("*.png")) == []


def test_wrong_dimensions_rejected(tmp_path: Path) -> None:
    handler = _handler(
        tmp_path, ScriptedPlanner([_plan()]), StubRuntime(size_override=(64, 64))
    )

    with pytest.raises(HandlerError):
        handler.handle(_context({}))


def test_config_validation(tmp_path: Path) -> None:
    handler = _handler(tmp_path, ScriptedPlanner([_plan()]))

    bad_configs: tuple[dict[str, object], ...] = (
        {"mode": "ultra"},
        {"width": 800, "height": 600},
        {"width": 1024, "height": 768},
        {"steps": 0},
        {"steps": 31},
        {"seed": -1},
        {"guidance_scale": 99.0},
        {"title": "  "},
        {"prompt": "  "},
    )
    for bad in bad_configs:
        with pytest.raises(HandlerError):
            handler.handle(_context(bad))
