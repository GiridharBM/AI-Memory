"""Markdown generation for Obsidian-compatible notes."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.domain.analysis import (
    DocumentAnalysis,
    ExtractedMetadata,
    ImportantEntity,
)
from app.domain.document_intelligence import Table
from app.domain.documents import SourceDocument
from app.domain.notes import ObsidianNote
from app.infrastructure.document_intelligence.tables.render import MarkdownTableRenderer

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
        ocr_confidence: float | None = None,
        processing_confidence: float | None = None,
    ) -> ObsidianNote:
        """Generate an Obsidian note from a source document and its analysis."""

        timestamp = generated_at or datetime.now(tz=UTC)
        title = _clean_title(analysis.suggested_note_title)
        tags = _clean_tags(analysis.tags)
        sections = [
            _frontmatter(
                title=title,
                document=document,
                generated_at=timestamp,
                tags=tags,
                analysis=analysis,
                ocr_confidence=ocr_confidence,
                processing_confidence=processing_confidence,
            ),
            f"# {title}",
            "",
            "## Summary",
            "",
            analysis.summary.short.strip(),
            "",
            analysis.summary.detailed.strip(),
            "",
            "## Reading Time",
            "",
            f"**{analysis.reading_time_minutes} minutes**",
            "",
            "## Difficulty Level",
            "",
            f"**{analysis.difficulty.title()}**",
            "",
        ]

        toc_entries: list[str] = ["Reading Time", "Difficulty Level"]
        if analysis.keywords:
            sections.extend(["## Keywords", "", _keywords_section(analysis), ""])
            toc_entries.append("Keywords")
        if analysis.categories:
            sections.extend(["## Categories", "", _categories_section(analysis), ""])
            toc_entries.append("Categories")

        tables_markdown = _tables_section(document)
        if tables_markdown:
            sections.extend(["## Tables", "", tables_markdown, ""])
            toc_entries.append("Tables")

        sections.extend([
            "## Key Concepts", "",
            _key_concepts_section(analysis), "",
            "## Definitions", "",
            _definitions_section(analysis), "",
            "## Important Entities", "",
            _important_entities_section(analysis), "",
            "## Related Topics", "",
            _related_topics_section(analysis), "",
        ])
        toc_entries.extend(["Key Concepts", "Definitions", "Important Entities", "Related Topics"])

        if analysis.suggested_related_notes:
            sections.extend(
                ["## Suggested Related Notes", "", _suggested_related_notes_section(analysis), ""]
            )
            toc_entries.append("Suggested Related Notes")
        if analysis.suggested_backlinks:
            sections.extend(
                ["## Suggested Backlinks", "", _suggested_backlinks_section(analysis), ""]
            )
            toc_entries.append("Suggested Backlinks")
        if analysis.questions_and_answers:
            sections.extend(["## Frequently Asked Questions", "", _qa_section(analysis), ""])
            toc_entries.append("Frequently Asked Questions")
        if analysis.flashcards:
            sections.extend(["## Flashcards", "", _flashcards_section(analysis), ""])
            toc_entries.append("Flashcards")
        if analysis.multiple_choice_questions:
            sections.extend(["## Multiple Choice Questions", "", _mcq_section(analysis), ""])
            toc_entries.append("Multiple Choice Questions")
        if analysis.short_answer_questions:
            sections.extend(["## Short Answer Questions", "", _short_answer_section(analysis), ""])
            toc_entries.append("Short Answer Questions")
        if analysis.long_answer_questions:
            sections.extend(["## Long Answer Questions", "", _long_answer_section(analysis), ""])
            toc_entries.append("Long Answer Questions")
        if analysis.revision_notes:
            sections.extend(["## Revision Notes", "", _revision_notes_section(analysis), ""])
            toc_entries.append("Revision Notes")

        toc_entries.extend(["Tags", "Metadata", "References"])

        toc_md = "\n".join(f"- [[#{entry}|{entry}]]" for entry in toc_entries)
        sections.insert(9, "## Table of Contents")
        sections.insert(10, "")
        sections.insert(11, toc_md)
        sections.insert(12, "")

        sections.extend([
            "## Tags",
            "",
            _tags_section(tags),
            "",
            "## Metadata",
            "",
            _metadata_section(analysis.extracted_metadata),
            "",
            "## References",
            "",
            _references_section(document, timestamp, ocr_confidence, processing_confidence),
            "",
        ])

        markdown = "\n".join(sections)

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
    analysis: DocumentAnalysis,
    ocr_confidence: float | None,
    processing_confidence: float | None,
) -> str:
    lines = [
        "---",
        f"title: {_yaml_string(title)}",
        f"source: {_yaml_string(document.source)}",
        f"source_type: {_yaml_string(document.source_type)}",
        f"filename: {_yaml_string(document.filename)}",
        f"generated_date: {_yaml_string(generated_at.isoformat())}",
        f"reading_time_minutes: {analysis.reading_time_minutes}",
        f"difficulty: {_yaml_string(analysis.difficulty)}",
    ]
    if analysis.categories:
        lines.append("categories:")
        lines.extend(f"  - {_yaml_string(c)}" for c in analysis.categories)
    if analysis.keywords:
        lines.append("keywords:")
        lines.extend(f"  - {_yaml_string(k)}" for k in analysis.keywords)
    lines.append("tags:")
    lines.extend(f"  - {_yaml_string(tag)}" for tag in tags)
    if ocr_confidence is not None:
        lines.append(f"ocr_confidence: {ocr_confidence:.2f}")
    if processing_confidence is not None:
        lines.append(f"processing_confidence: {processing_confidence:.2f}")
    lines.append("---")
    return "\n".join(lines)


def _keywords_section(analysis: DocumentAnalysis) -> str:
    if not analysis.keywords:
        return "- No keywords identified."
    return ", ".join(f"`{kw}`" for kw in analysis.keywords)


def _tables_section(document: SourceDocument) -> str:
    """Render ``metadata.extra["tables"]`` as Markdown (frozen §2.4).

    Returns ``""`` when no tables key exists (Phase-1-identical output). Each
    stored table is a serialized ``Table`` dict (``model_dump(mode="json")``).
    """
    raw_tables = document.metadata.extra.get("tables")
    if not raw_tables:
        return ""
    renderer = MarkdownTableRenderer()
    blocks: list[str] = []
    for raw in raw_tables:
        try:
            table = Table.model_validate(raw)
        except Exception:
            continue
        markdown = renderer.to_markdown(table)
        if markdown:
            blocks.append(markdown)
    return "\n\n".join(blocks)


def _categories_section(analysis: DocumentAnalysis) -> str:
    if not analysis.categories:
        return "- No categories identified."
    return "\n".join(f"- {cat}" for cat in analysis.categories)


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


def _suggested_related_notes_section(analysis: DocumentAnalysis) -> str:
    if not analysis.suggested_related_notes:
        return "- No related notes suggested."
    return "\n".join(f"- {_wiki_link(note)}" for note in analysis.suggested_related_notes)


def _suggested_backlinks_section(analysis: DocumentAnalysis) -> str:
    if not analysis.suggested_backlinks:
        return "- No backlinks suggested."
    return "\n".join(f"- {_wiki_link(note)}" for note in analysis.suggested_backlinks)


def _qa_section(analysis: DocumentAnalysis) -> str:
    if not analysis.questions_and_answers:
        return "- No questions and answers generated."
    parts: list[str] = []
    for i, qa in enumerate(analysis.questions_and_answers, 1):
        parts.append(f"**Q{i}: {qa.question.strip()}**")
        parts.append(f"A{i}: {qa.answer.strip()}")
        parts.append("")
    return "\n".join(parts).rstrip()


def _flashcards_section(analysis: DocumentAnalysis) -> str:
    if not analysis.flashcards:
        return "- No flashcards generated."
    parts: list[str] = []
    for i, card in enumerate(analysis.flashcards, 1):
        parts.append(f"**Card {i} - Front:** {card.front.strip()}")
        parts.append(f"**Back:** {card.back.strip()}")
        parts.append("")
    return "\n".join(parts).rstrip()


def _mcq_section(analysis: DocumentAnalysis) -> str:
    if not analysis.multiple_choice_questions:
        return "- No MCQs generated."
    parts: list[str] = []
    for i, mcq in enumerate(analysis.multiple_choice_questions, 1):
        parts.append(f"**{i}. {mcq.question.strip()}**")
        for j, option in enumerate(mcq.options):
            marker = "X" if option == mcq.correct_answer else " "
            parts.append(f"   {chr(65 + j)}. [{marker}] {option}")
        if mcq.explanation:
            parts.append(f"   *Explanation: {mcq.explanation.strip()}*")
        parts.append("")
    return "\n".join(parts).rstrip()


def _short_answer_section(analysis: DocumentAnalysis) -> str:
    if not analysis.short_answer_questions:
        return "- No short answer questions generated."
    parts: list[str] = []
    for i, qa in enumerate(analysis.short_answer_questions, 1):
        parts.append(f"**{i}. {qa.question.strip()}**")
        parts.append(f"*Answer: {qa.answer.strip()}*")
        parts.append("")
    return "\n".join(parts).rstrip()


def _long_answer_section(analysis: DocumentAnalysis) -> str:
    if not analysis.long_answer_questions:
        return "- No long answer questions generated."
    parts: list[str] = []
    for i, qa in enumerate(analysis.long_answer_questions, 1):
        parts.append(f"**{i}. {qa.question.strip()}**")
        parts.append("")
        parts.append(qa.answer.strip())
        parts.append("")
    return "\n".join(parts).rstrip()


def _revision_notes_section(analysis: DocumentAnalysis) -> str:
    if not analysis.revision_notes:
        return "- No revision notes generated."
    parts: list[str] = []
    for note in analysis.revision_notes:
        parts.append(f"### {note.heading.strip()}")
        parts.append("")
        for point in note.points:
            parts.append(f"- {point.strip()}")
        parts.append("")
    return "\n".join(parts).rstrip()


def _tags_section(tags: list[str]) -> str:
    if not tags:
        return "- No tags generated."
    return "\n".join(f"- #{tag}" for tag in tags)


def _metadata_section(meta: ExtractedMetadata) -> str:
    lines: list[str] = []
    if meta.author:
        lines.append(f"- **Author:** {meta.author}")
    if meta.word_count:
        lines.append(f"- **Word Count:** {meta.word_count:,}")
    if meta.page_count:
        lines.append(f"- **Page Count:** {meta.page_count}")
    if meta.language:
        lines.append(f"- **Language:** {meta.language}")
    if meta.source_url:
        lines.append(f"- **Source URL:** {meta.source_url}")
    if meta.creation_date:
        lines.append(f"- **Creation Date:** {meta.creation_date}")
    if meta.publisher:
        lines.append(f"- **Publisher:** {meta.publisher}")
    if meta.version:
        lines.append(f"- **Version:** {meta.version}")
    if meta.license:
        lines.append(f"- **License:** {meta.license}")
    return "\n".join(lines) if lines else "- No metadata extracted."


def _references_section(
    document: SourceDocument,
    generated_at: datetime,
    ocr_confidence: float | None,
    processing_confidence: float | None,
) -> str:
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
    if ocr_confidence is not None:
        lines.append(f"- OCR Confidence: {ocr_confidence:.0%}")
    if processing_confidence is not None:
        lines.append(f"- Processing Confidence: {processing_confidence:.0%}")

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
