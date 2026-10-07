"""Persistence tests for V2.1-B candidates and memories (real files)."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from app.domain.conversation import EvidenceSnapshot
from app.domain.memory import (
    CandidateStatus,
    Memory,
    MemoryCandidate,
    MemoryCategory,
    MemoryGrounding,
    MemorySource,
    MemoryStatus,
    ReviewDecision,
)
from app.infrastructure.memories import CandidateStore, MemoryStore


def _grounding(message_id: str = "msg-1") -> MemoryGrounding:
    return MemoryGrounding(
        conversation_id="conv-1", message_id=message_id, seq=1, quoted_text="quoted"
    )


def _candidate(text: str = "User prefers dark mode.") -> MemoryCandidate:
    return MemoryCandidate.propose(
        text, MemoryCategory.PREFERENCE, 0.9, _grounding()
    )


def _memory(text: str = "User prefers dark mode.") -> Memory:
    return Memory.create(
        text,
        MemoryCategory.PREFERENCE,
        0.9,
        MemorySource(
            conversation_id="conv-1", message_id="msg-1", seq=1, grounding=_grounding()
        ),
    )


def _stores(tmp_path: Path) -> tuple[CandidateStore, MemoryStore]:
    root = tmp_path / "manifests"
    return CandidateStore(root), MemoryStore(root)


def test_save_and_load_candidate(tmp_path: Path) -> None:
    candidates, _ = _stores(tmp_path)
    created = candidates.save(_candidate())

    assert candidates.get(created.id) == created


def test_save_and_load_memory(tmp_path: Path) -> None:
    _, memories = _stores(tmp_path)
    created = memories.save(_memory())

    assert memories.get(created.id) == created


def test_restart_survival(tmp_path: Path) -> None:
    candidates, memories = _stores(tmp_path)
    candidate = candidates.save(_candidate("first"))
    memory = memories.save(_memory("second"))

    fresh_candidates = CandidateStore(tmp_path / "manifests")
    fresh_memories = MemoryStore(tmp_path / "manifests")

    assert fresh_candidates.get(candidate.id) == candidate
    assert fresh_memories.get(memory.id) == memory


def test_deterministic_ordering(tmp_path: Path) -> None:
    candidates, memories = _stores(tmp_path)
    first = candidates.save(_candidate("b-text"))
    second = candidates.save(_candidate("a-text"))
    mem_first = memories.save(_memory("y-text"))
    mem_second = memories.save(_memory("x-text"))

    assert [c.id for c in candidates.list(limit=10)] == [first.id, second.id]
    assert [m.id for m in memories.list(limit=10)] == [mem_first.id, mem_second.id]


def test_corrupt_store_files_start_empty(tmp_path: Path) -> None:
    root = tmp_path / "manifests"
    root.mkdir(parents=True)
    (root / "memory_candidates.json").write_text("not json{{{", encoding="utf-8")
    (root / "memories.json").write_text("[1, 2, 3]", encoding="utf-8")

    candidates, memories = _stores(tmp_path)

    assert candidates.list() == []
    assert memories.list() == []


def test_corrupt_records_skipped_individually(tmp_path: Path) -> None:
    root = tmp_path / "manifests"
    root.mkdir(parents=True)
    good = _candidate("good")
    payload = {
        "version": 1,
        "candidates": [
            good.model_dump(mode="json"),
            {"id": "broken", "text": 5},
            "not-a-dict",
        ],
    }
    (root / "memory_candidates.json").write_text(json.dumps(payload), encoding="utf-8")

    candidates, _ = _stores(tmp_path)

    assert [c.id for c in candidates.list()] == [good.id]


def test_candidate_memory_isolation(tmp_path: Path) -> None:
    candidates, memories = _stores(tmp_path)
    candidates.save(_candidate("c"))
    memories.save(_memory("m"))

    assert candidates.get("nope") is None
    assert memories.get("nope") is None
    assert all(isinstance(c, MemoryCandidate) for c in candidates.list())
    assert all(isinstance(m, Memory) for m in memories.list())


def test_concurrent_saves_keep_all_rows(tmp_path: Path) -> None:
    candidates, memories = _stores(tmp_path)

    def worker(n: int) -> None:
        candidates.save(_candidate(f"cand {n}"))
        memories.save(_memory(f"mem {n}"))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(candidates.list(limit=50)) == 10
    assert len(memories.list(limit=50)) == 10


def test_version_history_survives_restart(tmp_path: Path) -> None:
    _, memories = _stores(tmp_path)
    first = memories.save(_memory("v1"))
    second = Memory.create(
        "v2",
        MemoryCategory.PREFERENCE,
        0.8,
        first.source,
        logical_id=first.logical_id,
        version=2,
        supersedes_id=first.id,
    )
    memories.save(second)

    fresh = MemoryStore(tmp_path / "manifests")
    versions = fresh.versions(first.logical_id)

    assert [v.version for v in versions] == [1, 2]
    assert versions[0].text == "v1"


def test_rejected_candidate_stays_rejected(tmp_path: Path) -> None:
    candidates, _ = _stores(tmp_path)
    candidate = _candidate()
    rejected = MemoryCandidate.model_validate(
        {
            **candidate.model_dump(),
            "status": CandidateStatus.REJECTED,
            "review": {
                "decision": ReviewDecision.REJECTED,
                "reviewed_at": datetime.now(UTC).isoformat(),
                "reason": "transient",
            },
        }
    )
    candidates.save(rejected)

    fresh = CandidateStore(tmp_path / "manifests")
    reloaded = fresh.get(candidate.id)

    assert reloaded is not None
    assert reloaded.status is CandidateStatus.REJECTED
    assert reloaded.review is not None
    assert reloaded.review.reason == "transient"


def test_approved_memory_stays_durable(tmp_path: Path) -> None:
    _, memories = _stores(tmp_path)
    memory = memories.save(_memory())

    fresh = MemoryStore(tmp_path / "manifests")
    reloaded = fresh.get(memory.id)

    assert reloaded == memory
    assert reloaded is not None
    assert reloaded.status is MemoryStatus.ACTIVE


def test_evidence_snapshot_round_trips(tmp_path: Path) -> None:
    candidates, _ = _stores(tmp_path)
    candidate = _candidate()
    candidate = MemoryCandidate.model_validate(
        {
            **candidate.model_dump(),
            "evidence": EvidenceSnapshot(model="qwen3:8b").model_dump(),
        }
    )
    candidates.save(candidate)

    reloaded = CandidateStore(tmp_path / "manifests").get(candidate.id)

    assert reloaded is not None
    assert reloaded.evidence is not None
    assert reloaded.evidence.model == "qwen3:8b"
