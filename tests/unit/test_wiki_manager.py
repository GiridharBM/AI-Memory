"""Tests for Obsidian wiki management."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.notes import ObsidianNote
from app.infrastructure.vault import VaultWriter
from app.infrastructure.vault.wiki_manager import MANAGED_BEGIN, WikiManager


def test_wiki_manager_creates_note_and_core_files(tmp_path) -> None:
    result = WikiManager(tmp_path).upsert_note(_note())

    assert result.created is True
    assert result.updated is False
    assert result.note_path.exists()
    assert (tmp_path / "index.md").exists()
    assert (tmp_path / "overview.md").exists()
    assert (tmp_path / "log.md").exists()

    note_text = result.note_path.read_text(encoding="utf-8")
    assert MANAGED_BEGIN in note_text
    assert "[[index]]" in note_text
    assert "[[overview]]" in note_text

    index_text = (tmp_path / "index.md").read_text(encoding="utf-8")
    assert "[[Local AI Memory|Local AI Memory]]" in index_text


def test_wiki_manager_updates_existing_note_by_source(tmp_path) -> None:
    manager = WikiManager(tmp_path)
    first = manager.upsert_note(_note(title="Local AI Memory", filename="Local AI Memory.md"))
    second = manager.upsert_note(
        _note(title="Renamed Memory Note", filename="Renamed Memory Note.md")
    )

    assert first.note_path == second.note_path
    assert second.created is False
    assert second.updated is True
    assert not (tmp_path / "Notes" / "Renamed Memory Note.md").exists()

    note_text = second.note_path.read_text(encoding="utf-8")
    assert "# Renamed Memory Note" in note_text


def test_wiki_manager_prevents_filename_conflicts_for_different_sources(tmp_path) -> None:
    manager = WikiManager(tmp_path)
    first = manager.upsert_note(
        _note(source="first.md", title="Shared Title", filename="Shared Title.md")
    )
    second = manager.upsert_note(
        _note(source="second.md", title="Shared Title", filename="Shared Title.md")
    )

    assert first.note_path.name == "Shared Title.md"
    assert second.note_path.name == "Shared Title 2.md"
    assert first.note_path.read_text(encoding="utf-8") != second.note_path.read_text(
        encoding="utf-8"
    )


def test_wiki_manager_does_not_overwrite_user_written_content(tmp_path) -> None:
    manager = WikiManager(tmp_path)
    result = manager.upsert_note(_note())

    with result.note_path.open("a", encoding="utf-8") as handle:
        handle.write("\n## My Own Notes\n\nThis paragraph is mine.\n")

    second = manager.upsert_note(_note(title="Local AI Memory Updated"))
    note_text = second.note_path.read_text(encoding="utf-8")

    assert "This paragraph is mine." in note_text
    assert "# Local AI Memory Updated" in note_text


def test_vault_writer_saves_to_configured_vault(tmp_path) -> None:
    result = VaultWriter(tmp_path).save(_note())

    assert result.created is True
    assert result.note_path.parent == tmp_path / "Notes"
    assert result.index_path == tmp_path / "index.md"


def _note(
    *,
    title: str = "Local AI Memory",
    filename: str = "Local AI Memory.md",
    source: str = "memory.md",
) -> ObsidianNote:
    generated_at = datetime(2026, 7, 8, tzinfo=UTC)
    markdown = f"""---
title: "{title}"
source: "{source}"
source_type: "markdown"
filename: "memory.md"
generated_date: "{generated_at.isoformat()}"
tags:
  - "local-ai"
---
# {title}

## Summary

A local AI memory system.

## Key Concepts

- [[Local AI memory]] (high): A local knowledge system.

## Definitions

- No definitions identified.

## Related Topics

- [[Personal knowledge management]]: The source concerns durable notes.

## Tags

- #local-ai

## References

- Source: {source}
- Generated date: {generated_at.isoformat()}
"""
    return ObsidianNote(
        title=title,
        filename=filename,
        markdown=markdown,
        generated_at=generated_at,
        tags=["local-ai"],
        source=source,
        source_type="markdown",
    )
