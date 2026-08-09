"""Relationship detection package (P4-103)."""

from app.infrastructure.document_intelligence.relationships.detector import (
    RelationshipDetector,
    analyze_document_relationships,
    get_default_relationship_detector,
)

__all__ = [
    "RelationshipDetector",
    "analyze_document_relationships",
    "get_default_relationship_detector",
]
