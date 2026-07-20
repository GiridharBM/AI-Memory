"""DOCX file ingestor."""

from __future__ import annotations

from pathlib import Path

from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.ingestion.base import (
    BaseIngestor,
    IngestionError,
    SourceReference,
    require_path_source,
)
from app.infrastructure.ingestion.utils import file_timestamp


class DocxIngestor(BaseIngestor):
    """Read DOCX files into normalized source documents."""

    source_type = "docx"
    supported_suffixes = (".docx",)

    def ingest(self, source: SourceReference) -> SourceDocument:
        source_path = require_path_source(source, ingestor_name="DOCX ingestor")
        text = self._extract_text(source_path)
        resolved_path = source_path.resolve()
        return SourceDocument(
            source=str(resolved_path),
            source_path=resolved_path,
            source_type=self.source_type,
            filename=source_path.name,
            text=text,
            metadata=DocumentMetadata(
                title=source_path.stem,
                modified_at=file_timestamp(source_path),
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        )

    def _extract_text(self, path: Path) -> str:
        try:
            from docx import Document  # type: ignore[import-untyped]

            doc = Document(str(path))
            return "\n".join(para.text for para in doc.paragraphs if para.text.strip())
        except ImportError:
            raise IngestionError(
                "python-docx is required for DOCX ingestion. Install with: pip install python-docx"
            )
        except Exception as exc:
            raise IngestionError(f"Unable to read DOCX file '{path}'.") from exc
