"""Document processors for each content type."""

from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger
from app.domain.documents import SourceDocument
from app.domain.processed_document import ProcessedDocument

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


def _ocr_extract(vision_client: object, document: SourceDocument, *, prompt: str) -> str:
    """Extract text from a document image via the vision client."""
    if not hasattr(vision_client, "describe_image"):
        logger.warning(
            "No vision client available for image processing. "
            "Pull a vision model with: ollama pull qwen2.5vl:latest",
        )
        return document.text

    source_path = document.source_path
    if not source_path or not source_path.exists():
        return document.text

    # For PDFs, convert each page to an image first
    if source_path.suffix.lower() == ".pdf":
        return _ocr_extract_from_pdf(vision_client, source_path, prompt=prompt)

    return vision_client.describe_image(source_path, prompt=prompt)


def _ocr_extract_from_pdf(vision_client: object, pdf_path: Path, *, prompt: str) -> str:
    """Convert PDF pages to images and extract text via vision model."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise ImportError(
            "PyMuPDF is required for scanned PDF OCR. "
            "Install with: pip install PyMuPDF",
        ) from exc

    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        logger.warning("Failed to open PDF for OCR: %s", pdf_path)
        return ""
    all_text = []
    for page_num in range(min(len(doc), 5)):  # limit to first 5 pages
        page = doc[page_num]
        # Render page to image (PNG)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better quality
        img_bytes = pix.tobytes("png")
        # Save to temp file and send to vision model
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(img_bytes)
            tmp_path = Path(tmp.name)
        try:
            text = vision_client.describe_image(tmp_path, prompt=prompt)
            if text.strip():
                all_text.append(text.strip())
        finally:
            tmp_path.unlink(missing_ok=True)
    doc.close()
    return "\n\n".join(all_text)


def _looks_handwritten(text: str) -> bool:
    """Heuristic: detect if extracted text looks like handwriting."""
    if not text or len(text.strip()) < 10:
        return False
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return False
    # Handwriting tends to have shorter, inconsistent lines
    avg_len = sum(len(l) for l in lines) / len(lines)
    if avg_len > 80:
        return False
    # Check for mixed case words (handwriting often has irregular capitalization)
    words = text.split()
    if len(words) < 5:
        return False
    mixed = sum(1 for w in words if w and w[0].isupper() and not w.isupper() and len(w) > 2)
    ratio = mixed / len(words)
    return 0.1 < ratio < 0.6


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
    """Process image files via vision model."""

    name = "VisionProcessor"
    supported_kinds = {"image"}

    def __init__(self, *, vision_client: object | None = None) -> None:
        self._vision_client = vision_client

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing image file: %s", document.filename)
        prompt = (
            "Analyze this image. If it contains handwritten text, transcribe "
            "all handwritten text accurately. If it contains printed text or "
            "digital content, extract all visible text. Return only the "
            "extracted text, nothing else."
        )
        extracted = _ocr_extract(
            self._vision_client, document, prompt=prompt,
        )
        t = _extract_title(document)
        is_handwritten = bool(self._vision_client) and _looks_handwritten(extracted)
        meta = {
            **_base_metadata(document),
            "model_used": bool(self._vision_client),
            "handwriting_detected": is_handwritten,
        }
        return ProcessedDocument(
            title=t,
            content=extracted,
            markdown=f"# {t}\n\n{extracted}",
            metadata=meta,
            extracted_text=extracted,
            confidence=0.85 if self._vision_client else 0.70,
            source_type="handwritten" if is_handwritten else "image",
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
    """Process scanned PDF files via vision-model OCR."""

    name = "OCRProcessor"
    supported_kinds = {"scanned_pdf"}

    def __init__(self, *, vision_client: object | None = None) -> None:
        self._vision_client = vision_client

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing scanned PDF: %s", document.filename)
        prompt = (
            "This is a scanned PDF page. Extract all visible text accurately. "
            "Return only the extracted text, nothing else."
        )
        extracted = _ocr_extract(self._vision_client, document, prompt=prompt)
        t = _extract_title(document)
        meta = {
            **_base_metadata(document),
            "ocr": True,
            "model_used": bool(self._vision_client),
        }
        return ProcessedDocument(
            title=t,
            content=extracted,
            markdown=f"# {t}\n\n{extracted}",
            metadata=meta,
            extracted_text=extracted,
            confidence=0.82 if self._vision_client else 0.50,
            source_type="scanned_pdf",
        )


class HandwritingProcessor:
    """Process handwritten PDF files via vision-model OCR."""

    name = "HandwritingProcessor"
    supported_kinds = {"handwritten"}

    def __init__(self, *, vision_client: object | None = None) -> None:
        self._vision_client = vision_client

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing handwritten document: %s", document.filename)
        prompt = (
            "This is a handwritten document. Transcribe all handwritten text "
            "as accurately as possible. Return only the transcribed text, "
            "nothing else."
        )
        extracted = _ocr_extract(self._vision_client, document, prompt=prompt)
        t = _extract_title(document)
        meta = {
            **_base_metadata(document),
            "handwriting": True,
            "model_used": bool(self._vision_client),
        }
        return ProcessedDocument(
            title=t,
            content=extracted,
            markdown=f"# {t}\n\n{extracted}",
            metadata=meta,
            extracted_text=extracted,
            confidence=0.75 if self._vision_client else 0.40,
            source_type="handwritten",
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


class DiagramProcessor:
    """Process diagram files (.drawio, .vsdx)."""

    name = "DiagramProcessor"
    supported_kinds = {"diagram"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        logger.debug("Processing diagram file: %s", document.filename)
        return _passthrough(document, source_type="diagram", confidence=0.85)


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
