"""Domain tests for V2.1-B1 memory models (candidate, memory, review)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.conversation import EvidenceSnapshot
from app.domain.memory import (
    MAX_MEMORY_CHARS,
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


def _grounding(**overrides: object) -> MemoryGrounding:
    values: dict[str, Any] = {
        "conversation_id": "conv-1",
        "message_id": "msg-1",
        "seq": 3,
        "quoted_text": "I prefer dark mode everywhere.",
    }
    values.update(overrides)
    return MemoryGrounding(**values)


def _candidate(**overrides: object) -> MemoryCandidate:
    grounding = _grounding()
    values: dict[str, Any] = {
        "id": "cand-1",
        "text": "User prefers dark mode.",
        "category": MemoryCategory.PREFERENCE,
        "confidence": 0.9,
        "conversation_id": grounding.conversation_id,
        "message_id": grounding.message_id,
        "seq": grounding.seq,
        "extracted_at": datetime.now(UTC),
        "grounding": grounding,
    }
    values.update(overrides)
    return MemoryCandidate(**values)


def _review(
    decision: ReviewDecision = ReviewDecision.APPROVED, **overrides: object
) -> MemoryReview:
    values: dict[str, Any] = {"decision": decision, "reviewed_at": datetime.now(UTC)}
    values.update(overrides)
    return MemoryReview(**values)


def _source() -> MemorySource:
    return MemorySource(
        conversation_id="conv-1",
        message_id="msg-1",
        seq=3,
        grounding=_grounding(),
    )


# ── A. Candidate creation ─────────────────────────────────────────────


def test_valid_candidate() -> None:
    candidate = _candidate()

    assert candidate.status is CandidateStatus.PENDING
    assert candidate.review is None
    assert candidate.text == "User prefers dark mode."


def test_candidate_rejects_empty_and_blank_text() -> None:
    with pytest.raises(ValidationError):
        _candidate(text="")
    with pytest.raises(ValidationError):
        _candidate(text="   \n  ")


def test_candidate_rejects_oversize_text() -> None:
    with pytest.raises(ValidationError):
        _candidate(text="x" * (MAX_MEMORY_CHARS + 1))
    assert _candidate(text="x" * MAX_MEMORY_CHARS).text == "x" * MAX_MEMORY_CHARS


def test_candidate_rejects_invalid_category() -> None:
    with pytest.raises(ValidationError):
        _candidate(category="vibe")  # type: ignore[arg-type]


def test_candidate_rejects_invalid_confidence() -> None:
    for bad in (-0.1, 1.5, float("nan"), float("inf"), True, "high"):
        with pytest.raises(ValidationError):
            _candidate(confidence=bad)
    assert _candidate(confidence=0).confidence == 0.0
    assert _candidate(confidence=1).confidence == 1.0


def test_propose_factory() -> None:
    first = MemoryCandidate.propose(
        "  User  likes  tea. ",
        MemoryCategory.PREFERENCE,
        0.8,
        _grounding(),
    )
    second = MemoryCandidate.propose(
        "User likes tea.", MemoryCategory.PREFERENCE, 0.8, _grounding()
    )

    assert first.text == "User likes tea."
    assert first.status is CandidateStatus.PENDING
    assert first.id != second.id


# ── B. Grounding ──────────────────────────────────────────────────────


def test_valid_grounding() -> None:
    grounding = _grounding()

    assert grounding.seq == 3
    assert grounding.quoted_text == "I prefer dark mode everywhere."


def test_grounding_rejects_missing_identifiers() -> None:
    with pytest.raises(ValidationError):
        _grounding(conversation_id="  ")
    with pytest.raises(ValidationError):
        _grounding(message_id="")
    with pytest.raises(ValidationError):
        _grounding(seq=0)
    with pytest.raises(ValidationError):
        _grounding(quoted_text="   ")


def test_candidate_grounding_must_match_source_message() -> None:
    with pytest.raises(ValidationError):
        _candidate(message_id="msg-2")
    with pytest.raises(ValidationError):
        _candidate(seq=4)
    with pytest.raises(ValidationError):
        _candidate(conversation_id="conv-2")


def test_evidence_snapshot_is_optional_not_grounding() -> None:
    without = _candidate()
    with_evidence = _candidate(evidence=EvidenceSnapshot(model="qwen3:8b"))

    assert without.evidence is None
    assert with_evidence.evidence is not None
    assert with_evidence.grounding.quoted_text == without.grounding.quoted_text


# ── C. Review ─────────────────────────────────────────────────────────


def test_approved_review() -> None:
    review = _review(ReviewDecision.APPROVED)

    assert review.decision is ReviewDecision.APPROVED
    assert review.reason is None
    assert review.edited is False


def test_rejected_review_requires_reason() -> None:
    with pytest.raises(ValidationError):
        _review(ReviewDecision.REJECTED)
    assert _review(ReviewDecision.REJECTED, reason="transient").reason == "transient"


def test_edited_review_requires_edited_text() -> None:
    with pytest.raises(ValidationError):
        _review(ReviewDecision.APPROVED, edited=True)
    review = _review(ReviewDecision.APPROVED, edited=True, edited_text="Fixed text.")
    assert review.edited_text == "Fixed text."
    with pytest.raises(ValidationError):
        _review(ReviewDecision.APPROVED, edited=False, edited_text="Fixed text.")


def test_review_requires_timestamp() -> None:
    with pytest.raises(ValidationError):
        MemoryReview(decision=ReviewDecision.APPROVED)  # type: ignore[call-arg]


# ── D. Candidate lifecycle ────────────────────────────────────────────


def _decided(status: CandidateStatus, review: MemoryReview) -> MemoryCandidate:
    return _candidate(status=status, review=review)


def test_pending_valid_without_review() -> None:
    assert _candidate().status is CandidateStatus.PENDING


def test_approved_rejected_superseded_require_matching_review() -> None:
    assert (
        _decided(CandidateStatus.APPROVED, _review(ReviewDecision.APPROVED)).status
        is CandidateStatus.APPROVED
    )
    assert (
        _decided(
            CandidateStatus.REJECTED, _review(ReviewDecision.REJECTED, reason="nope")
        ).status
        is CandidateStatus.REJECTED
    )
    assert (
        _decided(CandidateStatus.SUPERSEDED, _review(ReviewDecision.APPROVED)).status
        is CandidateStatus.SUPERSEDED
    )


def test_pending_with_review_rejected() -> None:
    with pytest.raises(ValidationError):
        _candidate(status=CandidateStatus.PENDING, review=_review())


def test_decided_without_review_rejected() -> None:
    with pytest.raises(ValidationError):
        _candidate(status=CandidateStatus.APPROVED)
    with pytest.raises(ValidationError):
        _candidate(status=CandidateStatus.REJECTED)


def test_mismatched_status_and_decision_rejected() -> None:
    with pytest.raises(ValidationError):
        _decided(CandidateStatus.APPROVED, _review(ReviewDecision.REJECTED, reason="x"))
    with pytest.raises(ValidationError):
        _decided(CandidateStatus.REJECTED, _review(ReviewDecision.APPROVED))
    with pytest.raises(ValidationError):
        _decided(CandidateStatus.SUPERSEDED, _review(ReviewDecision.REJECTED, reason="x"))


def test_rejected_without_reason_rejected() -> None:
    with pytest.raises(ValidationError):
        MemoryReview(decision=ReviewDecision.REJECTED, reviewed_at=datetime.now(UTC))


def test_pending_edit_keeps_pending_status() -> None:
    candidate = _candidate(edited_text="User prefers dark mode everywhere.")

    assert candidate.status is CandidateStatus.PENDING
    assert candidate.review is None
    assert candidate.edited_text == "User prefers dark mode everywhere."


# ── E. Memory ─────────────────────────────────────────────────────────


def _memory(**overrides: object) -> Memory:
    values: dict[str, Any] = {
        "id": "mem-v1",
        "logical_id": "mem-logical",
        "version": 1,
        "text": "User prefers dark mode.",
        "category": MemoryCategory.PREFERENCE,
        "confidence_at_approval": 0.9,
        "source": _source(),
        "approved_at": datetime.now(UTC),
    }
    values.update(overrides)
    return Memory(**values)


def test_valid_memory_version_1() -> None:
    memory = _memory()

    assert memory.version == 1
    assert memory.status is MemoryStatus.ACTIVE
    assert memory.source.message_id == "msg-1"


def test_memory_version_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _memory(version=0)


def test_memory_rejects_empty_and_oversize_text() -> None:
    with pytest.raises(ValidationError):
        _memory(text="  ")
    with pytest.raises(ValidationError):
        _memory(text="x" * (MAX_MEMORY_CHARS + 1))


def test_memory_valid_categories_and_statuses() -> None:
    for category in MemoryCategory:
        assert _memory(category=category).category is category
    for status in MemoryStatus:
        assert _memory(status=status).status is status


def test_memory_source_required_and_consistent() -> None:
    with pytest.raises(ValidationError):
        Memory(
            id="m",
            logical_id="l",
            version=1,
            text="t",
            category=MemoryCategory.FACT,
            confidence_at_approval=0.5,
            source=None,  # type: ignore[arg-type]
            approved_at=datetime.now(UTC),
        )
    bad_grounding = _grounding(message_id="msg-9")
    with pytest.raises(ValidationError):
        MemorySource(
            conversation_id="conv-1",
            message_id="msg-9",
            seq=3,
            grounding=_grounding(),
        )
    assert bad_grounding.message_id == "msg-9"


def test_memory_create_factory() -> None:
    first = Memory.create("User prefers dark mode.", MemoryCategory.PREFERENCE, 0.9, _source())
    second = Memory.create("User prefers dark mode.", MemoryCategory.PREFERENCE, 0.9, _source())

    assert first.version == 1
    assert first.logical_id == first.id
    assert first.id != second.id
    assert first.logical_id != second.logical_id


# ── F. Version identity ───────────────────────────────────────────────


def test_version_identity_stable_across_versions() -> None:
    first = Memory.create("v1 text.", MemoryCategory.FACT, 0.7, _source())
    second = Memory.create(
        "v2 text.",
        MemoryCategory.FACT,
        0.8,
        _source(),
        logical_id=first.logical_id,
        version=2,
        supersedes_id=first.id,
    )

    assert second.logical_id == first.logical_id
    assert second.id != first.id
    assert second.version == 2
    assert second.supersedes_id == first.id
    assert first.text == "v1 text."
    assert first.status is MemoryStatus.ACTIVE


def test_models_are_immutable() -> None:
    candidate = _candidate()
    with pytest.raises(ValidationError):
        candidate.text = "changed"  # type: ignore[misc]
    memory = _memory()
    with pytest.raises(ValidationError):
        memory.status = MemoryStatus.SUPERSEDED  # type: ignore[misc]


# ── G. Serialization ──────────────────────────────────────────────────


def test_round_trip_candidate_memory_grounding_source_review() -> None:
    candidate = _decided(
        CandidateStatus.APPROVED, _review(ReviewDecision.APPROVED)
    )
    memory = _memory()

    assert MemoryCandidate.model_validate_json(candidate.model_dump_json()) == candidate
    assert Memory.model_validate_json(memory.model_dump_json()) == memory
    assert (
        MemoryGrounding.model_validate_json(candidate.grounding.model_dump_json())
        == candidate.grounding
    )
    assert MemorySource.model_validate_json(memory.source.model_dump_json()) == memory.source
    assert (
        MemoryReview.model_validate_json(candidate.review.model_dump_json())  # type: ignore[union-attr]
        == candidate.review
    )


# ── H. Security/integrity ─────────────────────────────────────────────


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        _candidate(extra="x")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        _memory(extra="x")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        _grounding(extra="x")  # type: ignore[call-arg]


def test_invalid_categories_rejected_everywhere() -> None:
    with pytest.raises(ValidationError):
        _candidate(category="mood")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        _memory(category="mood")  # type: ignore[arg-type]


# ── I. Tombstone deferral ─────────────────────────────────────────────


def test_only_approved_memory_statuses_accepted() -> None:
    assert set(MemoryStatus) == {MemoryStatus.ACTIVE, MemoryStatus.SUPERSEDED}
    with pytest.raises(ValidationError):
        _memory(status="tombstoned")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        _memory(status="deleted")  # type: ignore[arg-type]
