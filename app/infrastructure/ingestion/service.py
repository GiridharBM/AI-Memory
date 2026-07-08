"""Reusable ingestion service and adapter registry."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from app.core.logging import get_logger
from app.domain.documents import DocumentIngestionError, DocumentIngestionResult, SourceDocument
from app.infrastructure.ingestion.base import (
    BaseIngestor,
    IngestionError,
    SourceReference,
    UnsupportedSourceError,
)
from app.infrastructure.ingestion.github_readme_ingestor import GitHubReadmeIngestor
from app.infrastructure.ingestion.markdown_ingestor import MarkdownIngestor
from app.infrastructure.ingestion.pdf_ingestor import PdfIngestor
from app.infrastructure.ingestion.txt_ingestor import TextIngestor
from app.infrastructure.ingestion.youtube_transcript_ingestor import YouTubeTranscriptIngestor

logger = get_logger(__name__)


class DocumentIngestionService:
    """Select and run the appropriate ingestor for a source document."""

    def __init__(self, ingestors: list[BaseIngestor] | None = None) -> None:
        self._ingestors = ingestors or [
            YouTubeTranscriptIngestor(),
            GitHubReadmeIngestor(),
            PdfIngestor(),
            MarkdownIngestor(),
            TextIngestor(),
        ]

    def ingest(self, source: str | Path) -> DocumentIngestionResult:
        """Ingest a single source and return either a document or a structured error."""

        normalized_source = self._normalize_source(source)
        try:
            document = self._ingest_source(normalized_source)
            logger.info(
                "Ingested source document.",
                extra={
                    "source": document.source,
                    "source_path": str(document.source_path) if document.source_path else None,
                    "source_type": document.source_type,
                    "document_filename": document.filename,
                },
            )
            return DocumentIngestionResult(document=document)
        except (UnsupportedSourceError, IngestionError) as exc:
            logger.error(
                "Failed to ingest source document.",
                extra={"source": self._source_label(normalized_source), "reason": str(exc)},
                exc_info=True,
            )
            return DocumentIngestionResult(
                error=DocumentIngestionError(
                    source=self._source_label(normalized_source),
                    source_path=normalized_source if isinstance(normalized_source, Path) else None,
                    source_type=self._detect_source_type(normalized_source),
                    reason=str(exc),
                )
            )

    def supported_extensions(self) -> tuple[str, ...]:
        """Return the registered file extensions accepted by local file ingestors."""

        extensions = {
            suffix
            for ingestor in self._ingestors
            for suffix in ingestor.supported_suffixes
        }
        return tuple(sorted(extensions))

    def register(self, ingestor: BaseIngestor) -> None:
        """Register an additional ingestor for future source types."""

        self._ingestors.append(ingestor)

    def _ingest_source(self, source: SourceReference) -> SourceDocument:
        if isinstance(source, Path):
            if not source.exists():
                raise IngestionError(f"Source file '{source}' does not exist.")
            if not source.is_file():
                raise IngestionError(f"Source path '{source}' is not a file.")

        ingestor = self._select_ingestor(source)
        return ingestor.ingest(source)

    def _select_ingestor(self, source: SourceReference) -> BaseIngestor:
        for ingestor in self._ingestors:
            if ingestor.can_ingest(source):
                return ingestor

        if isinstance(source, Path):
            source_label = source.suffix or "[no extension]"
            name = source.name
        else:
            source_label = urlparse(source).netloc or "[unknown source]"
            name = source

        raise UnsupportedSourceError(
            f"Unsupported source '{name}' ({source_label})."
        )

    def _detect_source_type(self, source: SourceReference) -> str | None:
        for ingestor in self._ingestors:
            if ingestor.can_ingest(source):
                return ingestor.source_type
        return None

    @staticmethod
    def _normalize_source(source: str | Path) -> SourceReference:
        if isinstance(source, Path):
            return source.expanduser().resolve()

        stripped = source.strip()
        parsed = urlparse(stripped)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return stripped

        return Path(stripped).expanduser().resolve()

    @staticmethod
    def _source_label(source: SourceReference) -> str:
        return str(source)
