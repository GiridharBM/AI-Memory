"""Tests for Obsidian Markdown generation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.domain.analysis import DocumentAnalysis
from app.domain.documents import DocumentMetadata, SourceDocument
from app.templates.obsidian_note import ObsidianMarkdownGenerator


def test_obsidian_markdown_generator_creates_required_sections() -> None:
    generated_at = datetime(2026, 7, 8, 12, 30, tzinfo=UTC)

    note = ObsidianMarkdownGenerator().generate(
        document=_document(),
        analysis=_analysis(),
        generated_at=generated_at,
    )

    assert note.title == "Local AI Memory"
    assert note.filename == "Local AI Memory.md"
    assert note.generated_at == generated_at
    assert note.source == "memory.md"
    assert note.source_type == "markdown"

    markdown = note.markdown
    assert markdown.startswith("---\n")
    assert 'title: "Local AI Memory"' in markdown
    assert 'generated_date: "2026-07-08T12:30:00+00:00"' in markdown
    assert "# Local AI Memory" in markdown
    assert "## Summary" in markdown
    assert "## Key Concepts" in markdown
    assert "## Definitions" in markdown
    assert "## Related Topics" in markdown
    assert "## Tags" in markdown
    assert "## References" in markdown


def test_obsidian_markdown_generator_uses_wiki_links_and_tags() -> None:
    note = ObsidianMarkdownGenerator().generate(
        document=_document(),
        analysis=_analysis(),
        generated_at=datetime(2026, 7, 8, tzinfo=UTC),
    )

    markdown = note.markdown
    assert "[[Local AI memory]]" in markdown
    assert "[[Incremental ingestion]]" in markdown
    assert "[[Obsidian]]" in markdown
    assert "[[Personal knowledge management]]" in markdown
    assert "- #local-ai" in markdown
    assert "- #memory" in markdown
    assert "  - \"local-ai\"" in markdown
    assert "  - \"memory\"" in markdown


def _document() -> SourceDocument:
    return SourceDocument(
        source="memory.md",
        source_type="markdown",
        filename="memory.md",
        text="# Local Memory\n\nA local AI memory system.",
        metadata=DocumentMetadata(title="Local Memory", author="Test Author"),
    )


def _analysis() -> DocumentAnalysis:
    payload: dict[str, Any] = {
        "suggested_note_title": "Local AI Memory",
        "summary": {
            "short": "A local AI memory system.",
            "detailed": "The source describes a local AI memory system for durable notes.",
        },
        "key_concepts": [
            {
                "name": "Local AI memory",
                "explanation": "A local system for building durable personal knowledge.",
                "importance": "high",
            }
        ],
        "definitions": [
            {
                "term": "Incremental ingestion",
                "definition": "Adding changed sources without rebuilding the whole wiki.",
            }
        ],
        "important_entities": [
            {
                "name": "Obsidian",
                "type": "product",
                "description": "A Markdown knowledge base application.",
            }
        ],
        "tags": ["Local AI", "#memory"],
        "related_topics": [
            {
                "topic": "Personal knowledge management",
                "reason": "The source is about maintaining useful personal knowledge.",
            }
        ],
    }
    return DocumentAnalysis.model_validate(payload)
