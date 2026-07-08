"""Markdown source ingestor."""

from __future__ import annotations

from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.ingestion.base import (
    BaseIngestor,
    IngestionError,
    SourceReference,
    require_path_source,
)
from app.infrastructure.ingestion.utils import clean_text, file_timestamp


class MarkdownIngestor(BaseIngestor):
    """Read Markdown files into normalized source documents."""

    source_type = "markdown"
    supported_suffixes = (".md", ".markdown")

    def ingest(self, source: SourceReference) -> SourceDocument:
        source_path = require_path_source(source, ingestor_name="Markdown ingestor")

        try:
            raw_text = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise IngestionError(
                f"Unable to decode Markdown file '{source_path}' as UTF-8."
            ) from exc
        except OSError as exc:
            raise IngestionError(f"Unable to read Markdown file '{source_path}'.") from exc

        cleaned_text = clean_text(raw_text)
        if not cleaned_text:
            raise IngestionError(f"Markdown file '{source_path}' does not contain readable text.")

        resolved_path = source_path.resolve()
        return SourceDocument(
            source=str(resolved_path),
            source_path=resolved_path,
            source_type=self.source_type,
            filename=source_path.name,
            text=cleaned_text,
            metadata=DocumentMetadata(
                title=_extract_markdown_title(raw_text) or source_path.stem,
                modified_at=file_timestamp(source_path),
                mime_type="text/markdown",
                encoding="utf-8",
            ),
        )


def _extract_markdown_title(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None
