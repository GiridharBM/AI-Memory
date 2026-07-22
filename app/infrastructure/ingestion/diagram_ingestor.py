"""Ingestor for diagram files (.drawio, .vsdx)."""

from __future__ import annotations

import re
from xml.etree import ElementTree

from app.core.logging import get_logger
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.ingestion.base import (
    BaseIngestor,
    IngestionError,
    SourceReference,
    require_path_source,
)
from app.infrastructure.ingestion.utils import clean_text, file_timestamp

logger = get_logger(__name__)


class DiagramIngestor(BaseIngestor):
    """Ingest diagram files by extracting labels and structure."""

    source_type = "diagram"
    supported_suffixes = (".drawio", ".vsdx", ".mmd")

    def ingest(self, source: SourceReference) -> SourceDocument:
        path = require_path_source(source, ingestor_name="DiagramIngestor")
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            raise IngestionError(f"Failed to read diagram '{path.name}'.") from exc

        suffix = path.suffix.lower()
        if suffix == ".drawio":
            content = self._parse_drawio(raw)
        else:
            content = raw

        cleaned = clean_text(content)
        return SourceDocument(
            source=str(path),
            source_path=path,
            source_type=self.source_type,
            filename=path.name,
            text=cleaned,
            metadata=DocumentMetadata(
                title=path.stem,
                created_at=file_timestamp(path),
                modified_at=file_timestamp(path),
                extra={"format": suffix.lstrip(".")},
            ),
        )

    @staticmethod
    def _parse_drawio(xml_content: str) -> str:
        try:
            root = ElementTree.fromstring(xml_content)
        except ElementTree.ParseError:
            return xml_content

        parts: list[str] = ["Diagram: draw.io", ""]
        for cell in root.iter("mxCell"):
            label = cell.get("value", "").strip()
            if label and not label.startswith("<"):
                parts.append(f"  - {label}")
            elif label and "<" in label:
                text = re.sub(r"<[^>]+>", "", label).strip()
                if text:
                    parts.append(f"  - {text}")
        return "\n".join(parts) if len(parts) > 2 else xml_content
