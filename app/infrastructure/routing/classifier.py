"""Heuristic document classifier used before processing."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from app.core.extensions import (
    AUDIO_EXTENSIONS,
    CODE_EXTENSIONS,
    DOCX_EXTENSIONS,
    IMAGE_EXTENSIONS,
    PPTX_EXTENSIONS,
    SPREADSHEET_EXTENSIONS,
    VIDEO_EXTENSIONS,
)
from app.domain.documents import SourceDocument
from app.domain.routing import DocumentClassification


class DocumentClassifier:
    """Classify source documents into structured kinds."""

    def classify(self, document: SourceDocument) -> DocumentClassification:
        path = document.source_path
        extension = path.suffix.lower() if path else Path(document.filename).suffix.lower()
        mime_type, _ = mimetypes.guess_type(document.filename)
        kind = self._detect_kind(extension, document.source_type)
        requires_ocr = kind in {"scanned_pdf", "handwritten_pdf", "image"}
        requires_vision = kind in {"image", "handwritten_pdf", "video"}
        requires_table = kind in {"csv", "spreadsheet"}
        requires_code = kind == "code"

        return DocumentClassification(
            source=document.source,
            source_path=document.source_path,
            extension=extension or None,
            mime_type=mime_type,
            kind=kind,
            requires_ocr=requires_ocr,
            requires_vision=requires_vision,
            requires_table_extraction=requires_table,
            requires_code_parsing=requires_code,
            confidence=self._confidence_for(kind),
        )

    @staticmethod
    def _detect_kind(extension: str, source_type: str) -> str:
        if extension in CODE_EXTENSIONS:
            return "code"
        if extension == ".md" or source_type == "markdown":
            return "markdown"
        if extension == ".txt" or source_type == "text":
            return "text"
        if source_type == "scanned_pdf":
            return "scanned_pdf"
        if source_type == "handwritten":
            return "handwritten"
        if extension == ".pdf" or source_type == "pdf":
            return "pdf"
        if extension == ".csv":
            return "csv"
        if extension in SPREADSHEET_EXTENSIONS:
            return "spreadsheet"
        if extension in DOCX_EXTENSIONS:
            return "docx"
        if extension in PPTX_EXTENSIONS:
            return "pptx"
        if extension in IMAGE_EXTENSIONS:
            return "image"
        if extension in AUDIO_EXTENSIONS:
            return "audio"
        if extension in VIDEO_EXTENSIONS:
            return "video"
        if extension in {".html", ".htm"}:
            return "html"
        if extension == ".json":
            return "json"
        if extension == ".xml":
            return "xml"
        return "unknown"

    @staticmethod
    def _confidence_for(kind: str) -> float:
        if kind in {"markdown", "text", "code", "pdf", "docx", "pptx"}:
            return 0.92
        if kind in {"csv", "spreadsheet", "image", "audio", "video"}:
            return 0.86
        if kind in {"scanned_pdf", "handwritten"}:
            return 0.80
        return 0.4
