"""Domain models for V2.1-B memory candidates and approved memories.

A ``MemoryCandidate`` is a proposed long-term memory awaiting human review;
a ``Memory`` is a durable, versioned record created only by approving a
candidate. Versions are immutable — supersession creates a new version under
the same ``logical_id``; history is never rewritten. No persistence,
extraction, or application logic lives here.
"""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.conversation import EvidenceSnapshot

MAX_MEMORY_CHARS = 2000


class MemoryCategory(StrEnum):
    """What kind of durable fact a memory records."""

    FACT = "fact"
    PREFERENCE = "preference"
    GOAL = "goal"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    PROJECT = "project"
    CORRECTION = "correction"


class CandidateStatus(StrEnum):
    """Lifecycle state of a memory candidate."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class MemoryStatus(StrEnum):
    """Lifecycle state of an approved memory version.

    Tombstones are deliberately deferred: supersession covers replacement,
    and no unreachable state is introduced.
    """

    ACTIVE = "active"
    SUPERSEDED = "superseded"


class ReviewDecision(StrEnum):
    """Human review outcome for a candidate."""

    APPROVED = "approved"
    REJECTED = "rejected"


def _clean_text(value: str, *, field_name: str, max_chars: int = MAX_MEMORY_CHARS) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError(f"Memory {field_name} must not be empty.")
    if len(cleaned) > max_chars:
        raise ValueError(f"Memory {field_name} must be at most {max_chars} characters.")
    return cleaned


def _clean_id(value: str, *, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"Memory {field_name} must not be empty.")
    return cleaned


def _clean_confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Memory confidence must be a number.")
    confidence = float(value)
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise ValueError("Memory confidence must be between 0.0 and 1.0.")
    return confidence


class MemoryGrounding(BaseModel):
    """Why PAM believes the user said the memory: the exact user-origin span.

    Distinct from supporting QA evidence: grounding identifies the utterance,
    evidence (where present) corroborates it. A candidate is never properly
    grounded by an ``EvidenceSnapshot`` alone.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: str
    message_id: str
    seq: int = Field(ge=1)
    quoted_text: str

    @field_validator("conversation_id")
    @classmethod
    def _validate_conversation_id(cls, value: str) -> str:
        return _clean_id(value, field_name="conversation id")

    @field_validator("message_id")
    @classmethod
    def _validate_message_id(cls, value: str) -> str:
        return _clean_id(value, field_name="message id")

    @field_validator("quoted_text")
    @classmethod
    def _validate_quoted_text(cls, value: str) -> str:
        return _clean_text(value, field_name="quoted text")


class MemorySource(BaseModel):
    """Provenance link from an approved memory to its origin."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: str
    message_id: str
    seq: int = Field(ge=1)
    grounding: MemoryGrounding
    evidence: EvidenceSnapshot | None = None

    @field_validator("conversation_id")
    @classmethod
    def _validate_conversation_id(cls, value: str) -> str:
        return _clean_id(value, field_name="conversation id")

    @field_validator("message_id")
    @classmethod
    def _validate_message_id(cls, value: str) -> str:
        return _clean_id(value, field_name="message id")

    @model_validator(mode="after")
    def _validate_grounding_consistency(self) -> MemorySource:
        grounding = self.grounding
        if (
            grounding.conversation_id != self.conversation_id
            or grounding.message_id != self.message_id
            or grounding.seq != self.seq
        ):
            raise ValueError(
                "Memory grounding must identify the same conversation message "
                "as its source."
            )
        return self


class MemoryReview(BaseModel):
    """Human review metadata attached to a decided candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: ReviewDecision
    reviewed_at: datetime
    reason: str | None = None
    edited: bool = False
    edited_text: str | None = None

    @field_validator("reason", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @field_validator("edited_text", mode="before")
    @classmethod
    def _clean_edited_text(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Review edited text must be a string.")
        return _clean_text(value, field_name="edited text")

    @model_validator(mode="after")
    def _validate_review_coherence(self) -> MemoryReview:
        if self.decision is ReviewDecision.REJECTED and self.reason is None:
            raise ValueError("A rejected candidate requires a reason.")
        if self.edited != (self.edited_text is not None):
            raise ValueError(
                "Review 'edited' must be true exactly when edited text is present."
            )
        return self


class MemoryCandidate(BaseModel):
    """A proposed long-term memory awaiting human review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    text: str
    category: MemoryCategory
    confidence: float
    conversation_id: str
    message_id: str
    seq: int = Field(ge=1)
    extracted_at: datetime
    grounding: MemoryGrounding
    evidence: EvidenceSnapshot | None = None
    status: CandidateStatus = CandidateStatus.PENDING
    review: MemoryReview | None = None
    edited_text: str | None = None
    supersedes_id: str | None = None

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return _clean_id(value, field_name="candidate id")

    @field_validator("text")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _clean_text(value, field_name="candidate text")

    @field_validator("confidence", mode="before")
    @classmethod
    def _validate_confidence(cls, value: object) -> float:
        return _clean_confidence(value)

    @field_validator("conversation_id")
    @classmethod
    def _validate_conversation_id(cls, value: str) -> str:
        return _clean_id(value, field_name="conversation id")

    @field_validator("message_id")
    @classmethod
    def _validate_message_id(cls, value: str) -> str:
        return _clean_id(value, field_name="message id")

    @field_validator("edited_text", "supersedes_id", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @model_validator(mode="after")
    def _validate_lifecycle(self) -> MemoryCandidate:
        if self.status is CandidateStatus.PENDING and self.review is not None:
            raise ValueError("An unreviewed pending candidate must not carry review.")
        if self.status is not CandidateStatus.PENDING and self.review is None:
            raise ValueError("A decided candidate requires review metadata.")
        if self.review is not None:
            expected = (
                ReviewDecision.APPROVED
                if self.status in (CandidateStatus.APPROVED, CandidateStatus.SUPERSEDED)
                else ReviewDecision.REJECTED
            )
            if self.review.decision is not expected:
                raise ValueError(
                    "Candidate status and review decision must agree."
                )
            if self.status is CandidateStatus.REJECTED and self.review.reason is None:
                raise ValueError("A rejected candidate requires a reason.")
        grounding = self.grounding
        if (
            grounding.conversation_id != self.conversation_id
            or grounding.message_id != self.message_id
            or grounding.seq != self.seq
        ):
            raise ValueError(
                "Candidate grounding must identify the candidate's source message."
            )
        return self

    @property
    def content_hash(self) -> str:
        """Deterministic content hash for future duplicate detection.

        Informational only: duplicate/re-extraction policy belongs to the
        future extraction/service layer, not to this model.
        """

        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @classmethod
    def propose(
        cls,
        text: str,
        category: MemoryCategory,
        confidence: float,
        grounding: MemoryGrounding,
        *,
        evidence: EvidenceSnapshot | None = None,
    ) -> MemoryCandidate:
        """Propose a new pending candidate from user-origin grounding."""

        now = datetime.now(UTC)
        return cls(
            id=uuid4().hex,
            text=text,
            category=category,
            confidence=confidence,
            conversation_id=grounding.conversation_id,
            message_id=grounding.message_id,
            seq=grounding.seq,
            extracted_at=now,
            grounding=grounding,
            evidence=evidence,
        )


class Memory(BaseModel):
    """One durable, versioned approved memory. Versions never mutate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    logical_id: str
    version: int = Field(ge=1)
    text: str
    category: MemoryCategory
    confidence_at_approval: float
    source: MemorySource
    approved_at: datetime
    status: MemoryStatus = MemoryStatus.ACTIVE
    supersedes_id: str | None = None

    @field_validator("id", "logical_id")
    @classmethod
    def _validate_ids(cls, value: str) -> str:
        return _clean_id(value, field_name="memory id")

    @field_validator("text")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _clean_text(value, field_name="memory text")

    @field_validator("confidence_at_approval", mode="before")
    @classmethod
    def _validate_confidence(cls, value: object) -> float:
        return _clean_confidence(value)

    @field_validator("supersedes_id", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @classmethod
    def create(
        cls,
        text: str,
        category: MemoryCategory,
        confidence: float,
        source: MemorySource,
        *,
        logical_id: str | None = None,
        version: int = 1,
        supersedes_id: str | None = None,
    ) -> Memory:
        """Create a memory version; ``logical_id`` defaults to the first id."""

        concrete_id = uuid4().hex
        return cls(
            id=concrete_id,
            logical_id=logical_id or concrete_id,
            version=version,
            text=text,
            category=category,
            confidence_at_approval=confidence,
            source=source,
            approved_at=datetime.now(UTC),
            supersedes_id=supersedes_id,
        )
