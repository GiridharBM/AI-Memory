"""Tests for the content classifier."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.routing.classifier import DocumentClassifier


def _doc(filename: str, source_type: str, text: str = "") -> SourceDocument:
    return SourceDocument(
        source=filename,
        source_path=Path(filename),
        source_type=source_type,
        filename=filename,
        text=text,
        metadata=DocumentMetadata(),
    )


class TestClassifierFileTypes:
    def setup_method(self) -> None:
        self.classifier = DocumentClassifier()

    def test_markdown_detection(self) -> None:
        kind = self.classifier._detect_kind(".md", "markdown")
        assert kind == "markdown"

    def test_text_detection(self) -> None:
        kind = self.classifier._detect_kind(".txt", "text")
        assert kind == "text"

    def test_pdf_detection(self) -> None:
        kind = self.classifier._detect_kind(".pdf", "pdf")
        assert kind == "pdf"

    def test_code_python(self) -> None:
        kind = self.classifier._detect_kind(".py", "code")
        assert kind == "code"

    def test_code_javascript(self) -> None:
        kind = self.classifier._detect_kind(".js", "code")
        assert kind == "code"

    def test_code_typescript(self) -> None:
        kind = self.classifier._detect_kind(".ts", "code")
        assert kind == "code"

    def test_code_java(self) -> None:
        kind = self.classifier._detect_kind(".java", "code")
        assert kind == "code"

    def test_code_go(self) -> None:
        kind = self.classifier._detect_kind(".go", "code")
        assert kind == "code"

    def test_code_rust(self) -> None:
        kind = self.classifier._detect_kind(".rs", "code")
        assert kind == "code"

    def test_csv_detection(self) -> None:
        kind = self.classifier._detect_kind(".csv", "csv")
        assert kind == "csv"

    def test_excel_detection(self) -> None:
        kind = self.classifier._detect_kind(".xlsx", "spreadsheet")
        assert kind == "spreadsheet"

    def test_image_png(self) -> None:
        kind = self.classifier._detect_kind(".png", "image")
        assert kind == "image"

    def test_image_jpg(self) -> None:
        kind = self.classifier._detect_kind(".jpg", "image")
        assert kind == "image"

    def test_image_webp(self) -> None:
        kind = self.classifier._detect_kind(".webp", "image")
        assert kind == "image"

    def test_audio_mp3(self) -> None:
        kind = self.classifier._detect_kind(".mp3", "audio")
        assert kind == "audio"

    def test_audio_wav(self) -> None:
        kind = self.classifier._detect_kind(".wav", "audio")
        assert kind == "audio"

    def test_audio_flac(self) -> None:
        kind = self.classifier._detect_kind(".flac", "audio")
        assert kind == "audio"

    def test_video_mp4(self) -> None:
        kind = self.classifier._detect_kind(".mp4", "video")
        assert kind == "video"

    def test_video_mkv(self) -> None:
        kind = self.classifier._detect_kind(".mkv", "video")
        assert kind == "video"

    def test_docx_detection(self) -> None:
        kind = self.classifier._detect_kind(".docx", "docx")
        assert kind == "docx"

    def test_pptx_detection(self) -> None:
        kind = self.classifier._detect_kind(".pptx", "pptx")
        assert kind == "pptx"

    def test_unknown_extension(self) -> None:
        kind = self.classifier._detect_kind(".xyz", "unknown")
        assert kind == "unknown"


class TestClassifierClassify:
    def setup_method(self) -> None:
        self.classifier = DocumentClassifier()

    def test_classify_markdown(self) -> None:
        doc = _doc("readme.md", "markdown")
        result = self.classifier.classify(doc)
        assert result.kind == "markdown"
        assert result.extension == ".md"
        assert result.confidence == 0.92

    def test_classify_code(self) -> None:
        doc = _doc("main.py", "code")
        result = self.classifier.classify(doc)
        assert result.kind == "code"
        assert result.requires_code_parsing is True

    def test_classify_image(self) -> None:
        doc = _doc("photo.png", "image")
        result = self.classifier.classify(doc)
        assert result.kind == "image"
        assert result.requires_ocr is True
        assert result.requires_vision is True

    def test_classify_audio(self) -> None:
        doc = _doc("speech.mp3", "audio")
        result = self.classifier.classify(doc)
        assert result.kind == "audio"

    def test_classify_video(self) -> None:
        doc = _doc("clip.mp4", "video")
        result = self.classifier.classify(doc)
        assert result.kind == "video"
        assert result.requires_vision is True

    def test_classify_csv(self) -> None:
        doc = _doc("data.csv", "csv")
        result = self.classifier.classify(doc)
        assert result.kind == "csv"
        assert result.requires_table_extraction is True

    def test_classify_xlsx(self) -> None:
        doc = _doc("report.xlsx", "spreadsheet")
        result = self.classifier.classify(doc)
        assert result.kind == "spreadsheet"
        assert result.requires_table_extraction is True

    def test_classify_docx(self) -> None:
        doc = _doc("letter.docx", "docx")
        result = self.classifier.classify(doc)
        assert result.kind == "docx"

    def test_classify_pptx(self) -> None:
        doc = _doc("slides.pptx", "pptx")
        result = self.classifier.classify(doc)
        assert result.kind == "pptx"
