"""Source code file ingestor."""

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


class CodeIngestor(BaseIngestor):
    """Read source code files into normalized source documents."""

    source_type = "code"
    supported_suffixes = (
        ".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs",
        ".go", ".rb", ".rs", ".php", ".sh", ".bash",
    )

    def ingest(self, source: SourceReference) -> SourceDocument:
        source_path = require_path_source(source, ingestor_name="Code ingestor")
        try:
            text = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = source_path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError as exc:
                raise IngestionError(f"Unable to decode code file '{source_path}'.") from exc
        except OSError as exc:
            raise IngestionError(f"Unable to read code file '{source_path}'.") from exc

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
                mime_type="text/plain",
            ),
        )
