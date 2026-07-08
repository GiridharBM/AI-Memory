"""End-to-end ingestion workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.application import AIProcessingResult, DocumentAIProcessor
from app.core.logging import get_logger
from app.domain.analysis import DocumentAnalysis
from app.domain.documents import SourceDocument
from app.domain.notes import ObsidianNote
from app.infrastructure.ingestion import DocumentIngestionService
from app.infrastructure.llm import OllamaClient
from app.infrastructure.vault import VaultWriter, WikiUpdateResult
from app.templates import ObsidianMarkdownGenerator

logger = get_logger(__name__)


class DocumentProcessor(Protocol):
    """Protocol for components that analyze source documents."""

    def process(self, document: SourceDocument) -> AIProcessingResult:
        """Process a source document and return validated AI analysis."""


class NoteGenerator(Protocol):
    """Protocol for components that turn analysis into Markdown notes."""

    def generate(self, *, document: SourceDocument, analysis: DocumentAnalysis) -> ObsidianNote:
        """Generate a Markdown note from a document and analysis."""


class NoteWriter(Protocol):
    """Protocol for components that persist generated notes."""

    def save(self, note: ObsidianNote) -> WikiUpdateResult:
        """Persist a generated note."""


class IngestionWorkflowError(RuntimeError):
    """Raised when the end-to-end ingestion workflow cannot complete."""


@dataclass(slots=True)
class IngestionWorkflowResult:
    """Successful end-to-end ingestion workflow result."""

    document: SourceDocument
    ai_result: AIProcessingResult
    note: ObsidianNote
    write_result: WikiUpdateResult


class IngestionWorkflow:
    """Coordinate document ingestion, AI analysis, Markdown generation, and vault writes."""

    def __init__(
        self,
        *,
        ingestion_service: DocumentIngestionService,
        processor: DocumentProcessor,
        note_generator: NoteGenerator,
        writer: NoteWriter,
    ) -> None:
        self._ingestion_service = ingestion_service
        self._processor = processor
        self._note_generator = note_generator
        self._writer = writer

    @classmethod
    def from_runtime(
        cls,
        *,
        ollama_client: OllamaClient,
        writer: VaultWriter,
    ) -> IngestionWorkflow:
        """Create the production workflow from runtime integrations."""

        return cls(
            ingestion_service=DocumentIngestionService(),
            processor=DocumentAIProcessor(ollama_client),
            note_generator=ObsidianMarkdownGenerator(),
            writer=writer,
        )

    def run(
        self,
        source: str | Path,
        *,
        expected_source_type: str | None = None,
    ) -> IngestionWorkflowResult:
        """Run the complete document-to-Obsidian workflow."""

        logger.info("Starting ingestion workflow.", extra={"source": str(source)})

        ingestion_result = self._ingestion_service.ingest(source)
        if not ingestion_result.succeeded or ingestion_result.document is None:
            reason = (
                ingestion_result.error.reason
                if ingestion_result.error
                else "Unknown ingestion error."
            )
            raise IngestionWorkflowError(reason)

        document = ingestion_result.document
        if expected_source_type is not None and document.source_type != expected_source_type:
            raise IngestionWorkflowError(
                f"Expected source type '{expected_source_type}', "
                f"but detected '{document.source_type}'."
            )

        ai_result = self._processor.process(document)
        note = self._note_generator.generate(
            document=document,
            analysis=ai_result.analysis,
        )
        write_result = self._writer.save(note)

        logger.info(
            "Completed ingestion workflow.",
            extra={
                "source": document.source,
                "source_type": document.source_type,
                "note_path": str(write_result.note_path),
            },
        )

        return IngestionWorkflowResult(
            document=document,
            ai_result=ai_result,
            note=note,
            write_result=write_result,
        )
