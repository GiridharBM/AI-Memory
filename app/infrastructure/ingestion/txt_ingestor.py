"""Plain-text source ingestor."""

from __future__ import annotations

from pathlib import Path

from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.ingestion.base import (
    BaseIngestor,
    IngestionError,
    SourceReference,
    require_path_source,
)
from app.infrastructure.ingestion.utils import clean_text, file_timestamp


class TextIngestor(BaseIngestor):
    """Read TXT files into normalized source documents."""

    source_type = "text"
    supported_suffixes = (".txt",)

    def ingest(self, source: SourceReference) -> SourceDocument:
        source_path = require_path_source(source, ingestor_name="Text ingestor")
        raw_text = self._read_text(source_path)
        cleaned_text = clean_text(raw_text)
        if not cleaned_text:
            raise IngestionError(f"Text file '{source_path}' does not contain readable text.")

        resolved_path = source_path.resolve()
        return SourceDocument(
            source=str(resolved_path),
            source_path=resolved_path,
            source_type=self.source_type,
            filename=source_path.name,
            text=cleaned_text,
            metadata=DocumentMetadata(
                title=source_path.stem,
                modified_at=file_timestamp(source_path),
                mime_type="text/plain",
                encoding="utf-8",
            ),
        )

    def _read_text(self, source_path: Path) -> str:
        try:
            return source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                return source_path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError as exc:
                raise IngestionError(f"Unable to decode text file '{source_path}'.") from exc
        except OSError as exc:
            raise IngestionError(f"Unable to read text file '{source_path}'.") from exc
