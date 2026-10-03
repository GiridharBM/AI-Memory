"""Tests for the V2 report and presentation task handlers (fake LLM)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.application.generation_errors import HandlerError
from app.application.presentation_handler import PresentationTaskHandler
from app.application.report_handler import ReportTaskHandler
from app.domain.artifacts import ArtifactKind, ProvenanceRole
from app.domain.generation import GenerationRequest, GenerationTaskType
from app.domain.generation_context import GenerationContext, RetrievedChunk
from app.domain.scopes import MemoryScope, resolve_memory_scope


def _hit(source: str = "a.md") -> RetrievedChunk:
    return RetrievedChunk(source=source, text="body", entry_id=f"{source}::0")


def _context(config: dict[str, object], task: str) -> GenerationContext:
    request = GenerationRequest(
        task_type=task,  # type: ignore[arg-type]
        memory_scope=MemoryScope.documents(["a.md", "b.md"]),
        config=config,  # type: ignore[arg-type]
    )
    return GenerationContext(
        request=request,
        scope=resolve_memory_scope(request.memory_scope),
        hits=(_hit("a.md"), _hit("b.md")),
    )


def _report(count: int) -> dict[str, object]:
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


def _presentation(count: int) -> dict[str, object]:
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
    """Fake structured LLM: each call consumes the next scripted response."""

    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system_prompt: str, user_prompt: str, model: type) -> Any:
        self.calls.append((system_prompt, user_prompt))
        if not self._responses:
            raise AssertionError("Fake LLM called more times than scripted.")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return model.model_validate(response)


# ── Report handler ────────────────────────────────────────────────────


def test_report_task_type_and_kind() -> None:
    handler = ReportTaskHandler(ScriptedGenerate([_report(2)]))

    assert handler.task_type is GenerationTaskType.REPORT
    result = handler.handle(_context({"section_count": 2}, task="report"))

    assert result.kind is ArtifactKind.REPORT
    assert result.metadata == {"sections": "2"}


def test_report_rendering_and_title() -> None:
    handler = ReportTaskHandler(ScriptedGenerate([_report(1)]))

    result = handler.handle(_context({"section_count": 1}, task="report"))

    assert result.title == "Report"
    assert result.content is not None
    assert result.content.startswith("# Report\n\nSummary.")
    assert "## Section 0" in result.content
    assert "- point 0" in result.content
    assert "- [1] a.md" in result.content


def test_report_count_bounds_rejected() -> None:
    handler = ReportTaskHandler(ScriptedGenerate([_report(1)]))

    with pytest.raises(HandlerError):
        handler.handle(_context({"section_count": 0}, task="report"))
    with pytest.raises(HandlerError):
        handler.handle(_context({"section_count": 13}, task="report"))


def test_report_provenance_candidates() -> None:
    handler = ReportTaskHandler(ScriptedGenerate([_report(2)]))

    result = handler.handle(_context({"section_count": 2}, task="report"))

    # Every section references every retrieved hit (set-level attribution).
    assert len(result.provenance) == 2 * 2
    assert {record.source_id for record in result.provenance} == {"a.md", "b.md"}
    assert all(record.role is ProvenanceRole.EVIDENCE_CHUNK for record in result.provenance)


def test_report_deterministic_output() -> None:
    first = ReportTaskHandler(ScriptedGenerate([_report(2)])).handle(
        _context({"section_count": 2}, task="report")
    )
    second = ReportTaskHandler(ScriptedGenerate([_report(2)])).handle(
        _context({"section_count": 2}, task="report")
    )

    assert first == second


def test_report_malformed_retries_then_succeeds() -> None:
    malformed = {"title": "Report", "summary": "S", "sections": []}
    handler = ReportTaskHandler(ScriptedGenerate([malformed, _report(1)]))

    result = handler.handle(_context({"section_count": 1}, task="report"))

    assert result.metadata == {"sections": "1"}


def test_report_second_failure_raises() -> None:
    malformed = {"title": "Report", "summary": "S", "sections": []}
    handler = ReportTaskHandler(ScriptedGenerate([malformed, malformed]))

    with pytest.raises(HandlerError):
        handler.handle(_context({"section_count": 1}, task="report"))


def test_report_transport_failure_fails_immediately() -> None:
    handler = ReportTaskHandler(ScriptedGenerate([RuntimeError("down")]))

    with pytest.raises(HandlerError):
        handler.handle(_context({"section_count": 1}, task="report"))


def test_report_duplicate_headings_rejected() -> None:
    payload = _report(2)
    payload["sections"][1]["heading"] = "SECTION 0"  # type: ignore[index]
    handler = ReportTaskHandler(ScriptedGenerate([payload, payload]))

    with pytest.raises(HandlerError):
        handler.handle(_context({"section_count": 2}, task="report"))


# ── Presentation handler ──────────────────────────────────────────────


def _presentation_handler(tmp_path: Path, responses: list[object]) -> PresentationTaskHandler:
    return PresentationTaskHandler(
        ScriptedGenerate(responses),
        artifact_root=tmp_path / "artifacts",
        project_root=tmp_path,
    )


def test_presentation_task_type_and_kind(tmp_path: Path) -> None:
    handler = _presentation_handler(tmp_path, [_presentation(2)])

    assert handler.task_type is GenerationTaskType.PPT
    result = handler.handle(_context({"slide_count": 2}, task="ppt"))

    assert result.kind is ArtifactKind.PPT
    assert result.metadata == {"slides": "2", "theme": "default"}


def test_presentation_content_ref_is_project_relative(tmp_path: Path) -> None:
    handler = _presentation_handler(tmp_path, [_presentation(1)])

    result = handler.handle(_context({"slide_count": 1}, task="ppt"))

    assert result.content is None
    assert result.content_ref is not None
    assert result.content_ref.endswith(".pptx")
    assert not Path(result.content_ref).is_absolute()
    assert (tmp_path / result.content_ref).exists()


def test_presentation_slide_count_bounds_rejected(tmp_path: Path) -> None:
    handler = _presentation_handler(tmp_path, [_presentation(1)])

    with pytest.raises(HandlerError):
        handler.handle(_context({"slide_count": 0}, task="ppt"))
    with pytest.raises(HandlerError):
        handler.handle(_context({"slide_count": 21}, task="ppt"))


def test_presentation_non_default_theme_rejected(tmp_path: Path) -> None:
    handler = _presentation_handler(tmp_path, [_presentation(1)])

    with pytest.raises(HandlerError):
        handler.handle(_context({"slide_count": 1, "theme": "dark"}, task="ppt"))


def test_presentation_provenance_candidates(tmp_path: Path) -> None:
    handler = _presentation_handler(tmp_path, [_presentation(2)])

    result = handler.handle(_context({"slide_count": 2}, task="ppt"))

    assert len(result.provenance) == 2 * 2
    assert {record.source_id for record in result.provenance} == {"a.md", "b.md"}


def test_presentation_deterministic_output(tmp_path: Path) -> None:
    first = _presentation_handler(tmp_path, [_presentation(1)]).handle(
        _context({"slide_count": 1}, task="ppt")
    )
    second = _presentation_handler(tmp_path, [_presentation(1)]).handle(
        _context({"slide_count": 1}, task="ppt")
    )

    assert first.title == second.title
    assert first.metadata == second.metadata


def test_presentation_malformed_retries_then_succeeds(tmp_path: Path) -> None:
    malformed = {"title": "Deck", "slides": []}
    handler = _presentation_handler(tmp_path, [malformed, _presentation(1)])

    result = handler.handle(_context({"slide_count": 1}, task="ppt"))

    assert result.metadata["slides"] == "1"


def test_presentation_second_failure_raises(tmp_path: Path) -> None:
    malformed = {"title": "Deck", "slides": []}
    handler = _presentation_handler(tmp_path, [malformed, malformed])

    with pytest.raises(HandlerError):
        handler.handle(_context({"slide_count": 1}, task="ppt"))


def test_presentation_transport_failure_fails_immediately(tmp_path: Path) -> None:
    handler = _presentation_handler(tmp_path, [RuntimeError("down")])

    with pytest.raises(HandlerError):
        handler.handle(_context({"slide_count": 1}, task="ppt"))


def test_presentation_duplicate_slides_rejected(tmp_path: Path) -> None:
    payload = _presentation(2)
    payload["slides"][1] = dict(payload["slides"][0])  # type: ignore[index]
    handler = _presentation_handler(tmp_path, [payload, payload])

    with pytest.raises(HandlerError):
        handler.handle(_context({"slide_count": 2}, task="ppt"))


def test_presentation_speaker_notes_config(tmp_path: Path) -> None:
    with_notes = _presentation_handler(tmp_path, [_presentation(1)]).handle(
        _context({"slide_count": 1, "speaker_notes": False}, task="ppt")
    )

    assert with_notes.content_ref is not None
    assert (tmp_path / with_notes.content_ref).exists()


def _relative_root_handler(
    tmp_path: Path, responses: list[object]
) -> PresentationTaskHandler:
    return PresentationTaskHandler(
        ScriptedGenerate(responses),
        artifact_root=Path("data/artifacts"),
        project_root=tmp_path,
    )


def test_presentation_relative_artifact_root_resolves_under_project(
    tmp_path: Path,
) -> None:
    handler = _relative_root_handler(tmp_path, [_presentation(1)])

    result = handler.handle(_context({"slide_count": 1}, task="ppt"))

    assert result.content_ref is not None
    assert result.content_ref.startswith("data/artifacts/")
    assert result.content_ref.endswith(".pptx")
    assert (tmp_path / result.content_ref).exists()


def test_presentation_different_cwd_still_resolves_under_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "other-cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    handler = _relative_root_handler(tmp_path, [_presentation(1)])

    result = handler.handle(_context({"slide_count": 1}, task="ppt"))

    assert result.content_ref is not None
    assert (tmp_path / result.content_ref).exists()
    assert not (elsewhere / "data").exists()


def test_presentation_content_ref_points_at_generated_file(tmp_path: Path) -> None:
    handler = _relative_root_handler(tmp_path, [_presentation(1)])

    result = handler.handle(_context({"slide_count": 1}, task="ppt"))

    assert result.content_ref is not None
    resolved = (tmp_path / result.content_ref).resolve()
    assert resolved.is_file()
    assert resolved.parent == (tmp_path / "data" / "artifacts").resolve()


def test_presentation_artifact_root_outside_project_rejected(
    tmp_path: Path,
) -> None:
    handler = PresentationTaskHandler(
        ScriptedGenerate([_presentation(1)]),
        artifact_root=tmp_path.parent / "outside-root",
        project_root=tmp_path,
    )

    with pytest.raises(HandlerError):
        handler.handle(_context({"slide_count": 1}, task="ppt"))
