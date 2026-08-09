"""Metadata extraction package — public API surface (P2-201)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.core.logging import get_logger
from app.domain.document_intelligence import MetadataExtraction
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.document_intelligence.metadata.hooks import (
    IngestionHook,
    get_default_hook_registry,
    register_hook,
)
from app.infrastructure.document_intelligence.metadata.language import detect_language
from app.infrastructure.document_intelligence.metadata.mime import detect_mime

logger = get_logger(__name__)

_KNOWN_METADATA_FIELDS = frozenset(
    {
        "title",
        "author",
        "created_at",
        "modified_at",
        "page_count",
        "mime_type",
        "encoding",
    }
)


@runtime_checkable
class MetadataExtractor(Protocol):
    """Contract implemented by every metadata extractor (frozen §2.3)."""

    source_types: tuple[str, ...]

    def extract(self, document: SourceDocument) -> dict[str, Any]:
        """Extract metadata values from a source document."""
        ...


class DocumentMetadataService:
    """Registry that selects metadata extractors for a source type.

    Extractors are registered per ``source_types`` and selected in
    registration order. ``extract`` runs every matching extractor and merges
    their values into one ``MetadataExtraction``.
    """

    def __init__(self, extractors: list[MetadataExtractor] | None = None) -> None:
        self._extractors: list[MetadataExtractor] = list(extractors or [])

    def register(self, extractor: MetadataExtractor) -> None:
        """Register a metadata extractor (idempotent)."""
        if extractor not in self._extractors:
            self._extractors.append(extractor)

    @property
    def extractors(self) -> list[MetadataExtractor]:
        """Return a snapshot of registered extractors in registration order."""
        return list(self._extractors)

    def extractors_for(self, source_type: str) -> list[MetadataExtractor]:
        """Return extractors supporting the given source type, in registration order."""
        return [e for e in self._extractors if source_type in e.source_types]

    def extract(self, document: SourceDocument) -> MetadataExtraction:
        """Run matching extractors and merge their values into one extraction.

        A source type with no matching extractor yields an empty extraction
        (never raises). Each matching extractor's result is merged in order;
        later extractors override earlier values for shared keys.
        """
        matching = self.extractors_for(document.source_type)
        if not matching:
            logger.debug(
                "No metadata extractor registered.",
                extra={"source_type": document.source_type, "source": document.source},
            )
            return MetadataExtraction(
                source_type=document.source_type,
                values={},
                extractor="<none>",
            )

        values: dict[str, Any] = {}
        names: list[str] = []
        for extractor in matching:
            values.update(extractor.extract(document))
            names.append(getattr(extractor, "name", type(extractor).__name__))
        return MetadataExtraction(
            source_type=document.source_type,
            values=values,
            extractor=",".join(names),
        )

    @staticmethod
    def merge(
        metadata: DocumentMetadata,
        extraction: MetadataExtraction,
    ) -> DocumentMetadata:
        """Merge an extraction into document metadata (additive).

        Known ``DocumentMetadata`` fields are written directly; unknown keys
        are routed into ``metadata.extra``.
        """
        updates: dict[str, Any] = {}
        extra = dict(metadata.extra or {})
        for key, value in extraction.values.items():
            if key in _KNOWN_METADATA_FIELDS:
                updates[key] = value
            else:
                extra[key] = value
        updates["extra"] = extra
        return metadata.model_copy(update=updates)


_default_service: DocumentMetadataService | None = None


def get_default_metadata_service() -> DocumentMetadataService:
    """Return the process-wide default metadata service, creating it lazily."""
    global _default_service
    if _default_service is None:
        _default_service = DocumentMetadataService()
    return _default_service


def register_extractor(extractor: MetadataExtractor) -> None:
    """Register a metadata extractor on the default service (public alias)."""
    get_default_metadata_service().register(extractor)


__all__ = [
    "DocumentMetadataService",
    "IngestionHook",
    "MetadataExtraction",
    "MetadataExtractor",
    "detect_language",
    "detect_mime",
    "get_default_hook_registry",
    "get_default_metadata_service",
    "register_extractor",
    "register_hook",
]
