"""Tests for the VisionOcrEngine (P2-102)."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from app.infrastructure.document_intelligence.ocr.engines import VisionOcrEngine


def _tmp_pdf(n_pages: int = 4) -> Path:
    import fitz

    pdf_path = Path(tempfile.mktemp(suffix=".pdf"))
    doc = fitz.open()
    for page_no in range(n_pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {page_no + 1} content")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _mock_vision(text: str = "extracted text") -> MagicMock:
    client = MagicMock()
    client.describe_image.return_value = text
    return client


class TestVisionOcrEnginePdf:
    def test_four_pages_yields_four_results(self) -> None:
        client = _mock_vision("Page text")
        engine = VisionOcrEngine(client)
        pdf_path = _tmp_pdf(4)
        try:
            result = engine.run(pdf_path, prompt="x")
            assert len(result.pages) == 4
            assert [p.page_no for p in result.pages] == [0, 1, 2, 3]
            assert result.text == "\n\n".join(["Page text"] * 4)
            assert result.empty_pages == []
            assert client.describe_image.call_count == 4
        finally:
            pdf_path.unlink()

    def test_page_limit_limits_pages(self) -> None:
        engine = VisionOcrEngine(_mock_vision("Page text"), page_limit=2)
        pdf_path = _tmp_pdf(4)
        try:
            result = engine.run(pdf_path, prompt="x")
            assert len(result.pages) == 2
        finally:
            pdf_path.unlink()

    def test_stops_early_on_empty_page(self) -> None:
        client = _mock_vision("Page text")
        client.describe_image.side_effect = ["first", "", "never reached"]
        engine = VisionOcrEngine(client)
        pdf_path = _tmp_pdf(4)
        try:
            result = engine.run(pdf_path, prompt="x")
            assert [p.text for p in result.pages] == ["first", ""]
            assert result.empty_pages == [1]
            assert client.describe_image.call_count == 2
        finally:
            pdf_path.unlink()

    def test_retries_once_on_transient_error(self) -> None:
        client = _mock_vision("recovered")
        client.describe_image.side_effect = [RuntimeError("vision down"), "recovered"]
        engine = VisionOcrEngine(client)
        pdf_path = _tmp_pdf(1)
        try:
            result = engine.run(pdf_path, prompt="x")
            assert result.text == "recovered"
            assert client.describe_image.call_count == 2
        finally:
            pdf_path.unlink()

    def test_two_consecutive_failures_yield_empty_page(self, caplog) -> None:
        client = MagicMock()
        client.describe_image.side_effect = [RuntimeError("down"), RuntimeError("still down")]
        engine = VisionOcrEngine(client)
        pdf_path = _tmp_pdf(1)
        try:
            with caplog.at_level(logging.WARNING):
                result = engine.run(pdf_path, prompt="x")
            assert len(result.pages) == 1 and result.pages[0].text == ""
            assert result.text == ""
            assert result.empty_pages == [0]
            assert "Vision OCR failed on page" in caplog.text
        finally:
            pdf_path.unlink()

    def test_temp_png_files_are_cleaned_up(self) -> None:
        client = _mock_vision("Page text")
        engine = VisionOcrEngine(client)
        pdf_path = _tmp_pdf(1)
        try:
            engine.run(pdf_path, prompt="x")
        finally:
            pdf_path.unlink()
        temp_paths = [c.args[0] for c in client.describe_image.call_args_list]
        assert temp_paths
        assert all(not Path(p).exists() for p in temp_paths)


class TestVisionOcrEngineImage:
    def test_image_source_is_described(self) -> None:
        client = _mock_vision("image text")
        engine = VisionOcrEngine(client)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image bytes")
            img_path = Path(f.name)
        try:
            result = engine.run(img_path, prompt="x")
            assert result.text == "image text"
            assert result.pages[0].page_no == 0
            client.describe_image.assert_called_once()
        finally:
            img_path.unlink()

    def test_supported_kinds(self) -> None:
        assert VisionOcrEngine(_mock_vision()).supported_kinds == {
            "scanned_pdf", "image", "handwritten",
        }
