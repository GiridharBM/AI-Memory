"""Embedded-image extraction from PDFs (P2-506).

Runs at the shared enrichment call site in the ingest workflow for
``kind == "pdf"`` documents and attaches per-image ``ImageInfo`` entries
(with page provenance) to ``metadata.extra["images"]``. PyMuPDF (``fitz``) is
an optional dependency; when absent the extractor returns an empty list and
the workflow leaves the document untouched (additive behavior, R-4).
"""

from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger
from app.domain.document_intelligence import ImageExif, ImageInfo

logger = get_logger(__name__)


class MultiImageExtractor:
    """Extract ``ImageInfo`` for every image embedded in a PDF."""

    def extract(self, path: Path, *, max_images: int = 100) -> list[ImageInfo]:
        try:
            import fitz  # type: ignore[import-untyped]  # PyMuPDF — optional dep
        except ImportError:
            logger.warning("PyMuPDF unavailable; skipping embedded-image extraction.")
            return []

        # ponytail: pass bytes, not a path — MuPDF leaks the file handle on a
        # failed open() on Windows, which would lock the source file and break
        # the worker's post-processing move. Byte read is bounded upstream by
        # max_file_size_mb (50 MiB default).
        try:
            data = path.read_bytes()
        except OSError:
            return []

        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            logger.warning(
                "Failed to open PDF for image extraction.",
                extra={"path": str(path)},
                exc_info=exc,
            )
            return []

        images: list[ImageInfo] = []
        try:
            for page_no, page in enumerate(doc, start=1):
                if len(images) >= max_images:
                    break
                try:
                    items = page.get_images(full=True)
                except Exception:
                    continue
                for item in items:
                    if len(images) >= max_images:
                        break
                    xref = item[0]
                    try:
                        extracted = doc.extract_image(xref)
                    except Exception:
                        continue
                    data = extracted.get("image") or b""
                    images.append(
                        ImageInfo(
                            path=str(path),
                            format=(extracted.get("ext") or "UNKNOWN").upper(),
                            width=extracted.get("width", 0),
                            height=extracted.get("height", 0),
                            size_bytes=len(data),
                            mode="",
                            page_no=page_no,
                            index=len(images),
                            exif=ImageExif(),
                        )
                    )
        finally:
            doc.close()
        return images


def get_default_multi_image_extractor() -> MultiImageExtractor:
    """Return the configured multi-image extractor."""
    return MultiImageExtractor()
