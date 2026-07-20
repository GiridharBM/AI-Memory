"""Version history for generated notes."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class NoteVersion:
    """A single version of a note."""

    version: int
    timestamp: str
    filename: str
    sha256: str = ""
    source: str = ""


@dataclass
class VersionHistory:
    """Track versions for a note file."""

    note_filename: str
    versions: list[NoteVersion] = field(default_factory=list)


class VersionManager:
    """Manage note version history on the filesystem."""

    def __init__(self, vault_root: Path) -> None:
        self._versions_dir = vault_root / "Versions"

    def record_version(
        self,
        note_filename: str,
        content: str,
        *,
        source: str = "",
    ) -> NoteVersion:
        self._versions_dir.mkdir(parents=True, exist_ok=True)
        note_dir = self._versions_dir / note_filename.replace(".md", "")
        note_dir.mkdir(parents=True, exist_ok=True)
        history = self._load_history(note_filename)
        version_num = len(history.versions) + 1
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        version_filename = f"{timestamp}_v{version_num}.md"
        version_path = note_dir / version_filename
        version_path.write_text(content, encoding="utf-8")

        entry = NoteVersion(
            version=version_num,
            timestamp=datetime.now(tz=UTC).isoformat(),
            filename=version_filename,
            source=source,
        )
        history.versions.append(entry)
        self._save_history(note_filename, history)
        logger.info(
            "Recorded note version.",
            extra={"note": note_filename, "version": version_num},
        )
        return entry

    def get_versions(self, note_filename: str) -> list[NoteVersion]:
        return self._load_history(note_filename).versions

    def get_version_content(
        self, note_filename: str, version: int,
    ) -> str | None:
        history = self._load_history(note_filename)
        for v in history.versions:
            if v.version == version:
                note_dir = self._versions_dir / note_filename.replace(".md", "")
                path = note_dir / v.filename
                if path.exists():
                    return path.read_text(encoding="utf-8")
        return None

    def has_versions(self, note_filename: str) -> bool:
        return len(self._load_history(note_filename).versions) > 0

    def _history_path(self, note_filename: str) -> Path:
        return self._versions_dir / note_filename.replace(".md", "") / "history.json"

    def _load_history(self, note_filename: str) -> VersionHistory:
        path = self._history_path(note_filename)
        if not path.exists():
            return VersionHistory(note_filename=note_filename)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            versions = [NoteVersion(**v) for v in data.get("versions", [])]
            return VersionHistory(note_filename=note_filename, versions=versions)
        except (json.JSONDecodeError, KeyError):
            return VersionHistory(note_filename=note_filename)

    def _save_history(self, note_filename: str, history: VersionHistory) -> None:
        path = self._history_path(note_filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "note_filename": history.note_filename,
            "versions": [asdict(v) for v in history.versions],
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
