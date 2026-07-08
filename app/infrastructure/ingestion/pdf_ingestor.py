"""PDF source ingestor."""

from __future__ import annotations

from datetime import UTC, datetime

from pypdf import PdfReader

from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.ingestion.base import (
    BaseIngestor,
    IngestionError,
    SourceReference,
    require_path_source,
)
from app.infrastructure.ingestion.utils import clean_text, file_timestamp


class PdfIngestor(BaseIngestor):
    """Read PDF files into normalized source documents."""

    source_type = "pdf"
    supported_suffixes = (".pdf",)

    def ingest(self, source: SourceReference) -> SourceDocument:
        source_path = require_path_source(source, ingestor_name="PDF ingestor")

        try:
            reader = PdfReader(str(source_path))
        except Exception as exc:
            raise IngestionError(f"Unable to open PDF file '{source_path}'.") from exc

        extracted_pages: list[str] = []
        for page in reader.pages:
            extracted_pages.append(page.extract_text() or "")

        cleaned_text = clean_text("\n\n".join(extracted_pages))
        if not cleaned_text:
            raise IngestionError(f"PDF file '{source_path}' does not contain extractable text.")

        metadata: dict[str, object] = dict(reader.metadata or {})
        resolved_path = source_path.resolve()

        return SourceDocument(
            source=str(resolved_path),
            source_path=resolved_path,
            source_type=self.source_type,
            filename=source_path.name,
            text=cleaned_text,
            metadata=DocumentMetadata(
                title=_clean_pdf_string(metadata.get("/Title")) or source_path.stem,
                author=_clean_pdf_string(metadata.get("/Author")),
                created_at=_parse_pdf_datetime(metadata.get("/CreationDate")),
                modified_at=file_timestamp(source_path),
                page_count=len(reader.pages),
                mime_type="application/pdf",
                extra={
                    "producer": _clean_pdf_string(metadata.get("/Producer")),
                    "subject": _clean_pdf_string(metadata.get("/Subject")),
                },
            ),
        )


def _clean_pdf_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _parse_pdf_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None

    cleaned = value.removeprefix("D:")
    if len(cleaned) < 14:
        return None

    try:
        return datetime.strptime(cleaned[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None
