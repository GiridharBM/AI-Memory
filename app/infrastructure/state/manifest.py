"""Manifest persistence for processed files."""

from __future__ import annotations

import json
import os
import re
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from app.core.logging import get_logger
from app.infrastructure.state.hashing import compute_file_hash
from app.infrastructure.state.models import ManifestEntry, ManifestState

logger = get_logger(__name__)

SUCCESSFUL_STATUSES = frozenset({"processed", "skipped_duplicate"})

_REPEATED_SLASH = re.compile(r"/{2,}")


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


def _url_scheme(url: str) -> str:
    """Return the lower-cased scheme of a URL string."""

    return urlparse(url.strip()).scheme.lower()


def historical_url_ledger_form(url: str) -> str:
    """Return the CWD-mangled ledger spelling the pre-D3-C writer produced.

    ``Path(url).resolve()`` prefixed the URL with the working directory and
    collapsed repeated separators, so the ledger kept ``https:/github.com/o/r``
    (never ``https://...``). Reproduce only that mangling: no case, query,
    fragment, port, or ``.git`` folding. A trailing slash is preserved, so
    ``.../o/r`` and ``.../o/r/`` produce different forms and never collapse.
    Returns ``""`` when the URL has no scheme marker to anchor on.
    """

    text = url.strip()
    scheme = _url_scheme(text)
    if scheme not in {"http", "https"}:
        return ""
    start = text.lower().find(f"{scheme}:/")
    if start == -1:
        return ""
    raw_scheme = text[start : start + len(scheme)]
    tail = _REPEATED_SLASH.sub("/", text[start + len(raw_scheme) + 1 :])
    return f"{raw_scheme}:{tail}"


def _historical_entry_form(entry_path: str, scheme: str) -> str:
    """Return the URL part of a stored legacy row, or ``""`` when absent.

    Anchored at the *first* occurrence of the URL's own scheme marker so a row
    whose CWD prefix merely contains ``:/`` (a Windows drive, or a URL nested in
    another URL's path) is never mistaken for this URL's mangled form.
    """

    text = entry_path.replace("\\", "/")
    start = text.lower().find(f"{scheme}:/")
    if start == -1:
        return ""
    return text[start:]


def _entry_is_local_file(entry_path: str, project_root: Path | None) -> bool:
    """Return true when a stored row addresses a real path on disk.

    Relative rows resolve against the project root (the same anchor the
    ledger writer uses), never against the process CWD, so the answer does
    not change with the working directory.
    """

    candidate = Path(entry_path)
    if not candidate.is_absolute() and project_root is not None:
        candidate = project_root / candidate
    return os.path.exists(candidate)


def url_matches_ledger_entry(
    entry_path: object, url: str, project_root: Path | None = None
) -> bool:
    """Match an exact URL against current and recognized historical ledger forms.

    New URL rows store the exact submitted URL. A historical row is recognized
    only when its URL part is exactly the mangled form of *this* URL, anchored
    at the first scheme marker, with no filesystem path mistaken for one.
    Historical rows are never rewritten or merged.
    """

    if not isinstance(entry_path, str) or not entry_path or not is_url_source(url):
        return False
    target = url.strip()
    if entry_path == target:
        return True
    # A current exact-URL row is a complete identity: never collapse spellings.
    if is_url_source(entry_path):
        return False
    entry_form = _historical_entry_form(entry_path, _url_scheme(target))
    if not entry_form:
        return False
    # A row that is a real path on disk is a local file, not a historical URL.
    if _entry_is_local_file(entry_path, project_root):
        return False
    form = historical_url_ledger_form(target)
    return bool(form) and entry_form == form


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

        return any(
            url_matches_ledger_entry(entry.original_path, url, self.project_root)
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
        path: Path | str | None = None,
    ) -> bool:
        """Remove the first entry matching hash or path.

        A URL target is compared against the exact stored URL identity; a
        filesystem target keeps the existing project-root normalization.
        """

        if sha256 is None and path is None:
            raise ValueError("Either sha256 or path must be provided.")

        raw = str(path) if path is not None else ""
        normalized_path: str | None
        if path is not None and is_url_source(raw):
            # Ledger URL rows are stored stripped; strip the target too so a
            # padded argument still addresses the exact stored identity.
            normalized_path = raw.strip()
        else:
            normalized_path = self._normalize_path(Path(path)) if path is not None else None
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

        URL strings retain their exact submitted form, trimmed exactly like the
        ingestion service normalizes them, so the same URL has the same logical
        identity from any working directory. Filesystem paths use the existing
        project-root normalization unchanged.
        """

        if is_url_source(source):
            return str(source).strip()
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
