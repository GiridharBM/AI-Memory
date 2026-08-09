"""OCR pipeline integration tests (M2.1). Real Tesseract path, hermetic."""

from __future__ import annotations

from pathlib import Path

import pytest

pytesseract = pytest.importorskip("pytesseract")


def _tesseract_available() -> bool:
    try:
        pytesseract.get_tesseract_version()
        return True
    except pytesseract.TesseractNotFoundError:
        return False


@pytest.mark.integration
@pytest.mark.skipif(not _tesseract_available(), reason="Tesseract binary not installed")
def test_tesseract_engine_ocrs_printed_png(tmp_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    from app.infrastructure.document_intelligence.ocr.engines import TesseractOcrEngine

    image = Image.new("L", (900, 300), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=56)
    draw.text((40, 60), "HELLO TESSERACT", font=font, fill=0)
    draw.text((40, 160), "PRINTED TEXT 12345", font=font, fill=0)
    src = tmp_path / "printed.png"
    image.save(src)

    result = TesseractOcrEngine().run(src, prompt="x")
    upper = result.text.upper()
    assert "HELLO" in upper
    assert "TESSERACT" in upper
    assert "12345" in upper
