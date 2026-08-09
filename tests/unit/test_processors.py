"""Functional tests for all document processors."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.domain.documents import DocumentMetadata, SourceDocument
from app.domain.processed_document import ProcessedDocument
from app.infrastructure.document_intelligence.ocr.base import (
    DocumentOcrService,
    OCRSelectionError,
)
from app.infrastructure.document_intelligence.ocr.engines import VisionOcrEngine
from app.infrastructure.document_intelligence.ocr.models import OcrResult, PageOcrResult
from app.infrastructure.routing.processor_impls import (
    ArchiveProcessor,
    AudioProcessor,
    CodeProcessor,
    ConfigProcessor,
    DatabaseProcessor,
    DiagramProcessor,
    DocxProcessor,
    EmailProcessor,
    HandwritingProcessor,
    MarkdownProcessor,
    NotebookProcessor,
    OCRProcessor,
    PDFProcessor,
    PptxProcessor,
    ResearchProcessor,
    TableProcessor,
    TextProcessor,
    VideoProcessor,
    VisionProcessor,
    WebProcessor,
    _prompt_templates,
    _resolve_prompt,
    get_processor_by_name,
)


def _make_document(
    *,
    text: str = "hello world",
    source_type: str = "text",
    filename: str = "test.txt",
    source_path: Path | None = None,
) -> SourceDocument:
    return SourceDocument(
        source=str(source_path or Path("test.txt")),
        source_path=source_path,
        source_type=source_type,
        filename=filename,
        text=text,
        metadata=DocumentMetadata(title="Test Title"),
    )


def _assert_processed(doc: ProcessedDocument, *, expected_source_type: str) -> None:
    assert isinstance(doc, ProcessedDocument)
    assert doc.title == "Test Title"
    assert doc.content
    assert doc.markdown.startswith("# Test Title")
    assert doc.extracted_text
    assert 0 <= doc.confidence <= 1.0


def _tmp_pdf() -> Path:
    """Create a minimal valid one-page PDF for testing."""
    try:
        import fitz
        pdf_path = Path(tempfile.mktemp(suffix=".pdf"))
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Test content")
        doc.save(str(pdf_path))
        doc.close()
        return pdf_path
    except Exception:
        return Path(tempfile.mktemp(suffix=".pdf"))


# ── TextProcessor ──────────────────────────────────────────────────────


class TestTextProcessor:
    def test_returns_processed_document(self) -> None:
        proc = TextProcessor()
        doc = _make_document(text="plain text content", source_type="text")
        result = proc.process(doc)
        _assert_processed(result, expected_source_type="text")
        assert result.extracted_text == "plain text content"

    def test_confidence_is_095(self) -> None:
        proc = TextProcessor()
        result = proc.process(_make_document())
        assert result.confidence == 0.95


# ── MarkdownProcessor ──────────────────────────────────────────────────


class TestMarkdownProcessor:
    def test_returns_processed_document(self) -> None:
        proc = MarkdownProcessor()
        doc = _make_document(text="# Heading\n\nBody", source_type="markdown")
        result = proc.process(doc)
        _assert_processed(result, expected_source_type="markdown")
        assert result.extracted_text == "# Heading\n\nBody"

    def test_confidence_is_095(self) -> None:
        proc = MarkdownProcessor()
        result = proc.process(_make_document())
        assert result.confidence == 0.95


# ── CodeProcessor ──────────────────────────────────────────────────────


class TestCodeProcessor:
    def test_returns_processed_document(self) -> None:
        proc = CodeProcessor()
        doc = _make_document(text="def foo(): pass", source_type="code")
        result = proc.process(doc)
        _assert_processed(result, expected_source_type="code")
        assert result.extracted_text == "def foo(): pass"

    def test_confidence_is_092(self) -> None:
        proc = CodeProcessor()
        result = proc.process(_make_document())
        assert result.confidence == 0.92


# ── PDFProcessor ───────────────────────────────────────────────────────


class TestPDFProcessor:
    def test_returns_processed_document(self) -> None:
        proc = PDFProcessor()
        doc = _make_document(text="PDF body text", source_type="pdf")
        result = proc.process(doc)
        _assert_processed(result, expected_source_type="pdf")

    def test_confidence_is_090(self) -> None:
        proc = PDFProcessor()
        result = proc.process(_make_document())
        assert result.confidence == 0.90


# ── VisionProcessor ────────────────────────────────────────────────────


class TestVisionProcessor:
    def test_passthrough_when_no_client(self) -> None:
        proc = VisionProcessor()
        doc = _make_document(text="[image placeholder]", source_type="image")
        result = proc.process(doc)
        _assert_processed(result, expected_source_type="image")
        assert result.confidence == 0.70

    def test_with_mock_vision_client(self) -> None:
        mock_client = MagicMock()
        mock_client.describe_image.return_value = "Extracted text from image"

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image bytes")
            img_path = Path(f.name)

        try:
            doc = _make_document(text="", source_type="image", source_path=img_path)
            proc = VisionProcessor(vision_client=mock_client)
            result = proc.process(doc)

            _assert_processed(result, expected_source_type="image")
            assert result.extracted_text == "Extracted text from image"
            assert result.confidence == 0.85
            mock_client.describe_image.assert_called_once()
        finally:
            img_path.unlink()

    def test_fallback_when_no_source_path(self) -> None:
        mock_client = MagicMock()
        proc = VisionProcessor(vision_client=mock_client)
        doc = _make_document(text="fallback text", source_type="image")
        result = proc.process(doc)
        assert result.extracted_text == "fallback text"


# ── TableProcessor ─────────────────────────────────────────────────────


class TestTableProcessor:
    def test_csv(self) -> None:
        proc = TableProcessor()
        doc = _make_document(text="a,b,c\n1,2,3", source_type="csv")
        result = proc.process(doc)
        _assert_processed(result, expected_source_type="csv")

    def test_spreadsheet(self) -> None:
        proc = TableProcessor()
        doc = _make_document(text="col1\tcol2\nval1\tval2", source_type="spreadsheet")
        result = proc.process(doc)
        _assert_processed(result, expected_source_type="spreadsheet")

    def test_confidence_is_088(self) -> None:
        proc = TableProcessor()
        result = proc.process(_make_document())
        assert result.confidence == 0.88


# ── AudioProcessor ─────────────────────────────────────────────────────


class TestAudioProcessor:
    def test_passthrough_when_no_transcriber(self) -> None:
        proc = AudioProcessor()
        doc = _make_document(text="[audio placeholder]", source_type="audio")
        result = proc.process(doc)
        _assert_processed(result, expected_source_type="audio")
        assert result.confidence == 0.60

    def test_with_mock_transcriber(self) -> None:
        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.return_value = "Transcribed speech text"

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"fake audio bytes")
            audio_path = Path(f.name)

        try:
            doc = _make_document(text="", source_type="audio", source_path=audio_path)
            proc = AudioProcessor(transcriber=mock_transcriber)
            result = proc.process(doc)

            _assert_processed(result, expected_source_type="audio")
            assert result.extracted_text == "Transcribed speech text"
            assert result.confidence == 0.85
            mock_transcriber.transcribe.assert_called_once()
        finally:
            audio_path.unlink()

    def test_fallback_when_no_source_path(self) -> None:
        mock_transcriber = MagicMock()
        proc = AudioProcessor(transcriber=mock_transcriber)
        doc = _make_document(text="fallback", source_type="audio")
        result = proc.process(doc)
        assert result.extracted_text == "fallback"


# ── VideoProcessor ─────────────────────────────────────────────────────


class TestVideoProcessor:
    def test_returns_processed_document(self) -> None:
        proc = VideoProcessor()
        doc = _make_document(text="[video placeholder]", source_type="video")
        result = proc.process(doc)
        _assert_processed(result, expected_source_type="video")

    def test_confidence_is_070(self) -> None:
        proc = VideoProcessor()
        result = proc.process(_make_document())
        assert result.confidence == 0.70


# ── DocxProcessor ──────────────────────────────────────────────────────


class TestDocxProcessor:
    def test_returns_processed_document(self) -> None:
        proc = DocxProcessor()
        doc = _make_document(text="DOCX body", source_type="docx")
        result = proc.process(doc)
        _assert_processed(result, expected_source_type="docx")

    def test_confidence_is_090(self) -> None:
        proc = DocxProcessor()
        result = proc.process(_make_document())
        assert result.confidence == 0.90


# ── PptxProcessor ──────────────────────────────────────────────────────


class TestPptxProcessor:
    def test_returns_processed_document(self) -> None:
        proc = PptxProcessor()
        doc = _make_document(text="Slide 1 content", source_type="pptx")
        result = proc.process(doc)
        _assert_processed(result, expected_source_type="pptx")

    def test_confidence_is_088(self) -> None:
        proc = PptxProcessor()
        result = proc.process(_make_document())
        assert result.confidence == 0.88


# ── OCRProcessor ───────────────────────────────────────────────────────


class TestOCRProcessor:
    def test_passthrough_when_no_client(self) -> None:
        proc = OCRProcessor()
        doc = _make_document(text="existing extracted text", source_type="scanned_pdf")
        result = proc.process(doc)
        _assert_processed(result, expected_source_type="scanned_pdf")
        assert result.confidence == 0.50
        assert result.metadata["ocr"] is True
        assert result.extracted_text == "existing extracted text"

    def test_with_mock_vision_client(self) -> None:
        mock_client = MagicMock()
        mock_client.describe_image.return_value = "OCR extracted text"

        pdf_path = _tmp_pdf()

        try:
            doc = _make_document(text="", source_type="scanned_pdf", source_path=pdf_path)
            proc = OCRProcessor(vision_client=mock_client)
            result = proc.process(doc)

            _assert_processed(result, expected_source_type="scanned_pdf")
            assert result.extracted_text == "OCR extracted text"
            assert result.confidence == 0.82
            assert result.metadata["ocr"] is True
            mock_client.describe_image.assert_called_once()
        finally:
            pdf_path.unlink()

    def test_fallback_when_no_source_path(self) -> None:
        mock_client = MagicMock()
        proc = OCRProcessor(vision_client=mock_client)
        doc = _make_document(text="existing text", source_type="scanned_pdf")
        result = proc.process(doc)
        assert result.extracted_text == "existing text"

    def test_scanned_pdf_requires_pymupdf(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setitem(sys.modules, "fitz", None)
        pdf = tmp_path / "scan.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        service = DocumentOcrService(engines=[VisionOcrEngine(MagicMock())])

        proc = OCRProcessor(ocr_service=service)
        doc = _make_document(source_type="scanned_pdf", source_path=pdf)
        with pytest.raises(ImportError, match="PyMuPDF"):
            proc.process(doc)


# ── HandwritingProcessor ───────────────────────────────────────────────


class TestHandwritingProcessor:
    def test_passthrough_when_no_client(self) -> None:
        proc = HandwritingProcessor()
        doc = _make_document(text="existing handwritten text", source_type="handwritten")
        result = proc.process(doc)
        _assert_processed(result, expected_source_type="handwritten")
        assert result.confidence == 0.40
        assert result.metadata["handwriting"] is True
        assert result.extracted_text == "existing handwritten text"

    def test_with_mock_vision_client(self) -> None:
        mock_client = MagicMock()
        mock_client.describe_image.return_value = "Handwriting transcribed"

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image bytes")
            img_path = Path(f.name)

        try:
            doc = _make_document(text="", source_type="handwritten", source_path=img_path)
            proc = HandwritingProcessor(vision_client=mock_client)
            result = proc.process(doc)

            _assert_processed(result, expected_source_type="handwritten")
            assert result.extracted_text == "Handwriting transcribed"
            assert result.confidence == 0.75
            assert result.metadata["handwriting"] is True
            mock_client.describe_image.assert_called_once()
        finally:
            img_path.unlink()

    def test_fallback_when_no_source_path(self) -> None:
        mock_client = MagicMock()
        proc = HandwritingProcessor(vision_client=mock_client)
        doc = _make_document(text="fallback", source_type="handwritten")
        result = proc.process(doc)
        assert result.extracted_text == "fallback"


# ── OCR service delegation (P2-107) ─────────────────────────────────────

EXPECTED_OCR_PROMPT = (
    "This is a scanned PDF page. Extract all visible text accurately. "
    "Return only the extracted text, nothing else."
)
EXPECTED_HANDWRITING_PROMPT = (
    "This is a handwritten document. Transcribe all handwritten text "
    "as accurately as possible. Return only the transcribed text, "
    "nothing else."
)
EXPECTED_VISION_PROMPT = (
    "Analyze this image. If it contains handwritten text, transcribe "
    "all handwritten text accurately. If it contains printed text or "
    "digital content, extract all visible text. Return only the "
    "extracted text, nothing else."
)


class TestOcrServiceDelegation:
    def test_vision_delegates_to_service(self, tmp_path: Path) -> None:
        path = tmp_path / "img.png"
        path.write_bytes(b"fake")
        service = MagicMock()
        service.extract.return_value = OcrResult(
            pages=[PageOcrResult(page_no=0, text="Extracted from service")]
        )

        doc = _make_document(source_type="image", source_path=path)
        result = VisionProcessor(ocr_service=service).process(doc)

        assert result.extracted_text == "Extracted from service"
        assert result.confidence == 0.85
        assert result.metadata["model_used"] is True
        assert result.ocr is service.extract.return_value
        service.extract.assert_called_once_with(
            doc, prompt=EXPECTED_VISION_PROMPT, preprocess=False
        )

    def test_ocr_delegates_to_service(self, tmp_path: Path) -> None:
        path = tmp_path / "scan.pdf"
        path.write_bytes(b"%PDF-1.4")
        service = MagicMock()
        service.extract.return_value = OcrResult(pages=[])

        doc = _make_document(source_type="scanned_pdf", source_path=path)
        result = OCRProcessor(ocr_service=service).process(doc)

        assert result.metadata["ocr"] is True
        assert result.ocr is service.extract.return_value
        service.extract.assert_called_once_with(
            doc, prompt=EXPECTED_OCR_PROMPT, preprocess=False
        )

    def test_handwriting_delegates_to_service(self, tmp_path: Path) -> None:
        path = tmp_path / "note.png"
        path.write_bytes(b"fake")
        service = MagicMock()
        service.extract.return_value = OcrResult(pages=[])

        doc = _make_document(source_type="handwritten", source_path=path)
        result = HandwritingProcessor(ocr_service=service).process(doc)

        assert result.metadata["handwriting"] is True
        assert result.ocr is service.extract.return_value
        service.extract.assert_called_once_with(
            doc, prompt=EXPECTED_HANDWRITING_PROMPT, preprocess=False
        )

    def test_missing_source_path_falls_back_to_document_text(self) -> None:
        service = MagicMock()
        service.extract.side_effect = ValueError("source path is missing")

        doc = _make_document(text="existing text", source_type="image")
        result = VisionProcessor(ocr_service=service).process(doc)

        assert result.extracted_text == "existing text"
        assert result.confidence == 0.85

    def test_no_fallback_raise_when_engine_missing(self, tmp_path: Path) -> None:
        path = tmp_path / "scan.pdf"
        path.write_bytes(b"%PDF-1.4")
        proc = OCRProcessor(ocr_service=DocumentOcrService())
        doc = _make_document(source_type="scanned_pdf", source_path=path)

        with pytest.raises(OCRSelectionError):
            proc.process(doc)


class TestPromptTemplates:
    def test_defaults_are_byte_identical_to_phase1(self) -> None:
        templates = _prompt_templates()
        assert templates["ocr"] == EXPECTED_OCR_PROMPT
        assert templates["handwriting"] == EXPECTED_HANDWRITING_PROMPT
        assert templates["vision"] == EXPECTED_VISION_PROMPT

    def test_language_slot_substitution(self) -> None:
        template = "Extract all text. Respond in {language}."
        assert _resolve_prompt(template, language="French") == (
            "Extract all text. Respond in French."
        )
        assert _resolve_prompt(template) == "Extract all text. Respond in ."


# ── get_processor_by_name ──────────────────────────────────────────────


class TestGetProcessorByName:
    def test_all_processors_registered(self) -> None:
        names = [
            "TextProcessor", "MarkdownProcessor", "CodeProcessor", "PDFProcessor",
            "VisionProcessor", "TableProcessor", "AudioProcessor", "VideoProcessor",
            "DocxProcessor", "PptxProcessor", "OCRProcessor", "HandwritingProcessor",
        ]
        for name in names:
            proc = get_processor_by_name(name)
            assert proc is not None, f"{name} not found in registry"
            assert hasattr(proc, "process")

    def test_unknown_returns_none(self) -> None:
        assert get_processor_by_name("NonexistentProcessor") is None


# ── ProcessedDocument structure consistency ─────────────────────────────


class TestProcessedDocumentStructure:
    ALL_PROCESSORS = [
        TextProcessor(), MarkdownProcessor(), WebProcessor(), CodeProcessor(),
        ConfigProcessor(), PDFProcessor(), DocxProcessor(), PptxProcessor(),
        ResearchProcessor(), TableProcessor(), DatabaseProcessor(),
        NotebookProcessor(), VisionProcessor(), AudioProcessor(), VideoProcessor(),
        OCRProcessor(), HandwritingProcessor(), ArchiveProcessor(),
        EmailProcessor(), DiagramProcessor(),
    ]

    def test_all_return_processed_document(self) -> None:
        for proc in self.ALL_PROCESSORS:
            doc = _make_document(source_type=list(proc.supported_kinds)[0])
            result = proc.process(doc)
            assert isinstance(result, ProcessedDocument), (
                f"{proc.name} did not return ProcessedDocument"
            )

    def test_all_have_required_fields(self) -> None:
        for proc in self.ALL_PROCESSORS:
            doc = _make_document(source_type=list(proc.supported_kinds)[0])
            result = proc.process(doc)
            assert result.title, f"{proc.name} missing title"
            assert isinstance(result.content, str), f"{proc.name} content not str"
            assert isinstance(result.markdown, str), f"{proc.name} markdown not str"
            assert result.markdown.startswith("# "), f"{proc.name} markdown missing heading"
            assert isinstance(result.metadata, dict), f"{proc.name} metadata not dict"
            assert isinstance(result.extracted_text, str), f"{proc.name} extracted_text not str"
            assert isinstance(result.confidence, float), f"{proc.name} confidence not float"
            assert isinstance(result.source_type, str), f"{proc.name} source_type not str"
