"""Tests for the PDF page renderer (P2-103, prerequisite of P2-102)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.infrastructure.document_intelligence.ocr.pdf import render_pdf_pages


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


class TestRenderPdfPages:
    def test_renders_all_pages(self) -> None:
        pdf_path = _tmp_pdf(4)
        try:
            pages = list(render_pdf_pages(pdf_path))
            assert len(pages) == 4
            assert [p.page_no for p in pages] == [0, 1, 2, 3]
            assert all(p.png_bytes.startswith(b"\x89PNG") for p in pages)
        finally:
            pdf_path.unlink()

    def test_page_limit_is_honored(self) -> None:
        pdf_path = _tmp_pdf(4)
        try:
            assert len(list(render_pdf_pages(pdf_path, page_limit=2))) == 2
            assert len(list(render_pdf_pages(pdf_path, page_limit=0))) == 4
            assert len(list(render_pdf_pages(pdf_path, page_limit=99))) == 4
            assert len(list(render_pdf_pages(pdf_path, max_pages=2))) == 2
        finally:
            pdf_path.unlink()

    def test_zoom_changes_output(self) -> None:
        pdf_path = _tmp_pdf(1)
        try:
            low = list(render_pdf_pages(pdf_path, zoom=1.0))[0]
            high = list(render_pdf_pages(pdf_path, zoom=4.0))[0]
            assert len(high.png_bytes) > len(low.png_bytes)
        finally:
            pdf_path.unlink()

    def test_missing_pymupdf_raises(self, monkeypatch) -> None:
        import sys

        pdf_path = _tmp_pdf(1)
        try:
            with monkeypatch.context() as ctx:
                ctx.setitem(sys.modules, "fitz", None)
                with pytest.raises(ImportError, match="PyMuPDF"):
                    list(render_pdf_pages(pdf_path))
        finally:
            pdf_path.unlink()
