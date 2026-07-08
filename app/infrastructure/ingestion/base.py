"""Base abstractions for source ingestion."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.domain.documents import SourceDocument

SourceReference = str | Path


class IngestionError(RuntimeError):
    """Raised when a source document cannot be ingested."""


class UnsupportedSourceError(IngestionError):
    """Raised when no ingestion adapter supports a source."""


class BaseIngestor(ABC):
    """Abstract source ingestor contract."""

    source_type: str
    supported_suffixes: tuple[str, ...] = ()

    def can_ingest(self, source: SourceReference) -> bool:
        """Return whether the ingestor supports the provided source."""

        if isinstance(source, Path):
            return source.suffix.lower() in self.supported_suffixes
        return False

    @abstractmethod
    def ingest(self, source: SourceReference) -> SourceDocument:
        """Read a source and return a normalized document."""


def require_path_source(source: SourceReference, *, ingestor_name: str) -> Path:
    """Return a path source or raise a consistent ingestion error."""

    if isinstance(source, Path):
        return source
    raise IngestionError(
        f"{ingestor_name} received unsupported source reference '{source}'."
    )
