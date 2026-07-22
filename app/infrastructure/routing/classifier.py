"""Heuristic document classifier used before processing."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from app.core.extensions import (
    ARCHIVE_EXTENSIONS,
    AUDIO_EXTENSIONS,
    CODE_EXTENSIONS,
    CONFIG_EXTENSIONS,
    DATABASE_EXTENSIONS,
    DIAGRAM_EXTENSIONS,
    DOCX_EXTENSIONS,
    EMAIL_EXTENSIONS,
    EPUB_EXTENSIONS,
    IMAGE_EXTENSIONS,
    NOTEBOOK_EXTENSIONS,
    PPTX_EXTENSIONS,
    RESEARCH_EXTENSIONS,
    SPREADSHEET_EXTENSIONS,
    TEX_EXTENSIONS,
    VIDEO_EXTENSIONS,
    WEB_EXTENSIONS,
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
        requires_ocr = kind in {"scanned_pdf", "handwritten", "image"}
        requires_vision = kind in {"image", "handwritten", "video"}
        requires_table = kind in {"csv", "spreadsheet", "database"}
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
        # Source-type overrides (scanned/handwritten PDFs)
        if source_type == "scanned_pdf":
            return "scanned_pdf"
        if source_type == "handwritten":
            return "handwritten"

        # Extensions checked first, then source_type fallbacks
        if extension in CONFIG_EXTENSIONS:
            return "config"
        if extension in CODE_EXTENSIONS:
            return "code"
        if extension in {".md", ".markdown"}:
            return "markdown"
        if extension == ".txt":
            return "text"
        if extension == ".pdf":
            return "pdf"
        if extension in {".csv", ".tsv"}:
            return "csv"
        if extension in SPREADSHEET_EXTENSIONS:
            return "spreadsheet"
        if extension in NOTEBOOK_EXTENSIONS:
            return "notebook"
        if extension in DOCX_EXTENSIONS:
            return "docx"
        if extension in PPTX_EXTENSIONS:
            return "pptx"
        if extension in TEX_EXTENSIONS:
            return "tex"
        if extension in EPUB_EXTENSIONS:
            return "epub"
        if extension in IMAGE_EXTENSIONS:
            return "image"
        if extension in DIAGRAM_EXTENSIONS:
            return "diagram"
        if extension in AUDIO_EXTENSIONS:
            return "audio"
        if extension in VIDEO_EXTENSIONS:
            return "video"
        if extension in ARCHIVE_EXTENSIONS:
            return "archive"
        if extension in EMAIL_EXTENSIONS:
            return "email"
        if extension in DATABASE_EXTENSIONS:
            return "database"
        if extension in RESEARCH_EXTENSIONS:
            return "research"
        if extension in WEB_EXTENSIONS:
            return "web"
        # Source-type fallbacks (no extension match)
        if source_type == "markdown":
            return "markdown"
        if source_type == "text":
            return "text"
        if source_type == "pdf":
            return "pdf"
        if source_type == "csv":
            return "csv"
        if source_type == "spreadsheet":
            return "spreadsheet"
        if source_type == "notebook":
            return "notebook"
        if source_type == "docx":
            return "docx"
        if source_type == "pptx":
            return "pptx"
        if source_type == "code":
            return "code"
        if source_type == "config":
            return "config"
        if source_type == "image":
            return "image"
        if source_type == "audio":
            return "audio"
        if source_type == "video":
            return "video"
        if source_type == "archive":
            return "archive"
        if source_type == "email":
            return "email"
        if source_type == "database":
            return "database"
        if source_type == "research":
            return "research"
        if source_type == "diagram":
            return "diagram"
        return "unknown"

    @staticmethod
    def _confidence_for(kind: str) -> float:
        if kind in {"markdown", "text", "code", "config", "pdf", "docx", "pptx", "tex", "notebook"}:
            return 0.92
        if kind in {"csv", "spreadsheet", "image", "audio", "video", "diagram", "web"}:
            return 0.86
        if kind in {
            "scanned_pdf", "handwritten", "epub", "archive",
            "email", "database", "research",
        }:
            return 0.80
        return 0.4
