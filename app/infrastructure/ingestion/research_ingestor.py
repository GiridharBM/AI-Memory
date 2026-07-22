"""Ingestor for research citation files (.bib, .ris)."""

from __future__ import annotations

import re

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


class ResearchIngestor(BaseIngestor):
    """Ingest research citation files (.bib, .ris)."""

    source_type = "research"
    supported_suffixes = (".bib", ".ris")

    def ingest(self, source: SourceReference) -> SourceDocument:
        path = require_path_source(source, ingestor_name="ResearchIngestor")
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            raise IngestionError(f"Failed to read research file '{path.name}'.") from exc

        suffix = path.suffix.lower()
        if suffix == ".bib":
            entries = self._parse_bib(raw)
        else:
            entries = self._parse_ris(raw)

        cleaned = clean_text(entries)
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
    def _parse_bib(content: str) -> str:
        entries: list[str] = []
        for match in re.finditer(r"@\w+\{([^,]+),(.*?)\n\}", content, re.DOTALL):
            key = match.group(1).strip()
            body = match.group(2).strip()
            fields: list[str] = [f"Citation Key: {key}"]
            for field_match in re.finditer(r"(\w+)\s*=\s*\{([^}]*)\}", body):
                fields.append(f"{field_match.group(1)}: {field_match.group(2)}")
            entries.append("\n".join(fields))
        return "\n\n".join(entries) if entries else content

    @staticmethod
    def _parse_ris(content: str) -> str:
        entries: list[str] = []
        current: list[str] = []
        for line in content.splitlines():
            if line.startswith("ER  -"):
                if current:
                    entries.append("\n".join(current))
                    current = []
            elif " - " in line:
                tag, _, value = line.partition(" - ")
                current.append(f"{tag.strip()}: {value.strip()}")
        if current:
            entries.append("\n".join(current))
        return "\n\n".join(entries) if entries else content
