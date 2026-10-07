"""Lifecycle tests: approve/reject/edit/supersede with version integrity."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.application.conversation_service import ConversationService
from app.application.memory_service import (
    InvalidCandidateStateError,
    MemoryService,
    UnknownCandidateError,
    UnknownMemoryError,
)
from app.domain.conversation import MessageRole
from app.domain.memory import (
    CandidateStatus,
    MemoryCandidate,
    MemoryCategory,
    MemoryGrounding,
    MemorySource,
    MemoryStatus,
)
from app.infrastructure.conversations import ConversationStore
from app.infrastructure.memories import CandidateStore, MemoryStore


def _service(tmp_path: Path) -> tuple[MemoryService, ConversationService]:
    root = tmp_path / "manifests"
    conversations = ConversationService(ConversationStore(root))
    service = MemoryService(
        CandidateStore(root),
        MemoryStore(root),
        conversations,
        lambda system, prompt, model: (_ for _ in ()).throw(
            AssertionError("no model calls expected")
        ),
    )
    return service, conversations


def _pending(
    service: MemoryService,
    conversations: ConversationService,
    text: str = "User likes tea.",
) -> MemoryCandidate:
    conversation = conversations.create_conversation("t")
    user = conversations._store.append_message(conversation.id, MessageRole.USER, text)
    grounding = MemoryGrounding(
        conversation_id=conversation.id,
        message_id=user.id,
        seq=user.seq,
        quoted_text=text,
    )
    from app.domain.memory import MemoryCandidate

    candidate = MemoryCandidate.propose(text, MemoryCategory.PREFERENCE, 0.8, grounding)
    return service._candidates.save(candidate)


def test_approve_pending_creates_memory_v1(tmp_path: Path) -> None:
    service, conversations = _service(tmp_path)
    candidate = _pending(service, conversations)

    memory = service.approve(candidate.id)

    assert memory.version == 1
    assert memory.logical_id == memory.id
    assert memory.text == "User likes tea."
    assert memory.category is MemoryCategory.PREFERENCE
    assert memory.confidence_at_approval == 0.8
    assert memory.status is MemoryStatus.ACTIVE
    assert memory.source.message_id == candidate.message_id
    assert memory.source.grounding.quoted_text == "User likes tea."
    stored = service.get_candidate(candidate.id)
    assert stored.status is CandidateStatus.APPROVED
    assert stored.review is not None
    assert stored.review.decision.value == "approved"


def test_approve_uses_edited_text(tmp_path: Path) -> None:
    service, conversations = _service(tmp_path)
    candidate = _pending(service, conversations)

    memory = service.approve(candidate.id, edited_text="  User loves tea.  ")

    assert memory.text == "User loves tea."
    stored = service.get_candidate(candidate.id)
    assert stored.review is not None
    assert stored.review.edited is True
    assert stored.review.edited_text == "User loves tea."


def test_approve_rejects_bad_edits(tmp_path: Path) -> None:
    service, conversations = _service(tmp_path)
    candidate = _pending(service, conversations)

    with pytest.raises(InvalidCandidateStateError):
        service.approve(candidate.id, edited_text="   ")
    with pytest.raises(InvalidCandidateStateError):
        service.approve(candidate.id, edited_text="x" * 2001)


def test_approve_non_pending_rejected(tmp_path: Path) -> None:
    service, conversations = _service(tmp_path)
    candidate = _pending(service, conversations)
    service.approve(candidate.id)

    with pytest.raises(InvalidCandidateStateError):
        service.approve(candidate.id)
    with pytest.raises(UnknownCandidateError):
        service.approve("ghost")


def test_reject_pending_requires_reason(tmp_path: Path) -> None:
    service, conversations = _service(tmp_path)
    candidate = _pending(service, conversations)

    rejected = service.reject(candidate.id, "transient chatter")

    assert rejected.status is CandidateStatus.REJECTED
    assert rejected.review is not None
    assert rejected.review.reason == "transient chatter"
    with pytest.raises(InvalidCandidateStateError):
        service.reject(candidate.id, "again")
    with pytest.raises(UnknownCandidateError):
        service.reject("ghost", "reason")


def test_reject_empty_reason_rejected(tmp_path: Path) -> None:
    service, conversations = _service(tmp_path)
    candidate = _pending(service, conversations)

    with pytest.raises(InvalidCandidateStateError):
        service.reject(candidate.id, "   ")


def test_rejected_candidate_cannot_be_approved(tmp_path: Path) -> None:
    service, conversations = _service(tmp_path)
    candidate = _pending(service, conversations)
    service.reject(candidate.id, "nope")

    with pytest.raises(InvalidCandidateStateError):
        service.approve(candidate.id)


def test_edit_pending_candidate(tmp_path: Path) -> None:
    service, conversations = _service(tmp_path)
    candidate = _pending(service, conversations)

    edited = service.edit_candidate(candidate.id, "  User adores tea. ")

    assert edited.status is CandidateStatus.PENDING
    assert edited.review is None
    assert edited.edited_text == "User adores tea."
    with pytest.raises(InvalidCandidateStateError):
        service.edit_candidate(candidate.id, "x" * 2001)
    with pytest.raises(UnknownCandidateError):
        service.edit_candidate("ghost", "x")


def test_edit_approved_candidate_rejected(tmp_path: Path) -> None:
    service, conversations = _service(tmp_path)
    candidate = _pending(service, conversations)
    service.approve(candidate.id)

    with pytest.raises(InvalidCandidateStateError):
        service.edit_candidate(candidate.id, "late edit")


def test_candidate_auditable_after_decision(tmp_path: Path) -> None:
    service, conversations = _service(tmp_path)
    first = _pending(service, conversations, text="First claim.")
    second = _pending(service, conversations, text="Second claim.")
    memory = service.approve(first.id)
    service.reject(second.id, "duplicate")

    assert service.get_candidate(first.id).status is CandidateStatus.APPROVED
    assert service.get_candidate(second.id).status is CandidateStatus.REJECTED
    assert service.get_candidate(first.id).text == "First claim."
    assert service.get_memory(memory.id).text == "First claim."


def test_supersede_creates_version_2(tmp_path: Path) -> None:
    service, conversations = _service(tmp_path)
    candidate = _pending(service, conversations)
    first = service.approve(candidate.id)

    second = service.supersede(
        first.logical_id,
        "User loves tea.",
        category=MemoryCategory.PREFERENCE,
        confidence=0.95,
        source=MemorySource(
            conversation_id=first.source.conversation_id,
            message_id=first.source.message_id,
            seq=first.source.seq,
            grounding=first.source.grounding,
        ),
    )

    assert second.logical_id == first.logical_id
    assert second.id != first.id
    assert second.version == 2
    assert second.status is MemoryStatus.ACTIVE
    assert service.get_memory(first.id).status is MemoryStatus.SUPERSEDED
    assert service.get_memory(first.id).text == "User likes tea."
    assert [v.version for v in service.memory_versions(first.logical_id)] == [1, 2]


def test_only_one_active_version_after_supersede(tmp_path: Path) -> None:
    service, conversations = _service(tmp_path)
    candidate = _pending(service, conversations)
    first = service.approve(candidate.id)

    service.supersede(
        first.logical_id,
        "v2",
        category=first.category,
        confidence=0.5,
        source=first.source,
    )

    active = [
        m
        for m in service.memory_versions(first.logical_id)
        if m.status is MemoryStatus.ACTIVE
    ]
    assert len(active) == 1
    assert active[0].version == 2
    third = service.supersede(
        first.logical_id,
        "v3",
        category=first.category,
        confidence=0.5,
        source=first.source,
    )
    assert third.version == 3
    assert [v.version for v in service.memory_versions(first.logical_id)] == [1, 2, 3]
    assert (
        len(
            [
                m
                for m in service.memory_versions(first.logical_id)
                if m.status is MemoryStatus.ACTIVE
            ]
        )
        == 1
    )


def test_supersede_unknown_logical_raises(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    grounding = MemoryGrounding(
        conversation_id="c", message_id="m", seq=1, quoted_text="q"
    )
    with pytest.raises(UnknownMemoryError):
        service.supersede(
            "ghost-logical",
            "text",
            category=MemoryCategory.FACT,
            confidence=0.5,
            source=MemorySource(
                conversation_id="c", message_id="m", seq=1, grounding=grounding
            ),
        )
    with pytest.raises(UnknownMemoryError):
        service.get_memory("ghost")


def test_invalid_lifecycle_transitions_rejected(tmp_path: Path) -> None:
    service, conversations = _service(tmp_path)
    candidate = _pending(service, conversations)
    service.reject(candidate.id, "nope")

    # Rejected cannot move anywhere.
    with pytest.raises(InvalidCandidateStateError):
        service.approve(candidate.id)
    with pytest.raises(InvalidCandidateStateError):
        service.reject(candidate.id, "again")
    with pytest.raises(InvalidCandidateStateError):
        service.edit_candidate(candidate.id, "edit")


def test_restart_preserves_lifecycle_state(tmp_path: Path) -> None:
    service, conversations = _service(tmp_path)
    candidate = _pending(service, conversations)
    memory = service.approve(candidate.id)

    root = tmp_path / "manifests"
    fresh = MemoryService(
        CandidateStore(root),
        MemoryStore(root),
        ConversationService(ConversationStore(root)),
        lambda system, prompt, model: (_ for _ in ()).throw(
            AssertionError("no model calls expected")
        ),
    )

    assert fresh.get_candidate(candidate.id).status is CandidateStatus.APPROVED
    assert fresh.get_memory(memory.id).status is MemoryStatus.ACTIVE
    assert [v.version for v in fresh.memory_versions(memory.logical_id)] == [1]
