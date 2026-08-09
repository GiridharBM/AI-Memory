"""Document intelligence package — OCR engines, image preprocessing, and later milestones."""

from app.infrastructure.document_intelligence.entities import (
    analyze_document_entities,
    get_default_entity_extractor,
)
from app.infrastructure.document_intelligence.graph import (
    build_document_graph,
    find_relationships,
    get_default_document_graph_builder,
    get_entity,
    graph_from_dict,
    graph_to_dict,
    nodes_by_source,
    query_graph,
    related_entities,
)
from app.infrastructure.document_intelligence.relationships import (
    analyze_document_relationships,
    get_default_relationship_detector,
)
from app.infrastructure.document_intelligence.structure.detector import (
    analyze_document_structure,
    get_default_structure_analyzer,
)

__all__ = [
    "analyze_document_entities",
    "analyze_document_relationships",
    "analyze_document_structure",
    "build_document_graph",
    "find_relationships",
    "get_default_document_graph_builder",
    "get_default_entity_extractor",
    "get_default_relationship_detector",
    "get_default_structure_analyzer",
    "get_entity",
    "graph_from_dict",
    "graph_to_dict",
    "nodes_by_source",
    "query_graph",
    "related_entities",
]
