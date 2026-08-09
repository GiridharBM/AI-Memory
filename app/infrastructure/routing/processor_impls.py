"""Document processors for each content type."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, cast

from app.core.logging import get_logger
from app.domain.documents import SourceDocument
from app.domain.processed_document import ProcessedDocument

if TYPE_CHECKING:
    from app.infrastructure.document_intelligence.ocr.base import DocumentOcrService
    from app.infrastructure.document_intelligence.ocr.models import OcrResult

logger = get_logger(__name__)

# Type aliases for optional dependencies to avoid import cycles at module level
_OllamaVisionClient = object  # app.infrastructure.llm.vision_client.OllamaVisionClient
_WhisperTranscriber = object  # app.infrastructure.llm.whisper_transcriber.WhisperTranscriber


def _extract_title(document: SourceDocument) -> str:
    return document.metadata.title or document.filename or document.source


def _base_metadata(document: SourceDocument) -> dict[str, object]:
    return {
        "source": document.source,
        "source_type": document.source_type,
        "filename": document.filename,
    }


def _passthrough(
    document: SourceDocument,
    *,
    title: str | None = None,
    source_type: str | None = None,
    confidence: float = 0.90,
    extra: dict[str, object] | None = None,
) -> ProcessedDocument:
    t = title or _extract_title(document)
    meta = {**_base_metadata(document), **(extra or {})}
    return ProcessedDocument(
        title=t,
        content=document.text,
        markdown=f"# {t}\n\n{document.text}",
        metadata=meta,
        extracted_text=document.text,
        confidence=confidence,
        source_type=source_type or document.source_type,
    )


@lru_cache(maxsize=1)
def _prompt_templates() -> dict[str, str]:
    """Load the vision/OCR prompt templates from application config (R-6)."""
    from app.core.config import load_settings

    prompts = load_settings().intelligence.prompts
    return {"ocr": prompts.ocr, "handwriting": prompts.handwriting, "vision": prompts.vision}


def _resolve_prompt(template: str, language: str | None = None) -> str:
    """Substitute the ``{language}`` slot in an OCR prompt template."""
    return template.replace("{language}", language or "")


def _ocr_service_from_client(vision_client: object | None) -> DocumentOcrService | None:
    """Wrap a legacy vision client into a ``DocumentOcrService``, or None."""
    if vision_client is None:
        return None
    from app.infrastructure.document_intelligence.ocr.base import DocumentOcrService
    from app.infrastructure.document_intelligence.ocr.engines import VisionOcrEngine
    from app.infrastructure.llm.vision_client import OllamaVisionClient

    return DocumentOcrService(
        engines=[VisionOcrEngine(cast(OllamaVisionClient, vision_client))]
    )


def _extract_via_service(
    service: DocumentOcrService,
    document: SourceDocument,
    *,
    prompt: str,
    preprocess: bool = False,
) -> tuple[str, OcrResult | None]:
    """Extract text through the OCR service.

    A missing source path falls back to the document text (legacy behavior);
    engine-selection failures propagate so the workflow's vision-required
    no-fallback guard stays intact.  The ``preprocess`` flag is driven by
    the per-path config toggle (``images.preprocess`` for images,
    ``ocr.preprocess`` for OCR/handwriting) — never hardcoded.
    """
    try:
        result = service.extract(document, prompt=prompt, preprocess=preprocess)
    except ValueError:
        logger.warning(
            "OCR service could not run (source path missing); using document text.",
            extra={"source": document.source},
        )
        return document.text, None
    return result.text, result


def _audio_extract(transcriber: object, document: SourceDocument) -> str:
    """Extract text from an audio file via the whisper transcriber."""
    if not hasattr(transcriber, "transcribe"):
        return document.text

    source_path = document.source_path
    if source_path and source_path.exists():
        return transcriber.transcribe(source_path)
    return document.text


# ── Text & Markup ────────────────────────────────────────────────────────────


class TextProcessor:
    """Process plain text and generic unknown files."""

    name = "TextProcessor"
    supported_kinds = {"text", "unknown", "tex", "epub"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing text file: %s", document.filename)
        return _passthrough(document, source_type=document.source_type, confidence=0.95)


class MarkdownProcessor:
    """Process Markdown files."""

    name = "MarkdownProcessor"
    supported_kinds = {"markdown"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing markdown file: %s", document.filename)
        return _passthrough(document, source_type="markdown", confidence=0.95)


class WebProcessor:
    """Process web content files (HTML, XML, JSON, RSS)."""

    name = "WebProcessor"
    supported_kinds = {"web", "html", "json", "xml"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing web file: %s", document.filename)
        return _passthrough(document, source_type="web", confidence=0.90)


# ── Code & Config ────────────────────────────────────────────────────────────


class CodeProcessor:
    """Process source code files."""

    name = "CodeProcessor"
    supported_kinds = {"code"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing code file: %s", document.filename)
        return _passthrough(document, source_type="code", confidence=0.92)


class ConfigProcessor:
    """Process configuration files (.env, .toml, .ini, .cfg, .conf)."""

    name = "ConfigProcessor"
    supported_kinds = {"config"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing config file: %s", document.filename)
        return _passthrough(document, source_type="config", confidence=0.93)


# ── Documents ────────────────────────────────────────────────────────────────


class PDFProcessor:
    """Process typed PDF files."""

    name = "PDFProcessor"
    supported_kinds = {"pdf"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing PDF file: %s", document.filename)
        return _passthrough(document, source_type="pdf", confidence=0.90)


class DocxProcessor:
    """Process DOCX/ODT/RTF document files."""

    name = "DocxProcessor"
    supported_kinds = {"docx"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing document file: %s", document.filename)
        return _passthrough(document, source_type="docx", confidence=0.90)


class PptxProcessor:
    """Process PPTX/PPT/ODP presentation files."""

    name = "PptxProcessor"
    supported_kinds = {"pptx"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing presentation file: %s", document.filename)
        return _passthrough(document, source_type="pptx", confidence=0.88)


class ResearchProcessor:
    """Process research citation files (.bib, .ris)."""

    name = "ResearchProcessor"
    supported_kinds = {"research"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing research file: %s", document.filename)
        return _passthrough(document, source_type="research", confidence=0.88)


# ── Data ─────────────────────────────────────────────────────────────────────


class TableProcessor:
    """Process CSV/TSV and spreadsheet files."""

    name = "TableProcessor"
    supported_kinds = {"csv", "spreadsheet"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing table file: %s", document.filename)
        return _passthrough(document, source_type=document.source_type, confidence=0.88)


class DatabaseProcessor:
    """Process database files (.sqlite, .db)."""

    name = "DatabaseProcessor"
    supported_kinds = {"database"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing database file: %s", document.filename)
        return _passthrough(document, source_type="database", confidence=0.85)


class NotebookProcessor:
    """Process Jupyter notebook files."""

    name = "NotebookProcessor"
    supported_kinds = {"notebook"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing notebook file: %s", document.filename)
        return _passthrough(document, source_type="notebook", confidence=0.90)


# ── Media ────────────────────────────────────────────────────────────────────


class VisionProcessor:
    """Process image files via the vision OCR engine."""

    name = "VisionProcessor"
    supported_kinds = {"image"}

    def __init__(
        self,
        *,
        vision_client: object | None = None,
        ocr_service: DocumentOcrService | None = None,
        prompt: str | None = None,
        language: str | None = None,
        preprocess: bool = False,
    ) -> None:
        self._vision_client = vision_client
        self._ocr_service = ocr_service
        self._prompt = prompt
        self._language = language
        self._preprocess = preprocess

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing image file: %s", document.filename)
        service = self._ocr_service or _ocr_service_from_client(self._vision_client)
        if service is None:
            return _passthrough(
                document,
                source_type="image",
                confidence=0.70,
                extra={"model_used": False},
            )
        prompt = _resolve_prompt(
            self._prompt or _prompt_templates()["vision"], self._language
        )
        extracted, ocr_result = _extract_via_service(
            service, document, prompt=prompt, preprocess=self._preprocess,
        )
        t = _extract_title(document)
        meta = {**_base_metadata(document), "model_used": True}
        return ProcessedDocument(
            title=t,
            content=extracted,
            markdown=f"# {t}\n\n{extracted}",
            metadata=meta,
            extracted_text=extracted,
            confidence=0.85,
            source_type="image",
            ocr=ocr_result,
        )


class AudioProcessor:
    """Process audio files via whisper transcriber."""

    name = "AudioProcessor"
    supported_kinds = {"audio"}

    def __init__(self, *, transcriber: object | None = None) -> None:
        self._transcriber = transcriber

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing audio file: %s", document.filename)
        extracted = _audio_extract(self._transcriber, document)
        t = _extract_title(document)
        meta = {**_base_metadata(document), "model_used": bool(self._transcriber)}
        return ProcessedDocument(
            title=t,
            content=extracted,
            markdown=f"# {t}\n\n{extracted}",
            metadata=meta,
            extracted_text=extracted,
            confidence=0.85 if self._transcriber else 0.60,
            source_type="audio",
        )


class VideoProcessor:
    """Process video files."""

    name = "VideoProcessor"
    supported_kinds = {"video"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing video file: %s", document.filename)
        return _passthrough(document, source_type="video", confidence=0.70)


# ── Specialized ──────────────────────────────────────────────────────────────


class OCRProcessor:
    """Process scanned PDF files via the OCR engine."""

    name = "OCRProcessor"
    supported_kinds = {"scanned_pdf"}

    def __init__(
        self,
        *,
        vision_client: object | None = None,
        ocr_service: DocumentOcrService | None = None,
        prompt: str | None = None,
        language: str | None = None,
        preprocess: bool = False,
    ) -> None:
        self._vision_client = vision_client
        self._ocr_service = ocr_service
        self._prompt = prompt
        self._language = language
        self._preprocess = preprocess

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing scanned PDF: %s", document.filename)
        service = self._ocr_service or _ocr_service_from_client(self._vision_client)
        if service is None:
            return _passthrough(
                document,
                source_type="scanned_pdf",
                confidence=0.50,
                extra={"ocr": True, "model_used": False},
            )
        prompt = _resolve_prompt(self._prompt or _prompt_templates()["ocr"], self._language)
        extracted, ocr_result = _extract_via_service(
            service, document, prompt=prompt, preprocess=self._preprocess,
        )
        t = _extract_title(document)
        meta = {**_base_metadata(document), "ocr": True, "model_used": True}
        return ProcessedDocument(
            title=t,
            content=extracted,
            markdown=f"# {t}\n\n{extracted}",
            metadata=meta,
            extracted_text=extracted,
            confidence=0.82,
            source_type="scanned_pdf",
            ocr=ocr_result,
        )


class HandwritingProcessor:
    """Process handwritten documents via the OCR engine."""

    name = "HandwritingProcessor"
    supported_kinds = {"handwritten"}

    def __init__(
        self,
        *,
        vision_client: object | None = None,
        ocr_service: DocumentOcrService | None = None,
        prompt: str | None = None,
        language: str | None = None,
        preprocess: bool = False,
    ) -> None:
        self._vision_client = vision_client
        self._ocr_service = ocr_service
        self._prompt = prompt
        self._language = language
        self._preprocess = preprocess

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing handwritten document: %s", document.filename)
        service = self._ocr_service or _ocr_service_from_client(self._vision_client)
        if service is None:
            return _passthrough(
                document,
                source_type="handwritten",
                confidence=0.40,
                extra={"handwriting": True, "model_used": False},
            )
        prompt = _resolve_prompt(
            self._prompt or _prompt_templates()["handwriting"], self._language
        )
        extracted, ocr_result = _extract_via_service(
            service, document, prompt=prompt, preprocess=self._preprocess,
        )
        t = _extract_title(document)
        meta = {**_base_metadata(document), "handwriting": True, "model_used": True}
        return ProcessedDocument(
            title=t,
            content=extracted,
            markdown=f"# {t}\n\n{extracted}",
            metadata=meta,
            extracted_text=extracted,
            confidence=0.75,
            source_type="handwritten",
            ocr=ocr_result,
        )


class ArchiveProcessor:
    """Process archive files (.zip, .tar, .gz, .7z, .rar)."""

    name = "ArchiveProcessor"
    supported_kinds = {"archive"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing archive file: %s", document.filename)
        return _passthrough(document, source_type="archive", confidence=0.80)


class EmailProcessor:
    """Process email files (.eml, .msg)."""

    name = "EmailProcessor"
    supported_kinds = {"email"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing email file: %s", document.filename)
        return _passthrough(document, source_type="email", confidence=0.88)


def _diagram_enabled() -> bool:
    """Whether the drawio→Mermaid conversion is enabled (Milestone 2.5, R-4)."""
    from app.core.config import load_settings

    return load_settings().intelligence.images.diagram_enabled


class DiagramProcessor:
    """Process diagram files (.drawio, .vsdx).

    When diagram intelligence is enabled, ``.drawio`` sources are converted
    to a Mermaid skeleton so the note renders an actual diagram; otherwise the
    raw text (label list) passes through unchanged (R-4 rollback).
    """

    name = "DiagramProcessor"
    supported_kinds = {"diagram"}

    def __init__(self, *, parser: object | None = None) -> None:
        self._parser = parser

    def _parser_impl(self) -> object:
        if self._parser is None:
            from app.infrastructure.document_intelligence.images import DiagramParser

            self._parser = DiagramParser()
        return self._parser

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing diagram file: %s", document.filename)
        if not _diagram_enabled():
            return _passthrough(document, source_type="diagram", confidence=0.85)

        source_path = document.source_path
        mermaid = ""
        if source_path is not None:
            try:
                mermaid = self._parser_impl().parse(source_path)
            except Exception:
                logger.warning(
                    "Diagram parsing failed; falling back to raw text.",
                    extra={"source": document.source},
                    exc_info=True,
                )
                mermaid = ""
        if not mermaid.strip():
            return _passthrough(document, source_type="diagram", confidence=0.85)

        t = _extract_title(document)
        meta = {
            **_base_metadata(document),
            "diagram": True,
            "model_used": False,
            "mermaid": True,
        }
        return ProcessedDocument(
            title=t,
            content=mermaid,
            markdown=f"# {t}\n\n```mermaid\n{mermaid}\n```",
            metadata=meta,
            extracted_text=mermaid,
            confidence=0.85,
            source_type="diagram",
        )


# ── Registry ─────────────────────────────────────────────────────────────────

_ALL_PROCESSORS: list[type] = [
    TextProcessor,
    MarkdownProcessor,
    WebProcessor,
    CodeProcessor,
    ConfigProcessor,
    PDFProcessor,
    DocxProcessor,
    PptxProcessor,
    ResearchProcessor,
    TableProcessor,
    DatabaseProcessor,
    NotebookProcessor,
    VisionProcessor,
    AudioProcessor,
    VideoProcessor,
    OCRProcessor,
    HandwritingProcessor,
    ArchiveProcessor,
    EmailProcessor,
    DiagramProcessor,
]


def get_processor_by_name(name: str) -> object | None:
    """Return the processor instance for a given name, or None."""
    _registry = {cls.__name__: cls for cls in _ALL_PROCESSORS}
    cls = _registry.get(name)
    return cls() if cls is not None else None
