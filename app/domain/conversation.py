"""Domain models for V2.1-A conversations.

A conversation is the session: continuing means appending messages to the
same conversation. Messages are immutable once stored — corrections are new
messages, which keeps future (V2.1-B) memory provenance traceable. No
long-term memory entities live here; this milestone stores history only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_MESSAGE_CHARS = 8000


class ConversationStatus(StrEnum):
    """Lifecycle state of a conversation."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class MessageRole(StrEnum):
    """Who produced a message. Clients may only submit ``user`` messages."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class EvidenceCitation(BaseModel):
    """One retrieved-evidence link snapshot stored on an assistant message."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    number: int = Field(ge=1)
    source: str
    chunk_id: str | None = None
    chunk_index: int | None = Field(default=None, ge=0)

    @field_validator("source")
    @classmethod
    def _validate_source(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Citation source must not be empty.")
        return cleaned

    @field_validator("chunk_id", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value


class EvidenceSnapshot(BaseModel):
    """Compact evidence behind one assistant message, for future provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = ""
    outcome: str = ""
    citations: tuple[EvidenceCitation, ...] = ()
    error: str | None = None

    @field_validator("error", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value


class Conversation(BaseModel):
    """One conversation thread. Immutable value object; stores mutate rows."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    status: ConversationStatus = ConversationStatus.ACTIVE
    message_count: int = Field(default=0, ge=0)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Conversation id must not be empty.")
        return cleaned

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Conversation title must not be empty.")
        return cleaned

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

    @classmethod
    def create(cls, title: str) -> Conversation:
        """Create a new active conversation with a generated id."""

        now = datetime.now(UTC)
        return cls(
            id=uuid4().hex,
            title=title,
            created_at=now,
            updated_at=now,
        )


class Message(BaseModel):
    """One immutable message in a conversation. Sequence is server-assigned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    conversation_id: str
    role: MessageRole
    content: str
    created_at: datetime
    seq: int = Field(ge=1)
    model: str | None = None
    evidence: EvidenceSnapshot | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("id", "conversation_id")
    @classmethod
    def _validate_ids(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message identifiers must not be empty.")
        return cleaned

    @field_validator("content")
    @classmethod
    def _validate_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message content must not be empty.")
        if len(cleaned) > MAX_MESSAGE_CHARS:
            raise ValueError(
                f"Message content must be at most {MAX_MESSAGE_CHARS} characters."
            )
        return cleaned

    @field_validator("model", mode="before")
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

    @classmethod
    def create(
        cls,
        conversation_id: str,
        role: MessageRole,
        content: str,
        seq: int,
        *,
        model: str | None = None,
        evidence: EvidenceSnapshot | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Message:
        """Create a message with a generated id; ``seq`` comes from the store."""

        return cls(
            id=uuid4().hex,
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=datetime.now(UTC),
            seq=seq,
            model=model,
            evidence=evidence,
            metadata=dict(metadata or {}),
        )
