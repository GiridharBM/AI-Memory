"""Domain models for ingested source documents."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentMetadata(BaseModel):
    """Normalized metadata extracted from a source document."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    author: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    page_count: int | None = None
    mime_type: str | None = None
    encoding: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class SourceDocument(BaseModel):
    """Canonical document object returned by the ingestion system."""

    model_config = ConfigDict(extra="forbid")

    source: str
    source_path: Path | None = None
    source_type: str
    filename: str
    text: str
    metadata: DocumentMetadata

    @field_validator("source")
    @classmethod
    def _validate_source(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Document source must not be empty.")
        return cleaned


class DocumentIngestionError(BaseModel):
    """Structured ingestion failure information."""

    model_config = ConfigDict(extra="forbid")

    source: str
    source_path: Path | None = None
    source_type: str | None = None
    reason: str


class DocumentIngestionResult(BaseModel):
    """Outcome returned by the ingestion service."""

    model_config = ConfigDict(extra="forbid")

    document: SourceDocument | None = None
    error: DocumentIngestionError | None = None

    @property
    def succeeded(self) -> bool:
        """Return whether the document was ingested successfully."""

        return self.document is not None and self.error is None
