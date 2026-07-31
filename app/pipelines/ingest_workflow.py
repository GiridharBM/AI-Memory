"""End-to-end ingestion workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.application import AIProcessingResult, DocumentAIProcessor
from app.core.config import ModelRoutingSettings, Settings
from app.core.logging import get_logger
from app.domain.analysis import DocumentAnalysis
from app.domain.documents import SourceDocument
from app.domain.knowledge_graph import KnowledgeGraph
from app.domain.notes import ObsidianNote
from app.infrastructure.embeddings import EmbeddingService
from app.infrastructure.ingestion import DocumentIngestionService
from app.infrastructure.knowledge_graph import KnowledgeGraphBuilder
from app.infrastructure.llm import OllamaClient
from app.infrastructure.routing.classifier import DocumentClassifier
from app.infrastructure.routing.processors import default_processors
from app.infrastructure.routing.router import ProcessorRouter
from app.infrastructure.semantic_chunking import SemanticChunker
from app.infrastructure.vault import VaultWriter, WikiUpdateResult
from app.infrastructure.vector_store import VectorStore
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
    knowledge_graph: KnowledgeGraph | None = None
    chunks_stored: int = 0
    cross_links_added: int = 0


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
        chunker: object | None = None,
        embedding_service: object | None = None,
        vector_store: object | None = None,
        knowledge_graph_builder: object | None = None,
        graph_persistence_path: Path | None = None,
    ) -> None:
        self._ingestion_service = ingestion_service
        self._note_generator = note_generator
        self._writer = writer
        self._vision_client = vision_client
        self._transcriber = transcriber
        self._routing = routing or ModelRoutingSettings()
        self._classifier = DocumentClassifier()
        self._router = ProcessorRouter(self._routing)
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

        self._chunker = chunker
        self._embedding_service = embedding_service
        self._vector_store = vector_store
        self._kg_builder = knowledge_graph_builder
        self._graph_path = graph_persistence_path

    @classmethod
    def from_runtime(
        cls,
        *,
        ollama_client: OllamaClient,
        writer: VaultWriter,
        routing: ModelRoutingSettings | None = None,
        vision_client: object | None = None,
        transcriber: object | None = None,
        chunker: object | None = None,
        embedding_service: object | None = None,
        vector_store: object | None = None,
        knowledge_graph_builder: object | None = None,
        graph_persistence_path: Path | None = None,
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
            chunker=chunker,
            embedding_service=embedding_service,
            vector_store=vector_store,
            knowledge_graph_builder=knowledge_graph_builder,
            graph_persistence_path=graph_persistence_path,
        )

    @classmethod
    def create_default(
        cls,
        settings: Settings,
        *,
        vision_client: object | None = None,
        transcriber: object | None = None,
    ) -> IngestionWorkflow:
        """Create the production workflow from application settings."""

        ollama_client = OllamaClient(settings.ollama)
        if vision_client is None:
            try:
                from app.infrastructure.llm.vision_client import OllamaVisionClient

                vision_client = OllamaVisionClient(
                    settings.ollama, vision_model=settings.models.vision,
                )
            except Exception:
                logger.debug("Vision client unavailable.")
        if transcriber is None:
            try:
                from app.infrastructure.llm.whisper_transcriber import WhisperTranscriber

                transcriber = WhisperTranscriber()
            except Exception:
                logger.debug("Whisper transcriber unavailable.")
        manifest_root = settings.paths.manifest_root
        return cls.from_runtime(
            ollama_client=ollama_client,
            writer=VaultWriter.from_settings(settings),
            routing=settings.models,
            vision_client=vision_client,
            transcriber=transcriber,
            chunker=SemanticChunker(),
            embedding_service=EmbeddingService(
                settings.ollama, model=settings.models.embeddings,
            ),
            vector_store=VectorStore(
                persistence_path=manifest_root / "vector_store.json",
            ),
            knowledge_graph_builder=KnowledgeGraphBuilder(),
            graph_persistence_path=manifest_root / "knowledge_graph.json",
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
            # Use general_text model for AI analysis regardless of which
            # processor extracted the text (vision/audio processors use
            # specialized models for extraction, not analysis).
            analysis_model = self._routing.model_for("general_text")
            processor = DocumentAIProcessor(
                self._ollama_client,
                model=analysis_model,
            )
            ai_result = processor.process(document)

        kg, chunks_stored, cross_links = self._run_knowledge_engine(
            document, ai_result.analysis,
        )

        if cross_links:
            existing = set(ai_result.analysis.suggested_related_notes)
            existing.update(ai_result.analysis.suggested_backlinks)
            for link in cross_links:
                if link not in existing:
                    ai_result.analysis.suggested_backlinks.append(link)

        ocr_confidence = processing_confidence if selection.processor_name in (
            "OCRProcessor", "HandwritingProcessor", "VisionProcessor",
        ) else None

        note = self._note_generator.generate(
            document=document,
            analysis=ai_result.analysis,
            ocr_confidence=ocr_confidence,
            processing_confidence=processing_confidence,
        )
        write_result = self._writer.save(note)

        if hasattr(self._writer, "create_placeholder"):
            for related_title in ai_result.analysis.suggested_related_notes:
                self._writer.create_placeholder(related_title, note.title)

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
            knowledge_graph=kg,
            chunks_stored=chunks_stored,
            cross_links_added=cross_links,
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
            # For vision-required types (image, scanned_pdf, handwritten), don't silently
            # fall back to original document (which has no text) - that sends images to
            # text-only model causing "this model does not support image input" errors.
            vision_required = {"VisionProcessor", "OCRProcessor", "HandwritingProcessor"}
            if processor_name in vision_required:
                logger.error(
                    "Vision processor failed for vision-required type, not falling back.",
                    extra={"processor": processor_name, "source": document.source},
                    exc_info=True,
                )
                raise
            logger.warning(
                "Routed processor failed, falling back to original document.",
                extra={"processor": processor_name, "source": document.source},
                exc_info=True,
            )
            return document, None

    def _run_knowledge_engine(
        self,
        document: SourceDocument,
        analysis: DocumentAnalysis,
    ) -> tuple[KnowledgeGraph | None, int, int]:
        """Run knowledge engine steps: chunk, embed, store, graph, cross-links."""
        if self._chunker is None or self._embedding_service is None or self._vector_store is None:
            return None, 0, 0

        from app.domain.vector_store import VectorEntry
        from app.infrastructure.knowledge_graph import KnowledgeGraphBuilder

        graph = None
        chunks_stored = 0
        cross_links = 0

        try:
            chunks = self._chunker.chunk(
                document.text, str(document.source), document.source_type,
            )

            if chunks:
                texts = [c.text for c in chunks]
                embeddings = self._embedding_service.embed_batch(texts)
                entries = []
                for chunk, emb_result in zip(chunks, embeddings, strict=False):
                    if emb_result.embedding:
                        entries.append(VectorEntry(
                            id=chunk.chunk_id,
                            text=chunk.text,
                            embedding=emb_result.embedding,
                            source=chunk.source,
                            source_type=chunk.source_type,
                            chunk_index=chunk.chunk_index,
                        ))
                if entries:
                    self._vector_store.add_batch(entries)
                    chunks_stored = len(entries)
                    self._vector_store.save()

            if self._kg_builder is None:
                self._kg_builder = KnowledgeGraphBuilder()
            result = self._kg_builder.build_from_analysis(
                analysis, str(document.source),
            )
            graph = result.graph

            if self._graph_path:
                existing = (
                    KnowledgeGraph.load(self._graph_path)
                    if self._graph_path.exists()
                    else KnowledgeGraph()
                )
                merged = self._kg_builder.merge_graphs(existing, graph)
                merged.save(self._graph_path)
                graph = merged

            if chunks and embeddings:
                cross_links = self._find_cross_document_links(
                    chunks, embeddings, document.source,
                )

        except Exception:
            logger.warning(
                "Knowledge engine step failed.",
                extra={"source": document.source},
                exc_info=True,
            )

        logger.info(
            "Knowledge engine completed.",
            extra={
                "source": document.source,
                "chunks_stored": chunks_stored,
                "cross_links": cross_links,
            },
        )
        return graph, chunks_stored, cross_links

    def _find_cross_document_links(
        self,
        chunks: list,
        precomputed_embeddings: list,
        current_source: str,
    ) -> int:
        """Find similar existing chunks and return cross-document link count."""
        from app.infrastructure.search import SemanticSearch

        search = SemanticSearch(self._vector_store)
        link_count = 0
        seen_sources: set[str] = set()

        for chunk, emb_result in zip(chunks[:3], precomputed_embeddings[:3], strict=False):
            if not emb_result.embedding:
                continue
            hits = search.search(emb_result.embedding, top_k=3, min_score=0.7)
            for hit in hits:
                if hit.source != current_source and hit.source not in seen_sources:
                    seen_sources.add(hit.source)
                    link_count += 1

        return link_count
