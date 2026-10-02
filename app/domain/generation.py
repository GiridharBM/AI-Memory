"""Domain models for V2 generation requests.

A generation request names a task, the memory it may use, and the knobs
future features need (configuration, model role, provenance depth). It is a
pure value object: no filesystem access, no network access, no retrieval
execution, no mutation. Feature-specific implementations live elsewhere.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.scopes import MemoryScope


class GenerationTaskType(StrEnum):
    """V2 generation tasks from the product blueprint."""

    ASK = "ask"
    FLASHCARDS = "flashcards"
    QUIZ = "quiz"
    IMAGE = "image"
    VIDEO = "video"
    PPT = "ppt"
    REPORT = "report"
    MINDMAP_ENRICH = "mindmap_enrich"


class ProvenanceLevel(StrEnum):
    """How much lineage a generation must retain.

    STANDARD records best-effort lineage (sources, chunks, nodes as
    available). STRICT fails the generation when lineage is incomplete.
    """

    STANDARD = "standard"
    STRICT = "strict"


# Scalar-only task configuration for V2-A. Complex task schemas arrive with
# their features; anything else is rejected rather than silently accepted.
ConfigValue = str | int | float | bool | None


class GenerationRequest(BaseModel):
    """A validated request to generate something from shared memory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_type: GenerationTaskType
    memory_scope: MemoryScope
    config: dict[str, ConfigValue] = Field(default_factory=dict)
    model_role: str = "general_text"
    provenance: ProvenanceLevel = ProvenanceLevel.STANDARD
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("model_role")
    @classmethod
    def _validate_model_role(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Model role must not be empty.")
        return cleaned

    @field_validator("config")
    @classmethod
    def _validate_config(cls, value: dict[str, Any]) -> dict[str, ConfigValue]:
        for key in value:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Configuration keys must be non-empty strings.")
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
