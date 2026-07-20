"""Tests for processor router selection."""

from __future__ import annotations

import pytest

from app.core.config import ModelRoutingSettings
from app.domain.routing import DocumentClassification, ProcessorSelection
from app.infrastructure.routing.processors import default_processors
from app.infrastructure.routing.router import ProcessorRouter


def _classification(kind: str) -> DocumentClassification:
    return DocumentClassification(
        source=f"test.{kind}",
        source_path=None,
        extension=f".{kind}",
        mime_type=None,
        kind=kind,
    )


class TestProcessorRouter:
    def setup_method(self) -> None:
        self.routing = ModelRoutingSettings()
        self.router = ProcessorRouter(self.routing)
        for proc in default_processors():
            self.router.register(proc)

    def test_markdown_routes_to_general_text(self) -> None:
        sel = self.router.select(_classification("markdown"))
        assert sel.processor_name == "MarkdownProcessor"
        assert sel.model_name == "qwen3:8b"

    def test_code_routes_to_programming(self) -> None:
        sel = self.router.select(_classification("code"))
        assert sel.processor_name == "CodeProcessor"
        assert sel.model_name == "qwen2.5-coder:7b"

    def test_image_routes_to_vision(self) -> None:
        sel = self.router.select(_classification("image"))
        assert sel.processor_name == "VisionProcessor"
        assert sel.model_name == "qwen2.5vl:7b"

    def test_pdf_routes_to_general_text(self) -> None:
        sel = self.router.select(_classification("pdf"))
        assert sel.processor_name == "PDFProcessor"
        assert sel.model_name == "qwen3:8b"

    def test_csv_routes_to_table(self) -> None:
        sel = self.router.select(_classification("csv"))
        assert sel.processor_name == "TableProcessor"
        assert sel.model_name == "qwen3:8b"

    def test_spreadsheet_routes_to_table(self) -> None:
        sel = self.router.select(_classification("spreadsheet"))
        assert sel.processor_name == "TableProcessor"
        assert sel.model_name == "qwen3:8b"

    def test_audio_routes_to_audio(self) -> None:
        sel = self.router.select(_classification("audio"))
        assert sel.processor_name == "AudioProcessor"
        assert sel.model_name == "faster-whisper"

    def test_video_routes_to_vision(self) -> None:
        sel = self.router.select(_classification("video"))
        assert sel.processor_name == "VideoProcessor"
        assert sel.model_name == "qwen2.5vl:7b"

    def test_docx_routes_to_general_text(self) -> None:
        sel = self.router.select(_classification("docx"))
        assert sel.processor_name == "DocxProcessor"
        assert sel.model_name == "qwen3:8b"

    def test_pptx_routes_to_general_text(self) -> None:
        sel = self.router.select(_classification("pptx"))
        assert sel.processor_name == "PptxProcessor"
        assert sel.model_name == "qwen3:8b"

    def test_text_routes_to_general_text(self) -> None:
        sel = self.router.select(_classification("text"))
        assert sel.processor_name == "TextProcessor"
        assert sel.model_name == "qwen3:8b"

    def test_unknown_falls_back_to_text(self) -> None:
        sel = self.router.select(_classification("unknown"))
        assert sel.processor_name == "TextProcessor"
        assert sel.model_name == "qwen3:8b"
