"""Reusable ingestion service and adapter registry."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import CodeSettings, ImageSettings, MetadataSettings, Settings
from app.core.logging import get_logger
from app.domain.documents import DocumentIngestionError, DocumentIngestionResult, SourceDocument
from app.infrastructure.document_intelligence.metadata import (
    DocumentMetadataService,
    get_default_hook_registry,
)
from app.infrastructure.document_intelligence.metadata.extractors import DEFAULT_EXTRACTORS
from app.infrastructure.document_intelligence.metadata.hooks import IngestionHook
from app.infrastructure.ingestion.archive_ingestor import ArchiveIngestor
from app.infrastructure.ingestion.audio_ingestor import AudioIngestor
from app.infrastructure.ingestion.base import (
    BaseIngestor,
    IngestionError,
    SourceReference,
    UnsupportedSourceError,
)
from app.infrastructure.ingestion.code_ingestor import CodeIngestor
from app.infrastructure.ingestion.config_ingestor import ConfigIngestor
from app.infrastructure.ingestion.csv_ingestor import CSVIngestor
from app.infrastructure.ingestion.database_ingestor import DatabaseIngestor
from app.infrastructure.ingestion.diagram_ingestor import DiagramIngestor
from app.infrastructure.ingestion.docx_ingestor import DocxIngestor
from app.infrastructure.ingestion.email_ingestor import EmailIngestor
from app.infrastructure.ingestion.epub_ingestor import EpubIngestor
from app.infrastructure.ingestion.github_readme_ingestor import GitHubReadmeIngestor
from app.infrastructure.ingestion.image_ingestor import ImageIngestor
from app.infrastructure.ingestion.markdown_ingestor import MarkdownIngestor
from app.infrastructure.ingestion.notebook_ingestor import NotebookIngestor
from app.infrastructure.ingestion.pdf_ingestor import PdfIngestor
from app.infrastructure.ingestion.pptx_ingestor import PptxIngestor
from app.infrastructure.ingestion.research_ingestor import ResearchIngestor
from app.infrastructure.ingestion.spreadsheet_ingestor import SpreadsheetIngestor
from app.infrastructure.ingestion.txt_ingestor import TextIngestor
from app.infrastructure.ingestion.video_ingestor import VideoIngestor
from app.infrastructure.ingestion.youtube_transcript_ingestor import YouTubeTranscriptIngestor

logger = get_logger(__name__)

_SECRET_EXTENSIONS = frozenset({".pem", ".key", ".ppk", ".p12", ".pfx"})
_SECRET_BASENAMES = frozenset(
    {"credentials", "credential", "secret", "secrets", "passwd", "shadow", "htpasswd"}
)


def is_secret_bearing(source: SourceReference) -> bool:
    """Return whether a file source is an obvious secret-bearing file.

    Remote (URL) sources always pass; the guard targets local secret files.
    Blocking happens before any reading/processing, so secret contents never
    enter memory, logs, vectors, or the knowledge graph.
    """
    if not isinstance(source, Path):
        return False
    name = source.name
    if name == ".env" or name.startswith(".env."):
        return True
    if source.suffix.lower() in _SECRET_EXTENSIONS:
        return True
    if name.lower().replace(" ", "") in _SECRET_BASENAMES:
        return True
    if name.lower() in {f"{base}.txt" for base in _SECRET_BASENAMES}:
        return True
    return False


class BlockedSourceError(IngestionError):
    """Raised when a source file is blocked by the secret-ingestion guard."""




class DocumentIngestionService:
    """Select and run the appropriate ingestor for a source document."""

    def __init__(
        self,
        ingestors: list[BaseIngestor] | None = None,
        *,
        settings: Settings | None = None,
        hooks: Iterable[IngestionHook] | None = None,
        metadata_service: DocumentMetadataService | None = None,
    ) -> None:
        self._settings = settings
        self._hook_registry = get_default_hook_registry()
        self._hooks = {hook.name: hook for hook in (hooks or [])}
        self._metadata_service = metadata_service or DocumentMetadataService(
            list(DEFAULT_EXTRACTORS)
        )
        self._ingestors = ingestors or [
            YouTubeTranscriptIngestor(),
            GitHubReadmeIngestor(),
            PdfIngestor(),
            NotebookIngestor(max_cell_outputs=self._code().max_cell_outputs),
            EpubIngestor(),
            MarkdownIngestor(),
            CodeIngestor(),
            ConfigIngestor(),
            TextIngestor(),
            CSVIngestor(),
            SpreadsheetIngestor(),
            ImageIngestor(exif_enabled=self._images().exif_enabled),
            DocxIngestor(),
            PptxIngestor(),
            AudioIngestor(),
            VideoIngestor(),
            DiagramIngestor(),
            ArchiveIngestor(),
            EmailIngestor(metadata=self._metadata()),
            DatabaseIngestor(),
            ResearchIngestor(),
        ]

    def _metadata(self) -> MetadataSettings:
        if self._settings is None:
            return MetadataSettings()
        return self._settings.intelligence.metadata

    def _images(self) -> ImageSettings:
        if self._settings is None:
            return ImageSettings()
        return self._settings.intelligence.images

    def _code(self) -> CodeSettings:
        if self._settings is None:
            return CodeSettings()
        return self._settings.intelligence.code

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
            self._enforce_size_limit(source)
            if is_secret_bearing(source):
                raise BlockedSourceError(
                    f"Source '{source}' is blocked: it appears to be a secret-bearing "
                    f"or credential file and cannot be ingested."
                )

        source = self._run_pre_hooks(source)
        ingestor = self._select_ingestor(source)
        document = ingestor.ingest(source)
        document = self._enrich_document(document)
        return self._run_post_hooks(document)

    def _enrich_document(self, document: SourceDocument) -> SourceDocument:
        metadata = self._metadata()
        if not metadata.enabled:
            return document
        if metadata.extractors != "default":
            logger.debug(
                "Unsupported extractor set '%s'; skipping enrichment.",
                metadata.extractors,
            )
            return document
        try:
            extraction = self._metadata_service.extract(document)
            merged = DocumentMetadataService.merge(document.metadata, extraction)
        except Exception:
            logger.debug("Metadata enrichment failed; document unchanged.", exc_info=True)
            return document
        return document.model_copy(update={"metadata": merged})

    def _enforce_size_limit(self, source: Path) -> None:
        metadata = self._metadata()
        if not metadata.enabled:
            return
        limit_bytes = metadata.max_file_size_mb * 1024 * 1024
        if source.stat().st_size > limit_bytes:
            raise IngestionError(
                f"Source file '{source}' exceeds the "
                f"{metadata.max_file_size_mb} MB size limit."
            )

    def _resolve_hook(self, name: str) -> IngestionHook | None:
        hook = self._hooks.get(name)
        if hook is not None:
            return hook
        return self._hook_registry.get(name)

    def _run_pre_hooks(self, source: SourceReference) -> SourceReference:
        metadata = self._metadata()
        if not metadata.enabled:
            return source
        for name in metadata.hooks.pre:
            hook = self._resolve_hook(name)
            if hook is None:
                logger.warning("Pre-hook '%s' is not registered; skipping.", name)
                continue
            try:
                source = hook.pre(source)
            except IngestionError:
                raise
            except Exception:
                logger.exception("Pre-hook '%s' raised; skipping.", name)
        return source

    def _run_post_hooks(self, document: SourceDocument) -> SourceDocument:
        metadata = self._metadata()
        if not metadata.enabled:
            return document
        for name in metadata.hooks.post:
            hook = self._resolve_hook(name)
            if hook is None:
                logger.warning("Post-hook '%s' is not registered; skipping.", name)
                continue
            try:
                document = hook.post(document)
            except Exception:
                logger.exception("Post-hook '%s' raised; skipping.", name)
        return document

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
