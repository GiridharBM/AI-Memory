"""Audio file ingestor."""

from __future__ import annotations

from pathlib import Path

from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.ingestion.base import (
    BaseIngestor,
    SourceReference,
    require_path_source,
)
from app.infrastructure.ingestion.utils import file_timestamp


class AudioIngestor(BaseIngestor):
    """Read audio files into normalized source documents (metadata only)."""

    source_type = "audio"
    supported_suffixes = (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac")

    def ingest(self, source: SourceReference) -> SourceDocument:
        source_path = require_path_source(source, ingestor_name="Audio ingestor")
        resolved_path = source_path.resolve()
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
            ),
        )

    @staticmethod
    def _guess_mime(path: Path) -> str:
        ext = path.suffix.lower()
        mime_map = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
            ".flac": "audio/flac",
            ".ogg": "audio/ogg",
            ".aac": "audio/aac",
        }
        return mime_map.get(ext, "audio/*")
