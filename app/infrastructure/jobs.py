"""Persistence for V2 generation jobs.

A dedicated atomic-JSON store, separate from the ingestion queue state.
Writes follow the repository's tmp-file + ``os.replace`` pattern and are
best-effort (a failed write is logged, never raised), mirroring
``QueueStateStore``. A corrupt file loads as empty with a warning, matching
the queue's recovery posture.

Recovery policy is conservative: jobs reload exactly as persisted. A job
found in PROCESSING or VALIDATING after a restart is preserved unchanged —
never silently marked DONE or FAILED. Reconciliation belongs to a future
worker, not to the store.
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
from app.domain.generation import GenerationRequest
from app.domain.jobs import GenerationJob

logger = get_logger(__name__)


class GenerationJobStore:
    """Thread-safe atomic-JSON store for generation jobs."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._jobs: dict[str, GenerationJob] = {}
        self._loaded = False

    def _load_once(self) -> None:
        if self._loaded:
            return
        self._jobs = self._read_all()
        self._loaded = True

    def _read_all(self) -> dict[str, GenerationJob]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError):
            logger.warning("Generation job store unreadable; starting empty: %s", self.path)
            return {}
        raw_jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        if not isinstance(raw_jobs, list):
            return {}
        jobs: dict[str, GenerationJob] = {}
        for raw in raw_jobs:
            if not isinstance(raw, dict):
                continue
            try:
                job = GenerationJob.model_validate(raw)
            except ValidationError:
                logger.warning("Skipping unparseable generation job entry.")
                continue
            jobs[job.job_id] = job
        return jobs

    def _persist(self) -> None:
        payload: dict[str, Any] = {
            "version": 1,
            "jobs": [
                job.model_dump(mode="json")
                for _, job in sorted(
                    self._jobs.items(), key=lambda item: (item[1].created_at, item[0])
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
            logger.warning("Failed to persist generation job store.", exc_info=True)

    def create(self, request: GenerationRequest) -> GenerationJob:
        """Create, persist, and return a new PENDING job."""

        with self._lock:
            self._load_once()
            job = GenerationJob.create(request)
            self._jobs[job.job_id] = job
            self._persist()
            return job

    def get(self, job_id: str) -> GenerationJob | None:
        """Return the job with this id, or ``None`` when unknown."""

        with self._lock:
            self._load_once()
            return self._jobs.get(job_id)

    def update(self, job: GenerationJob) -> None:
        """Persist an updated job; raises ``KeyError`` when unknown."""

        with self._lock:
            self._load_once()
            if job.job_id not in self._jobs:
                raise KeyError(f"Unknown generation job: {job.job_id}")
            self._jobs[job.job_id] = job
            self._persist()

    def list_jobs(self) -> list[GenerationJob]:
        """Return all jobs ordered by creation time, then id (deterministic)."""

        with self._lock:
            self._load_once()
            return sorted(self._jobs.values(), key=lambda job: (job.created_at, job.job_id))
