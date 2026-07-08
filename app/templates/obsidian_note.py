"""Markdown generation for Obsidian-compatible notes."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.domain.analysis import DocumentAnalysis, ImportantEntity
from app.domain.documents import SourceDocument
from app.domain.notes import ObsidianNote

_FILENAME_UNSAFE_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MULTISPACE_PATTERN = re.compile(r"\s+")


class ObsidianMarkdownGenerator:
    """Generate deterministic Obsidian Markdown notes from analyzed documents."""

    def generate(
        self,
        *,
        document: SourceDocument,
        analysis: DocumentAnalysis,
        generated_at: datetime | None = None,
    ) -> ObsidianNote:
        """Generate an Obsidian note from a source document and its analysis."""

        timestamp = generated_at or datetime.now(tz=UTC)
        title = _clean_title(analysis.suggested_note_title)
        tags = _clean_tags(analysis.tags)
        markdown = "\n".join(
            [
                _frontmatter(
                    title=title,
                    document=document,
                    generated_at=timestamp,
                    tags=tags,
                ),
                f"# {title}",
                "",
                "## Summary",
                "",
                analysis.summary.short.strip(),
                "",
                analysis.summary.detailed.strip(),
                "",
                "## Key Concepts",
                "",
                _key_concepts_section(analysis),
                "",
                "## Definitions",
                "",
                _definitions_section(analysis),
                "",
                "## Important Entities",
                "",
                _important_entities_section(analysis),
                "",
                "## Related Topics",
                "",
                _related_topics_section(analysis),
                "",
                "## Tags",
                "",
                _tags_section(tags),
                "",
                "## References",
                "",
                _references_section(document, timestamp),
                "",
            ]
        )

        return ObsidianNote(
            title=title,
            filename=f"{_safe_filename(title)}.md",
            markdown=markdown,
            generated_at=timestamp,
            tags=tags,
            source=document.source,
            source_type=document.source_type,
        )


def _frontmatter(
    *,
    title: str,
    document: SourceDocument,
    generated_at: datetime,
    tags: list[str],
) -> str:
    lines = [
        "---",
        f"title: {_yaml_string(title)}",
        f"source: {_yaml_string(document.source)}",
        f"source_type: {_yaml_string(document.source_type)}",
        f"filename: {_yaml_string(document.filename)}",
        f"generated_date: {_yaml_string(generated_at.isoformat())}",
        "tags:",
    ]
    lines.extend(f"  - {_yaml_string(tag)}" for tag in tags)
    lines.append("---")
    return "\n".join(lines)


def _key_concepts_section(analysis: DocumentAnalysis) -> str:
    if not analysis.key_concepts:
        return "- No key concepts identified."

    return "\n".join(
        (
            f"- {_wiki_link(concept.name)} ({concept.importance}): "
            f"{concept.explanation.strip()}"
        )
        for concept in analysis.key_concepts
    )


def _definitions_section(analysis: DocumentAnalysis) -> str:
    if not analysis.definitions:
        return "- No definitions identified."

    return "\n".join(
        f"- {_wiki_link(definition.term)}: {definition.definition.strip()}"
        for definition in analysis.definitions
    )


def _important_entities_section(analysis: DocumentAnalysis) -> str:
    if not analysis.important_entities:
        return "- No important entities identified."

    return "\n".join(_format_entity(entity) for entity in analysis.important_entities)


def _related_topics_section(analysis: DocumentAnalysis) -> str:
    if not analysis.related_topics:
        return "- No related topics identified."

    return "\n".join(
        f"- {_wiki_link(topic.topic)}: {topic.reason.strip()}"
        for topic in analysis.related_topics
    )


def _tags_section(tags: list[str]) -> str:
    if not tags:
        return "- No tags generated."
    return "\n".join(f"- #{tag}" for tag in tags)


def _references_section(document: SourceDocument, generated_at: datetime) -> str:
    lines = [
        f"- Source: {document.source}",
        f"- Source type: {document.source_type}",
        f"- Original filename: {document.filename}",
        f"- Generated date: {generated_at.isoformat()}",
    ]

    if document.metadata.title:
        lines.append(f"- Source title: {document.metadata.title}")
    if document.metadata.author:
        lines.append(f"- Author: {document.metadata.author}")

    return "\n".join(lines)


def _format_entity(entity: ImportantEntity) -> str:
    return f"- {_wiki_link(entity.name)} ({entity.type}): {entity.description.strip()}"


def _wiki_link(value: str) -> str:
    label = _clean_title(value)
    escaped = label.replace("|", "\\|").replace("[", "").replace("]", "")
    return f"[[{escaped}]]"


def _clean_title(value: str) -> str:
    cleaned = _MULTISPACE_PATTERN.sub(" ", value).strip()
    return cleaned or "Untitled Note"


def _safe_filename(value: str) -> str:
    filename = _FILENAME_UNSAFE_PATTERN.sub("", _clean_title(value))
    filename = filename.rstrip(". ")
    return filename or "Untitled Note"


def _clean_tags(tags: list[str]) -> list[str]:
    cleaned_tags: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        cleaned = tag.strip().lower().replace(" ", "-").lstrip("#")
        cleaned = re.sub(r"[^a-z0-9_-]+", "-", cleaned)
        cleaned = cleaned.strip("-")
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        cleaned_tags.append(cleaned)
    return cleaned_tags


def _yaml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
