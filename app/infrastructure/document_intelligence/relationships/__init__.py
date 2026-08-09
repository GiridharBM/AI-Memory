"""Relationship detection package (P4-103)."""

from app.infrastructure.document_intelligence.relationships.detector import (
    RelationshipDetector,
    get_default_relationship_detector,
)

__all__ = [
    "RelationshipDetector",
    "get_default_relationship_detector",
]
