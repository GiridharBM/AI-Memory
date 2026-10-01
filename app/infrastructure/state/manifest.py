"""Manifest persistence for processed files."""

from __future__ import annotations

import json
import os
from collections.abc import Collection
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path, PurePath
from urllib.parse import urlparse

from app.core.logging import get_logger
from app.infrastructure.state.hashing import compute_file_hash
from app.infrastructure.state.models import ManifestEntry, ManifestState

logger = get_logger(__name__)

SUCCESSFUL_STATUSES = frozenset({"processed", "skipped_duplicate"})


def is_successful_status(status: str) -> bool:
    """Return true for statuses that count as durably processed."""
    return status in SUCCESSFUL_STATUSES


def is_url_source(value: object) -> bool:
    """Return true for an HTTP/HTTPS URL source string."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    parsed = urlparse(text)
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def _url_ledger_suffix(url: str) -> str:
    """Return the CWD-independent filesystem spelling of a URL string."""
    return PurePath(url).as_posix()


def url_matches_ledger_entry(
    entry_path: object, url: str, known_exact_paths: Collection[str] | None = None
) -> bool:
    """Match an exact URL against current and recognized historical ledger forms.

    New URL ledger rows use the exact submitted URL. Historical rows created by
    ``Path(url).resolve()`` retain a CWD-derived mangled spelling. Recognize
    those rows by their URL-derived suffix without rewriting them and without
    equating different URL spellings that produce different suffixes.
    """
    if not isinstance(entry_path, str) or not entry_path:
        return False
    if not is_url_source(url):
        return False
    if entry_path == url:
        return True
    # A current exact-URL row is itself a complete identity. Do not use legacy
    # suffix matching to collapse distinct URL spellings.
    if is_url_source(entry_path):
        return False
    suffix = _url_ledger_suffix(url)
    known_exact_paths = known_exact_paths or ()
    if any(
        is_url_source(known_path) and _url_ledger_suffix(known_path) == suffix
        for known_path in known_exact_paths
    ):
        return False
    normalized_entry = entry_path.replace(os.sep, "/")
    return normalized_entry == suffix or normalized_entry.endswith("/" + suffix)


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

    def contains_successful_hash(self, sha256: str) -> bool:
        """Return true if the hash was already processed successfully.

        Failed entries do not count as duplicates: a file re-dropped after a
        failure (ingestion, embedding, or indexing) must be retried, not skipped.
        """

        return any(
            entry.sha256 == sha256 and is_successful_status(entry.status)
            for entry in self._state.files
        )

    def contains_path(self, path: Path) -> bool:
        """Return true if the manifest already contains the path."""

        normalized = self._normalize_path(path)
        return any(entry.original_path == normalized for entry in self._state.files)

    def contains_successful_path(self, path: Path) -> bool:
        """Return true if the path was already processed successfully.

        The path-scoped mirror of :meth:`contains_successful_hash`, for sources
        that cannot be hashed (URLs, unsupported suffixes).  Failed entries do
        not count as duplicates here either, so re-submitting a source that
        previously failed is retried rather than skipped.  A source that was
        processed or skipped as a duplicate stays protected.
        """

        normalized = self._normalize_path(path)
        return any(
            entry.original_path == normalized and is_successful_status(entry.status)
            for entry in self._state.files
        )

    def contains_successful_url(self, url: str) -> bool:
        """Return true if an exact URL was already processed successfully.

        Matches both current exact-URL ledger rows and recognized historical
        CWD-derived URL rows. Failed entries do not count as duplicates.
        """

        known_exact_paths = [entry.original_path for entry in self._state.files]
        return any(
            url_matches_ledger_entry(entry.original_path, url, known_exact_paths)
            and is_successful_status(entry.status)
            for entry in self._state.files
        )

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

    def _normalize_ledger_source(self, source: Path | str) -> str:
        """Return the stored ledger spelling for a filesystem or URL source.

        URL strings retain their exact submitted form so the same URL has the
        same logical identity from any working directory. Filesystem paths use
        the existing project-root normalization unchanged.
        """

        if is_url_source(source):
            return str(source)
        return self._normalize_path(source if isinstance(source, Path) else Path(source))

    def add_processed_file(
        self,
        *,
        path: Path | str,
        sha256: str,
        extension: str,
        generated_note: str | None = None,
        status: str = "processed",
        error_reason: str | None = None,
        chunks_stored: int | None = None,
        embedding_succeeded: bool | None = None,
        indexing_succeeded: bool | None = None,
    ) -> ManifestEntry:
        """Create and add a ledger entry for a processed file.

        ``status`` may be ``processed``, ``skipped_duplicate``, or ``failed``.
        Failed entries carry ``error_reason`` and are excluded from hash-based
        dedup so the file can be retried on re-drop.
        """

        entry = ManifestEntry(
            sha256=sha256,
            original_filename=Path(path).name,
            original_path=self._normalize_ledger_source(path),
            processed_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            extension=extension,
            status=status,
            generated_note=generated_note,
            error_reason=error_reason,
            chunks_stored=chunks_stored,
            embedding_succeeded=embedding_succeeded,
            indexing_succeeded=indexing_succeeded,
        )
        self.add_entry(entry)
        return entry

    def add_failed_file(
        self,
        *,
        path: Path | str,
        sha256: str,
        extension: str,
        error_reason: str,
    ) -> ManifestEntry:
        """Record a failed ingest in the ledger (retryable on re-drop)."""

        return self.add_processed_file(
            path=path,
            sha256=sha256,
            extension=extension,
            status="failed",
            error_reason=error_reason,
        )

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
