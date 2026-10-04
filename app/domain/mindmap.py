"""Structured models for V2-F AI-enriched mind map generation.

The enriched map is a derived artifact: ``KnowledgeNode`` remains
authoritative for the knowledge graph, while these models describe the
LLM-generated, annotated mind map persisted as a MINDMAP artifact.
Provenance lives in ``ProvenanceStore``, not here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _clean_lines(values: list[str]) -> list[str]:
    """Strip each line and drop blanks, preserving order."""

    return [line.strip() for line in values if isinstance(line, str) and line.strip()]


class EnrichedMindMapNode(BaseModel):
    """One annotated node of an enriched mind map."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    node_type: str
    source: str = ""
    description: str = ""
    key_points: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Node id must not be empty.")
        return cleaned

    @field_validator("label")
    @classmethod
    def _validate_label(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Node label must not be empty.")
        return cleaned

    @field_validator("node_type")
    @classmethod
    def _validate_node_type(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Node type must not be empty.")
        return cleaned

    @field_validator("source", "description", mode="before")
    @classmethod
    def _clean_optional_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Node text fields must be strings.")
        return " ".join(value.split())

    @field_validator("key_points", mode="before")
    @classmethod
    def _clean_key_points(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("Node key_points must be a list of strings.")
        return _clean_lines(value)


class EnrichedMindMapEdge(BaseModel):
    """One directed relationship between two enriched nodes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    target_id: str
    relationship: str

    @field_validator("source_id", "target_id")
    @classmethod
    def _validate_endpoint(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Edge endpoints must not be empty.")
        return cleaned

    @field_validator("relationship")
    @classmethod
    def _validate_relationship(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Edge relationship must not be empty.")
        return cleaned


class EnrichedMindMap(BaseModel):
    """A validated enriched mind map from one generation call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    root_node_id: str
    nodes: list[EnrichedMindMapNode] = Field(min_length=1, max_length=60)
    edges: list[EnrichedMindMapEdge] = Field(default_factory=list, max_length=120)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Mind map title must not be empty.")
        return cleaned

    @field_validator("root_node_id")
    @classmethod
    def _validate_root(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Root node id must not be empty.")
        return cleaned

    @model_validator(mode="after")
    def _validate_structure(self) -> EnrichedMindMap:
        ids = [node.id for node in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate node ids are not allowed.")
        by_id = set(ids)
        if self.root_node_id not in by_id:
            raise ValueError("Root node id must match an existing node.")
        seen_edges: set[tuple[str, str, str]] = set()
        for edge in self.edges:
            if edge.source_id == edge.target_id:
                raise ValueError("Self-edges are not allowed.")
            if edge.source_id not in by_id or edge.target_id not in by_id:
                raise ValueError("Every edge endpoint must match an existing node.")
            key = (edge.source_id, edge.target_id, edge.relationship)
            if key in seen_edges:
                raise ValueError("Duplicate edges are not allowed.")
            seen_edges.add(key)
        return self
