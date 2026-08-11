"""PPTX file ingestor."""

from __future__ import annotations

from pathlib import Path

from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.ingestion.base import (
    BaseIngestor,
    IngestionError,
    SourceReference,
    require_path_source,
)
from app.infrastructure.ingestion.utils import file_timestamp


class PptxIngestor(BaseIngestor):
    """Read PPTX files into normalized source documents."""

    source_type = "pptx"
    supported_suffixes = (".pptx", ".ppt", ".odp")

    def ingest(self, source: SourceReference) -> SourceDocument:
        source_path = require_path_source(source, ingestor_name="PPTX ingestor")
        text = self._extract_text(source_path)
        resolved_path = source_path.resolve()
        return SourceDocument(
            source=str(resolved_path),
            source_path=resolved_path,
            source_type=self.source_type,
            filename=source_path.name,
            text=text,
            metadata=DocumentMetadata(
                title=source_path.stem,
                modified_at=file_timestamp(source_path),
                mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ),
        )

    def _extract_text(self, path: Path) -> str:
        try:
            from pptx import Presentation  # type: ignore[import-untyped]

            prs = Presentation(str(path))
            texts: list[str] = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        texts.append(shape.text)
            return "\n".join(texts)
        except ImportError:
            raise IngestionError(
                "python-pptx is required for PPTX ingestion. Install with: pip install python-pptx"
            ) from None
        except Exception as exc:
            raise IngestionError(f"Unable to read PPTX file '{path}'.") from exc
