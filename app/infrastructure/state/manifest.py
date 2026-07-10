"""Manifest persistence for processed files."""

from __future__ import annotations

import json
import logging
import os
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from app.infrastructure.state.hashing import compute_file_hash
from app.infrastructure.state.models import ManifestEntry, ManifestState

logger = logging.getLogger(__name__)


class ManifestManager:
    """Cache and persist the manifest of processed files."""

    def __init__(self, manifest_path: Path, *, project_root: Path, enabled: bool = True) -> None:
        self.manifest_path = self._resolve_manifest_path(manifest_path, project_root)
        self.project_root = project_root
        self.enabled = enabled
        self._state = ManifestState()
        self._loaded = False
        self.load()

    def load(self) -> ManifestState:
        """Load the manifest once and cache it in memory."""

        if self._loaded:
            return self._state

        if not self.enabled:
            self._state = ManifestState()
            self._loaded = True
            return self._state

        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self._state = ManifestState()
            self.save()
            self._loaded = True
            return self._state

        try:
            raw_data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if not isinstance(raw_data, dict):
                raise ValueError("Manifest root must be a mapping.")
            self._state = ManifestState.from_dict(raw_data)
        except (json.JSONDecodeError, ValueError, KeyError, TypeError):
            logger.warning("Manifest corrupted, recreating: %s", self.manifest_path)
            self._quarantine_corrupted_manifest()
            self._state = ManifestState()
            self.save()

        self._loaded = True
        return self._state

    def save(self) -> None:
        """Write the cached manifest back to disk."""

        if not self.enabled:
            return

        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.manifest_path.with_suffix(f"{self.manifest_path.suffix}.tmp")
        try:
            temporary_path.write_text(
                json.dumps(self._state.to_dict(), indent=2, ensure_ascii=True),
                encoding="utf-8",
            )
            os.replace(temporary_path, self.manifest_path)
        finally:
            with suppress(FileNotFoundError):
                temporary_path.unlink()

    def contains_hash(self, sha256: str) -> bool:
        """Return true if the manifest already contains the hash."""

        return any(entry.sha256 == sha256 for entry in self._state.files)

    def contains_path(self, path: Path) -> bool:
        """Return true if the manifest already contains the path."""

        normalized = self._normalize_path(path)
        return any(entry.original_path == normalized for entry in self._state.files)

    def add_entry(self, entry: ManifestEntry) -> None:
        """Add an entry to the cached manifest."""

        self._state.files.append(entry)

    def remove_entry(
        self,
        *,
        sha256: str | None = None,
        path: Path | None = None,
    ) -> bool:
        """Remove the first entry matching hash or path."""

        if sha256 is None and path is None:
            raise ValueError("Either sha256 or path must be provided.")

        normalized_path = self._normalize_path(path) if path is not None else None
        for index, entry in enumerate(self._state.files):
            if sha256 is not None and entry.sha256 == sha256:
                del self._state.files[index]
                return True
            if normalized_path is not None and entry.original_path == normalized_path:
                del self._state.files[index]
                return True
        return False

    def list_entries(self) -> list[ManifestEntry]:
        """Return a copy of all entries in the manifest."""

        return list(self._state.files)

    def count(self) -> int:
        """Return the number of stored entries."""

        return len(self._state.files)

    def add_processed_file(
        self,
        *,
        path: Path,
        sha256: str,
        extension: str,
        generated_note: str | None = None,
    ) -> ManifestEntry:
        """Create and add an entry for a processed file."""

        entry = ManifestEntry(
            sha256=sha256,
            original_filename=path.name,
            original_path=self._normalize_path(path),
            processed_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            extension=extension,
            status="processed",
            generated_note=generated_note,
        )
        self.add_entry(entry)
        return entry

    def hash_for_path(self, path: Path) -> str:
        """Compute a supported file hash."""

        return compute_file_hash(path)

    def _quarantine_corrupted_manifest(self) -> None:
        corrupted_path = self.manifest_path.with_name("processed_files.corrupted.json")
        try:
            if corrupted_path.exists():
                corrupted_path.unlink()
            self.manifest_path.replace(corrupted_path)
        except OSError:
            logger.warning("Unable to rename corrupted manifest: %s", self.manifest_path)

    def _normalize_path(self, path: Path | None) -> str:
        if path is None:
            return ""

        candidate = Path(path)
        try:
            return str(candidate.resolve().relative_to(self.project_root))
        except ValueError:
            return str(candidate.resolve())

    @staticmethod
    def _resolve_manifest_path(manifest_path: Path, project_root: Path) -> Path:
        candidate = Path(manifest_path)
        return candidate if candidate.is_absolute() else (project_root / candidate).resolve()
