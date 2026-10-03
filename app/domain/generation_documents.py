"""Structured models for V2 report and presentation generation.

These are the top-level structured-output contracts for report/PPT LLM
calls: small, frozen, validated Pydantic models mirroring the role
``FlashcardSet``/``QuizSet`` play for V2-C. Provenance is not embedded
here — it lives in ``ProvenanceStore``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _clean_lines(values: list[str]) -> list[str]:
    """Strip each line and drop blanks, preserving order."""

    return [line.strip() for line in values if isinstance(line, str) and line.strip()]


class ReportTable(BaseModel):
    """A rectangular string grid rendered as a Markdown table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    headers: list[str]
    rows: list[list[str]] = Field(default_factory=list)

    @field_validator("headers", mode="before")
    @classmethod
    def _clean_headers(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("Table headers must be a list of strings.")
        cleaned = _clean_lines(value)
        if not cleaned:
            raise ValueError("Table headers must not be empty.")
        return cleaned

    @field_validator("rows", mode="before")
    @classmethod
    def _clean_rows(cls, value: object) -> list[list[str]]:
        if not isinstance(value, list):
            raise ValueError("Table rows must be a list of string lists.")
        cleaned: list[list[str]] = []
        for row in value:
            if not isinstance(row, list) or not all(isinstance(cell, str) for cell in row):
                raise ValueError("Table rows must be lists of strings.")
            cleaned.append([cell.strip() for cell in row])
        return cleaned

    @model_validator(mode="after")
    def _validate_rectangular(self) -> ReportTable:
        width = len(self.headers)
        for row in self.rows:
            if len(row) != width:
                raise ValueError("Every table row must match the header width.")
        return self


class ReportSection(BaseModel):
    """One headed section of a generated report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    heading: str
    paragraphs: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)
    table: ReportTable | None = None
    references: list[str] = Field(default_factory=list)

    @field_validator("heading")
    @classmethod
    def _validate_heading(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Section heading must not be empty.")
        return cleaned

    @field_validator("paragraphs", "bullets", "references", mode="before")
    @classmethod
    def _clean_text_lists(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("Section text lists must be lists of strings.")
        return _clean_lines(value)

    @model_validator(mode="after")
    def _validate_non_empty(self) -> ReportSection:
        if not self.paragraphs and not self.bullets and self.table is None:
            raise ValueError("A section needs paragraphs, bullets, or a table.")
        return self


class Report(BaseModel):
    """A validated structured report from one generation call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    summary: str
    sections: list[ReportSection] = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Report title must not be empty.")
        return cleaned

    @field_validator("summary")
    @classmethod
    def _validate_summary(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Report summary must not be empty.")
        return cleaned


class Slide(BaseModel):
    """One slide of a generated presentation (content only, no layout)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    bullets: list[str] = Field(default_factory=list)
    speaker_notes: str | None = None

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Slide title must not be empty.")
        return cleaned

    @field_validator("bullets", mode="before")
    @classmethod
    def _clean_bullets(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("Slide bullets must be a list of strings.")
        return _clean_lines(value)

    @field_validator("speaker_notes", mode="before")
    @classmethod
    def _clean_notes(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value


class Presentation(BaseModel):
    """A validated structured presentation from one generation call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    slides: list[Slide] = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Presentation title must not be empty.")
        return cleaned
