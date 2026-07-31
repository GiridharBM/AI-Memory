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

EXTENSION_KIND_MAP: dict[str, str] = {
    **{ext: "config" for ext in CONFIG_EXTENSIONS},
    **{ext: "code" for ext in CODE_EXTENSIONS},
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".pdf": "pdf",
    ".csv": "csv",
    ".tsv": "csv",
    **{ext: "spreadsheet" for ext in SPREADSHEET_EXTENSIONS},
    **{ext: "notebook" for ext in NOTEBOOK_EXTENSIONS},
    **{ext: "docx" for ext in DOCX_EXTENSIONS},
    **{ext: "pptx" for ext in PPTX_EXTENSIONS},
    **{ext: "tex" for ext in TEX_EXTENSIONS},
    **{ext: "epub" for ext in EPUB_EXTENSIONS},
    **{ext: "image" for ext in IMAGE_EXTENSIONS},
    **{ext: "diagram" for ext in DIAGRAM_EXTENSIONS},
    **{ext: "audio" for ext in AUDIO_EXTENSIONS},
    **{ext: "video" for ext in VIDEO_EXTENSIONS},
    **{ext: "archive" for ext in ARCHIVE_EXTENSIONS},
    **{ext: "email" for ext in EMAIL_EXTENSIONS},
    **{ext: "database" for ext in DATABASE_EXTENSIONS},
    **{ext: "research" for ext in RESEARCH_EXTENSIONS},
    **{ext: "web" for ext in WEB_EXTENSIONS},
}

SOURCE_TYPE_FALLBACK: dict[str, str] = {
    "markdown": "markdown",
    "text": "text",
    "pdf": "pdf",
    "csv": "csv",
    "spreadsheet": "spreadsheet",
    "notebook": "notebook",
    "docx": "docx",
    "pptx": "pptx",
    "code": "code",
    "config": "config",
    "image": "image",
    "audio": "audio",
    "video": "video",
    "archive": "archive",
    "email": "email",
    "database": "database",
    "research": "research",
    "diagram": "diagram",
}


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
        if source_type == "scanned_pdf":
            return "scanned_pdf"
        if source_type == "handwritten":
            return "handwritten"
        if extension in EXTENSION_KIND_MAP:
            return EXTENSION_KIND_MAP[extension]
        return SOURCE_TYPE_FALLBACK.get(source_type, "unknown")

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
