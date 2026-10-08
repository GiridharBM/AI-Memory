"""Tests for V2.1-C runtime memory context (no LLM, no embeddings)."""

from __future__ import annotations

import itertools
from datetime import UTC, datetime

from app.application.conversation_service import ConversationService
from app.application.memory_context import (
    MemoryMatch,
    build_memory_context,
    memory_match_to_hit,
    retrieve_memories,
    score_memory,
)
from app.application.memory_service import MemoryService
from app.core.config import Settings
from app.domain.memory import (
    CandidateStatus,
    Memory,
    MemoryCandidate,
    MemoryCategory,
    MemoryGrounding,
    MemorySource,
    MemoryStatus,
)
from app.infrastructure.conversations import ConversationStore
from app.infrastructure.memories import CandidateStore, MemoryStore


def _source() -> MemorySource:
    grounding = MemoryGrounding(
        conversation_id="conv-1",
        message_id="msg-1",
        seq=1,
        quoted_text="I prefer dark mode.",
    )
    return MemorySource(
        conversation_id="conv-1",
        message_id="msg-1",
        seq=1,
        grounding=grounding,
    )


_IDS = itertools.count()


def _memory(
    text: str,
    *,
    approved_at: datetime | None = None,
    status: MemoryStatus = MemoryStatus.ACTIVE,
    logical_id: str | None = None,
    version: int = 1,
) -> Memory:
    number = next(_IDS)
    return Memory(
        id=f"mem-test-{number}",
        logical_id=logical_id or f"logical-test-{number}",
        version=version,
        text=text,
        category=MemoryCategory.PREFERENCE,
        confidence_at_approval=0.9,
        source=_source(),
        approved_at=approved_at or datetime.now(UTC),
        status=status,
    )


def _service(tmp_settings: Settings) -> MemoryService:
    root = tmp_settings.paths.manifest_root
    conversations = ConversationService(ConversationStore(root))

    def _no_llm(*args: object) -> object:
        raise AssertionError("runtime context must not call the model")

    return MemoryService(CandidateStore(root), MemoryStore(root), conversations, _no_llm)  # type: ignore[arg-type]


class TestScoreMemory:
    def test_exact_match_scores_one(self) -> None:
        memory = _memory("User prefers dark mode.")

        assert score_memory("User prefers dark mode.", memory) == 1.0

    def test_partial_overlap_is_proportional(self) -> None:
        memory = _memory("User prefers dark mode.")

        assert score_memory("dark mode", memory) == 2 / 2
        assert score_memory("dark mode extra words here", memory) == 2 / 5

    def test_no_overlap_scores_zero(self) -> None:
        memory = _memory("User prefers dark mode.")

        assert score_memory("completely unrelated question", memory) == 0.0

    def test_normalization_is_case_and_punctuation_insensitive(self) -> None:
        memory = _memory("User prefers DARK mode!")

        assert score_memory("user prefers dark mode", memory) == 1.0
        assert score_memory("  USER   prefers\tdark\nmode ", memory) == 1.0

    def test_empty_question_scores_zero(self) -> None:
        memory = _memory("User prefers dark mode.")

        assert score_memory("", memory) == 0.0
        assert score_memory("   ", memory) == 0.0


class TestActiveMemories:
    def test_store_returns_only_active(self, tmp_settings: Settings) -> None:
        store = MemoryStore(tmp_settings.paths.manifest_root)
        active = _memory("User prefers dark mode.")
        old = _memory(
            "User prefers light mode.",
            status=MemoryStatus.SUPERSEDED,
            logical_id="logical-other",
        )
        store.save(active)
        store.save(old)

        assert store.active_memories() == [active]

    def test_store_active_ordering_is_deterministic(self, tmp_settings: Settings) -> None:
        store = MemoryStore(tmp_settings.paths.manifest_root)
        first = _memory(
            "First memory text here.",
            approved_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        second = _memory(
            "Second memory text here.",
            approved_at=datetime(2026, 2, 1, tzinfo=UTC),
        )
        store.save(second)
        store.save(first)

        assert store.active_memories() == [first, second]

    def test_store_active_empty_when_nothing_approved(self, tmp_settings: Settings) -> None:
        assert MemoryStore(tmp_settings.paths.manifest_root).active_memories() == []

    def test_service_delegates_active_only(self, tmp_settings: Settings) -> None:
        service = _service(tmp_settings)
        active = _memory("User prefers dark mode.")
        old = _memory(
            "User prefers light mode.",
            status=MemoryStatus.SUPERSEDED,
            logical_id="logical-other",
        )
        service._memories.save(active)
        service._memories.save(old)

        assert service.active_memories() == [active]

    def test_rejected_candidate_is_unavailable(self, tmp_settings: Settings) -> None:
        service = _service(tmp_settings)
        candidate = MemoryCandidate.propose(
            "User prefers dark mode.",
            MemoryCategory.PREFERENCE,
            0.9,
            MemoryGrounding(
                conversation_id="conv-1",
                message_id="msg-1",
                seq=1,
                quoted_text="I prefer dark mode.",
            ),
        )
        service._candidates.save(candidate)
        service.reject(candidate.id, "not durable")

        store = MemoryStore(tmp_settings.paths.manifest_root)
        assert store.active_memories() == []
        assert retrieve_memories("dark mode?", store) == []
        assert service._candidates.get(candidate.id) is not None
        assert service._candidates.get(candidate.id).status is CandidateStatus.REJECTED


class TestRetrieveMemories:
    def test_active_memory_returned_above_threshold(self, tmp_settings: Settings) -> None:
        store = MemoryStore(tmp_settings.paths.manifest_root)
        store.save(_memory("User prefers dark mode."))

        matches = retrieve_memories("Does the user prefers dark mode?", store)

        assert len(matches) == 1
        assert matches[0].score >= 0.5

    def test_below_threshold_discarded(self, tmp_settings: Settings) -> None:
        store = MemoryStore(tmp_settings.paths.manifest_root)
        store.save(_memory("User prefers dark mode."))

        assert retrieve_memories("What is the capital of France?", store) == []

    def test_threshold_boundary_is_inclusive(self, tmp_settings: Settings) -> None:
        store = MemoryStore(tmp_settings.paths.manifest_root)
        store.save(_memory("alpha beta gamma delta"))

        # Exactly 2/4 question tokens overlap -> score 0.5 == threshold.
        matches = retrieve_memories("alpha beta other words", store)

        assert [match.score for match in matches] == [0.5]

    def test_limit_of_three(self, tmp_settings: Settings) -> None:
        store = MemoryStore(tmp_settings.paths.manifest_root)
        for index in range(5):
            store.save(_memory(f"shared tokens memory number {index}"))

        matches = retrieve_memories("shared tokens memory number", store)

        assert len(matches) == 3

    def test_ordering_score_then_approval_then_id(self, tmp_settings: Settings) -> None:
        store = MemoryStore(tmp_settings.paths.manifest_root)
        weaker = _memory(
            "dark mode",
            approved_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        stronger = _memory(
            "User prefers dark mode always.",
            approved_at=datetime(2026, 3, 1, tzinfo=UTC),
        )
        store.save(weaker)
        store.save(stronger)

        matches = retrieve_memories("user prefers dark mode", store)

        assert [match.memory.id for match in matches] == [stronger.id, weaker.id]
        assert matches[0].score >= matches[1].score

    def test_tie_break_is_deterministic(self, tmp_settings: Settings) -> None:
        store = MemoryStore(tmp_settings.paths.manifest_root)
        moment = datetime(2026, 1, 1, tzinfo=UTC)
        first = _memory("same text here", approved_at=moment)
        second = Memory(
            id="mem-aaa-second",
            logical_id="logical-second",
            version=1,
            text="same text here",
            category=MemoryCategory.PREFERENCE,
            confidence_at_approval=0.9,
            source=_source(),
            approved_at=moment,
        )
        store.save(second)
        store.save(first)

        matches = retrieve_memories("same text here", store)

        assert [match.memory.id for match in matches] == sorted(
            [first.id, second.id]
        )

    def test_empty_store_returns_empty(self, tmp_settings: Settings) -> None:
        store = MemoryStore(tmp_settings.paths.manifest_root)

        assert retrieve_memories("dark mode?", store) == []

    def test_empty_question_returns_empty(self, tmp_settings: Settings) -> None:
        store = MemoryStore(tmp_settings.paths.manifest_root)
        store.save(_memory("User prefers dark mode."))

        assert retrieve_memories("", store) == []
        assert retrieve_memories("   ", store) == []

    def test_superseded_memory_excluded(self, tmp_settings: Settings) -> None:
        store = MemoryStore(tmp_settings.paths.manifest_root)
        store.save(
            _memory(
                "User prefers dark mode.",
                status=MemoryStatus.SUPERSEDED,
            )
        )

        assert retrieve_memories("dark mode?", store) == []


class TestBuildMemoryContext:
    def test_empty_matches_produce_empty_context(self) -> None:
        assert build_memory_context([], start_number=1, max_chars=12_000) == ""

    def test_block_carries_provenance(self, tmp_settings: Settings) -> None:
        store = MemoryStore(tmp_settings.paths.manifest_root)
        memory = _memory("User prefers dark mode.")
        store.save(memory)

        (match,) = retrieve_memories("dark mode?", store)
        section = build_memory_context([match], start_number=4, max_chars=12_000)

        assert "[SOURCE 4]" in section
        assert f"memory:{memory.logical_id}@v{memory.version}" in section
        assert "preference" in section
        assert "User prefers dark mode." in section
        assert "I prefer dark mode." in section
        assert "conv-1" in section
        assert "USER-CONFIRMED PERSONAL FACTS" in section

    def test_numbering_continues_after_documents(self) -> None:
        match = MemoryMatch(memory=_memory("User prefers dark mode."), score=1.0)

        section = build_memory_context([match], start_number=3, max_chars=12_000)

        assert "[SOURCE 3]" in section

    def test_budget_is_enforced(self) -> None:
        match = MemoryMatch(memory=_memory("User prefers dark mode."), score=1.0)

        assert build_memory_context([match], start_number=1, max_chars=0) == ""
        assert build_memory_context([match], start_number=1, max_chars=10) == ""

    def test_match_to_hit_encodes_provenance(self) -> None:
        memory = _memory("User prefers dark mode.")
        hit = memory_match_to_hit(MemoryMatch(memory=memory, score=0.75))

        assert hit.source == f"memory:{memory.logical_id}@v{memory.version}"
        assert hit.entry_id == memory.id
        assert hit.score == 0.75
        # No document-retrieval leg produced this hit; gates never see it.
        assert hit.cosine_score == 0.0
        assert hit.bm25_score == 0.0
