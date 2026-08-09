"""PDF source ingestor."""

from __future__ import annotations

from pypdf import PdfReader

from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.document_intelligence.metadata.extractors import (
    clean_pdf_string,
    parse_pdf_datetime,
)
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
        resolved_path = source_path.resolve()
        if not cleaned_text:
            # Scanned PDF — no extractable text, return with scanned_pdf source type
            return SourceDocument(
                source=str(resolved_path),
                source_path=resolved_path,
                source_type="scanned_pdf",
                filename=source_path.name,
                text="",
                metadata=DocumentMetadata(
                    title=source_path.stem,
                    page_count=len(reader.pages),
                    mime_type="application/pdf",
                ),
            )

        metadata: dict[str, object] = dict(reader.metadata or {})

        return SourceDocument(
            source=str(resolved_path),
            source_path=resolved_path,
            source_type=self.source_type,
            filename=source_path.name,
            text=cleaned_text,
            metadata=DocumentMetadata(
                title=clean_pdf_string(metadata.get("/Title")) or source_path.stem,
                author=clean_pdf_string(metadata.get("/Author")),
                created_at=parse_pdf_datetime(metadata.get("/CreationDate")),
                modified_at=file_timestamp(source_path),
                page_count=len(reader.pages),
                mime_type="application/pdf",
                extra={
                    "producer": clean_pdf_string(metadata.get("/Producer")),
                    "subject": clean_pdf_string(metadata.get("/Subject")),
                },
            ),
        )
