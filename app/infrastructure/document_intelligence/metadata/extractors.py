"""Built-in metadata extractors (P2-202).

Stdlib-only for docx/pptx/notebook/audio/email; PDF reuses the pypdf
metadata read previously owned by ``PdfIngestor`` (moved here verbatim).
No image/EXIF reader — image fields are consumed from 2.5's ``ImageInfo``
when present (R-3). Wiring into ingestion happens at P2-207.
"""

from __future__ import annotations

import email
import email.policy
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from pypdf import PdfReader

from app.domain.documents import SourceDocument


def _file_timestamp(path: Path) -> datetime:
    """Return the filesystem modification time in UTC."""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)

_DC_NS = "http://purl.org/dc/elements/1.1/"
_CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
_DCTERMS_NS = "http://purl.org/dc/terms/"
_EP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

_OOXML_MIME = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

_AUDIO_MIME = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
}


def _document_path(document: SourceDocument) -> Path:
    if document.source_path is not None:
        return document.source_path
    return Path(document.source)


def clean_pdf_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def parse_pdf_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    cleaned = value.removeprefix("D:")
    if len(cleaned) < 14:
        return None
    try:
        return datetime.strptime(cleaned[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _parse_w3cdtf(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _element_text(root: ET.Element, namespace: str, tag: str) -> str | None:
    el = root.find(f"{{{namespace}}}{tag}")
    if el is not None and el.text and el.text.strip():
        return el.text.strip()
    return None


def _extract_ooxml(document: SourceDocument, mime_type: str, page_element: str) -> dict[str, Any]:
    path = _document_path(document)
    result: dict[str, Any] = {
        "title": path.stem,
        "modified_at": _file_timestamp(path),
        "mime_type": mime_type,
    }
    try:
        with zipfile.ZipFile(path) as zf:
            core_root = ET.fromstring(zf.read("docProps/core.xml"))
            app_root = ET.fromstring(zf.read("docProps/app.xml"))
    except Exception:
        return result

    if title := _element_text(core_root, _DC_NS, "title"):
        result["title"] = title
    if author := _element_text(core_root, _DC_NS, "creator"):
        result["author"] = author
    if created := _parse_w3cdtf(_element_text(core_root, _DCTERMS_NS, "created")):
        result["created_at"] = created
    if modified := _parse_w3cdtf(_element_text(core_root, _DCTERMS_NS, "modified")):
        result["modified_at"] = modified
    if last_by := _element_text(core_root, _CP_NS, "lastModifiedBy"):
        result["last_modified_by"] = last_by
    if page_text := _element_text(app_root, _EP_NS, page_element):
        try:
            result["page_count"] = int(page_text)
        except ValueError:
            pass
    return result


class PdfExtractor:
    """PDF metadata via pypdf (logic moved from ``PdfIngestor``)."""

    name = "pdf"
    source_types = ("pdf",)

    def extract(self, document: SourceDocument) -> dict[str, Any]:
        path = _document_path(document)
        try:
            reader = PdfReader(str(path))
            metadata: dict[str, object] = dict(reader.metadata or {})
        except Exception:
            return {}
        return {
            "title": clean_pdf_string(metadata.get("/Title")) or path.stem,
            "author": clean_pdf_string(metadata.get("/Author")),
            "created_at": parse_pdf_datetime(metadata.get("/CreationDate")),
            "modified_at": _file_timestamp(path),
            "page_count": len(reader.pages),
            "mime_type": "application/pdf",
            "producer": clean_pdf_string(metadata.get("/Producer")),
            "subject": clean_pdf_string(metadata.get("/Subject")),
        }


class DocxExtractor:
    """DOCX core properties via stdlib zipfile + ElementTree."""

    name = "docx"
    source_types = ("docx",)

    def extract(self, document: SourceDocument) -> dict[str, Any]:
        return _extract_ooxml(document, _OOXML_MIME["docx"], "Pages")


class PptxExtractor:
    """PPTX core properties via stdlib zipfile + ElementTree."""

    name = "pptx"
    source_types = ("pptx",)

    def extract(self, document: SourceDocument) -> dict[str, Any]:
        return _extract_ooxml(document, _OOXML_MIME["pptx"], "Slides")


class NotebookExtractor:
    """Notebook top-level JSON fields (cells, kernelspec)."""

    name = "notebook"
    source_types = ("notebook",)

    def extract(self, document: SourceDocument) -> dict[str, Any]:
        path = _document_path(document)
        try:
            notebook = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        cells = notebook.get("cells", [])
        meta = notebook.get("metadata", {})
        kernel = meta.get("kernelspec", {})
        language = kernel.get(
            "language",
            meta.get("language_info", {}).get("name", ""),
        )
        return {
            "title": path.stem,
            "created_at": _file_timestamp(path),
            "modified_at": _file_timestamp(path),
            "mime_type": "application/x-ipynb+json",
            "cell_count": len(cells),
            "kernel": kernel.get("display_name", ""),
            "language": language,
        }


class AudioExtractor:
    """Deterministic file-level audio fields (no tag library)."""

    name = "audio"
    source_types = ("audio",)

    def extract(self, document: SourceDocument) -> dict[str, Any]:
        path = _document_path(document)
        return {
            "title": path.stem,
            "modified_at": _file_timestamp(path),
            "mime_type": _AUDIO_MIME.get(path.suffix.lower(), "audio/*"),
        }


class EmailExtractor:
    """Email header fields (subject/from/to/date)."""

    name = "email"
    source_types = ("email",)

    def extract(self, document: SourceDocument) -> dict[str, Any]:
        path = _document_path(document)
        try:
            msg = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
        except Exception:
            return {}
        subject = str(msg.get("subject", ""))
        sender = str(msg.get("from", ""))
        date = str(msg.get("date", ""))
        to = str(msg.get("to", ""))
        return {
            "title": subject,
            "created_at": _file_timestamp(path),
            "modified_at": _file_timestamp(path),
            "mime_type": "message/rfc822",
            "subject": subject,
            "from": sender,
            "to": to,
            "date": date,
        }


DEFAULT_EXTRACTORS: tuple[Any, ...] = (
    PdfExtractor(),
    DocxExtractor(),
    PptxExtractor(),
    NotebookExtractor(),
    AudioExtractor(),
    EmailExtractor(),
)


__all__ = [
    "AudioExtractor",
    "DEFAULT_EXTRACTORS",
    "DocxExtractor",
    "EmailExtractor",
    "NotebookExtractor",
    "PdfExtractor",
    "PptxExtractor",
    "clean_pdf_string",
    "parse_pdf_datetime",
]
