"""Domain models for document entities and relationships (P4-101).

Foundational, serializable data model for the entities mentioned in a
source document and the typed relationships between them, plus the
provenance references (source document, chunk, character offsets) the
existing architecture already supports. This milestone deliberately
ships no graph storage or retrieval — later milestones (MEDD Phase 5)
consume these models for graph construction.

Compatibility notes:
- ``EntityType`` / ``ImportanceLevel`` are reused from ``app.domain.analysis``.
- ``EdgeType`` is reused from ``app.domain.knowledge_graph`` so a
  ``Relationship`` maps 1:1 onto a future ``KnowledgeEdge``.
- ``SourceReference`` mirrors the provenance fields carried by
  ``DocumentChunk`` (``source``, ``source_type``, ``chunk_id``,
  ``start_char``/``end_char``) and the ``DocumentStructure`` sections.
"""

from __future__ import annotations

import json
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.analysis import EntityType, ImportanceLevel, ImportantEntity
from app.domain.knowledge_graph import EdgeType
from app.domain.semantic_chunking import DocumentChunk


def _ensure_json_safe(values: dict[str, Any]) -> dict[str, Any]:
    """Reject metadata values that would break JSON serialization."""
    for key, value in values.items():
        try:
            json.dumps(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Metadata value for {key!r} is not JSON-serializable.") from exc
    return values


class _EntityRelationshipModel(BaseModel):
    """Base model with deterministic JSON serialization (extra keys forbidden)."""

    model_config = ConfigDict(extra="forbid")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict in a deterministic field order."""
        return self.model_dump(mode="json")

    def to_json(self) -> str:
        """Return a canonical, byte-stable JSON string (keys sorted)."""
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls.model_validate(data)

    @classmethod
    def from_json(cls, data: str) -> Self:
        return cls.model_validate(json.loads(data))


class SourceReference(_EntityRelationshipModel):
    """A provenance reference into a source document.

    Mirrors the fields ``DocumentChunk`` already carries (``source``,
    ``source_type``, ``chunk_id``, ``start_char``/``end_char``) plus an
    optional ``section_id`` when the structure subsystem is available.
    Character offsets are preserved wherever the source text supports
    them; both must be provided together and ``end_char >= start_char``.
    """

    source: str = Field(min_length=1)
    source_type: str = ""
    chunk_id: str | None = None
    section_id: str | None = None
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)
    snippet: str = ""

    @model_validator(mode="after")
    def _validate_offsets(self) -> SourceReference:
        start_char = self.start_char
        end_char = self.end_char
        if (start_char is None) != (end_char is None):
            raise ValueError("start_char and end_char must be provided together.")
        if start_char is not None and end_char is not None and end_char < start_char:
            raise ValueError("end_char must be >= start_char.")
        return self

    @classmethod
    def from_chunk(cls, chunk: DocumentChunk) -> SourceReference:
        """Build a reference from an existing chunk, preserving its offsets."""
        return cls(
            source=chunk.source,
            source_type=chunk.source_type,
            chunk_id=chunk.chunk_id,
            start_char=chunk.start_char,
            end_char=chunk.end_char,
            snippet=chunk.text,
        )


class EntityMetadata(_EntityRelationshipModel):
    """Typed metadata for an entity.

    Known fields mirror what the existing ``KnowledgeGraphBuilder`` writes
    into node metadata (``importance``); ``extra`` carries arbitrary
    JSON-safe attributes for later graph-construction extensibility.
    """

    importance: ImportanceLevel | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("extra")
    @classmethod
    def _extra_json_safe(cls, values: dict[str, Any]) -> dict[str, Any]:
        return _ensure_json_safe(values)


class RelationshipMetadata(_EntityRelationshipModel):
    """Typed metadata for a relationship.

    ``confidence`` allows extraction confidence to survive serialization
    (the existing graph stores metadata as ``dict[str, str]``, which
    cannot hold numerics — TD-14); ``extra`` is JSON-safe and open.
    """

    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("extra")
    @classmethod
    def _extra_json_safe(cls, values: dict[str, Any]) -> dict[str, Any]:
        return _ensure_json_safe(values)


class Entity(_EntityRelationshipModel):
    """A named entity mentioned in a source document.

    ``id`` is a stable identifier; ``make_id`` derives it deterministically
    from label and type (same normalization as the existing graph builder's
    ``_make_id``). ``sources`` preserve where the entity was observed.
    """

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    entity_type: EntityType = "other"
    description: str = ""
    aliases: list[str] = Field(default_factory=list)
    metadata: EntityMetadata = Field(default_factory=EntityMetadata)
    sources: list[SourceReference] = Field(default_factory=list)

    @field_validator("label")
    @classmethod
    def _label_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Entity label must not be empty.")
        return cleaned

    @staticmethod
    def make_id(label: str, entity_type: str) -> str:
        """Deterministic stable id: ``{entity_type}::{normalized_label}``."""
        return f"{entity_type}::{label.strip().lower().replace(' ', '_')}"

    @classmethod
    def from_important_entity(cls, entity: ImportantEntity, source: str) -> Entity:
        """Build an entity from an existing analysis ``ImportantEntity``."""
        return cls(
            id=cls.make_id(entity.name, entity.type),
            label=entity.name,
            entity_type=entity.type,
            description=entity.description,
            sources=[SourceReference(source=source)],
        )


class Relationship(_EntityRelationshipModel):
    """A typed, directed relationship between two entities.

    ``source_id``/``target_id`` reference ``Entity.id`` values;
    ``relationship_type`` reuses the graph ``EdgeType`` vocabulary so the
    relationship maps 1:1 onto a future ``KnowledgeEdge``. Validation
    rejects malformed or incomplete data: blank endpoints and self-loops.
    """

    id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    relationship_type: EdgeType = "related_to"
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: RelationshipMetadata = Field(default_factory=RelationshipMetadata)
    sources: list[SourceReference] = Field(default_factory=list)

    @field_validator("source_id", "target_id")
    @classmethod
    def _endpoint_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Relationship endpoints must not be blank.")
        return cleaned

    @model_validator(mode="after")
    def _validate_endpoints(self) -> Relationship:
        if self.source_id == self.target_id:
            raise ValueError("Relationship source_id and target_id must differ.")
        return self

    @staticmethod
    def make_id(source_id: str, target_id: str, relationship_type: str = "related_to") -> str:
        """Deterministic stable id: ``{source_id}::{type}::{target_id}``."""
        return f"{source_id}::{relationship_type}::{target_id}"
