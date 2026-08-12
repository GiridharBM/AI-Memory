"""End-to-end ingestion workflow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from app.application import AIProcessingResult, DocumentAIProcessor
from app.core.config import (
    CodeSettings,
    EntitySettings,
    GraphSettings,
    ImageSettings,
    MetadataSettings,
    ModelRoutingSettings,
    RelationshipSettings,
    Settings,
    StructureSettings,
    TableSettings,
)
from app.core.logging import get_logger
from app.domain.analysis import DocumentAnalysis
from app.domain.documents import SourceDocument
from app.domain.entity_relationship import Entity, Relationship
from app.domain.knowledge_graph import KnowledgeGraph
from app.domain.notes import ObsidianNote
from app.infrastructure.document_intelligence import (
    get_default_document_graph_builder,
    get_default_entity_extractor,
    get_default_relationship_detector,
    get_default_structure_analyzer,
    graph_to_dict,
)
from app.infrastructure.document_intelligence.entities import EntityExtractor
from app.infrastructure.document_intelligence.graph.builder import DocumentGraphBuilder
from app.infrastructure.document_intelligence.ocr import get_default_ocr_service
from app.infrastructure.document_intelligence.ocr.base import DocumentOcrService
from app.infrastructure.document_intelligence.ocr.models import OcrResult
from app.infrastructure.document_intelligence.relationships import RelationshipDetector
from app.infrastructure.document_intelligence.structure.detector import (
    TEXT_BEARING_KINDS,
    StructureAnalyzer,
    max_structure_text_bytes,
)
from app.infrastructure.document_intelligence.tables import get_table_extractor
from app.infrastructure.embeddings import EmbeddingService
from app.infrastructure.ingestion import DocumentIngestionService
from app.infrastructure.knowledge_graph import KnowledgeGraphBuilder
from app.infrastructure.llm import OllamaClient
from app.infrastructure.routing.classifier import DocumentClassifier
from app.infrastructure.routing.processors import default_processors
from app.infrastructure.routing.router import ProcessorRouter
from app.infrastructure.semantic_chunking import ChunkingPolicy, SemanticChunker
from app.infrastructure.vault import VaultWriter, WikiUpdateResult
from app.infrastructure.vector_store import VectorStore
from app.templates import ObsidianMarkdownGenerator

if TYPE_CHECKING:
    from app.infrastructure.routing.processor_impls import RoutedDocumentProcessor

logger = get_logger(__name__)


class DocumentProcessor(Protocol):
    """Protocol for components that analyze source documents."""

    def process(self, document: SourceDocument) -> AIProcessingResult:
        """Process a source document and return validated AI analysis."""


class NoteGenerator(Protocol):
    """Protocol for components that turn analysis into Markdown notes."""

    def generate(
        self,
        *,
        document: SourceDocument,
        analysis: DocumentAnalysis,
        ocr_confidence: float | None = None,
        processing_confidence: float | None = None,
    ) -> ObsidianNote:
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
        settings: Settings | None = None,
        ocr_service: DocumentOcrService | None = None,
        note_generator: NoteGenerator,
        writer: NoteWriter,
        chunker: SemanticChunker | None = None,
        embedding_service: EmbeddingService | None = None,
        vector_store: VectorStore | None = None,
        knowledge_graph_builder: KnowledgeGraphBuilder | None = None,
        graph_persistence_path: Path | None = None,
    ) -> None:
        self._ingestion_service = ingestion_service
        self._note_generator = note_generator
        self._writer = writer
        self._vision_client: object | None = None
        self._transcriber: object | None = None
        self._ocr_service = ocr_service
        self._structure_analyzer: StructureAnalyzer | None = None
        self._entity_extractor: EntityExtractor | None = None
        self._relationship_detector: RelationshipDetector | None = None
        self._document_graph_builder: DocumentGraphBuilder | None = None
        self._routing = routing or ModelRoutingSettings()
        self._settings = settings
        self._classifier = DocumentClassifier(
            mime_enabled=self._metadata().mime_enabled,
            language_detection_enabled=self._metadata().language_detection_enabled,
        )
        self._router = ProcessorRouter(self._routing)
        for proc in default_processors():
            self._router.register(proc)

        self._processor: DocumentProcessor | None
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

    def _metadata(self) -> MetadataSettings:
        if self._settings is None:
            return MetadataSettings()
        return self._settings.intelligence.metadata

    def _structure(self) -> StructureSettings:
        if self._settings is None:
            return StructureSettings()
        return self._settings.intelligence.structure

    def _entities(self) -> EntitySettings:
        if self._settings is None:
            return EntitySettings()
        return self._settings.intelligence.entities

    def _relationships(self) -> RelationshipSettings:
        if self._settings is None:
            return RelationshipSettings()
        return self._settings.intelligence.relationships

    def _graph(self) -> GraphSettings:
        if self._settings is None:
            return GraphSettings()
        return self._settings.intelligence.graph

    def _tables(self) -> TableSettings:
        if self._settings is None:
            return TableSettings()
        return self._settings.intelligence.tables

    def _images(self) -> ImageSettings:
        if self._settings is None:
            return ImageSettings()
        return self._settings.intelligence.images

    def _code(self) -> CodeSettings:
        if self._settings is None:
            return CodeSettings()
        return self._settings.intelligence.code

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
                    settings.ollama,
                    vision_model=settings.models.vision,
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
        # ponytail: enabled gates the service at the workflow boundary — an
        # empty DocumentOcrService would raise on extract, not passthrough.
        ocr_service = (
            None if not settings.intelligence.ocr.enabled else get_default_ocr_service(settings)
        )
        workflow = cls(
            ingestion_service=DocumentIngestionService(settings=settings),
            ollama_client=ollama_client,
            routing=settings.models,
            settings=settings,
            ocr_service=ocr_service,
            note_generator=ObsidianMarkdownGenerator(),
            writer=VaultWriter.from_settings(settings),
            chunker=SemanticChunker(
                sentence_tokenizer=settings.chunking.sentence_tokenizer,
                policy=ChunkingPolicy(
                    heading_size_step=settings.chunking.heading_size_step,
                    min_chunk_chars=settings.chunking.min_chunk_chars,
                    snap_overlap=settings.chunking.snap_overlap,
                    snap_max_back=settings.chunking.snap_max_back,
                    heading_overlap_boundary=settings.chunking.heading_overlap_boundary,
                ),
            ),
            embedding_service=EmbeddingService(
                settings.ollama,
                model=settings.models.embeddings,
            ),
            vector_store=VectorStore(
                persistence_path=manifest_root / "vector_store.json",
            ),
            knowledge_graph_builder=KnowledgeGraphBuilder(),
            graph_persistence_path=manifest_root / "knowledge_graph.json",
        )
        workflow._vision_client = vision_client
        workflow._transcriber = transcriber
        workflow._structure_analyzer = get_default_structure_analyzer()
        workflow._entity_extractor = get_default_entity_extractor()
        workflow._relationship_detector = get_default_relationship_detector()
        workflow._document_graph_builder = get_default_document_graph_builder()
        return workflow

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

        result = self._process_document(document, parent_id=None)
        self._ingest_children(document)
        return result

    def _process_document(
        self,
        document: SourceDocument,
        *,
        parent_id: str | None,
    ) -> IngestionWorkflowResult:
        """Classify, process, analyze, and write a single document's note."""

        classification = self._classifier.classify(document)
        selection = self._router.select(classification)
        logger.info(
            "Selected processor and model.",
            extra={
                "source": document.source,
                "kind": classification.kind,
                "processor": selection.processor_name,
                "model": selection.model_name,
                "parent_id": parent_id,
            },
        )

        document, processing_confidence, ocr_result = self._run_routed_processor(
            selection.processor_name,
            document,
            language=classification.language,
            parent_id=parent_id,
            kind=classification.kind,
            requires_table_extraction=classification.requires_table_extraction,
        )

        if self._processor is not None:
            ai_result = self._processor.process(document)
        else:
            # Use general_text model for AI analysis regardless of which
            # processor extracted the text (vision/audio processors use
            # specialized models for extraction, not analysis).
            analysis_model = self._routing.model_for("general_text")
            assert self._ollama_client is not None
            processor = DocumentAIProcessor(
                self._ollama_client,
                model=analysis_model,
                language=classification.language,
            )
            ai_result = processor.process(document)

        kg, chunks_stored, cross_links = self._run_knowledge_engine(
            document,
            ai_result.analysis,
        )

        ocr_confidence = None
        if ocr_result is not None and ocr_result.confidence is not None:
            ocr_confidence = ocr_result.confidence
        elif selection.processor_name in (
            "OCRProcessor",
            "HandwritingProcessor",
            "VisionProcessor",
        ):
            ocr_confidence = processing_confidence
        # ponytail: tesseract reports 0-100 but the note template expects 0-1.
        if ocr_confidence is not None and ocr_confidence > 1.0:
            ocr_confidence = ocr_confidence / 100.0

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

    def _ingest_children(self, document: SourceDocument) -> None:
        """Re-ingest email attachment child sources (P2-208).

        Children are ingested through the same ``DocumentIngestionService``
        (reuses ``max_file_size_mb``), capped at ``max_attachments``, and
        never recurse further — a nested email's own attachments are extracted
        but not re-ingested (depth guard, no infinite recursion).
        """
        metadata = self._metadata()
        if not (metadata.enabled and metadata.email_attachments):
            return
        attachment_paths = document.metadata.extra.get("attachment_paths") or []
        if not attachment_paths:
            return
        parent_id = document.source
        pending_cleanup = list(attachment_paths)
        try:
            for index, path_str in enumerate(attachment_paths):
                if index >= metadata.max_attachments:
                    logger.warning(
                        "Skipping email attachment beyond max_attachments.",
                        extra={
                            "path": path_str,
                            "max_attachments": metadata.max_attachments,
                        },
                    )
                    continue
                self._ingest_child(path_str, parent_id=parent_id, cleanup=pending_cleanup)
        finally:
            self._cleanup_attachment_temp_files(pending_cleanup)

    def _ingest_child(
        self,
        path_str: str,
        *,
        parent_id: str,
        cleanup: list[str],
    ) -> None:
        child_result = self._ingestion_service.ingest(path_str)
        if not child_result.succeeded or child_result.document is None:
            reason = child_result.error.reason if child_result.error else "Unknown ingestion error."
            logger.warning(
                "Skipping failed email attachment.",
                extra={"path": path_str, "reason": reason},
            )
            return
        child_document = child_result.document
        extra = dict(child_document.metadata.extra)
        extra["parent_id"] = parent_id
        child_document = child_document.model_copy(
            update={"metadata": child_document.metadata.model_copy(update={"extra": extra})}
        )
        nested = child_document.metadata.extra.get("attachment_paths") or []
        cleanup.extend(nested)
        # A failed attachment (e.g. the AI step errors on it) must not fail the
        # whole email; the parent note is already written by now. Log and move
        # on so the remaining children still get processed.
        try:
            self._process_document(child_document, parent_id=parent_id)
        except Exception:
            logger.exception(
                "Skipping failed email attachment after ingestion.",
                extra={"path": path_str, "parent_id": parent_id},
            )

    def _cleanup_attachment_temp_files(self, paths: list[str]) -> None:
        """Remove email-attachment temp files and their (now empty) dirs."""
        directories = {Path(p).parent for p in paths}
        for path_str in paths:
            try:
                candidate = Path(path_str)
                if candidate.is_file():
                    candidate.unlink()
            except OSError:
                logger.debug("Failed to remove email attachment temp file.", exc_info=True)
        for directory in directories:
            try:
                directory.rmdir()
            except OSError:
                pass

    def _run_routed_processor(
        self,
        processor_name: str,
        document: SourceDocument,
        language: str | None = None,
        parent_id: str | None = None,
        kind: str | None = None,
        requires_table_extraction: bool = False,
    ) -> tuple[SourceDocument, float | None, OcrResult | None]:
        """Run the routed processor to extract/enrich document text before AI analysis."""
        from app.infrastructure.routing.processor_impls import (
            AudioProcessor,
            HandwritingProcessor,
            OCRProcessor,
            VisionProcessor,
            get_processor_by_name,
        )

        audio_kw = {"transcriber": self._transcriber} if self._transcriber else {}

        ocr_preprocess = bool(
            self._settings and self._settings.intelligence.ocr.preprocess
        )
        images_preprocess = bool(
            self._settings and self._settings.intelligence.images.preprocess
        )

        _constructors: dict[str, Callable[[], RoutedDocumentProcessor]] = {
            "VisionProcessor": lambda: VisionProcessor(
                ocr_service=self._ocr_service, language=language,
                preprocess=images_preprocess,
            ),
            "OCRProcessor": lambda: OCRProcessor(
                ocr_service=self._ocr_service, language=language,
                preprocess=ocr_preprocess,
            ),
            "HandwritingProcessor": lambda: HandwritingProcessor(
                ocr_service=self._ocr_service, language=language,
                preprocess=ocr_preprocess,
            ),
            "AudioProcessor": lambda: AudioProcessor(**audio_kw),
        }

        factory = _constructors.get(processor_name)
        processor: RoutedDocumentProcessor | None
        if factory is not None:
            processor = factory()
        else:
            processor = get_processor_by_name(processor_name)

        if processor is None:
            return document, None, None

        try:
            result = processor.process(document)
            if language is not None:
                result.language = language
            if parent_id is not None:
                result.parent_id = parent_id
            extra = dict(document.metadata.extra)
            structure_dict = self._enrich_structure(
                result.extracted_text or document.text,
                str(document.source),
                result.source_type,
            )
            if structure_dict is not None:
                extra["structure"] = structure_dict
            entities = self._enrich_entities(
                result.extracted_text or document.text,
                str(document.source),
                result.source_type,
            )
            if entities is not None:
                extra["entities"] = [entity.model_dump(mode="json") for entity in entities]
                relationships = self._enrich_relationships(
                    entities,
                    str(document.source),
                    result.source_type,
                )
                if relationships is not None:
                    extra["relationships"] = [
                        relationship.model_dump(mode="json") for relationship in relationships
                    ]
                graph_dict = self._enrich_graph(
                    entities,
                    relationships or [],
                    str(document.source),
                )
                if graph_dict is not None:
                    extra["knowledge_graph"] = graph_dict
            tables_dict = self._enrich_tables(
                document,
                kind or result.source_type,
                requires_table_extraction,
            )
            if tables_dict is not None:
                extra["tables"] = tables_dict
            images_dict = self._enrich_images(document, kind or result.source_type)
            if images_dict is not None:
                extra["images"] = images_dict
            doc_kind = kind or result.source_type
            code_entry = self._enrich_code(document, doc_kind)
            if code_entry is not None:
                extra["code_structure" if doc_kind == "code" else "notebook_structure"] = (
                    code_entry
                )
            elif doc_kind == "notebook":
                # ponytail: NotebookIngestor attaches notebook_structure
                # unconditionally (P2-605); dropping it here on the disabled
                # path restores pre-M2.6 flattening exactly (rollback R-4).
                extra.pop("notebook_structure", None)
            enriched = document.model_copy(
                update={
                    "text": result.extracted_text or document.text,
                    "source_type": result.source_type,
                    "metadata": document.metadata.model_copy(update={"extra": extra}),
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
            return enriched, result.confidence, result.ocr
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
            return document, None, None

    def _enrich_structure(
        self,
        text: str,
        source: str,
        source_type: str,
    ) -> dict[str, object] | None:
        """Return a serialized ``DocumentStructure`` for ``metadata.extra`` (P2-305).

        Gated by ``structure.enabled`` (frozen §5.3), ``TEXT_BEARING_KINDS`` (§7),
        and the 5 MB cap (frozen §5.4 step 4). Analyzer failures are contained
        (frozen §10 R5 / M2.2 lesson L4): a raised analyzer yields no key and
        ingestion continues. ``enrich_analysis_input`` is never read (C-5).
        """
        if not self._structure().enabled:
            return None
        if source_type not in TEXT_BEARING_KINDS:
            return None
        analyzer = self._structure_analyzer
        if analyzer is None:
            return None
        if len(text.encode("utf-8")) > max_structure_text_bytes:
            logger.warning(
                "Skipping structure analysis: text exceeds 5 MB cap.",
                extra={"bytes": len(text.encode("utf-8"))},
            )
            return None
        try:
            structure = analyzer.analyze(text, source)
        except Exception:
            logger.warning("Structure analysis failed.", extra={"source": source}, exc_info=True)
            return None
        return structure.model_dump(mode="json")

    def _enrich_entities(
        self,
        text: str,
        source: str,
        source_type: str,
    ) -> list[Entity] | None:
        """Return extracted entities for ``metadata.extra`` (P4-102).

        Gated by ``entities.enabled`` and ``TEXT_BEARING_KINDS`` (§7). The
        extractor is deterministic and offline; its failures are contained
        (M2.2 lesson L4): a raised extractor yields no key and ingestion
        continues. ``structure`` is computed only when structure enrichment is
        enabled, so entity extraction falls back to a flat text scan otherwise.
        Serialization to ``extra["entities"]`` happens in the caller, which
        also feeds the returned entities to relationship detection (P4-103).
        """
        if not self._entities().enabled:
            return None
        if source_type not in TEXT_BEARING_KINDS:
            return None
        extractor = self._entity_extractor
        if extractor is None:
            return None
        if len(text.encode("utf-8")) > max_structure_text_bytes:
            logger.warning(
                "Skipping entity extraction: text exceeds 5 MB cap.",
                extra={"bytes": len(text.encode("utf-8"))},
            )
            return None
        structure = None
        if self._structure().enabled and self._structure_analyzer is not None:
            try:
                structure = self._structure_analyzer.analyze(text, source)
            except Exception:
                logger.warning(
                    "Structure analysis failed (entity extraction continues).",
                    extra={"source": source},
                    exc_info=True,
                )
        try:
            entities = extractor.extract(text, source, source_type, structure)
        except Exception:
            logger.warning(
                "Entity extraction failed.", extra={"source": source}, exc_info=True
            )
            return None
        return list(entities)

    def _enrich_relationships(
        self,
        entities: list[Entity],
        source: str,
        source_type: str,
    ) -> list[Relationship] | None:
        """Return detected relationships for ``metadata.extra`` (P4-103).

        Consumes the entities extracted for this document (P4-102) so
        relationship detection is a single-pass, consistent stage. Gated by
        ``relationships.enabled``; detection is deterministic and offline, and
        its failures are contained (M2.2 lesson L4): a raised detector yields
        no key and ingestion continues. Serialization to
        ``extra["relationships"]`` happens in the caller, which also feeds the
        returned relationships to document-graph construction (P4-104).
        """
        if not self._relationships().enabled:
            return None
        detector = self._relationship_detector
        if detector is None:
            return None
        try:
            relationships = detector.detect(entities)
        except Exception:
            logger.warning(
                "Relationship detection failed.", extra={"source": source}, exc_info=True
            )
            return None
        return list(relationships)

    def _enrich_graph(
        self,
        entities: list[Entity],
        relationships: list[Relationship],
        source: str,
    ) -> dict[str, object] | None:
        """Return a serialized document ``KnowledgeGraph`` for ``metadata.extra`` (P4-104).

        Consumes the entities and relationships already extracted for this
        document, so the graph is a single-pass, consistent document-level
        construction. Gated by ``graph.enabled``; construction is deterministic
        and offline, and its failures are contained (M2.2 lesson L4): a raised
        builder yields no key and ingestion continues. When relationships are
        disabled the graph is built from entities alone (disconnected nodes).
        """
        if not self._graph().enabled:
            return None
        builder = self._document_graph_builder
        if builder is None:
            return None
        try:
            graph = builder.build(entities, relationships, source)
        except Exception:
            logger.warning(
                "Document graph construction failed.", extra={"source": source}, exc_info=True
            )
            return None
        return graph_to_dict(graph)

    def _enrich_tables(
        self,
        document: SourceDocument,
        kind: str,
        requires_table_extraction: bool = False,
    ) -> list[dict[str, object]] | None:
        """Return serialized tables for ``metadata.extra`` (frozen §4.4 P2-406).

        Gated by ``tables.enabled`` (frozen §2.4) and the frozen AC4 trigger:
        ``requires_table_extraction`` (csv/spreadsheet/database) OR the existing
        classifier ``kind == "pdf"`` (R2). Extraction is best-effort: a missing
        engine or a failed extraction yields ``None`` so the note keeps its flat
        text (frozen §2.4 failure modes).
        """
        if not self._tables().enabled:
            return None
        if not (requires_table_extraction or kind == "pdf"):
            return None
        cfg = self._tables()
        extractor = get_table_extractor(
            pdf_engine=cfg.pdf_engine,
            max_rows=cfg.max_rows,
            max_cols=cfg.max_cols,
            header_sniffing=cfg.header_sniffing,
        )
        selected = extractor.select(kind)
        if selected is None:
            return None
        try:
            tables = selected.extract(document)
        except Exception:
            logger.warning(
                "Table extraction failed.",
                extra={"source": document.source},
                exc_info=True,
            )
            return None
        if not tables:
            return None
        return [table.model_dump(mode="json") for table in tables]

    def _enrich_images(
        self,
        document: SourceDocument,
        kind: str,
    ) -> list[dict[str, object]] | None:
        """Return serialized per-image info for ``metadata.extra`` (frozen §4.5 P2-506).

        Gated by the frozen trigger ``kind == "pdf"`` (F-1): embedded images
        are extracted per page with provenance and attached as ``ImageInfo``
        entries. Extraction is best-effort and additive — a missing PyMuPDF,
        an unreadable PDF, or a PDF with no images yields ``None`` so the
        document and note are unchanged (frozen §10 R-4).
        """
        if kind != "pdf":
            return None
        source_path = document.source_path
        if source_path is None or not source_path.exists():
            return None
        from app.infrastructure.document_intelligence.images import (
            get_default_multi_image_extractor,
        )

        extractor = get_default_multi_image_extractor()
        try:
            images = extractor.extract(source_path)
        except Exception:
            logger.warning(
                "Embedded-image extraction failed.",
                extra={"source": document.source},
                exc_info=True,
            )
            return None
        if not images:
            return None
        return [image.model_dump(mode="json") for image in images]

    def _enrich_code(
        self,
        document: SourceDocument,
        kind: str,
    ) -> dict[str, object] | None:
        """Return serialized code/notebook structure for ``metadata.extra`` (frozen §4.6 P2-606).

        Gated by ``code.enabled`` (frozen §4.6 rollback R-4) and the frozen
        trigger ``kind in {"code", "notebook"}`` (consistent with
        ``_enrich_tables()``/``_enrich_images()``). Code files are parsed from
        ``document.text`` at parse time (capped at ``code.max_code_chars``);
        notebooks already carry ``notebook_structure`` from ``NotebookIngestor``
        (P2-605) and are passed through unchanged. Best-effort: a failed parse
        yields ``None`` so the document keeps its flat text (frozen §4.6
        failure modes). ``code.languages`` / ``code.include_docstrings`` are
        contract-only fields this milestone (C-5): not read here.
        """
        cfg = self._code()
        if kind == "notebook":
            return document.metadata.extra.get("notebook_structure") if cfg.enabled else None
        if kind != "code" or not cfg.enabled:
            return None
        from app.infrastructure.document_intelligence.code import parse_code

        try:
            structure = parse_code(
                document.text,
                document.filename,
                max_chars=cfg.max_code_chars,
            )
        except Exception:
            logger.warning(
                "Code structure analysis failed.",
                extra={"source": document.source},
                exc_info=True,
            )
            return None
        return structure.model_dump(mode="json")

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
                document.text,
                str(document.source),
                document.source_type,
            )

            if chunks:
                texts = [c.text for c in chunks]
                embeddings = self._embedding_service.embed_batch(texts)
                entries = []
                for chunk, emb_result in zip(chunks, embeddings, strict=False):
                    if emb_result.embedding:
                        entries.append(
                            VectorEntry(
                                id=chunk.chunk_id,
                                text=chunk.text,
                                embedding=emb_result.embedding,
                                source=chunk.source,
                                source_type=chunk.source_type,
                                chunk_index=chunk.chunk_index,
                                start_char=chunk.start_char,
                                end_char=chunk.end_char,
                                metadata=chunk.metadata,
                            )
                        )
                if entries:
                    self._vector_store.add_batch(entries)
                    chunks_stored = len(entries)
                    self._vector_store.save()

            if self._kg_builder is None:
                self._kg_builder = KnowledgeGraphBuilder()
            result = self._kg_builder.build_from_analysis(
                analysis,
                str(document.source),
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
                    chunks,
                    embeddings,
                    document.source,
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

        if self._vector_store is None:
            return 0
        search = SemanticSearch(self._vector_store)
        link_count = 0
        seen_sources: set[str] = set()

        for _chunk, emb_result in zip(chunks[:3], precomputed_embeddings[:3], strict=False):
            if not emb_result.embedding:
                continue
            hits = search.search(emb_result.embedding, top_k=3, min_score=0.7)
            for hit in hits:
                if hit.source != current_source and hit.source not in seen_sources:
                    seen_sources.add(hit.source)
                    link_count += 1

        return link_count
