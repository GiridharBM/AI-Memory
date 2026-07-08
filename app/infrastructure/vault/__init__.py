"""Obsidian vault integration adapters."""

from app.infrastructure.vault.wiki_manager import WikiManager, WikiUpdateResult
from app.infrastructure.vault.writer import VaultWriter

__all__ = ["VaultWriter", "WikiManager", "WikiUpdateResult"]
