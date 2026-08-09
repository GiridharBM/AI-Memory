"""Processed document domain model."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.infrastructure.document_intelligence.ocr.models import OcrResult


@dataclass(slots=True)
class ProcessedDocument:
    """Output from a document processor."""

    title: str
    content: str
    markdown: str
    metadata: dict[str, object] = field(default_factory=dict)
    extracted_text: str = ""
    confidence: float = 0.0
    source_type: str = "unknown"
    language: str | None = None
    parent_id: str | None = None
    ocr: OcrResult | None = None
