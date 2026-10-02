"""Domain models for V2 artifacts and provenance.

An artifact is a versioned, persistent record of something generated from
shared PAM memory. Provenance records bind an artifact to the existing
memory identifiers it came from (sources, chunks, knowledge-graph nodes) —
provenance references memory, it never duplicates it: no second vector
index, no copied document contents, no parallel graph.

Everything here is pure: no filesystem access, no network access, no
retrieval execution, no mutation. Persistence lives in
``app.infrastructure.artifacts``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.generation import GenerationRequest
from app.domain.notes import ObsidianNote


class ArtifactKind(StrEnum):
    """Generatable artifact kinds from the product blueprint."""

    NOTE = "note"
    FLASHCARDS = "flashcards"
    QUIZ = "quiz"
    REPORT = "report"
    PPT = "ppt"
    IMAGE = "image"
    VIDEO = "video"
    MINDMAP = "mindmap"


class ProvenanceRole(StrEnum):
    """How a source record contributed to its artifact."""

    SOURCE_DOCUMENT = "source_document"
    EVIDENCE_CHUNK = "evidence_chunk"
    KNOWLEDGE_CONCEPT = "knowledge_concept"
    REFERENCE = "reference"


class ProvenanceRecord(BaseModel):
    """One evidence link between an artifact and existing memory.

    Only ``artifact_id``, ``source_id`` and ``role`` are required: chunk,
    span, node and quote fields stay optional because they cannot always be
    known. Identifiers reuse existing vocabulary (vector ``source`` values,
    ``{source}::chunk_{index}`` chunk ids, knowledge-graph node ids).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str
    source_id: str
    role: ProvenanceRole
    source_type: str | None = None
    chunk_id: str | None = None
    chunk_index: int | None = Field(default=None, ge=0)
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)
    kg_node_id: str | None = None
    quote: str | None = None

    @field_validator("artifact_id", "source_id")
    @classmethod
    def _validate_required_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Provenance identifiers must not be empty.")
        return cleaned

    @field_validator("source_type", "chunk_id", "kg_node_id", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @field_validator("quote", mode="before")
    @classmethod
    def _clean_quote(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @model_validator(mode="after")
    def _validate_span(self) -> ProvenanceRecord:
        if (
            self.start_char is not None
            and self.end_char is not None
            and self.end_char <= self.start_char
        ):
            raise ValueError("Provenance end_char must exceed start_char.")
        return self


class Artifact(BaseModel):
    """A versioned record of generated content.

    ``artifact_id`` identifies this version row; ``logical_id`` is stable
    across versions of the same logical artifact (v1 sets both to the same
    id). ``request`` is the immutable generation snapshot; ``model_role``
    and ``memory_scope`` are denormalized from it for flat querying and are
    validated to agree.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str
    logical_id: str
    kind: ArtifactKind
    title: str
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    job_id: str
    request: GenerationRequest
    model_role: str
    parent_artifact_id: str | None = None
    parent_version: int | None = Field(default=None, ge=1)
    content: str | None = None
    content_ref: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @property
    def memory_scope(self) -> object:
        """The memory scope from the immutable generation snapshot."""

        return self.request.memory_scope

    @field_validator("artifact_id", "logical_id", "job_id", "title", "model_role")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Artifact text fields must not be empty.")
        return cleaned

    @field_validator("content", "content_ref", "parent_artifact_id", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Metadata keys must be non-empty strings.")
            if not isinstance(item, str):
                raise ValueError("Metadata values must be strings.")
            cleaned[key.strip()] = item
        return cleaned

    @model_validator(mode="after")
    def _validate_consistency(self) -> Artifact:
        if self.model_role != self.request.model_role:
            raise ValueError("Artifact model_role must match its generation request.")
        if self.content is None and self.content_ref is None:
            raise ValueError("An artifact needs content or a content reference.")
        if (self.parent_artifact_id is None) != (self.parent_version is None):
            raise ValueError("Parent linkage needs both id and version, or neither.")
        if self.parent_artifact_id is None and self.version != 1:
            raise ValueError("Only a first version may have no parent.")
        if self.parent_artifact_id is not None and self.version == 1:
            raise ValueError("A first version cannot have a parent.")
        return self

    @classmethod
    def create(
        cls,
        *,
        kind: ArtifactKind,
        title: str,
        job_id: str,
        request: GenerationRequest,
        content: str | None = None,
        content_ref: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Artifact:
        """Create the first version of a new logical artifact."""

        now = datetime.now(UTC)
        artifact_id = uuid4().hex
        return cls(
            artifact_id=artifact_id,
            logical_id=artifact_id,
            kind=kind,
            title=title,
            version=1,
            created_at=now,
            updated_at=now,
            job_id=job_id,
            request=request,
            model_role=request.model_role,
            parent_artifact_id=None,
            parent_version=None,
            content=content,
            content_ref=content_ref,
            metadata=dict(metadata or {}),
        )

    def new_version(
        self,
        *,
        job_id: str,
        request: GenerationRequest,
        title: str | None = None,
        content: str | None = None,
        content_ref: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Artifact:
        """Create the next version, linked to this one; this row is untouched."""

        now = datetime.now(UTC)
        return Artifact(
            artifact_id=uuid4().hex,
            logical_id=self.logical_id,
            kind=self.kind,
            title=self.title if title is None else title,
            version=self.version + 1,
            created_at=now,
            updated_at=now,
            job_id=job_id,
            request=request,
            model_role=request.model_role,
            parent_artifact_id=self.artifact_id,
            parent_version=self.version,
            content=self.content if content is None else content,
            content_ref=self.content_ref if content_ref is None else content_ref,
            metadata=dict(self.metadata) if metadata is None else dict(metadata),
        )


def note_to_artifact(
    note: ObsidianNote, *, job_id: str, request: GenerationRequest
) -> Artifact:
    """Adapt an existing vault note into an artifact row (additive, no rewrite).

    The vault note itself is untouched; this only expresses it as
    ``Artifact(kind=NOTE)`` so future note generation can record lineage
    without changing V1.1.0 note behavior.
    """

    return Artifact.create(
        kind=ArtifactKind.NOTE,
        title=note.title,
        job_id=job_id,
        request=request,
        content=note.markdown,
        metadata={"filename": note.filename, "source_type": note.source_type},
    )
