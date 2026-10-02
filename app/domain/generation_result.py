"""Domain models for V2 task-handler results.

A generation result is what a task handler returns to the executor: the
generated content (inline or by reference), its kind, and provenance
candidates carrying placeholder artifact ids that the executor rewrites
with the real id at persist time. No feature-specific schemas live here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.artifacts import ArtifactKind, ProvenanceRecord


class GenerationResult(BaseModel):
    """Handler output: content plus provenance candidates. Immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ArtifactKind
    title: str
    content: str | None = None
    content_ref: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    provenance: tuple[ProvenanceRecord, ...] = ()

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Result title must not be empty.")
        return cleaned

    @field_validator("content", "content_ref", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Metadata keys must be non-empty strings.")
            if not isinstance(item, str):
                raise ValueError("Metadata values must be strings.")
            cleaned[key.strip()] = item
        return cleaned

    @model_validator(mode="after")
    def _validate_content_present(self) -> GenerationResult:
        if self.content is None and self.content_ref is None:
            raise ValueError("A result needs content or a content reference.")
        return self
