"""Persistence for V2 artifacts and provenance records.

Two dedicated atomic-JSON stores, independent from the ingestion queue
state, the manifest, and the vector store. Both follow the repository's
tmp-file + ``os.replace`` pattern with per-store locks and best-effort
writes (a failed write is logged, never raised), mirroring
``GenerationJobStore``. Corrupt files load as empty with a warning.

Provenance records reference existing memory identifiers; the stores never
duplicate document contents and never build another index.
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.core.logging import get_logger
from app.domain.artifacts import Artifact, ProvenanceRecord

logger = get_logger(__name__)


class ArtifactStore:
    """Thread-safe atomic-JSON store for versioned artifacts."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._artifacts: dict[str, Artifact] = {}
        self._loaded = False

    def _load_once(self) -> None:
        if self._loaded:
            return
        self._artifacts = self._read_all()
        self._loaded = True

    def _read_all(self) -> dict[str, Artifact]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError):
            logger.warning("Artifact store unreadable; starting empty: %s", self.path)
            return {}
        raw_items = payload.get("artifacts", []) if isinstance(payload, dict) else []
        if not isinstance(raw_items, list):
            return {}
        artifacts: dict[str, Artifact] = {}
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            try:
                artifact = Artifact.model_validate(raw)
            except ValidationError:
                logger.warning("Skipping unparseable artifact entry.")
                continue
            artifacts[artifact.artifact_id] = artifact
        return artifacts

    def _persist(self) -> None:
        payload: dict[str, Any] = {
            "version": 1,
            "artifacts": [
                artifact.model_dump(mode="json")
                for _, artifact in sorted(
                    self._artifacts.items(),
                    key=lambda item: (item[1].created_at, item[0]),
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
            logger.warning("Failed to persist artifact store.", exc_info=True)

    def create(self, artifact: Artifact) -> Artifact:
        """Persist a new artifact row; raises ``KeyError`` on id collision."""

        with self._lock:
            self._load_once()
            if artifact.artifact_id in self._artifacts:
                raise KeyError(f"Artifact already stored: {artifact.artifact_id}")
            self._artifacts[artifact.artifact_id] = artifact
            self._persist()
            return artifact

    def get(self, artifact_id: str) -> Artifact | None:
        """Return the artifact row with this id, or ``None`` when unknown."""

        with self._lock:
            self._load_once()
            return self._artifacts.get(artifact_id)

    def update(self, artifact: Artifact) -> None:
        """Persist a changed artifact row; raises ``KeyError`` when unknown."""

        with self._lock:
            self._load_once()
            if artifact.artifact_id not in self._artifacts:
                raise KeyError(f"Unknown artifact: {artifact.artifact_id}")
            self._artifacts[artifact.artifact_id] = artifact
            self._persist()

    def list_artifacts(self) -> list[Artifact]:
        """Return all rows ordered by creation time, then id (deterministic)."""

        with self._lock:
            self._load_once()
            return sorted(
                self._artifacts.values(), key=lambda item: (item.created_at, item.artifact_id)
            )

    def list_versions(self, logical_id: str) -> list[Artifact]:
        """Return every version row of one logical artifact, oldest first."""

        with self._lock:
            self._load_once()
            return sorted(
                (item for item in self._artifacts.values() if item.logical_id == logical_id),
                key=lambda item: (item.version, item.created_at, item.artifact_id),
            )

    def list_for_job(self, job_id: str) -> list[Artifact]:
        """Return every artifact row produced by one job, oldest first."""

        with self._lock:
            self._load_once()
            return sorted(
                (item for item in self._artifacts.values() if item.job_id == job_id),
                key=lambda item: (item.created_at, item.artifact_id),
            )


class ProvenanceStore:
    """Thread-safe atomic-JSON store for artifact provenance records.

    Records are kept per artifact in insertion order, which is preserved
    across reloads, so ``for_artifact`` is deterministic.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._records: dict[str, list[ProvenanceRecord]] = {}
        self._loaded = False

    def _load_once(self) -> None:
        if self._loaded:
            return
        self._records = self._read_all()
        self._loaded = True

    def _read_all(self) -> dict[str, list[ProvenanceRecord]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError):
            logger.warning("Provenance store unreadable; starting empty: %s", self.path)
            return {}
        raw_items = payload.get("records", []) if isinstance(payload, dict) else []
        if not isinstance(raw_items, list):
            return {}
        records: dict[str, list[ProvenanceRecord]] = {}
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            try:
                record = ProvenanceRecord.model_validate(raw)
            except ValidationError:
                logger.warning("Skipping unparseable provenance entry.")
                continue
            records.setdefault(record.artifact_id, []).append(record)
        return records

    def _persist(self) -> None:
        payload: dict[str, Any] = {
            "version": 1,
            "records": [
                record.model_dump(mode="json")
                for artifact_id in sorted(self._records)
                for record in self._records[artifact_id]
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
            logger.warning("Failed to persist provenance store.", exc_info=True)

    def add(self, record: ProvenanceRecord) -> ProvenanceRecord:
        """Append and persist one provenance record for its artifact."""

        with self._lock:
            self._load_once()
            self._records.setdefault(record.artifact_id, []).append(record)
            self._persist()
            return record

    def for_artifact(self, artifact_id: str) -> list[ProvenanceRecord]:
        """Return an artifact's records in stored (insertion) order."""

        with self._lock:
            self._load_once()
            return list(self._records.get(artifact_id, []))
