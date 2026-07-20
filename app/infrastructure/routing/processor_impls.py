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
        return document.text

    source_path = document.source_path
    if source_path and source_path.exists():
        return vision_client.describe_image(source_path, prompt=prompt)
    return document.text


def _audio_extract(transcriber: object, document: SourceDocument) -> str:
    """Extract text from an audio file via the whisper transcriber."""
    if not hasattr(transcriber, "transcribe"):
        return document.text

    source_path = document.source_path
    if source_path and source_path.exists():
        return transcriber.transcribe(source_path)
    return document.text


class TextProcessor:
    """Process plain text files."""

    name = "TextProcessor"
    supported_kinds = {"text", "html", "json", "xml", "unknown"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        return _passthrough(document, source_type=document.source_type, confidence=0.95)


class MarkdownProcessor:
    """Process Markdown files."""

    name = "MarkdownProcessor"
    supported_kinds = {"markdown"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        return _passthrough(document, source_type="markdown", confidence=0.95)


class CodeProcessor:
    """Process source code files."""

    name = "CodeProcessor"
    supported_kinds = {"code"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        return _passthrough(document, source_type="code", confidence=0.92)


class PDFProcessor:
    """Process typed PDF files."""

    name = "PDFProcessor"
    supported_kinds = {"pdf"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        return _passthrough(document, source_type="pdf", confidence=0.90)


class VisionProcessor:
    """Process image files via vision model."""

    name = "VisionProcessor"
    supported_kinds = {"image"}

    def __init__(self, *, vision_client: object | None = None) -> None:
        self._vision_client = vision_client

    def process(self, document: SourceDocument) -> ProcessedDocument:
        extracted = _ocr_extract(self._vision_client, document, prompt="Extract all text from this image. Return only the extracted text, nothing else.")
        t = _extract_title(document)
        meta = {**_base_metadata(document), "model_used": bool(self._vision_client)}
        return ProcessedDocument(
            title=t,
            content=extracted,
            markdown=f"# {t}\n\n{extracted}",
            metadata=meta,
            extracted_text=extracted,
            confidence=0.85 if self._vision_client else 0.70,
            source_type="image",
        )


class TableProcessor:
    """Process CSV and spreadsheet files."""

    name = "TableProcessor"
    supported_kinds = {"csv", "spreadsheet"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        return _passthrough(document, source_type=document.source_type, confidence=0.88)


class AudioProcessor:
    """Process audio files."""

    name = "AudioProcessor"
    supported_kinds = {"audio"}

    def __init__(self, *, transcriber: object | None = None) -> None:
        self._transcriber = transcriber

    def process(self, document: SourceDocument) -> ProcessedDocument:
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
        return _passthrough(document, source_type="video", confidence=0.70)


class DocxProcessor:
    """Process DOCX files."""

    name = "DocxProcessor"
    supported_kinds = {"docx"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        return _passthrough(document, source_type="docx", confidence=0.90)


class PptxProcessor:
    """Process PPTX files."""

    name = "PptxProcessor"
    supported_kinds = {"pptx"}

    def process(self, document: SourceDocument) -> ProcessedDocument:
        return _passthrough(document, source_type="pptx", confidence=0.88)


class OCRProcessor:
    """Process scanned PDF files via vision-model OCR."""

    name = "OCRProcessor"
    supported_kinds = {"scanned_pdf"}

    def __init__(self, *, vision_client: object | None = None) -> None:
        self._vision_client = vision_client

    def process(self, document: SourceDocument) -> ProcessedDocument:
        prompt = (
            "This is a scanned PDF page. Extract all visible text accurately. "
            "Return only the extracted text, nothing else."
        )
        extracted = _ocr_extract(self._vision_client, document, prompt=prompt)
        t = _extract_title(document)
        meta = {**_base_metadata(document), "ocr": True, "model_used": bool(self._vision_client)}
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
        prompt = (
            "This is a handwritten document. Transcribe all handwritten text as accurately "
            "as possible. Return only the transcribed text, nothing else."
        )
        extracted = _ocr_extract(self._vision_client, document, prompt=prompt)
        t = _extract_title(document)
        meta = {**_base_metadata(document), "handwriting": True, "model_used": bool(self._vision_client)}
        return ProcessedDocument(
            title=t,
            content=extracted,
            markdown=f"# {t}\n\n{extracted}",
            metadata=meta,
            extracted_text=extracted,
            confidence=0.75 if self._vision_client else 0.40,
            source_type="handwritten",
        )


def get_processor_by_name(name: str) -> object | None:
    """Return the processor instance for a given name, or None."""
    _registry: dict[str, type] = {
        cls.__name__: cls
        for cls in [
            TextProcessor,
            MarkdownProcessor,
            CodeProcessor,
            PDFProcessor,
            VisionProcessor,
            TableProcessor,
            AudioProcessor,
            VideoProcessor,
            DocxProcessor,
            PptxProcessor,
            OCRProcessor,
            HandwritingProcessor,
        ]
    }
    cls = _registry.get(name)
    return cls() if cls is not None else None
