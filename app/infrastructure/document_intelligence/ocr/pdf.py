"""PDF page rendering for OCR."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PageImage:
    """A rendered PDF page as PNG bytes."""

    page_no: int
    png_bytes: bytes


def render_pdf_pages(
    pdf_path: Path,
    *,
    zoom: float = 2.0,
    page_limit: int | None = None,
    max_pages: int = 200,
) -> Iterator[PageImage]:
    """Render PDF pages to PNG bytes with configurable zoom and page limit.

    ``page_limit`` of 0 or ``None`` renders every page; the count is always
    capped by ``max_pages``. A page that fails to render is skipped with a
    warning — a single bad page never aborts the pass. A missing PyMuPDF
    raises a clear ``ImportError`` immediately.
    """
    try:
        import fitz  # eager: clear ImportError if PyMuPDF is absent (legacy contract)
    except ImportError as exc:
        raise ImportError(
            "PyMuPDF is required for scanned PDF OCR. "
            "Install with: pip install PyMuPDF",
        ) from exc

    def _iter() -> Iterator[PageImage]:
        try:
            with fitz.open(str(pdf_path)) as doc:
                total = len(doc)
                limit = total if not page_limit or page_limit <= 0 else min(page_limit, total)
                limit = min(limit, max_pages)
                for page_no in range(limit):
                    try:
                        pix = doc[page_no].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                        yield PageImage(page_no=page_no, png_bytes=pix.tobytes("png"))
                    except Exception:
                        logger.warning(
                            "Failed to render PDF page.",
                            extra={"path": str(pdf_path), "page_no": page_no + 1},
                            exc_info=True,
                        )
        except Exception:
            logger.warning("Failed to open PDF for OCR: %s", pdf_path)

    return _iter()
