"""Tests for the V2 report/presentation domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.generation_documents import (
    Presentation,
    Report,
    ReportSection,
    ReportTable,
    Slide,
)


def _section(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "heading": "Background",
        "paragraphs": ["First paragraph."],
        "bullets": ["point one"],
        "references": ["source-a"],
    }
    values.update(overrides)
    return values


def test_valid_report_section() -> None:
    section = ReportSection(**_section())  # type: ignore[arg-type]

    assert section.heading == "Background"
    assert section.paragraphs == ["First paragraph."]


def test_invalid_report_section() -> None:
    with pytest.raises(ValidationError):
        ReportSection(**_section(heading="   "))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ReportSection(heading="Empty")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ReportSection(**_section(paragraphs=[], bullets=[], table=None))  # type: ignore[arg-type]


def test_valid_report() -> None:
    report = Report(
        title=" Quarterly Review ",
        summary="Summary text.",
        sections=[_section(), _section(heading="Next")],
    )

    assert report.title == "Quarterly Review"
    assert len(report.sections) == 2


def test_invalid_report() -> None:
    with pytest.raises(ValidationError):
        Report(title="T", summary="S", sections=[])
    with pytest.raises(ValidationError):
        Report(title="  ", summary="S", sections=[_section()])
    with pytest.raises(ValidationError):
        Report(title="T", summary="  ", sections=[_section()])


def test_table_rectangular_and_deterministic() -> None:
    table = ReportTable(headers=["a", "b"], rows=[["1", "2"], ["3", "4"]])

    assert table.headers == ["a", "b"]
    with pytest.raises(ValidationError):
        ReportTable(headers=["a", "b"], rows=[["only-one"]])
    with pytest.raises(ValidationError):
        ReportTable(headers=[], rows=[])


def test_valid_slide() -> None:
    slide = Slide(title=" Intro ", bullets=["one", "two"], speaker_notes="say hi")

    assert slide.title == "Intro"
    assert slide.speaker_notes == "say hi"


def test_invalid_slide() -> None:
    with pytest.raises(ValidationError):
        Slide(title="   ", bullets=["one"])
    assert Slide(title="T", bullets=["", "  "]).bullets == []


def test_valid_presentation() -> None:
    presentation = Presentation(
        title=" Deck ", slides=[{"title": "One", "bullets": ["a"]}]
    )

    assert presentation.title == "Deck"
    assert len(presentation.slides) == 1


def test_invalid_presentation() -> None:
    with pytest.raises(ValidationError):
        Presentation(title="T", slides=[])
    with pytest.raises(ValidationError):
        Presentation(title=" ", slides=[{"title": "One"}])


def test_normalization() -> None:
    section = ReportSection(
        heading="  Spaced  Out  ",
        paragraphs=["  padded  ", "   "],
        bullets=["x"],
    )

    assert section.heading == "Spaced Out"
    assert section.paragraphs == ["padded"]


def test_deterministic_serialization() -> None:
    report = Report(title="T", summary="S", sections=[_section()])
    presentation = Presentation(title="P", slides=[{"title": "One"}])

    assert Report.model_validate_json(report.model_dump_json()) == report
    assert (
        Presentation.model_validate_json(presentation.model_dump_json())
        == presentation
    )
