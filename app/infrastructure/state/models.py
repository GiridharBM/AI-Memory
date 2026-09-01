"""Manifest state models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ManifestEntry:
    """A ledger entry recorded in the processed-files manifest.

    ``status`` is one of ``processed`` (successfully ingested and indexed),
    ``skipped_duplicate`` (a repeat of an already-successful source), or
    ``failed`` (ingestion/embedding/indexing failed; retryable).  The outcome
    fields make the ledger a durable record of what actually happened.
    """

    sha256: str
    original_filename: str
    original_path: str
    processed_at: str
    extension: str
    status: str
    generated_note: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error_reason: str | None = None
    chunks_stored: int | None = None
    embedding_succeeded: bool | None = None
    indexing_succeeded: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entry to a JSON-friendly dictionary."""

        payload = asdict(self)
        if not payload["metadata"]:
            payload.pop("metadata")
        for optional in ("error_reason", "chunks_stored"):
            if payload.get(optional) is None:
                payload.pop(optional, None)
        for optional in ("embedding_succeeded", "indexing_succeeded"):
            if payload.get(optional) is None:
                payload.pop(optional, None)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ManifestEntry:
        """Build an entry from persisted manifest data."""

        return cls(
            sha256=str(data["sha256"]),
            original_filename=str(data["original_filename"]),
            original_path=str(data["original_path"]),
            processed_at=str(data["processed_at"]),
            extension=str(data["extension"]),
            status=str(data["status"]),
            generated_note=(
                None if data.get("generated_note") is None else str(data["generated_note"])
            ),
            metadata=dict(data.get("metadata", {})),
            error_reason=(
                None if data.get("error_reason") is None else str(data["error_reason"])
            ),
            chunks_stored=(
                None if data.get("chunks_stored") is None else int(data["chunks_stored"])
            ),
            embedding_succeeded=(
                None if data.get("embedding_succeeded") is None
                else bool(data["embedding_succeeded"])
            ),
            indexing_succeeded=(
                None if data.get("indexing_succeeded") is None
                else bool(data["indexing_succeeded"])
            ),
        )


@dataclass(slots=True)
class ManifestState:
    """The full manifest payload."""

    version: int = 1
    files: list[ManifestEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the state to a JSON-friendly dictionary."""

        return {
            "version": self.version,
            "files": [entry.to_dict() for entry in self.files],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ManifestState:
        """Build a state object from persisted data."""

        files = data.get("files", [])
        if not isinstance(files, list):
            raise ValueError("Manifest files payload must be a list.")

        return cls(
            version=int(data.get("version", 1)),
            files=[ManifestEntry.from_dict(entry) for entry in files],
        )
