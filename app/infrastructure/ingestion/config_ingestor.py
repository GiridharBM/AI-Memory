"""Configuration file ingestor (.toml, .ini, .cfg, .conf, .yaml, .yml)."""

from __future__ import annotations

from pathlib import Path

from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.ingestion.base import (
    BaseIngestor,
    IngestionError,
    SourceReference,
    require_path_source,
)
from app.infrastructure.ingestion.utils import clean_text, file_timestamp


class ConfigIngestor(BaseIngestor):
    """Read configuration files into normalized source documents."""

    source_type = "config"
    supported_suffixes = (
        ".toml", ".ini", ".cfg", ".conf", ".yaml", ".yml",
    )
    _DOTFILE_NAMES: frozenset[str] = frozenset({".env"})

    def can_ingest(self, source: SourceReference) -> bool:
        if isinstance(source, Path) and source.name in self._DOTFILE_NAMES:
            return True
        return super().can_ingest(source)

    def ingest(self, source: SourceReference) -> SourceDocument:
        source_path = require_path_source(source, ingestor_name="Config ingestor")
        try:
            text = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = source_path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError as exc:
                raise IngestionError(
                    f"Unable to decode config file '{source_path}'."
                ) from exc
        except OSError as exc:
            raise IngestionError(
                f"Unable to read config file '{source_path}'."
            ) from exc

        cleaned = clean_text(text)
        resolved_path = source_path.resolve()
        return SourceDocument(
            source=str(resolved_path),
            source_path=resolved_path,
            source_type=self.source_type,
            filename=source_path.name,
            text=cleaned,
            metadata=DocumentMetadata(
                title=source_path.stem,
                modified_at=file_timestamp(source_path),
                mime_type="text/plain",
            ),
        )
