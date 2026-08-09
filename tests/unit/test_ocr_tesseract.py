"""Tests for the TesseractOcrEngine (P2-105)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.infrastructure.document_intelligence.ocr.engines import (
    TesseractOcrEngine,
    TesseractOcrError,
)

pytesseract = pytest.importorskip("pytesseract")


def _png(tmp_path: Path, name: str = "scan.png") -> Path:
    path = tmp_path / name
    path.write_bytes(b"fake png bytes")
    return path


def _tmp_pdf(tmp_path: Path, n_pages: int = 2) -> Path:
    import fitz

    pdf_path = tmp_path / "scan.pdf"
    doc = fitz.open()
    for page_no in range(n_pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {page_no + 1} content")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


class TestTesseractOcrEngine:
    def test_supported_kinds(self) -> None:
        assert TesseractOcrEngine().supported_kinds == {"scanned_pdf", "image"}

    def test_missing_pytesseract_raises_clear_import_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "pytesseract", None)
        with pytest.raises(ImportError, match="pip install pytesseract"):
            TesseractOcrEngine().run(Path("scan.png"), prompt="x")

    def test_image_source_extracts_text_and_confidence(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            pytesseract, "image_to_string", MagicMock(return_value="Hello world\n")
        )
        monkeypatch.setattr(
            pytesseract,
            "image_to_data",
            MagicMock(return_value={"conf": ["95", "88", "-1"]}),
        )
        result = TesseractOcrEngine().run(_png(tmp_path), prompt="x")
        assert result.text == "Hello world"
        assert result.pages[0].page_no == 0
        assert result.confidence == pytest.approx(91.5)
        assert result.empty_pages == []

    def test_image_source_no_words_has_none_confidence(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(pytesseract, "image_to_string", MagicMock(return_value=""))
        monkeypatch.setattr(
            pytesseract, "image_to_data", MagicMock(return_value={"conf": ["-1", "-1"]})
        )
        result = TesseractOcrEngine().run(_png(tmp_path), prompt="x")
        assert result.text == ""
        assert result.confidence is None
        assert result.empty_pages == [0]

    def test_binary_missing_raises_clear_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            pytesseract,
            "image_to_string",
            MagicMock(side_effect=pytesseract.TesseractNotFoundError()),
        )
        monkeypatch.setattr(pytesseract, "image_to_data", MagicMock())
        with pytest.raises(TesseractOcrError, match="Tesseract OCR binary not found"):
            TesseractOcrEngine().run(_png(tmp_path), prompt="x")

    def test_tesseract_cmd_is_configured(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(pytesseract, "image_to_string", MagicMock(return_value="x"))
        monkeypatch.setattr(pytesseract, "image_to_data", MagicMock(return_value={"conf": []}))
        original = pytesseract.pytesseract.tesseract_cmd
        try:
            TesseractOcrEngine(tesseract_cmd="C:/tools/tesseract.exe").run(
                _png(tmp_path), prompt="x"
            )
            assert pytesseract.pytesseract.tesseract_cmd == "C:/tools/tesseract.exe"
        finally:
            pytesseract.pytesseract.tesseract_cmd = original

    def test_pdf_source_ocrs_each_page(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            pytesseract,
            "image_to_string",
            MagicMock(side_effect=["First page", "Second page"]),
        )
        monkeypatch.setattr(pytesseract, "image_to_data", MagicMock(return_value={"conf": []}))
        result = TesseractOcrEngine().run(_tmp_pdf(tmp_path, 2), prompt="x")
        assert len(result.pages) == 2
        assert result.text == "First page\n\nSecond page"
        assert pytesseract.image_to_string.call_count == 2

    def test_pdf_page_failure_degrades_but_continues(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(
            pytesseract,
            "image_to_string",
            MagicMock(side_effect=[RuntimeError("bad page"), "recovered"]),
        )
        monkeypatch.setattr(pytesseract, "image_to_data", MagicMock(return_value={"conf": []}))
        with caplog.at_level(logging.WARNING):
            result = TesseractOcrEngine().run(_tmp_pdf(tmp_path, 2), prompt="x")
        assert [p.text for p in result.pages] == ["", "recovered"]
        assert result.empty_pages == [0]
        assert "Tesseract OCR failed on page" in caplog.text
