"""Entity extraction package (P4-102)."""

from app.infrastructure.document_intelligence.entities.extractor import (
    EntityExtractor,
    analyze_document_entities,
    get_default_entity_extractor,
)

__all__ = ["EntityExtractor", "analyze_document_entities", "get_default_entity_extractor"]
