"""Domain models for document routing and classification."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class DocumentClassification:
    """Result of classifying a source document."""

    source: str
    source_path: Path | None
    extension: str | None
    mime_type: str | None
    kind: str
    language: str | None = None
    requires_ocr: bool = False
    requires_vision: bool = False
    requires_table_extraction: bool = False
    requires_code_parsing: bool = False
    confidence: float = 0.0


@dataclass(slots=True)
class ProcessorSelection:
    """Selected processor and model for a classified document."""

    processor_name: str
    model_name: str
