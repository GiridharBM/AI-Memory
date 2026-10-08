"""Persistence for V2.1-B memory candidates and approved memories.

Two logically separate atomic-JSON stores sharing one module: candidate rows
in ``memory_candidates.json``, versioned memory rows in ``memories.json``.
Both follow the repository's tmp-file + ``os.replace`` / lock conventions:
best-effort writes (logged, never raised), corrupt content degrades to skips
with a warning rather than destroying the store. No database, no vector
store involvement — approved memories are durable records only.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.core.logging import get_logger
from app.domain.memory import Memory, MemoryCandidate, MemoryStatus

logger = get_logger(__name__)


class CandidateStore:
    """Thread-safe atomic-JSON store for memory candidate rows."""

    def __init__(self, manifest_root: Path) -> None:
        self.path = manifest_root / "memory_candidates.json"
        self._lock = threading.Lock()
        self._candidates: dict[str, MemoryCandidate] = {}
        self._loaded = False

    def _load_once(self) -> None:
        if self._loaded:
            return
        self._candidates = self._read_all()
        self._loaded = True

    def _read_all(self) -> dict[str, MemoryCandidate]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError):
            logger.warning(
                "Memory candidate store unreadable; starting empty: %s", self.path
            )
            return {}
        raw_items = payload.get("candidates", []) if isinstance(payload, dict) else []
        if not isinstance(raw_items, list):
            return {}
        candidates: dict[str, MemoryCandidate] = {}
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            try:
                candidate = MemoryCandidate.model_validate(raw)
            except ValidationError:
                logger.warning("Skipping unparseable memory candidate entry.")
                continue
            candidates[candidate.id] = candidate
        return candidates

    def _persist(self) -> None:
        payload: dict[str, Any] = {
            "version": 1,
            "candidates": [
                candidate.model_dump(mode="json")
                for _, candidate in sorted(
                    self._candidates.items(),
                    key=lambda item: (item[1].extracted_at, item[0]),
                )
            ],
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
            try:
                temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                os.replace(temporary_path, self.path)
            finally:
                with suppress(FileNotFoundError):
                    temporary_path.unlink()
        except OSError:
            logger.warning("Failed to persist memory candidate store.", exc_info=True)

    def save(self, candidate: MemoryCandidate) -> MemoryCandidate:
        """Insert or replace one candidate row by id."""

        with self._lock:
            self._load_once()
            self._candidates[candidate.id] = candidate
            self._persist()
            return candidate

    def get(self, candidate_id: str) -> MemoryCandidate | None:
        """Return one candidate, or ``None`` when unknown."""

        with self._lock:
            self._load_once()
            return self._candidates.get(candidate_id)

    def list(self, limit: int = 50, offset: int = 0) -> list[MemoryCandidate]:
        """Candidates in deterministic extraction order (paginated)."""

        with self._lock:
            self._load_once()
            ordered = sorted(
                self._candidates.values(),
                key=lambda item: (item.extracted_at, item.id),
            )
            return ordered[offset : offset + limit]


class MemoryStore:
    """Thread-safe atomic-JSON store for versioned approved memory rows."""

    def __init__(self, manifest_root: Path) -> None:
        self.path = manifest_root / "memories.json"
        self._lock = threading.Lock()
        self._memories: dict[str, Memory] = {}
        self._loaded = False

    def _load_once(self) -> None:
        if self._loaded:
            return
        self._memories = self._read_all()
        self._loaded = True

    def _read_all(self) -> dict[str, Memory]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError):
            logger.warning("Memory store unreadable; starting empty: %s", self.path)
            return {}
        raw_items = payload.get("memories", []) if isinstance(payload, dict) else []
        if not isinstance(raw_items, list):
            return {}
        memories: dict[str, Memory] = {}
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            try:
                memory = Memory.model_validate(raw)
            except ValidationError:
                logger.warning("Skipping unparseable memory entry.")
                continue
            memories[memory.id] = memory
        return memories

    def _persist(self) -> None:
        payload: dict[str, Any] = {
            "version": 1,
            "memories": [
                memory.model_dump(mode="json")
                for _, memory in sorted(
                    self._memories.items(),
                    key=lambda item: (item[1].approved_at, item[0]),
                )
            ],
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
            try:
                temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                os.replace(temporary_path, self.path)
            finally:
                with suppress(FileNotFoundError):
                    temporary_path.unlink()
        except OSError:
            logger.warning("Failed to persist memory store.", exc_info=True)

    def save(self, memory: Memory) -> Memory:
        """Insert or replace one memory version row by id."""

        with self._lock:
            self._load_once()
            self._memories[memory.id] = memory
            self._persist()
            return memory

    def get(self, memory_id: str) -> Memory | None:
        """Return one memory version, or ``None`` when unknown."""

        with self._lock:
            self._load_once()
            return self._memories.get(memory_id)

    def versions(self, logical_id: str) -> list[Memory]:
        """Every stored version of one logical memory, oldest version first."""

        with self._lock:
            self._load_once()
            return sorted(
                (
                    memory
                    for memory in self._memories.values()
                    if memory.logical_id == logical_id
                ),
                key=lambda item: (item.version, item.id),
            )

    def list(self, limit: int = 50, offset: int = 0) -> list[Memory]:
        """Memory versions in deterministic approval order (paginated)."""

        with self._lock:
            self._load_once()
            ordered = sorted(
                self._memories.values(),
                key=lambda item: (item.approved_at, item.id),
            )
            return ordered[offset : offset + limit]

    def active_memories(self) -> Sequence[Memory]:
        """Every ACTIVE memory version, oldest approval first.

        Superseded versions are excluded: only the current durable state
        may participate in runtime memory context. Same locking and
        load-once conventions as the other readers; persistence untouched.

        (Annotated ``Sequence`` rather than ``list`` because this class
        already defines a ``list`` reader, which shadows the builtin in
        later annotations.)
        """

        with self._lock:
            self._load_once()
            return sorted(
                (
                    memory
                    for memory in self._memories.values()
                    if memory.status is MemoryStatus.ACTIVE
                ),
                key=lambda item: (item.approved_at, item.id),
            )
