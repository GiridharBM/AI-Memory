"""Tests for Document Intelligence features — Milestone 3."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.analysis import (
    Definition,
    DocumentAnalysis,
    DocumentSummary,
    Flashcard,
    ImportantEntity,
    KeyConcept,
    LongAnswerQuestion,
    MultipleChoiceQuestion,
    QuestionAnswer,
    RelatedTopic,
    RevisionNote,
    ShortAnswerQuestion,
)
from app.domain.documents import DocumentMetadata, SourceDocument
from app.templates.obsidian_note import ObsidianMarkdownGenerator


def _doc() -> SourceDocument:
    return SourceDocument(
        source="test.md",
        source_path=None,
        source_type="markdown",
        filename="test.md",
        text="Some content",
        metadata=DocumentMetadata(title="Test"),
    )


def _full_analysis() -> DocumentAnalysis:
    return DocumentAnalysis(
        suggested_note_title="Test Note",
        summary=DocumentSummary(short="Short.", detailed="Detailed."),
        keywords=["python", "testing"],
        categories=["Programming", "Quality Assurance"],
        reading_time_minutes=5,
        difficulty="intermediate",
        key_concepts=[KeyConcept(name="Concept A", explanation="Expl A", importance="high")],
        definitions=[Definition(term="Term A", definition="Def A")],
        important_entities=[ImportantEntity(name="Entity A", type="technology", description="Desc A")],
        tags=["test", "example"],
        related_topics=[RelatedTopic(topic="Topic B", reason="Reason B")],
        suggested_related_notes=["Related Note 1", "Related Note 2"],
        suggested_backlinks=["Backlink Note 1"],
        questions_and_answers=[QuestionAnswer(question="Q1?", answer="A1")],
        flashcards=[Flashcard(front="Front 1", back="Back 1")],
        multiple_choice_questions=[
            MultipleChoiceQuestion(
                question="MCQ 1?",
                options=["A", "B", "C", "D"],
                correct_answer="B",
                explanation="Because.",
            ),
        ],
        short_answer_questions=[ShortAnswerQuestion(question="SAQ 1?", answer="SA 1")],
        long_answer_questions=[LongAnswerQuestion(question="LAQ 1?", answer="LA answer 1")],
        revision_notes=[RevisionNote(heading="Rev 1", points=["Point 1", "Point 2"])],
    )


# ── DocumentAnalysis model ─────────────────────────────────────────────


class TestDocumentAnalysisModel:
    def test_new_fields_defaults(self) -> None:
        analysis = DocumentAnalysis(
            suggested_note_title="Title",
            summary=DocumentSummary(short="s", detailed="d"),
        )
        assert analysis.keywords == []
        assert analysis.categories == []
        assert analysis.reading_time_minutes == 0
        assert analysis.difficulty == "intermediate"
        assert analysis.suggested_related_notes == []
        assert analysis.suggested_backlinks == []
        assert analysis.questions_and_answers == []
        assert analysis.flashcards == []
        assert analysis.multiple_choice_questions == []
        assert analysis.short_answer_questions == []
        assert analysis.long_answer_questions == []
        assert analysis.revision_notes == []

    def test_keywords_validator(self) -> None:
        analysis = DocumentAnalysis(
            suggested_note_title="Title",
            summary=DocumentSummary(short="s", detailed="d"),
            keywords=["Python", "python", "TESTING", ""],
        )
        assert analysis.keywords == ["python", "testing"]

    def test_categories_validator(self) -> None:
        analysis = DocumentAnalysis(
            suggested_note_title="Title",
            summary=DocumentSummary(short="s", detailed="d"),
            categories=["science", "Science", "SCIENCE"],
        )
        assert analysis.categories == ["Science"]

    def test_full_analysis_roundtrip(self) -> None:
        a = _full_analysis()
        assert len(a.keywords) == 2
        assert len(a.categories) == 2
        assert a.reading_time_minutes == 5
        assert a.difficulty == "intermediate"
        assert len(a.flashcards) == 1
        assert len(a.multiple_choice_questions) == 1
        assert len(a.revision_notes) == 1


# ── ObsidianMarkdownGenerator ──────────────────────────────────────────


class TestGeneratorKeywords:
    def test_keywords_section_rendered(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "## Keywords" in note.markdown
        assert "`python`" in note.markdown
        assert "`testing`" in note.markdown

    def test_keywords_absent_when_empty(self) -> None:
        gen = ObsidianMarkdownGenerator()
        a = _full_analysis()
        a.keywords = []
        note = gen.generate(document=_doc(), analysis=a)
        assert "## Keywords" not in note.markdown


class TestGeneratorCategories:
    def test_categories_section_rendered(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "## Categories" in note.markdown
        assert "Programming" in note.markdown

    def test_categories_absent_when_empty(self) -> None:
        gen = ObsidianMarkdownGenerator()
        a = _full_analysis()
        a.categories = []
        note = gen.generate(document=_doc(), analysis=a)
        assert "## Categories" not in note.markdown


class TestGeneratorReadingTime:
    def test_reading_time_in_frontmatter(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "reading_time_minutes: 5" in note.markdown


class TestGeneratorDifficulty:
    def test_difficulty_in_frontmatter(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert 'difficulty: "intermediate"' in note.markdown


class TestGeneratorQA:
    def test_qa_section_rendered(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "## Frequently Asked Questions" in note.markdown
        assert "Q1: Q1?" in note.markdown
        assert "A1: A1" in note.markdown

    def test_qa_absent_when_empty(self) -> None:
        gen = ObsidianMarkdownGenerator()
        a = _full_analysis()
        a.questions_and_answers = []
        note = gen.generate(document=_doc(), analysis=a)
        assert "## Frequently Asked Questions" not in note.markdown


class TestGeneratorFlashcards:
    def test_flashcards_section_rendered(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "## Flashcards" in note.markdown
        assert "Front 1" in note.markdown
        assert "Back 1" in note.markdown

    def test_flashcards_absent_when_empty(self) -> None:
        gen = ObsidianMarkdownGenerator()
        a = _full_analysis()
        a.flashcards = []
        note = gen.generate(document=_doc(), analysis=a)
        assert "## Flashcards" not in note.markdown


class TestGeneratorMCQ:
    def test_mcq_section_rendered(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "## Multiple Choice Questions" in note.markdown
        assert "MCQ 1?" in note.markdown
        assert "[X] B" in note.markdown
        assert "[ ] A" in note.markdown

    def test_mcq_absent_when_empty(self) -> None:
        gen = ObsidianMarkdownGenerator()
        a = _full_analysis()
        a.multiple_choice_questions = []
        note = gen.generate(document=_doc(), analysis=a)
        assert "## Multiple Choice Questions" not in note.markdown


class TestGeneratorShortAnswer:
    def test_short_answer_section_rendered(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "## Short Answer Questions" in note.markdown
        assert "SAQ 1?" in note.markdown
        assert "SA 1" in note.markdown

    def test_short_answer_absent_when_empty(self) -> None:
        gen = ObsidianMarkdownGenerator()
        a = _full_analysis()
        a.short_answer_questions = []
        note = gen.generate(document=_doc(), analysis=a)
        assert "## Short Answer Questions" not in note.markdown


class TestGeneratorLongAnswer:
    def test_long_answer_section_rendered(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "## Long Answer Questions" in note.markdown
        assert "LAQ 1?" in note.markdown
        assert "LA answer 1" in note.markdown

    def test_long_answer_absent_when_empty(self) -> None:
        gen = ObsidianMarkdownGenerator()
        a = _full_analysis()
        a.long_answer_questions = []
        note = gen.generate(document=_doc(), analysis=a)
        assert "## Long Answer Questions" not in note.markdown


class TestGeneratorRevisionNotes:
    def test_revision_notes_section_rendered(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "## Revision Notes" in note.markdown
        assert "### Rev 1" in note.markdown
        assert "- Point 1" in note.markdown
        assert "- Point 2" in note.markdown

    def test_revision_notes_absent_when_empty(self) -> None:
        gen = ObsidianMarkdownGenerator()
        a = _full_analysis()
        a.revision_notes = []
        note = gen.generate(document=_doc(), analysis=a)
        assert "## Revision Notes" not in note.markdown


class TestGeneratorRelatedNotes:
    def test_related_notes_rendered(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "## Suggested Related Notes" in note.markdown
        assert "[[Related Note 1]]" in note.markdown

    def test_related_notes_absent_when_empty(self) -> None:
        gen = ObsidianMarkdownGenerator()
        a = _full_analysis()
        a.suggested_related_notes = []
        note = gen.generate(document=_doc(), analysis=a)
        assert "## Suggested Related Notes" not in note.markdown


class TestGeneratorBacklinks:
    def test_backlinks_rendered(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "## Suggested Backlinks" in note.markdown
        assert "[[Backlink Note 1]]" in note.markdown

    def test_backlinks_absent_when_empty(self) -> None:
        gen = ObsidianMarkdownGenerator()
        a = _full_analysis()
        a.suggested_backlinks = []
        note = gen.generate(document=_doc(), analysis=a)
        assert "## Suggested Backlinks" not in note.markdown


class TestGeneratorConfidence:
    def test_confidence_in_frontmatter(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(
            document=_doc(),
            analysis=_full_analysis(),
            ocr_confidence=0.92,
            processing_confidence=0.88,
        )
        assert "ocr_confidence: 0.92" in note.markdown
        assert "processing_confidence: 0.88" in note.markdown

    def test_confidence_in_references(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(
            document=_doc(),
            analysis=_full_analysis(),
            ocr_confidence=0.92,
            processing_confidence=0.88,
        )
        assert "OCR Confidence: 92%" in note.markdown
        assert "Processing Confidence: 88%" in note.markdown

    def test_no_confidence_when_none(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "ocr_confidence" not in note.markdown
        assert "processing_confidence" not in note.markdown


class TestExistingFeaturesUnchanged:
    def test_summary_present(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "## Summary" in note.markdown
        assert "Short." in note.markdown
        assert "Detailed." in note.markdown

    def test_toc_present(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "## Table of Contents" in note.markdown
        assert "[[#Key Concepts|Key Concepts]]" in note.markdown
        assert "[[#Tags|Tags]]" in note.markdown

    def test_toc_dynamic_entries(self) -> None:
        gen = ObsidianMarkdownGenerator()
        a = _full_analysis()
        a.flashcards = []
        a.revision_notes = []
        note = gen.generate(document=_doc(), analysis=a)
        toc_section = note.markdown.split("## Table of Contents")[1].split("\n## ")[0]
        assert "Flashcards" not in toc_section
        assert "Revision Notes" not in toc_section

    def test_key_concepts_present(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "## Key Concepts" in note.markdown
        assert "[[Concept A]]" in note.markdown

    def test_definitions_present(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "## Definitions" in note.markdown
        assert "[[Term A]]" in note.markdown

    def test_tags_present(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "## Tags" in note.markdown
        assert "#test" in note.markdown

    def test_references_present(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert "## References" in note.markdown
        assert "Source: test.md" in note.markdown

    def test_frontmatter_present(self) -> None:
        gen = ObsidianMarkdownGenerator()
        note = gen.generate(document=_doc(), analysis=_full_analysis())
        assert note.markdown.startswith("---")
        assert 'title: "Test Note"' in note.markdown
