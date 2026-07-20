"""End-to-end ingestion workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.application import AIProcessingResult, DocumentAIProcessor
from app.core.config import ModelRoutingSettings
from app.core.logging import get_logger
from app.domain.analysis import DocumentAnalysis
from app.domain.documents import SourceDocument
from app.domain.notes import ObsidianNote
from app.infrastructure.ingestion import DocumentIngestionService
from app.infrastructure.llm import OllamaClient
from app.infrastructure.routing.classifier import DocumentClassifier
from app.infrastructure.routing.processors import default_processors
from app.infrastructure.routing.router import ProcessorRouter
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
        processor: DocumentProcessor | None = None,
        ollama_client: OllamaClient | None = None,
        routing: ModelRoutingSettings | None = None,
        vision_client: object | None = None,
        transcriber: object | None = None,
        note_generator: NoteGenerator,
        writer: NoteWriter,
    ) -> None:
        self._ingestion_service = ingestion_service
        self._note_generator = note_generator
        self._writer = writer
        self._vision_client = vision_client
        self._transcriber = transcriber
        self._classifier = DocumentClassifier()
        self._router = ProcessorRouter(routing or ModelRoutingSettings())
        for proc in default_processors():
            self._router.register(proc)

        if processor is not None:
            self._processor = processor
            self._ollama_client = None
        elif ollama_client is not None:
            self._processor = None
            self._ollama_client = ollama_client
        else:
            raise ValueError("Either processor or ollama_client must be provided.")

    @classmethod
    def from_runtime(
        cls,
        *,
        ollama_client: OllamaClient,
        writer: VaultWriter,
        routing: ModelRoutingSettings | None = None,
        vision_client: object | None = None,
        transcriber: object | None = None,
    ) -> IngestionWorkflow:
        """Create the production workflow from runtime integrations."""

        return cls(
            ingestion_service=DocumentIngestionService(),
            ollama_client=ollama_client,
            routing=routing,
            vision_client=vision_client,
            transcriber=transcriber,
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

        classification = self._classifier.classify(document)
        selection = self._router.select(classification)
        logger.info(
            "Selected processor and model.",
            extra={
                "source": document.source,
                "kind": classification.kind,
                "processor": selection.processor_name,
                "model": selection.model_name,
            },
        )

        document, processing_confidence = self._run_routed_processor(
            selection.processor_name, document,
        )

        if self._processor is not None:
            ai_result = self._processor.process(document)
        else:
            processor = DocumentAIProcessor(
                self._ollama_client,
                model=selection.model_name,
            )
            ai_result = processor.process(document)

        note = self._note_generator.generate(
            document=document,
            analysis=ai_result.analysis,
            processing_confidence=processing_confidence,
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

    def _run_routed_processor(
        self,
        processor_name: str,
        document: SourceDocument,
    ) -> tuple[SourceDocument, float | None]:
        """Run the routed processor to extract/enrich document text before AI analysis."""
        from app.infrastructure.routing.processor_impls import (
            AudioProcessor,
            HandwritingProcessor,
            OCRProcessor,
            VisionProcessor,
            get_processor_by_name,
        )

        vision_kw = {"vision_client": self._vision_client} if self._vision_client else {}
        audio_kw = {"transcriber": self._transcriber} if self._transcriber else {}

        _constructors = {
            "VisionProcessor": lambda: VisionProcessor(**vision_kw),
            "OCRProcessor": lambda: OCRProcessor(**vision_kw),
            "HandwritingProcessor": lambda: HandwritingProcessor(**vision_kw),
            "AudioProcessor": lambda: AudioProcessor(**audio_kw),
        }

        factory = _constructors.get(processor_name)
        if factory is not None:
            processor = factory()
        else:
            processor = get_processor_by_name(processor_name)

        if processor is None:
            return document, None

        try:
            result = processor.process(document)
            enriched = document.model_copy(
                update={
                    "text": result.extracted_text or document.text,
                    "source_type": result.source_type,
                }
            )
            logger.info(
                "Routed processor completed.",
                extra={
                    "processor": processor_name,
                    "source": document.source,
                    "extracted_length": len(result.extracted_text),
                },
            )
            return enriched, result.confidence
        except Exception:
            logger.warning(
                "Routed processor failed, falling back to original document.",
                extra={"processor": processor_name, "source": document.source},
                exc_info=True,
            )
            return document, None
