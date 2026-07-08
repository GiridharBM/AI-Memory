"""Domain models for generated Obsidian notes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ObsidianNote(BaseModel):
    """A generated Obsidian-compatible Markdown note."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    markdown: str = Field(min_length=1)
    generated_at: datetime
    tags: list[str] = Field(default_factory=list)
    source: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
