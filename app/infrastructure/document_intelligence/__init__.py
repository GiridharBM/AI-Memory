"""Document intelligence package — OCR engines, image preprocessing, and later milestones."""

from app.infrastructure.document_intelligence.entities import get_default_entity_extractor
from app.infrastructure.document_intelligence.graph import (
    get_default_document_graph_builder,
    graph_to_dict,
)
from app.infrastructure.document_intelligence.relationships import (
    get_default_relationship_detector,
)
from app.infrastructure.document_intelligence.structure.detector import (
    get_default_structure_analyzer,
)

__all__ = [
    "get_default_document_graph_builder",
    "get_default_entity_extractor",
    "get_default_relationship_detector",
    "get_default_structure_analyzer",
    "graph_to_dict",
]
