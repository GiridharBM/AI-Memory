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


# ── Passthrough processors (data-driven) ──────────────────────────────────


class PassthroughProcessor:
    """Stateless passthrough processor, parametrized by a spec row.

    The 15 text/code/data passthrough processors are behaviorally identical —
    they differ only in ``name``, ``supported_kinds``, the ``source_type``
    they stamp (fixed, or the document's own for Text/Table), and
    ``confidence``. One implementation plus one spec table replaces 15 copies.
    """

    name: str = "PassthroughProcessor"
    supported_kinds: frozenset[str] = frozenset()
    _source_type: str | None = None
    _confidence: float = 0.90

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing file: %s", document.filename)
        return _passthrough(
            document,
            source_type=self._source_type or document.source_type,
            confidence=self._confidence,
        )


def _passthrough_cls(
    name: str,
    supported_kinds: frozenset[str],
    source_type: str | None,
    confidence: float,
) -> type[PassthroughProcessor]:
    """Build a named passthrough class so historical names stay importable."""
    return type(
        name,
        (PassthroughProcessor,),
        {
            "name": name,
            "supported_kinds": supported_kinds,
            "_source_type": source_type,
            "_confidence": confidence,
        },
    )


_PASSTHROUGH_SPECS: tuple[tuple[str, frozenset[str], str | None, float], ...] = (
    ("TextProcessor", frozenset({"text", "unknown", "tex", "epub"}), None, 0.95),
    ("MarkdownProcessor", frozenset({"markdown"}), "markdown", 0.95),
    ("WebProcessor", frozenset({"web", "html", "json", "xml"}), "web", 0.90),
    ("CodeProcessor", frozenset({"code"}), "code", 0.92),
    ("ConfigProcessor", frozenset({"config"}), "config", 0.93),
    ("PDFProcessor", frozenset({"pdf"}), "pdf", 0.90),
    ("DocxProcessor", frozenset({"docx"}), "docx", 0.90),
    ("PptxProcessor", frozenset({"pptx"}), "pptx", 0.88),
    ("ResearchProcessor", frozenset({"research"}), "research", 0.88),
    ("TableProcessor", frozenset({"csv", "spreadsheet"}), None, 0.88),
    ("DatabaseProcessor", frozenset({"database"}), "database", 0.85),
    ("NotebookProcessor", frozenset({"notebook"}), "notebook", 0.90),
    ("VideoProcessor", frozenset({"video"}), "video", 0.70),
    ("ArchiveProcessor", frozenset({"archive"}), "archive", 0.80),
    ("EmailProcessor", frozenset({"email"}), "email", 0.88),
)

_PASSTHROUGH_CLASSES: dict[str, type[PassthroughProcessor]] = {
    name: _passthrough_cls(name, kinds, source_type, confidence)
    for name, kinds, source_type, confidence in _PASSTHROUGH_SPECS
}

TextProcessor = _PASSTHROUGH_CLASSES["TextProcessor"]
MarkdownProcessor = _PASSTHROUGH_CLASSES["MarkdownProcessor"]
WebProcessor = _PASSTHROUGH_CLASSES["WebProcessor"]
CodeProcessor = _PASSTHROUGH_CLASSES["CodeProcessor"]
ConfigProcessor = _PASSTHROUGH_CLASSES["ConfigProcessor"]
PDFProcessor = _PASSTHROUGH_CLASSES["PDFProcessor"]
DocxProcessor = _PASSTHROUGH_CLASSES["DocxProcessor"]
PptxProcessor = _PASSTHROUGH_CLASSES["PptxProcessor"]
ResearchProcessor = _PASSTHROUGH_CLASSES["ResearchProcessor"]
TableProcessor = _PASSTHROUGH_CLASSES["TableProcessor"]
DatabaseProcessor = _PASSTHROUGH_CLASSES["DatabaseProcessor"]
NotebookProcessor = _PASSTHROUGH_CLASSES["NotebookProcessor"]
VideoProcessor = _PASSTHROUGH_CLASSES["VideoProcessor"]
ArchiveProcessor = _PASSTHROUGH_CLASSES["ArchiveProcessor"]
EmailProcessor = _PASSTHROUGH_CLASSES["EmailProcessor"]


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

_REGISTRY: dict[str, type] = {cls.__name__: cls for cls in _ALL_PROCESSORS}


def get_processor_by_name(name: str) -> object | None:
    """Return the processor instance for a given name, or None."""
    cls = _REGISTRY.get(name)
    return cls() if cls is not None else None
