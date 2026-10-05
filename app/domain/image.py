"""Structured models for V2-H image generation.

``ImagePlan`` is the structured-output contract for the prompt-planning LLM
call (existing ``generate_json`` seam): it distills retrieved evidence into
a visual prompt without ever touching pixels. ``ImageSpec`` is the validated
execution contract handed to the ``ImageRuntime``. Provenance lives in
``ProvenanceStore``, not here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ALLOWED_IMAGE_SIZES: tuple[tuple[int, int], ...] = ((512, 512), (768, 768), (1024, 1024))

MAX_IMAGE_STEPS = 30
MAX_PLANNER_PROMPT_CHARS = 1000
MAX_PLANNER_NEGATIVE_CHARS = 500


class ImagePlan(BaseModel):
    """A planned visual prompt distilled from retrieved memory context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str
    negative_prompt: str = ""
    title: str = ""

    @field_validator("prompt")
    @classmethod
    def _validate_prompt(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Image prompt must not be empty.")
        if len(cleaned) > MAX_PLANNER_PROMPT_CHARS:
            raise ValueError(
                f"Image prompt must be at most {MAX_PLANNER_PROMPT_CHARS} characters."
            )
        return cleaned

    @field_validator("negative_prompt", "title", mode="before")
    @classmethod
    def _clean_optional_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Image plan text fields must be strings.")
        cleaned = " ".join(value.split())
        if len(cleaned) > MAX_PLANNER_NEGATIVE_CHARS:
            raise ValueError(
                f"Image plan text must be at most {MAX_PLANNER_NEGATIVE_CHARS} characters."
            )
        return cleaned


class ImageSpec(BaseModel):
    """Validated execution parameters for one image diffusion run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str
    model_revision: str
    width: int
    height: int
    steps: int = Field(ge=1, le=MAX_IMAGE_STEPS)
    guidance_scale: float = Field(ge=0.0, le=30.0)
    seed: int = Field(ge=0)
    scheduler: str = ""

    @field_validator("model_id", "model_revision")
    @classmethod
    def _validate_model_ref(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Image model references must not be empty.")
        return cleaned

    @field_validator("scheduler", mode="before")
    @classmethod
    def _clean_scheduler(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Image scheduler must be a string.")
        return value.strip()

    @field_validator("width", "height")
    @classmethod
    def _validate_positive(cls, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("Image dimensions must be positive integers.")
        return value

    @model_validator(mode="after")
    def _validate_allowed_size(self) -> ImageSpec:
        if (self.width, self.height) not in ALLOWED_IMAGE_SIZES:
            raise ValueError(
                "Image dimensions must be one of: "
                + ", ".join(f"{w}x{h}" for w, h in ALLOWED_IMAGE_SIZES)
                + "."
            )
        return self
