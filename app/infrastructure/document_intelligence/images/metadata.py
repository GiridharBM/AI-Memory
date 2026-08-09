"""Image metadata analysis (P2-502): dimensions, format, size, EXIF.

Single owner of image EXIF in the codebase (R-3): the ``metadata.extractors``
module deliberately reads none, and image fields are consumed from the
``ImageInfo`` produced here. Pillow is optional (``[intelligence]`` extra);
when absent the analyzer degrades to a logged-warning minimal result rather
than raising (C-3 DoD clause).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.domain.document_intelligence import ImageExif, ImageInfo

logger = get_logger(__name__)

try:  # pragma: no cover - exercised implicitly by the C-3 degradation path
    from PIL import Image
    from PIL.ExifTags import TAGS

    _PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PIL_AVAILABLE = False


def _exif_value(value: Any) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return repr(value)
    if isinstance(value, tuple):
        return ",".join(_exif_value(item) for item in value)
    return str(value)


def _read_exif(path: Path) -> ImageExif:
    """Read EXIF tags via Pillow; preserve raw tag numbers and decoded names."""
    raw: dict[int, str] = {}
    decoded: dict[str, str] = {}
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            for tag_id, value in exif.items():
                if isinstance(value, bytes) and value == b"":
                    continue
                raw[tag_id] = _exif_value(value)
                name = TAGS.get(tag_id, "")
                if name:
                    decoded[name] = _exif_value(value)
    except Exception as exc:
        logger.debug(
            "Failed to read EXIF; returning empty block.",
            extra={"path": str(path)},
            exc_info=exc,
        )
    return ImageExif(raw=raw, decoded=decoded)


class ImageAnalyzer:
    """Produce an ``ImageInfo`` for a standalone image file."""

    def analyze(self, path: Path, *, include_exif: bool = True) -> ImageInfo:
        path = path.resolve()
        try:
            size_bytes = path.stat().st_size
        except OSError:
            size_bytes = 0

        width = height = 0
        mode = ""
        fmt = path.suffix.lstrip(".").upper() or "UNKNOWN"
        if _PIL_AVAILABLE:
            try:
                with Image.open(path) as image:
                    image.load()
                    width, height = image.size
                    mode = image.mode or ""
                    fmt = image.format or fmt
            except Exception as exc:
                logger.debug(
                    "Pillow could not read image; returning file-level info only.",
                    extra={"path": str(path)},
                    exc_info=exc,
                )

        exif = ImageExif()
        if include_exif and fmt.upper() not in {"SVG"}:
            exif = _read_exif(path)
        return ImageInfo(
            path=str(path),
            format=fmt,
            width=width,
            height=height,
            size_bytes=size_bytes,
            mode=mode,
            exif=exif,
        )


def analyze_image(
    path: Path,
    *,
    include_exif: bool = True,
    analyzer: ImageAnalyzer | None = None,
) -> ImageInfo:
    """Public API: analyze a standalone image file into an ``ImageInfo``."""
    return (analyzer or ImageAnalyzer()).analyze(path, include_exif=include_exif)
