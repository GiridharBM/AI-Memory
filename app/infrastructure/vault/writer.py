"""Vault writer for persisting generated Obsidian notes."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.notes import ObsidianNote
from app.infrastructure.vault.wiki_manager import WikiManager, WikiUpdateResult

logger = get_logger(__name__)


class VaultWriter:
    """Save generated notes into the configured Obsidian vault."""

    def __init__(self, vault_root: Path, *, notes_folder: str = "Notes") -> None:
        self._vault_root = vault_root.expanduser().resolve()
        self._wiki_manager = WikiManager(self._vault_root, notes_folder=notes_folder)

    @classmethod
    def from_settings(cls, settings: Settings) -> VaultWriter:
        """Create a vault writer from validated application settings."""

        return cls(settings.paths.vault_root)

    def save(self, note: ObsidianNote) -> WikiUpdateResult:
        """Save a generated note and update supporting wiki files."""

        logger.info(
            "Saving generated note to Obsidian vault.",
            extra={
                "vault_root": str(self._vault_root),
                "title": note.title,
                "note_filename": note.filename,
                "source": note.source,
            },
        )

        result = self._wiki_manager.upsert_note(note)

        logger.info(
            "Generated note saved to Obsidian vault.",
            extra={
                "vault_root": str(self._vault_root),
                "note_path": str(result.note_path),
                "note_created": result.created,
                "note_updated": result.updated,
                "source": note.source,
            },
        )

        return result

    def initialize(self) -> None:
        """Create the configured vault folder structure and core wiki files."""

        logger.info("Initializing Obsidian vault.", extra={"vault_root": str(self._vault_root)})
        self._wiki_manager.initialize()
