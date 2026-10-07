"""Pure business concepts and rules."""

from app.domain.analysis import (
    Definition,
    DocumentAnalysis,
    DocumentSummary,
    ImportantEntity,
    KeyConcept,
    RelatedTopic,
)
from app.domain.artifacts import (
    Artifact,
    ArtifactKind,
    ProvenanceRecord,
    ProvenanceRole,
    note_to_artifact,
)
from app.domain.conversation import (
    Conversation,
    ConversationStatus,
    EvidenceCitation,
    EvidenceSnapshot,
    Message,
    MessageRole,
)
from app.domain.documents import (
    DocumentIngestionError,
    DocumentIngestionResult,
    DocumentMetadata,
    SourceDocument,
)
from app.domain.entity_relationship import (
    Entity,
    EntityMetadata,
    Relationship,
    RelationshipMetadata,
    SourceReference,
)
from app.domain.generation import (
    ConfigValue,
    GenerationRequest,
    GenerationTaskType,
    ProvenanceLevel,
)
from app.domain.generation_context import GenerationContext, RetrievedChunk
from app.domain.generation_documents import Presentation, Report, ReportSection, Slide
from app.domain.generation_result import GenerationResult
from app.domain.generation_sets import FlashcardSet, QuizSet
from app.domain.image import ImagePlan, ImageSpec
from app.domain.jobs import (
    GenerationJob,
    GenerationJobStatus,
    InvalidJobTransitionError,
    cancel,
    fail,
    set_progress,
    transition,
)
from app.domain.knowledge_graph import (
    EdgeType,
    GraphBuildResult,
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
    NodeType,
)
from app.domain.memory import (
    CandidateStatus,
    Memory,
    MemoryCandidate,
    MemoryCategory,
    MemoryGrounding,
    MemoryReview,
    MemorySource,
    MemoryStatus,
    ReviewDecision,
)
from app.domain.mindmap import EnrichedMindMap, EnrichedMindMapEdge, EnrichedMindMapNode
from app.domain.notes import ObsidianNote
from app.domain.scopes import (
    MemoryScope,
    MemoryScopeKind,
    ResolvedScope,
    UnsupportedMemoryScopeError,
    resolve_memory_scope,
)
from app.domain.semantic_chunking import DocumentChunk
from app.domain.vector_store import SearchResult, VectorEntry

__all__ = [
    "Artifact",
    "ArtifactKind",
    "CandidateStatus",
    "ConfigValue",
    "Conversation",
    "ConversationStatus",
    "Definition",
    "DocumentAnalysis",
    "DocumentChunk",
    "DocumentIngestionError",
    "DocumentIngestionResult",
    "DocumentMetadata",
    "DocumentSummary",
    "EdgeType",
    "EnrichedMindMap",
    "EnrichedMindMapEdge",
    "EnrichedMindMapNode",
    "Entity",
    "EntityMetadata",
    "EvidenceCitation",
    "EvidenceSnapshot",
    "FlashcardSet",
    "GenerationContext",
    "GenerationJob",
    "GenerationJobStatus",
    "GenerationRequest",
    "GenerationResult",
    "GenerationTaskType",
    "GraphBuildResult",
    "ImagePlan",
    "ImageSpec",
    "ImportantEntity",
    "InvalidJobTransitionError",
    "KeyConcept",
    "KnowledgeEdge",
    "KnowledgeGraph",
    "KnowledgeNode",
    "Memory",
    "MemoryCandidate",
    "MemoryCategory",
    "MemoryGrounding",
    "MemoryReview",
    "MemoryScope",
    "MemoryScopeKind",
    "MemorySource",
    "MemoryStatus",
    "Message",
    "MessageRole",
    "NodeType",
    "ObsidianNote",
    "Presentation",
    "ProvenanceLevel",
    "ProvenanceRecord",
    "ProvenanceRole",
    "QuizSet",
    "RelatedTopic",
    "Relationship",
    "RelationshipMetadata",
    "Report",
    "ReportSection",
    "ResolvedScope",
    "RetrievedChunk",
    "ReviewDecision",
    "SearchResult",
    "Slide",
    "SourceDocument",
    "SourceReference",
    "UnsupportedMemoryScopeError",
    "VectorEntry",
    "cancel",
    "fail",
    "note_to_artifact",
    "resolve_memory_scope",
    "set_progress",
    "transition",
]
