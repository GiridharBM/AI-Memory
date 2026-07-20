"""End-to-end test that routed processors are actually called in the workflow."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.config import ModelRoutingSettings
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.routing.processor_impls import (
    AudioProcessor,
    HandwritingProcessor,
    OCRProcessor,
    VisionProcessor,
)
from app.infrastructure.routing.router import ProcessorRouter
from app.infrastructure.routing.processors import default_processors


def _make_document(
    *,
    source_type: str = "text",
    text: str = "hello",
    source_path: Path | None = None,
) -> SourceDocument:
    return SourceDocument(
        source=str(source_path or Path("test.txt")),
        source_path=source_path,
        source_type=source_type,
        filename="test.txt",
        text=text,
        metadata=DocumentMetadata(title="Test"),
    )


def _tmp_file(suffix: str, content: bytes = b"fake") -> Path:
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


class TestVisionProcessorWiring:
    def test_vision_client_is_used_when_provided(self) -> None:
        mock_client = MagicMock()
        mock_client.describe_image.return_value = "OCR text from image"
        img = _tmp_file(".png")

        try:
            proc = VisionProcessor(vision_client=mock_client)
            doc = _make_document(source_type="image", source_path=img)
            result = proc.process(doc)

            assert result.extracted_text == "OCR text from image"
            assert result.confidence == 0.85
            assert result.metadata["model_used"] is True
            mock_client.describe_image.assert_called_once()
        finally:
            img.unlink()

    def test_vision_client_not_used_when_none(self) -> None:
        proc = VisionProcessor()
        doc = _make_document(source_type="image", text="fallback")
        result = proc.process(doc)

        assert result.extracted_text == "fallback"
        assert result.confidence == 0.70
        assert result.metadata["model_used"] is False


class TestOCRProcessorWiring:
    def test_ocr_uses_vision_client(self) -> None:
        mock_client = MagicMock()
        mock_client.describe_image.return_value = "Scanned text extracted"
        pdf = _tmp_file(".pdf")

        try:
            proc = OCRProcessor(vision_client=mock_client)
            doc = _make_document(source_type="scanned_pdf", source_path=pdf)
            result = proc.process(doc)

            assert result.extracted_text == "Scanned text extracted"
            assert result.confidence == 0.82
            assert result.metadata["ocr"] is True
            mock_client.describe_image.assert_called_once()
        finally:
            pdf.unlink()

    def test_ocr_fallback_without_client(self) -> None:
        proc = OCRProcessor()
        doc = _make_document(source_type="scanned_pdf", text="existing")
        result = proc.process(doc)

        assert result.extracted_text == "existing"
        assert result.confidence == 0.50


class TestHandwritingProcessorWiring:
    def test_handwriting_uses_vision_client(self) -> None:
        mock_client = MagicMock()
        mock_client.describe_image.return_value = "Handwriting transcribed"
        img = _tmp_file(".png")

        try:
            proc = HandwritingProcessor(vision_client=mock_client)
            doc = _make_document(source_type="handwritten", source_path=img)
            result = proc.process(doc)

            assert result.extracted_text == "Handwriting transcribed"
            assert result.confidence == 0.75
            assert result.metadata["handwriting"] is True
            mock_client.describe_image.assert_called_once()
        finally:
            img.unlink()


class TestAudioProcessorWiring:
    def test_transcriber_is_used_when_provided(self) -> None:
        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.return_value = "Transcribed audio content"
        audio = _tmp_file(".wav")

        try:
            proc = AudioProcessor(transcriber=mock_transcriber)
            doc = _make_document(source_type="audio", source_path=audio)
            result = proc.process(doc)

            assert result.extracted_text == "Transcribed audio content"
            assert result.confidence == 0.85
            assert result.metadata["model_used"] is True
            mock_transcriber.transcribe.assert_called_once()
        finally:
            audio.unlink()

    def test_transcriber_not_used_when_none(self) -> None:
        proc = AudioProcessor()
        doc = _make_document(source_type="audio", text="fallback")
        result = proc.process(doc)

        assert result.extracted_text == "fallback"
        assert result.confidence == 0.60


class TestRouterSelectsCorrectProcessor:
    def setup_method(self) -> None:
        self.routing = ModelRoutingSettings()
        self.router = ProcessorRouter(self.routing)
        for proc in default_processors():
            self.router.register(proc)

    def test_image_routes_to_vision(self) -> None:
        from app.domain.routing import DocumentClassification
        cls = DocumentClassification(
            source="img.png", source_path=None, extension=".png",
            mime_type="image/png", kind="image",
        )
        sel = self.router.select(cls)
        assert sel.processor_name == "VisionProcessor"

    def test_scanned_pdf_routes_to_ocr(self) -> None:
        from app.domain.routing import DocumentClassification
        cls = DocumentClassification(
            source="scan.pdf", source_path=None, extension=".pdf",
            mime_type="application/pdf", kind="scanned_pdf",
        )
        sel = self.router.select(cls)
        assert sel.processor_name == "OCRProcessor"

    def test_handwritten_routes_to_handwriting(self) -> None:
        from app.domain.routing import DocumentClassification
        cls = DocumentClassification(
            source="note.pdf", source_path=None, extension=".pdf",
            mime_type="application/pdf", kind="handwritten",
        )
        sel = self.router.select(cls)
        assert sel.processor_name == "HandwritingProcessor"

    def test_audio_routes_to_audio(self) -> None:
        from app.domain.routing import DocumentClassification
        cls = DocumentClassification(
            source="speech.wav", source_path=None, extension=".wav",
            mime_type="audio/wav", kind="audio",
        )
        sel = self.router.select(cls)
        assert sel.processor_name == "AudioProcessor"
