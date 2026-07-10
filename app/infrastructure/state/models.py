"""Manifest state models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ManifestEntry:
    """A processed file entry stored in the manifest."""

    sha256: str
    original_filename: str
    original_path: str
    processed_at: str
    extension: str
    status: str
    generated_note: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entry to a JSON-friendly dictionary."""

        payload = asdict(self)
        if not payload["metadata"]:
            payload.pop("metadata")
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
