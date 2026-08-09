"""Image file ingestor."""

from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.document_intelligence.images.metadata import analyze_image
from app.infrastructure.ingestion.base import (
    BaseIngestor,
    SourceReference,
    require_path_source,
)
from app.infrastructure.ingestion.utils import file_timestamp

logger = get_logger(__name__)


class ImageIngestor(BaseIngestor):
    """Read image files into normalized source documents (metadata only).

    ``exif_enabled`` gates the additive ``image_info`` EXIF/dimension payload
    (Milestone 2.5 P2-502); ``False`` produces the Phase-1-identical document
    (R-4). Analysis is best-effort: Pillow absence or a corrupt file yields a
    logged-warning minimal payload rather than a failed ingestion.
    """

    source_type = "image"
    supported_suffixes = (
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".heic", ".svg",
    )

    def __init__(self, *, exif_enabled: bool = True) -> None:
        self._exif_enabled = exif_enabled

    def ingest(self, source: SourceReference) -> SourceDocument:
        source_path = require_path_source(source, ingestor_name="Image ingestor")
        resolved_path = source_path.resolve()
        extra: dict[str, object] = {}
        if self._exif_enabled:
            try:
                info = analyze_image(resolved_path)
                extra["image_info"] = info.model_dump(mode="json")
            except Exception:
                logger.warning(
                    "Image analysis failed; document unchanged.",
                    extra={"path": str(resolved_path)},
                    exc_info=True,
                )
        return SourceDocument(
            source=str(resolved_path),
            source_path=resolved_path,
            source_type=self.source_type,
            filename=source_path.name,
            text="",
            metadata=DocumentMetadata(
                title=source_path.stem,
                modified_at=file_timestamp(source_path),
                mime_type=self._guess_mime(source_path),
                extra=extra,
            ),
        )

    @staticmethod
    def _guess_mime(path: Path) -> str:
        ext = path.suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff",
            ".heic": "image/heic",
            ".svg": "image/svg+xml",
        }
        return mime_map.get(ext, "image/*")
