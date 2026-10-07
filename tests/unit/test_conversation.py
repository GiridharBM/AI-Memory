"""Domain tests for V2.1-A conversation models."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.conversation import (
    MAX_MESSAGE_CHARS,
    Conversation,
    ConversationStatus,
    EvidenceCitation,
    EvidenceSnapshot,
    Message,
    MessageRole,
)


def test_conversation_create() -> None:
    first = Conversation.create("  My   chat ")
    second = Conversation.create("My chat")

    assert first.title == "My chat"
    assert first.status is ConversationStatus.ACTIVE
    assert first.message_count == 0
    assert first.id != second.id
    assert first.created_at <= first.updated_at


def test_conversation_rejects_blank_title() -> None:
    with pytest.raises(ValidationError):
        Conversation.create("   ")


def test_conversation_rejects_blank_id() -> None:
    base: dict[str, Any] = {
        "id": "  ",
        "title": "t",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    with pytest.raises(ValidationError):
        Conversation(**base)


def test_conversation_metadata_strict() -> None:
    base: dict[str, Any] = {
        "id": "a",
        "title": "t",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    with pytest.raises(ValidationError):
        Conversation(**base, metadata={"": "x"})
    bad_metadata: dict[str, Any] = {"k": 5}
    with pytest.raises(ValidationError):
        Conversation(**base, metadata=bad_metadata)
    assert Conversation(**base, metadata={" k ": "v"}).metadata == {"k": "v"}


def test_message_create_and_roles() -> None:
    message = Message.create("conv-1", MessageRole.USER, "  hello ", 3)

    assert message.conversation_id == "conv-1"
    assert message.role is MessageRole.USER
    assert message.content == "hello"
    assert message.seq == 3
    assert message.model is None
    assert message.evidence is None
    for role in (MessageRole.USER, MessageRole.ASSISTANT, MessageRole.SYSTEM):
        assert Message.create("c", role, "x", 1).role is role


def test_message_rejects_invalid_role() -> None:
    with pytest.raises(ValidationError):
        Message.create("c", "tool", "x", 1)  # type: ignore[arg-type]


def test_message_rejects_empty_content() -> None:
    with pytest.raises(ValidationError):
        Message.create("c", MessageRole.USER, "   ", 1)


def test_message_rejects_oversize_content() -> None:
    with pytest.raises(ValidationError):
        Message.create("c", MessageRole.USER, "x" * (MAX_MESSAGE_CHARS + 1), 1)
    assert (
        Message.create("c", MessageRole.USER, "x" * MAX_MESSAGE_CHARS, 1).content
        == "x" * MAX_MESSAGE_CHARS
    )


def test_message_seq_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Message.create("c", MessageRole.USER, "x", 0)


def test_models_are_frozen_and_forbid_extra() -> None:
    conversation = Conversation.create("t")
    with pytest.raises(ValidationError):
        conversation.title = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        Message.create("c", MessageRole.USER, "x", 1).content = "y"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        Conversation(
            id="a",
            title="t",
            created_at="2026-01-01T00:00:00Z",  # type: ignore[arg-type]
            updated_at="2026-01-01T00:00:00Z",  # type: ignore[arg-type]
            unknown="x",  # type: ignore[call-arg]
        )


def test_evidence_snapshot_and_citations() -> None:
    snapshot = EvidenceSnapshot(
        model="qwen3:8b",
        outcome="answered",
        citations=(EvidenceCitation(number=1, source="a.md", chunk_id="a.md::0"),),
    )
    message = Message.create(
        "c", MessageRole.ASSISTANT, "answer", 2, model="qwen3:8b", evidence=snapshot
    )

    assert message.evidence is not None
    assert message.evidence.citations[0].source == "a.md"
    assert EvidenceSnapshot().citations == ()
    assert EvidenceSnapshot(error="  ").error is None
    with pytest.raises(ValidationError):
        EvidenceCitation(number=0, source="a.md")
    with pytest.raises(ValidationError):
        EvidenceCitation(number=1, source="  ")


def test_serialization_round_trip() -> None:
    conversation = Conversation.create("t")
    message = Message.create("c", MessageRole.USER, "x", 1)

    assert Conversation.model_validate_json(conversation.model_dump_json()) == conversation
    assert Message.model_validate_json(message.model_dump_json()) == message


def test_archive_state_is_a_field_not_a_type() -> None:
    conversation = Conversation.create("t")
    archived = conversation.model_copy(
        update={"status": ConversationStatus.ARCHIVED}
    )

    assert archived.status is ConversationStatus.ARCHIVED
    assert conversation.status is ConversationStatus.ACTIVE
