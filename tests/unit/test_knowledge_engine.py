"""Tests for the Knowledge Engine (Milestone 4) features."""

from __future__ import annotations

from pathlib import Path

import pytest

import app.infrastructure.sentence_tokenizer as sentence_tokenizer_mod
from app.domain.analysis import (
    Definition,
    DocumentAnalysis,
    DocumentSummary,
    ImportantEntity,
    KeyConcept,
    RelatedTopic,
)
from app.domain.knowledge_graph import (
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
)
from app.domain.semantic_chunking import DocumentChunk
from app.domain.vector_store import SearchResult, VectorEntry
from app.infrastructure.embeddings import EmbeddingResult
from app.infrastructure.knowledge_graph import KnowledgeGraphBuilder
from app.infrastructure.search import HybridSearch, SearchService, SemanticSearch
from app.infrastructure.semantic_chunking import ChunkingPolicy, SemanticChunker
from app.infrastructure.vector_store import VectorStore, _cosine_similarity

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _analysis() -> DocumentAnalysis:
    return DocumentAnalysis(
        suggested_note_title="Test Note",
        summary=DocumentSummary(short="Short", detailed="Long"),
        keywords=["python", "testing"],
        categories=["Programming"],
        reading_time_minutes=5,
        difficulty="beginner",
        key_concepts=[
            KeyConcept(name="Pytest", explanation="Testing framework", importance="high"),
            KeyConcept(name="Coverage", explanation="Code coverage", importance="medium"),
        ],
        definitions=[Definition(term="Fixture", definition="Test setup helper")],
        important_entities=[
            ImportantEntity(name="Python", type="technology", description="Programming language"),
        ],
        tags=["test"],
        related_topics=[RelatedTopic(topic="TDD", reason="Related methodology")],
        suggested_related_notes=["Other Note"],
        suggested_backlinks=["Parent Note"],
    )


def _embedding(dims: int = 8) -> list[float]:
    return [float(i) / dims for i in range(dims)]


def _similar_embedding(dims: int = 8) -> list[float]:
    return [float(i + 0.1) / dims for i in range(dims)]


# ---------------------------------------------------------------------------
# Semantic Chunking
# ---------------------------------------------------------------------------

class TestSemanticChunking:
    def test_empty_text_returns_no_chunks(self) -> None:
        chunker = SemanticChunker()
        chunks = chunker.chunk("", "test.md", "markdown")
        assert chunks == []

    def test_short_text_single_chunk(self) -> None:
        chunker = SemanticChunker()
        chunks = chunker.chunk("Hello world", "test.md", "markdown")
        assert len(chunks) == 1
        assert chunks[0].text == "Hello world"
        assert chunks[0].source == "test.md"
        assert chunks[0].chunk_index == 0

    def test_heading_based_splitting(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=200)
        text = "# Title\n\nFirst section.\n\n## Subtitle\n\nSecond section."
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) >= 2

    def test_long_text_splits_by_size(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=100)
        text = ". ".join(f"Sentence {i}" for i in range(50))
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) > 1

    def test_chunk_ids_are_unique(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=50)
        text = ". ".join(f"Sentence {i}" for i in range(20))
        chunks = chunker.chunk(text, "test.md", "markdown")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_metadata_preserves_source(self) -> None:
        chunker = SemanticChunker()
        chunks = chunker.chunk("Content", "doc.pdf", "pdf")
        assert chunks[0].source_type == "pdf"

    def test_overlap_chars(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=50, overlap_chars=10)
        text = ". ".join(f"Sentence {i}" for i in range(30))
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) > 1

    def test_chunk_overlap_produces_shared_text(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=300, overlap_chars=200)
        text = ". ".join(f"Sentence {i}" for i in range(50))
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) >= 2
        for previous, current in zip(chunks, chunks[1:], strict=False):
            assert previous.text[-200:] == current.text[:200]

    def test_chunk_overlap_single_chunk(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=2000, overlap_chars=200)
        chunks = chunker.chunk("Short text.", "test.md", "markdown")
        assert len(chunks) == 1
        assert chunks[0].text == "Short text."

    def test_chunk_overlap_uses_original_predecessor(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=5, overlap_chars=8)
        text = "AAAA. BBBB. CCCC. DDDD."
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) == 4
        assert chunks[1].text == "AAAA.BBBB."
        assert chunks[2].text == "BBBB.CCCC."
        assert chunks[3].text == "CCCC.DDDD."

    def test_chunk_overlap_offsets_preserved(self) -> None:
        text = ". ".join(f"Sentence {i}" for i in range(30))
        plain = SemanticChunker(max_chunk_chars=50, overlap_chars=0)
        overlapped = SemanticChunker(max_chunk_chars=50, overlap_chars=10)
        plain_chunks = plain.chunk(text, "test.md", "markdown")
        overlap_chunks = overlapped.chunk(text, "test.md", "markdown")
        assert len(plain_chunks) > 1
        assert [(c.start_char, c.end_char) for c in plain_chunks] == [
            (c.start_char, c.end_char) for c in overlap_chunks
        ]
        assert overlap_chunks[0].text == plain_chunks[0].text

    def test_chunk_overlap_zero(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=50, overlap_chars=0)
        text = ". ".join(f"Sentence {i}" for i in range(30))
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) > 1
        for previous, current in zip(chunks, chunks[1:], strict=False):
            assert not current.text.startswith(previous.text[-1:])

    def test_sentence_aligned_chunks_ac1_fixture(self) -> None:
        """P3-104 AC: an over-long AC1 paragraph splits into exactly 2
        sentence-aligned chunks, not the old regex's 3 or a naive 6."""
        chunker = SemanticChunker(max_chunk_chars=20, overlap_chars=0)
        text = "Dr. Smith went to Washington. He arrived at 9:00 a.m."
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) == 2
        assert chunks[0].text == "Dr. Smith went to Washington."
        assert chunks[1].text == "He arrived at 9:00 a.m."

    def test_sentence_chunk_offsets_accurate_single_spaces(self) -> None:
        """P3-104: start_char/end_char are contiguous across a multi-chunk long
        paragraph and consistent with each chunk's length (D5a offset math)."""
        chunker = SemanticChunker(max_chunk_chars=40, overlap_chars=0)
        text = (
            "Dr. Smith went to Washington. He arrived at 9:00 a.m. "
            "The meeting lasted an hour. Everyone agreed."
        )
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert [c.text for c in chunks] == [
            "Dr. Smith went to Washington.",
            "He arrived at 9:00 a.m.",
            "The meeting lasted an hour.",
            "Everyone agreed.",
        ]
        assert chunks[0].start_char == 0
        for previous, current in zip(chunks, chunks[1:], strict=False):
            assert previous.end_char == current.start_char
        for chunk in chunks:
            assert chunk.end_char == chunk.start_char + len(chunk.text)

    def test_heuristic_engine_deterministic(self) -> None:
        """P3-104: sentence_tokenizer="heuristic" resolves once and chunking
        is deterministic across calls."""
        text = ". ".join(f"Sentence {i}" for i in range(30))
        first = SemanticChunker(max_chunk_chars=50, sentence_tokenizer="heuristic").chunk(
            text, "test.md", "markdown"
        )
        second = SemanticChunker(max_chunk_chars=50, sentence_tokenizer="heuristic").chunk(
            text, "test.md", "markdown"
        )
        assert [(c.text, c.start_char, c.end_char) for c in first] == [
            (c.text, c.start_char, c.end_char) for c in second
        ]


_NLTK_REGISTERED = "nltk" in sentence_tokenizer_mod._ENGINE_REGISTRY
_NLTK_SKIP_REASON = (
    "nltk punkt_tab engine unavailable "
    "(pip install nltk, then nltk.download('punkt_tab'))"
)


class TestSemanticChunkingAllEnginePaths(TestSemanticChunking):
    """P3-106 R-2: the full existing TestSemanticChunking suite re-run under
    every sentence-tokenizer engine path (heuristic, nltk, auto).

    The parent class is left untouched and runs with the default ``"auto"``
    selection; this subclass re-executes the same tests with the engine forced
    via a monkeypatched constructor default. The nltk path is skipped when the
    optional extra is absent (import-guarded).
    """

    @pytest.fixture(autouse=True, params=["heuristic", "nltk", "auto"])
    def _inject_engine(
        self, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = request.param
        if engine == "nltk" and not _NLTK_REGISTERED:
            pytest.skip(_NLTK_SKIP_REASON)
        original_init = SemanticChunker.__init__

        def _init_with_engine(self_, *args: object, **kwargs: object) -> None:
            kwargs.setdefault("sentence_tokenizer", engine)
            original_init(self_, *args, **kwargs)

        monkeypatch.setattr(SemanticChunker, "__init__", _init_with_engine)

    def test_sentence_chunk_offsets_accurate_single_spaces(self) -> None:
        """Engine-aware R-2 variant of the parent offset test.

        The parent test (unchanged, runs under the default ``"auto"`` engine)
        asserts NLTK's segmentation of the ``a.m.`` + capitalized sentence
        boundary. The heuristic engine keeps ``a.m.`` with its sentence per the
        abbreviation rule (D7), so this re-run asserts each engine's own
        spec-correct segmentation while keeping the same D5a offset math
        (contiguous ``start_char``/``end_char``, accurate per-chunk length).
        """
        chunker = SemanticChunker(max_chunk_chars=40, overlap_chars=0)
        text = (
            "Dr. Smith went to Washington. He arrived at 9:00 a.m. "
            "The meeting lasted an hour. Everyone agreed."
        )
        chunks = chunker.chunk(text, "test.md", "markdown")
        if type(chunker._tokenizer).__name__ == "_NltkSentenceTokenizer":
            assert [c.text for c in chunks] == [
                "Dr. Smith went to Washington.",
                "He arrived at 9:00 a.m.",
                "The meeting lasted an hour.",
                "Everyone agreed.",
            ]
        else:
            assert [c.text for c in chunks] == [
                "Dr. Smith went to Washington.",
                "He arrived at 9:00 a.m. The meeting lasted an hour.",
                "Everyone agreed.",
            ]
        assert chunks[0].start_char == 0
        for previous, current in zip(chunks, chunks[1:], strict=False):
            assert previous.end_char == current.start_char
        for chunk in chunks:
            assert chunk.end_char == chunk.start_char + len(chunk.text)


# ---------------------------------------------------------------------------
# P3-201 Hierarchical Chunking (heading hierarchy metadata)
# ---------------------------------------------------------------------------

class TestHierarchicalChunking:
    """P3-201: every chunk carries heading hierarchy metadata.

    Heading-led sections attach ``heading`` (own title), ``heading_level``
    (ATX depth 1-6), ``heading_path`` (root-to-own chain), and
    ``parent_heading`` (immediate parent title, "" at root). Preamble and
    heading-less text keep the Phase 3.1 empty-metadata behavior.
    """

    def test_no_headings_leaves_metadata_empty(self) -> None:
        chunks = SemanticChunker().chunk("Just a paragraph.", "test.md", "markdown")
        assert len(chunks) == 1
        assert chunks[0].metadata == {}

    def test_single_heading_root(self) -> None:
        chunks = SemanticChunker().chunk("# Title\n\nBody.", "test.md", "markdown")
        assert len(chunks) == 1
        assert chunks[0].metadata == {
            "heading": "Title",
            "heading_level": "1",
            "heading_path": "Title",
            "parent_heading": "",
        }

    def test_nested_heading_path_and_parent(self) -> None:
        text = "# Top\n\n## Middle\n\n### Leaf\n\nContent."
        chunks = SemanticChunker().chunk(text, "test.md", "markdown")
        assert [c.metadata["heading"] for c in chunks] == ["Top", "Middle", "Leaf"]
        assert [c.metadata["heading_level"] for c in chunks] == ["1", "2", "3"]
        assert [c.metadata["heading_path"] for c in chunks] == [
            "Top",
            "Top/Middle",
            "Top/Middle/Leaf",
        ]
        assert [c.metadata["parent_heading"] for c in chunks] == ["", "Top", "Middle"]

    def test_sibling_headings_reset_parent(self) -> None:
        text = "# A\n\n## A1\n\n## A2\n\n# B\n\n## B1"
        chunks = SemanticChunker().chunk(text, "test.md", "markdown")
        assert [(c.metadata["heading_path"], c.metadata["parent_heading"]) for c in chunks] == [
            ("A", ""),
            ("A/A1", "A"),
            ("A/A2", "A"),
            ("B", ""),
            ("B/B1", "B"),
        ]

    def test_level_skip_parents_to_nearest_lower(self) -> None:
        text = "# A\n\n### C\n\n## D"
        chunks = SemanticChunker().chunk(text, "test.md", "markdown")
        assert [(c.metadata["heading"], c.metadata["parent_heading"]) for c in chunks] == [
            ("A", ""),
            ("C", "A"),
            ("D", "A"),
        ]

    def test_preamble_chunk_has_no_heading_metadata(self) -> None:
        text = "Preamble.\n\n# Title\n\nBody."
        chunks = SemanticChunker().chunk(text, "test.md", "markdown")
        assert chunks[0].metadata == {}
        assert chunks[1].metadata["heading"] == "Title"

    def test_sub_chunks_inherit_heading_metadata(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=100, overlap_chars=0)
        text = "# Long Section\n\n" + "\n\n".join(
            f"Paragraph {i}: " + "words " * 20 for i in range(4)
        )
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.metadata["heading"] == "Long Section"
            assert chunk.metadata["heading_path"] == "Long Section"

    def test_heading_metadata_deterministic(self) -> None:
        text = "# A\n\n## B\n\n### C\n\nBody."
        first = SemanticChunker().chunk(text, "test.md", "markdown")
        second = SemanticChunker().chunk(text, "test.md", "markdown")
        assert [c.metadata for c in first] == [c.metadata for c in second]

    def test_overlap_preserves_heading_metadata(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=100, overlap_chars=20)
        text = "# Section\n\n" + ". ".join(f"Sentence {i}" for i in range(40))
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.metadata["heading"] == "Section"


# ---------------------------------------------------------------------------
# P3-202 List-Aware Chunking (paragraph / list block boundaries)
# ---------------------------------------------------------------------------

class TestListAwareChunking:
    """P3-202: paragraphs and list blocks stay intact; over-long lists split at
    whole-item boundaries, never inside an item or via sentence splitting."""

    def test_short_unordered_list_stays_intact(self) -> None:
        text = "- Alpha\n- Beta\n- Gamma"
        chunks = SemanticChunker().chunk(text, "test.md", "markdown")
        assert len(chunks) == 1
        assert chunks[0].text == text

    def test_short_ordered_list_stays_intact(self) -> None:
        text = "1. Alpha\n2. Beta\n3. Gamma"
        chunks = SemanticChunker().chunk(text, "test.md", "markdown")
        assert len(chunks) == 1
        assert chunks[0].text == text

    def test_nested_list_stays_intact(self) -> None:
        text = "- Parent\n  - Child one\n  - Child two\n- Sibling"
        chunks = SemanticChunker().chunk(text, "test.md", "markdown")
        assert len(chunks) == 1
        assert chunks[0].text == text

    def test_blank_line_inside_short_list_stays_intact(self) -> None:
        text = "- Alpha\n\n- Beta"
        chunks = SemanticChunker().chunk(text, "test.md", "markdown")
        assert len(chunks) == 1
        assert chunks[0].text == text

    def test_long_list_splits_at_item_boundaries(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=30, overlap_chars=0)
        chunks = chunker.chunk(
            "- item one\n- item two\n- item three\n- item four",
            "test.md",
            "markdown",
        )
        assert [c.text for c in chunks] == [
            "- item one\n- item two",
            "- item three\n- item four",
        ]

    def test_blank_line_inside_list_never_fragmented(self) -> None:
        chunker = SemanticChunker(
            max_chunk_chars=25,
            overlap_chars=0,
            sentence_tokenizer="heuristic",
        )
        chunks = chunker.chunk(
            "- Alpha has two sentences here. Second one.\n\n"
            "- Beta has two sentences here. Third one.",
            "test.md",
            "markdown",
        )
        assert [c.text for c in chunks] == [
            "- Alpha has two sentences here. Second one.",
            "- Beta has two sentences here. Third one.",
        ]

    def test_long_list_never_sentence_splits_items(self) -> None:
        chunker = SemanticChunker(
            max_chunk_chars=90,
            overlap_chars=0,
            sentence_tokenizer="heuristic",
        )
        items = [
            "- Alpha has two sentences here. Second one.",
            "- Beta has two sentences here. Second one.",
            "- Gamma has two sentences here. Second one.",
        ]
        chunks = chunker.chunk("\n".join(items), "test.md", "markdown")
        assert len(chunks) == 2
        for chunk in chunks:
            for line in chunk.text.split("\n"):
                assert line in items

    def test_nested_items_never_split_from_parent(self) -> None:
        chunker = SemanticChunker(
            max_chunk_chars=30,
            overlap_chars=0,
            sentence_tokenizer="heuristic",
        )
        chunks = chunker.chunk(
            "- Parent one\n"
            "  - Child one\n"
            "  - Child two\n"
            "- Parent two\n"
            "  - Child three",
            "test.md",
            "markdown",
        )
        assert [c.text for c in chunks] == [
            "- Parent one\n  - Child one\n  - Child two",
            "- Parent two\n  - Child three",
        ]

    def test_list_chunk_offsets_contiguous_and_accurate(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=30, overlap_chars=0)
        chunks = chunker.chunk(
            "- item one\n- item two\n- item three\n- item four",
            "test.md",
            "markdown",
        )
        assert chunks[0].start_char == 0
        for previous, current in zip(chunks, chunks[1:], strict=False):
            assert previous.end_char == current.start_char
        for chunk in chunks:
            assert chunk.end_char == chunk.start_char + len(chunk.text)

    def test_list_chunking_deterministic(self) -> None:
        text = "- A\n- B\n  - nested\n- C\n1. one\n2. two\n3. three"
        first = SemanticChunker(max_chunk_chars=25, overlap_chars=0).chunk(
            text, "test.md", "markdown"
        )
        second = SemanticChunker(max_chunk_chars=25, overlap_chars=0).chunk(
            text, "test.md", "markdown"
        )
        assert [(c.text, c.start_char, c.end_char) for c in first] == [
            (c.text, c.start_char, c.end_char) for c in second
        ]

    def test_paragraph_followed_by_list_never_merged(self) -> None:
        chunker = SemanticChunker(
            max_chunk_chars=12,
            overlap_chars=0,
            sentence_tokenizer="heuristic",
        )
        chunks = chunker.chunk("para text\n- item", "test.md", "markdown")
        assert [c.text for c in chunks] == ["para text", "- item"]

    def test_fit_block_starts_new_chunk_after_flush(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=30, overlap_chars=0)
        chunks = chunker.chunk("P" * 28 + "\n\n" + "Q" * 25, "test.md", "markdown")
        assert [c.text for c in chunks] == ["P" * 28, "Q" * 25]

    def test_split_list_block_empty_text(self) -> None:
        assert SemanticChunker()._split_list_block("", 0) == []


# ---------------------------------------------------------------------------
# P3-203 Code-Aware Chunking (fenced code blocks, language, inline code)
# ---------------------------------------------------------------------------

class TestCodeAwareChunking:
    """P3-203: fenced code blocks are atomic (never split, never merged with
    prose), keep their language metadata and indentation verbatim; inline code
    spans survive sentence splitting."""

    def test_fenced_code_block_never_split(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=20, overlap_chars=0)
        text = "```python\nx = 1\n\ny = 2\n```"
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) == 1
        assert chunks[0].text == text

    def test_fenced_code_language_metadata(self) -> None:
        chunks = SemanticChunker().chunk(
            "```python\nprint('hi')\n```", "test.md", "markdown"
        )
        assert chunks[0].metadata["language"] == "python"

    def test_bare_fence_language_empty(self) -> None:
        chunks = SemanticChunker().chunk(
            "```\ncode\n```", "test.md", "markdown"
        )
        assert chunks[0].metadata["language"] == ""

    def test_fence_language_from_info_string(self) -> None:
        chunks = SemanticChunker().chunk(
            '```python linenums="1"\nprint(1)\n```', "test.md", "markdown"
        )
        assert chunks[0].metadata["language"] == "python"

    def test_tilde_fence_supported(self) -> None:
        chunks = SemanticChunker().chunk(
            '~~~json\n{"a": 1}\n~~~', "test.md", "markdown"
        )
        assert chunks[0].metadata["language"] == "json"
        assert chunks[0].text == '~~~json\n{"a": 1}\n~~~'

    def test_overlong_code_block_not_split(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=30, overlap_chars=0)
        code = "```\n" + "".join(f"line {n}\n" for n in range(40)) + "```"
        chunks = chunker.chunk(code, "test.md", "markdown")
        assert len(chunks) == 1
        assert chunks[0].text == code
        assert len(chunks[0].text) > 30

    def test_code_block_isolated_from_prose(self) -> None:
        chunks = SemanticChunker().chunk(
            "Prose intro.\n\n```python\nx = 1\n```\n\nOutro text.",
            "test.md",
            "markdown",
        )
        assert [c.text for c in chunks] == [
            "Prose intro.",
            "```python\nx = 1\n```",
            "Outro text.",
        ]
        assert "language" in chunks[1].metadata
        assert "language" not in chunks[0].metadata
        assert "language" not in chunks[2].metadata

    def test_unclosed_fence_runs_to_end(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=20, overlap_chars=0)
        text = "```python\nline one\n\nline two\nmore code"
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) == 1
        assert chunks[0].text == text

    def test_code_preserves_indentation(self) -> None:
        code = "```python\ndef f():\n    return 1\n        nested\n```"
        chunks = SemanticChunker().chunk(code, "test.md", "markdown")
        assert chunks[0].text == code

    def test_fence_breaks_paragraph_run(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=60, overlap_chars=0)
        text = "Some prose line.\n```\ncode\n```"
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert [c.text for c in chunks] == [
            "Some prose line.",
            "```\ncode\n```",
        ]
        assert chunks[1].metadata["language"] == ""

    def test_code_chunk_offsets_contiguous(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=20, overlap_chars=0)
        chunks = chunker.chunk(
            "Prose intro.\n\n```python\nx = 1\n```\n\nOutro text.",
            "test.md",
            "markdown",
        )
        assert chunks[0].start_char == 0
        for previous, current in zip(chunks, chunks[1:], strict=False):
            assert previous.end_char == current.start_char
        for chunk in chunks:
            assert chunk.end_char == chunk.start_char + len(chunk.text)

    def test_overlap_skipped_across_code_chunks(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=40, overlap_chars=10)
        text = "P" * 30 + "\n\n```\nCODE\n```\n\n" + "R" * 30
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert chunks[0].text == "P" * 30
        assert chunks[1].text == "```\nCODE\n```"
        assert chunks[2].text == "R" * 30

    def test_inline_code_not_sentence_split(self) -> None:
        chunker = SemanticChunker(
            max_chunk_chars=60,
            overlap_chars=0,
            sentence_tokenizer="heuristic",
        )
        marked = "`note. separate`"
        paragraph = "A" * 25 + " " + marked + " " + "B" * 25
        assert len(paragraph) > 60
        chunks = chunker.chunk(paragraph, "test.md", "markdown")
        assert len(chunks) == 1
        assert chunks[0].text == paragraph

    def test_code_chunk_keeps_heading_metadata(self) -> None:
        chunks = SemanticChunker().chunk(
            "# Setup\n\n```python\nx = 1\n```",
            "test.md",
            "markdown",
        )
        assert chunks[-1].metadata["heading"] == "Setup"
        assert chunks[-1].metadata["language"] == "python"

    def test_code_chunking_deterministic(self) -> None:
        text = (
            "Intro.\n\n```python\nx = 1\n\ny = 2\n```\n\n"
            "More prose here.\n\n~~~js\nconst a = 1;\n~~~"
        )
        first = SemanticChunker(max_chunk_chars=40, overlap_chars=0).chunk(
            text, "test.md", "markdown"
        )
        second = SemanticChunker(max_chunk_chars=40, overlap_chars=0).chunk(
            text, "test.md", "markdown"
        )
        assert [(c.text, c.start_char, c.end_char, c.metadata) for c in first] == [
            (c.text, c.start_char, c.end_char, c.metadata) for c in second
        ]


# ---------------------------------------------------------------------------
# P3-204 Structured Content Chunking (tables, blockquotes, callouts, definitions)
# ---------------------------------------------------------------------------

class TestStructuredContentChunking:
    """P3-204: markdown/HTML tables, blockquotes, callouts, and definition lists
    are atomic chunks — never split, never sentence-split, never merged with
    surrounding prose, and kept byte-for-byte."""

    _TABLE = "| Name | Value |\n|---|---|\n| alpha | 1 |\n| beta | 2 |"

    def test_markdown_table_preserved_verbatim(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=20, overlap_chars=0)
        chunks = chunker.chunk(self._TABLE, "test.md", "markdown")
        assert len(chunks) == 1
        assert chunks[0].text == self._TABLE
        assert chunks[0].metadata["structure_type"] == "table"

    def test_markdown_table_isolated_from_prose(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=20, overlap_chars=0)
        chunks = chunker.chunk(
            "Intro prose here.\n\n" + self._TABLE + "\n\nOutro prose here.",
            "test.md",
            "markdown",
        )
        assert [c.text for c in chunks] == [
            "Intro prose here.",
            self._TABLE,
            "Outro prose here.",
        ]
        assert chunks[1].metadata["structure_type"] == "table"
        assert "structure_type" not in chunks[0].metadata
        assert "structure_type" not in chunks[2].metadata

    def test_pipe_run_without_separator_is_paragraph(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=200, overlap_chars=0)
        chunks = chunker.chunk("| a | b |\n| c | d |", "test.md", "markdown")
        assert "structure_type" not in chunks[0].metadata
        assert chunks[0].text == "| a | b |\n| c | d |"

    def test_html_table_preserved_verbatim(self) -> None:
        html = (
            "<table>\n  <tr><td>a</td><td>b</td></tr>\n"
            "  <tr><td>1</td><td>2</td></tr>\n</table>"
        )
        chunks = SemanticChunker(max_chunk_chars=20, overlap_chars=0).chunk(
            html, "test.md", "markdown"
        )
        assert len(chunks) == 1
        assert chunks[0].text == html
        assert chunks[0].metadata["structure_type"] == "html_table"

    def test_html_table_single_line_atomic(self) -> None:
        html = "<table><tr><td>x</td></tr></table>"
        chunks = SemanticChunker().chunk(html, "test.md", "markdown")
        assert len(chunks) == 1
        assert chunks[0].text == html
        assert chunks[0].metadata["structure_type"] == "html_table"

    def test_html_table_unclosed_runs_to_end(self) -> None:
        html = "<table>\n<tr><td>open</td></tr>\nmore markup"
        chunks = SemanticChunker(max_chunk_chars=20, overlap_chars=0).chunk(
            html, "test.md", "markdown"
        )
        assert len(chunks) == 1
        assert chunks[0].text == html
        assert chunks[0].metadata["structure_type"] == "html_table"

    def test_blockquote_preserved_verbatim(self) -> None:
        quote = "> A quoted line one.\n>\n> A quoted line two."
        chunks = SemanticChunker(max_chunk_chars=20, overlap_chars=0).chunk(
            quote, "test.md", "markdown"
        )
        assert len(chunks) == 1
        assert chunks[0].text == quote
        assert chunks[0].metadata["structure_type"] == "blockquote"

    def test_blockquote_not_merged_with_prose(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=60, overlap_chars=0)
        chunks = chunker.chunk(
            "Lead paragraph text.\n\n> A quoted line one.\n>\n> A quoted line two."
            "\n\nTail paragraph text.",
            "test.md",
            "markdown",
        )
        assert [c.text for c in chunks] == [
            "Lead paragraph text.",
            "> A quoted line one.\n>\n> A quoted line two.",
            "Tail paragraph text.",
        ]
        assert chunks[1].metadata["structure_type"] == "blockquote"

    def test_callout_detected_with_type(self) -> None:
        text = "> [!WARNING] Check this carefully.\n> Second callout line."
        chunks = SemanticChunker().chunk(text, "test.md", "markdown")
        assert chunks[0].metadata["structure_type"] == "callout"
        assert chunks[0].metadata["callout_type"] == "warning"
        assert chunks[0].text == text

    def test_callout_type_variants(self) -> None:
        for marker, expected in [
            ("NOTE", "note"),
            ("TIP", "tip"),
            ("Caution", "caution"),
            ("IMPORTANT", "important"),
        ]:
            chunks = SemanticChunker().chunk(
                f"> [!{marker}] body text here.", "test.md", "markdown"
            )
            assert chunks[0].metadata["callout_type"] == expected

    def test_blockquote_without_callout_marker_has_no_type(self) -> None:
        chunks = SemanticChunker().chunk("> plain quote\n> second line", "test.md", "markdown")
        assert chunks[0].metadata["structure_type"] == "blockquote"
        assert "callout_type" not in chunks[0].metadata

    def test_definition_list_preserved(self) -> None:
        text = (
            "Pythonsaurus\n: A large reptile.\n: It lives in swamps.\n"
            "    Continuation here."
        )
        chunks = SemanticChunker(max_chunk_chars=20, overlap_chars=0).chunk(
            text, "test.md", "markdown"
        )
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].metadata["structure_type"] == "definition_list"

    def test_definition_list_over_long_atomic(self) -> None:
        text = "Term\n: " + " ".join(["word"] * 200) + "\n    trailing line"
        chunks = SemanticChunker(max_chunk_chars=30, overlap_chars=0).chunk(
            text, "test.md", "markdown"
        )
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].metadata["structure_type"] == "definition_list"

    def test_definition_list_ends_before_prose(self) -> None:
        chunks = SemanticChunker(max_chunk_chars=20, overlap_chars=0).chunk(
            "Term\n: A definition.\n\nAfter text.", "test.md", "markdown"
        )
        assert [c.text for c in chunks] == ["Term\n: A definition.", "After text."]
        assert chunks[0].metadata["structure_type"] == "definition_list"
        assert "structure_type" not in chunks[1].metadata

    def test_paragraph_term_preceding_definition_not_merged(self) -> None:
        chunks = SemanticChunker(max_chunk_chars=40, overlap_chars=0).chunk(
            "Some prose here.\nTerm\n: A definition.", "test.md", "markdown"
        )
        assert [c.text for c in chunks] == [
            "Some prose here.",
            "Term\n: A definition.",
        ]
        assert chunks[1].metadata["structure_type"] == "definition_list"

    def test_table_never_sentence_split(self) -> None:
        table = (
            "| Sentence. | End. |\n|---|---|\n"
            "| Alpha. Beta. | Gamma. Delta. |"
        )
        chunks = SemanticChunker(max_chunk_chars=10, overlap_chars=0).chunk(
            table, "test.md", "markdown"
        )
        assert len(chunks) == 1
        assert chunks[0].text == table
        assert chunks[0].metadata["structure_type"] == "table"

    def test_overlap_skipped_across_structured_blocks(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=40, overlap_chars=10)
        chunks = chunker.chunk(
            "P" * 30 + "\n\n" + self._TABLE + "\n\n" + "R" * 30,
            "test.md",
            "markdown",
        )
        assert chunks[0].text == "P" * 30
        assert chunks[1].text == self._TABLE
        assert chunks[2].text == "R" * 30

    def test_structured_offsets_contiguous(self) -> None:
        chunker = SemanticChunker(max_chunk_chars=20, overlap_chars=0)
        text = (
            "Prose.\n\n" + self._TABLE + "\n\n> quote\n\n"
            "<table>\n<tr><td>x</td></tr>\n</table>\n\n"
            "Term\n: def"
        )
        chunks = chunker.chunk(text, "test.md", "markdown")
        assert len(chunks) == 5
        assert chunks[0].start_char == 0
        for previous, current in zip(chunks, chunks[1:], strict=False):
            assert previous.end_char == current.start_char
        for chunk in chunks:
            assert chunk.end_char == chunk.start_char + len(chunk.text)

    def test_structured_keeps_heading_metadata(self) -> None:
        chunks = SemanticChunker().chunk(
            "# Title\n\n> quote line\n\n" + self._TABLE,
            "test.md",
            "markdown",
        )
        quote = [c for c in chunks if c.metadata.get("structure_type") == "blockquote"]
        table = [c for c in chunks if c.metadata.get("structure_type") == "table"]
        assert quote and table
        assert quote[0].metadata["heading"] == "Title"
        assert table[0].metadata["heading"] == "Title"
        assert table[0].metadata["structure_type"] == "table"

    def test_short_structured_section_gets_metadata(self) -> None:
        chunks = SemanticChunker(max_chunk_chars=200, overlap_chars=0).chunk(
            self._TABLE, "test.md", "markdown"
        )
        assert len(chunks) == 1
        assert chunks[0].text == self._TABLE
        assert chunks[0].metadata["structure_type"] == "table"

    def test_structured_chunking_deterministic(self) -> None:
        text = (
            "Intro.\n\n" + self._TABLE + "\n\n> quote\n\n"
            "> [!NOTE] callout here\n\nTerm\n: definition"
        )
        first = SemanticChunker(max_chunk_chars=40, overlap_chars=0).chunk(
            text, "test.md", "markdown"
        )
        second = SemanticChunker(max_chunk_chars=40, overlap_chars=0).chunk(
            text, "test.md", "markdown"
        )
        assert [(c.text, c.start_char, c.end_char, c.metadata) for c in first] == [
            (c.text, c.start_char, c.end_char, c.metadata) for c in second
        ]


class TestAdaptiveChunkingPolicy:
    """P3-205: dynamic chunk sizing, semantic overlap, configurable policy.

    Defaults reproduce P3-204 output (default ``ChunkingPolicy()`` is the
    no-op policy), so adaptive behavior is only asserted with explicit knobs.
    """

    _SENTENCE = "This is a complete sentence with enough words in it."

    def test_default_policy_reproduces_plain_chunking(self) -> None:
        text = "# A\n" + " ".join([self._SENTENCE] * 160)
        plain = SemanticChunker(max_chunk_chars=600, overlap_chars=0).chunk(
            text, "test.md", "markdown"
        )
        adaptive = SemanticChunker(
            max_chunk_chars=600, overlap_chars=0, policy=ChunkingPolicy()
        ).chunk(text, "test.md", "markdown")
        assert [(c.text, c.start_char, c.end_char) for c in plain] == [
            (c.text, c.start_char, c.end_char) for c in adaptive
        ]

    def test_heading_size_step_shrinks_budget_by_depth(self) -> None:
        policy = ChunkingPolicy(heading_size_step=1000, min_chunk_chars=200)
        chunker = SemanticChunker(max_chunk_chars=2000, policy=policy)
        body = " ".join([self._SENTENCE] * 240)
        deep = chunker.chunk("### Deep\n" + body, "t.md", "markdown")
        shallow = chunker.chunk("# Top\n" + body, "t.md", "markdown")
        assert len(deep) > len(shallow)
        assert max(len(c.text) for c in deep) <= 1200  # 2000 - 2*1000 + heading
        assert any(len(c.text) > 1200 for c in shallow)

    def test_min_chunk_chars_floors_the_budget(self) -> None:
        policy = ChunkingPolicy(heading_size_step=10000, min_chunk_chars=400)
        chunker = SemanticChunker(
            max_chunk_chars=2000, overlap_chars=0, policy=policy
        )
        chunks = chunker.chunk(
            "### Deep\n" + " ".join([self._SENTENCE] * 240), "t.md", "markdown"
        )
        body = [c for c in chunks if not c.text.startswith("#")]
        # a huge step would collapse the budget to zero; the floor keeps it at
        # ~min_chunk_chars, so chunks stay far below the 2000 base budget
        assert len(body) > 1
        assert all(len(c.text) <= 500 for c in body)

    def test_snap_overlap_starts_at_paragraph_boundary(self) -> None:
        para = "This is paragraph text with a good amount of words to fill up space. "
        text = "\n\n".join([para * 2] * 20)
        raw = SemanticChunker().chunk(text, "t.md", "markdown")
        snapped = SemanticChunker(policy=ChunkingPolicy(snap_overlap=True)).chunk(
            text, "t.md", "markdown"
        )
        assert len(snapped) == len(raw) >= 2
        raw_tail = raw[1].text[:30]
        assert raw_tail and not raw_tail.startswith("This is")  # mid-paragraph
        tail = snapped[1].text[:30]
        assert tail.startswith("This is paragraph text")  # paragraph start

    def test_snap_overlap_starts_at_list_item_boundary(self) -> None:
        item = "- item with a fair amount of text that keeps going for a while. "
        text = (item * 2 + "\n" + item * 2 + "\n" + item * 2 + "\n\n") * 6
        raw = SemanticChunker().chunk(text, "t.md", "markdown")
        snapped = SemanticChunker(policy=ChunkingPolicy(snap_overlap=True)).chunk(
            text, "t.md", "markdown"
        )
        assert len(snapped) == len(raw) >= 2
        tail = snapped[1].text[:3]
        assert tail in ("- i", "- item")  # starts at a whole list item
        assert not raw[1].text.startswith("- ")

    def test_heading_overlap_boundary_blocks_tail_into_heading_chunk(self) -> None:
        text = (
            "# First\n" + " ".join([self._SENTENCE] * 40) + "\n\n"
            "## Second\n" + " ".join([self._SENTENCE] * 40)
        )
        blocked = SemanticChunker(
            policy=ChunkingPolicy(heading_overlap_boundary=True)
        ).chunk(text, "t.md", "markdown")
        assert len(blocked) >= 2
        second_blocked = [c for c in blocked if c.metadata.get("heading") == "Second"][0]
        assert second_blocked.text.startswith("## Second")
        plain = SemanticChunker().chunk(text, "t.md", "markdown")
        second_plain = [c for c in plain if c.metadata.get("heading") == "Second"][0]
        # P3-204 behavior: the flag-off default prepends the previous tail,
        # so the heading-led chunk no longer starts with its heading
        assert not second_plain.text.startswith("## Second")
        assert len(second_plain.text) > len(second_blocked.text)


# ---------------------------------------------------------------------------
# Duplicate Detection (existing)
# ---------------------------------------------------------------------------

class TestDuplicateDetectionExisting:
    def test_manifest_hash_lookup(self, tmp_path: Path) -> None:
        from app.infrastructure.state.manifest import ManifestManager
        manifest = ManifestManager(
            tmp_path / "manifest.json",
            project_root=tmp_path,
        )
        assert manifest.contains_hash("nonexistent") is False

    def test_manifest_add_and_contains(self, tmp_path: Path) -> None:
        from app.infrastructure.state.manifest import ManifestManager
        manifest = ManifestManager(
            tmp_path / "manifest.json",
            project_root=tmp_path,
        )
        manifest.add_processed_file(
            path=tmp_path / "test.md",
            sha256="abc123",
            extension=".md",
        )
        manifest.save()
        assert manifest.contains_hash("abc123") is True
        assert manifest.contains_hash("xyz") is False


# ---------------------------------------------------------------------------
# Wiki Linking (existing)
# ---------------------------------------------------------------------------

class TestWikiLinking:
    def test_wiki_link_generation(self) -> None:
        from app.templates.obsidian_note import _wiki_link
        assert _wiki_link("Python") == "[[Python]]"
        assert _wiki_link("Machine Learning") == "[[Machine Learning]]"

    def test_wiki_link_escapes_pipes(self) -> None:
        from app.templates.obsidian_note import _wiki_link
        result = _wiki_link("A|B")
        assert "\\|" in result
        assert result == "[[A\\|B]]"


# ---------------------------------------------------------------------------
# Backlinks (existing + new write_backlinks)
# ---------------------------------------------------------------------------

class TestBacklinks:
    def test_write_backlinks_creates_section(self, tmp_path: Path) -> None:
        from app.infrastructure.vault.wiki_manager import WikiManager
        notes_dir = tmp_path / "Notes"
        notes_dir.mkdir()
        note_a = notes_dir / "Note A.md"
        note_a.write_text("---\ntitle: Note A\n---\nContent\n", encoding="utf-8")
        manager = WikiManager(tmp_path)
        updated = manager.write_backlinks("Note B.md", ["Note A"])
        assert updated == 1
        text = note_a.read_text(encoding="utf-8")
        assert "## Backlinks" in text
        assert "[[Note B" in text

    def test_write_backlinks_skips_existing(self, tmp_path: Path) -> None:
        from app.infrastructure.vault.wiki_manager import WikiManager
        notes_dir = tmp_path / "Notes"
        notes_dir.mkdir()
        note_a = notes_dir / "Note A.md"
        note_a.write_text(
            "---\ntitle: Note A\n---\nContent\n\n## Backlinks\n\n- [[Old]]\n",
            encoding="utf-8",
        )
        manager = WikiManager(tmp_path)
        updated = manager.write_backlinks("Note B.md", ["Note A"])
        assert updated == 0

    def test_write_backlinks_no_titles(self, tmp_path: Path) -> None:
        from app.infrastructure.vault.wiki_manager import WikiManager
        notes_dir = tmp_path / "Notes"
        notes_dir.mkdir()
        manager = WikiManager(tmp_path)
        updated = manager.write_backlinks("Note B.md", [])
        assert updated == 0


# ---------------------------------------------------------------------------
# Entity Extraction (existing via LLM)
# ---------------------------------------------------------------------------

class TestEntityExtraction:
    def test_entity_model_valid(self) -> None:
        entity = ImportantEntity(
            name="Python", type="technology", description="Language",
        )
        assert entity.name == "Python"
        assert entity.type == "technology"

    def test_entity_type_literal(self) -> None:
        for etype in ["person", "organization", "product", "project", "technology", "place", "paper", "concept", "other"]:
            entity = ImportantEntity(name="X", type=etype, description="Y")
            assert entity.type == etype


# ---------------------------------------------------------------------------
# Knowledge Graph
# ---------------------------------------------------------------------------

class TestKnowledgeGraph:
    def test_add_node(self) -> None:
        g = KnowledgeGraph()
        n = KnowledgeNode(id="n1", label="A", node_type="concept")
        g.add_node(n)
        assert "n1" in g.nodes

    def test_add_edge_requires_nodes(self) -> None:
        g = KnowledgeGraph()
        g.add_node(KnowledgeNode(id="n1", label="A", node_type="concept"))
        g.add_node(KnowledgeNode(id="n2", label="B", node_type="concept"))
        g.add_edge(KnowledgeEdge(source_id="n1", target_id="n2", edge_type="related_to"))
        assert len(g.edges) == 1

    def test_add_edge_ignores_missing_nodes(self) -> None:
        g = KnowledgeGraph()
        g.add_edge(KnowledgeEdge(source_id="missing", target_id="also_missing", edge_type="related_to"))
        assert len(g.edges) == 0

    def test_add_edge_valid_endpoints_returns_true(self) -> None:
        g = KnowledgeGraph()
        g.add_node(KnowledgeNode(id="n1", label="A", node_type="concept"))
        g.add_node(KnowledgeNode(id="n2", label="B", node_type="concept"))
        added = g.add_edge(KnowledgeEdge(source_id="n1", target_id="n2", edge_type="related_to"))
        assert added is True
        assert len(g.edges) == 1

    def test_add_edge_missing_source_returns_false(self) -> None:
        g = KnowledgeGraph()
        g.add_node(KnowledgeNode(id="n2", label="B", node_type="concept"))
        added = g.add_edge(KnowledgeEdge(source_id="n1", target_id="n2", edge_type="related_to"))
        assert added is False
        assert len(g.edges) == 0

    def test_add_edge_missing_target_returns_false(self) -> None:
        g = KnowledgeGraph()
        g.add_node(KnowledgeNode(id="n1", label="A", node_type="concept"))
        added = g.add_edge(KnowledgeEdge(source_id="n1", target_id="n2", edge_type="related_to"))
        assert added is False
        assert len(g.edges) == 0

    def test_add_edge_both_missing_returns_false(self) -> None:
        g = KnowledgeGraph()
        added = g.add_edge(KnowledgeEdge(source_id="n1", target_id="n2", edge_type="related_to"))
        assert added is False
        assert len(g.edges) == 0

    def test_neighbors(self) -> None:
        g = KnowledgeGraph()
        g.add_node(KnowledgeNode(id="a", label="A", node_type="concept"))
        g.add_node(KnowledgeNode(id="b", label="B", node_type="concept"))
        g.add_edge(KnowledgeEdge(source_id="a", target_id="b", edge_type="related_to"))
        neighbors = g.neighbors("a")
        assert len(neighbors) == 1
        assert neighbors[0][0].id == "b"

    def test_subgraph(self) -> None:
        g = KnowledgeGraph()
        for nid in ["a", "b", "c"]:
            g.add_node(KnowledgeNode(id=nid, label=nid, node_type="concept"))
        g.add_edge(KnowledgeEdge(source_id="a", target_id="b", edge_type="related_to"))
        g.add_edge(KnowledgeEdge(source_id="b", target_id="c", edge_type="related_to"))
        sub = g.subgraph("a", depth=1)
        assert "a" in sub.nodes
        assert "b" in sub.nodes
        assert "c" not in sub.nodes


class TestKnowledgeGraphBuilder:
    def test_build_from_analysis(self) -> None:
        builder = KnowledgeGraphBuilder()
        result = builder.build_from_analysis(_analysis(), "test.md")
        assert result.nodes_added > 0
        assert result.edges_added > 0
        assert len(result.graph.nodes) > 0

    def test_merge_graphs(self) -> None:
        g1 = KnowledgeGraph()
        g1.add_node(KnowledgeNode(id="a", label="A", node_type="concept"))
        g2 = KnowledgeGraph()
        g2.add_node(KnowledgeNode(id="b", label="B", node_type="concept"))
        builder = KnowledgeGraphBuilder()
        merged = builder.merge_graphs(g1, g2)
        assert "a" in merged.nodes
        assert "b" in merged.nodes


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

class TestEmbeddings:
    def test_embedding_result_dataclass(self) -> None:
        r = EmbeddingResult(model="test", embedding=[0.1, 0.2])
        assert r.model == "test"
        assert len(r.embedding) == 2

    def test_embedding_result_with_eval_count(self) -> None:
        r = EmbeddingResult(model="test", embedding=[0.1], prompt_eval_count=42)
        assert r.prompt_eval_count == 42

    def test_embedding_result_default_eval_count(self) -> None:
        r = EmbeddingResult(model="test", embedding=[0.1])
        assert r.prompt_eval_count is None


class TestEmbeddingService:
    def test_embed_empty_text_raises(self) -> None:
        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        with pytest.raises(ValueError, match="empty"):
            svc.embed("")

    def test_embed_whitespace_only_raises(self) -> None:
        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        with pytest.raises(ValueError, match="empty"):
            svc.embed("   ")

    def test_embed_batch_empty_returns_empty(self) -> None:
        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        assert svc.embed_batch([]) == []

    def test_embed_success(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "embeddings": [[0.1, 0.2, 0.3]],
            "prompt_eval_count": 10,
        }
        with patch.object(svc._client, "embed", return_value=mock_response) as m:
            result = svc.embed("hello world")
            m.assert_called_once_with(model="nomic-embed-text", input="hello world")
            assert result.model == "nomic-embed-text"
            assert result.embedding == [0.1, 0.2, 0.3]
            assert result.prompt_eval_count == 10

    def test_embed_no_model_dump(self) -> None:
        from unittest.mock import patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        raw_dict = {"embeddings": [[0.5, 0.6]], "prompt_eval_count": None}
        with patch.object(svc._client, "embed", return_value=raw_dict) as m:
            result = svc.embed("test")
            assert result.embedding == [0.5, 0.6]

    def test_embed_empty_embeddings_list(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"embeddings": []}
        with patch.object(svc._client, "embed", return_value=mock_response):
            result = svc.embed("test")
            assert result.embedding == []

    def test_embed_client_error_propagates(self) -> None:
        from unittest.mock import patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        with patch.object(svc._client, "embed", side_effect=RuntimeError("connection")), \
             patch("app.infrastructure.embeddings.time.sleep"):
            with pytest.raises(RuntimeError, match="connection"):
                svc.embed("test")

    def test_embed_retry_on_transient_failure(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"embeddings": [[0.1, 0.2]]}
        calls = {"count": 0}

        def flaky(*args: object, **kwargs: object) -> MagicMock:
            calls["count"] += 1
            if calls["count"] < 3:
                raise RuntimeError("transient")
            return mock_response

        with patch.object(svc._client, "embed", side_effect=flaky) as m, \
             patch("app.infrastructure.embeddings.time.sleep") as sleep:
            result = svc.embed("hello")
        assert m.call_count == 3
        assert sleep.call_args_list[0].args[0] == 1.0
        assert sleep.call_args_list[1].args[0] == 2.0
        assert result.embedding == [0.1, 0.2]

    def test_embed_retry_exhausted(self) -> None:
        from unittest.mock import patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        with patch.object(svc._client, "embed", side_effect=RuntimeError("fail")) as m, \
             patch("app.infrastructure.embeddings.time.sleep"):
            with pytest.raises(RuntimeError, match="fail"):
                svc.embed("test")
        assert m.call_count == 3

    def test_embed_batch_retry_on_transient_failure(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"embeddings": [[0.1, 0.2]]}
        calls = {"count": 0}

        def flaky(*args: object, **kwargs: object) -> MagicMock:
            calls["count"] += 1
            if calls["count"] < 3:
                raise RuntimeError("transient")
            return mock_response

        with patch.object(svc._client, "embed", side_effect=flaky) as m, \
             patch("app.infrastructure.embeddings.time.sleep"):
            results = svc.embed_batch(["a"])
        assert m.call_count == 3
        assert results[0].embedding == [0.1, 0.2]

    def test_embed_batch_success(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "embeddings": [[0.1, 0.2], [0.3, 0.4]],
        }
        with patch.object(svc._client, "embed", return_value=mock_response) as m:
            results = svc.embed_batch(["a", "b"])
            m.assert_called_once_with(model="nomic-embed-text", input=["a", "b"])
            assert len(results) == 2
            assert results[0].embedding == [0.1, 0.2]
            assert results[1].embedding == [0.3, 0.4]

    def test_embed_batch_client_error_propagates(self) -> None:
        from unittest.mock import patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        with patch.object(svc._client, "embed", side_effect=RuntimeError("fail")), \
             patch("app.infrastructure.embeddings.time.sleep"):
            with pytest.raises(RuntimeError, match="fail"):
                svc.embed_batch(["a"])

    def test_embed_batch_count_mismatch_raises_without_retry(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.core.config import OllamaSettings
        from app.infrastructure.embeddings import EmbeddingCountMismatchError, EmbeddingService
        svc = EmbeddingService(OllamaSettings())
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"embeddings": [[0.1, 0.2]]}
        with patch.object(svc._client, "embed", return_value=mock_response) as m:
            with pytest.raises(EmbeddingCountMismatchError, match="misalign"):
                svc.embed_batch(["a", "b"])
        # Deterministic server misconfiguration must fail loudly and immediately.
        assert m.call_count == 1


# ---------------------------------------------------------------------------
# Vector Store
# ---------------------------------------------------------------------------

class TestVectorStore:
    def test_add_and_get(self) -> None:
        store = VectorStore()
        entry = VectorEntry(id="e1", text="hello", embedding=[1.0, 0.0, 0.0])
        store.add(entry)
        assert store.get("e1") is not None
        assert store.get("missing") is None
        assert len(store) == 1

    def test_remove(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="hello", embedding=[1.0]))
        assert store.remove("e1") is True
        assert store.get("e1") is None
        assert store.remove("e1") is False

    def test_search(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="cat", embedding=[1.0, 0.0, 0.0]))
        store.add(VectorEntry(id="e2", text="dog", embedding=[0.9, 0.1, 0.0]))
        store.add(VectorEntry(id="e3", text="car", embedding=[0.0, 0.0, 1.0]))
        results = store.search([1.0, 0.0, 0.0], top_k=2)
        assert len(results) == 2
        assert results[0].entry.id == "e1"

    def test_search_min_score(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="x", embedding=[0.0, 1.0]))
        results = store.search([1.0, 0.0], top_k=5, min_score=0.5)
        assert len(results) == 0

    def test_add_batch(self) -> None:
        store = VectorStore()
        entries = [
            VectorEntry(id=f"e{i}", text=f"text{i}", embedding=[float(i)])
            for i in range(5)
        ]
        store.add_batch(entries)
        assert len(store) == 5

    def test_duplicate_ids_deduped(self) -> None:
        store = VectorStore()
        store.add_batch([
            VectorEntry(id="e1", text="first", embedding=[1.0, 0.0]),
            VectorEntry(id="e1", text="second", embedding=[1.0, 0.0]),
        ])
        assert len(store) == 1
        assert store.get("e1").text == "second"
        assert len(store.search([1.0, 0.0], top_k=5)) == 1

    def test_search_deterministic_ties(self) -> None:
        store = VectorStore()
        for eid in ("e3", "e1", "e2"):
            store.add(VectorEntry(id=eid, text=eid, embedding=[1.0, 0.0]))
        results = store.search([1.0, 0.0], top_k=5)
        assert [r.entry.id for r in results] == ["e1", "e2", "e3"]
        assert [r.entry.id for r in store.search([1.0, 0.0])] == [
            r.entry.id for r in store.search([1.0, 0.0])
        ]

    def test_search_filter(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(
            id="e1", text="python", embedding=[1.0, 0.0],
            source_type="pdf", metadata={"heading": "Intro"},
        ))
        store.add(VectorEntry(
            id="e2", text="python", embedding=[1.0, 0.0],
            source_type="markdown", metadata={"heading": "Outro"},
        ))
        results = store.search([1.0, 0.0], top_k=5, filters={"source_type": "pdf"})
        assert [r.entry.id for r in results] == ["e1"]
        results = store.search([1.0, 0.0], top_k=5, filters={"heading": "Outro"})
        assert [r.entry.id for r in results] == ["e2"]
        assert store.search([1.0, 0.0], top_k=5, filters={"heading": "Nope"}) == []

    def test_offsets_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "vectors.json"
        store = VectorStore(persistence_path=path)
        store.add(VectorEntry(
            id="e1", text="hello", embedding=[1.0, 0.5],
            start_char=3, end_char=8,
        ))
        store.save()
        loaded = VectorStore(persistence_path=path)
        assert loaded.get("e1").start_char == 3
        assert loaded.get("e1").end_char == 8

    def test_persistence(self, tmp_path: Path) -> None:
        path = tmp_path / "vectors.json"
        store1 = VectorStore(persistence_path=path)
        store1.add(VectorEntry(id="e1", text="hello", embedding=[1.0, 0.5]))
        store1.save()
        store2 = VectorStore(persistence_path=path)
        assert len(store2) == 1
        assert store2.get("e1").text == "hello"

    def test_save_is_atomic(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = tmp_path / "vectors.json"
        store = VectorStore(persistence_path=path)
        store.add(VectorEntry(id="e1", text="hello", embedding=[1.0, 0.5]))
        store.save()
        assert path.exists()
        assert not path.with_suffix(".json.tmp").exists()

        original = path.read_bytes()

        def _boom(*args: object, **kwargs: object) -> object:
            raise RuntimeError("serialization failed")

        monkeypatch.setattr("json.dumps", _boom)
        with pytest.raises(RuntimeError):
            store.save()
        assert path.read_bytes() == original
        assert not path.with_suffix(".json.tmp").exists()

    def test_load_corrupt_file_starts_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "vectors.json"
        path.write_bytes(b"\xff\xfe{not json")
        store = VectorStore(persistence_path=path)
        assert len(store) == 0

    def test_load_non_dict_root_starts_empty(self, tmp_path: Path) -> None:
        import json

        path = tmp_path / "vectors.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        store = VectorStore(persistence_path=path)
        assert len(store) == 0

    def test_load_skips_malformed_entries(self, tmp_path: Path) -> None:
        import json

        path = tmp_path / "vectors.json"
        path.write_text(json.dumps({
            "entries": [
                {"id": "good", "text": "ok", "embedding": [1.0, 0.0]},
                {"id": "bad", "text": "no embedding"},
                {"id": "bad2", "text": "x", "embedding": "not-a-vector"},
                "not-a-dict",
            ]
        }), encoding="utf-8")
        store = VectorStore(persistence_path=path)
        assert len(store) == 1
        assert store.get("good") is not None
        assert store.get("bad") is None
        assert store.get("bad2") is None

    def test_load_reads_indented_legacy_file(self, tmp_path: Path) -> None:
        import json

        path = tmp_path / "vectors.json"
        path.write_text(json.dumps({
            "entries": [{"id": "legacy", "text": "old", "embedding": [1.0, 0.0]}]
        }, indent=2), encoding="utf-8")
        store = VectorStore(persistence_path=path)
        assert len(store) == 1
        assert store.get("legacy").text == "old"

    def test_save_writes_compact_json(self, tmp_path: Path) -> None:
        path = tmp_path / "vectors.json"
        store = VectorStore(persistence_path=path)
        store.add(VectorEntry(id="e1", text="hello", embedding=[1.0, 0.5]))
        store.save()
        raw = path.read_text(encoding="utf-8")
        assert "\n" not in raw.strip()
        loaded = VectorStore(persistence_path=path)
        assert loaded.get("e1").text == "hello"


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_different_lengths(self) -> None:
        assert _cosine_similarity([1.0], [1.0, 0.0]) == 0.0

    def test_zero_vector(self) -> None:
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# Semantic Search
# ---------------------------------------------------------------------------

class TestSemanticSearch:
    def test_search_returns_hits(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="python is great", embedding=[1.0, 0.0, 0.0]))
        store.add(VectorEntry(id="e2", text="java is okay", embedding=[0.9, 0.1, 0.0]))
        store.add(VectorEntry(id="e3", text="rust is fast", embedding=[0.0, 0.0, 1.0]))
        ss = SemanticSearch(store)
        results = ss.search([1.0, 0.0, 0.0], top_k=2)
        assert len(results) == 2
        assert results[0].text == "python is great"
        assert results[0].score > results[1].score

    def test_empty_store(self) -> None:
        ss = SemanticSearch(VectorStore())
        assert ss.search([1.0, 0.0], top_k=5) == []

    def test_hit_carries_provenance(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(
            id="doc.md::chunk_0", text="python is great",
            embedding=[1.0, 0.0], source="doc.md", source_type="markdown",
            chunk_index=2, start_char=10, end_char=26,
            metadata={"heading": "Intro"},
        ))
        hit = SemanticSearch(store).search([1.0, 0.0], top_k=1)[0]
        assert hit.source_type == "markdown"
        assert hit.chunk_index == 2
        assert hit.start_char == 10
        assert hit.end_char == 26
        assert hit.metadata == {"heading": "Intro"}
        assert hit.parent_section is None


class TestHybridSearch:
    def test_fuses_semantic_and_lexical(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="python testing framework", embedding=[1.0, 0.0]))
        store.add(VectorEntry(id="e2", text="java enterprise", embedding=[0.9, 0.1]))
        results = HybridSearch(store).search("python testing", [1.0, 0.0], top_k=2)
        assert len(results) == 2
        assert results[0].entry_id == "e1"

    def test_deterministic_ties(self) -> None:
        store = VectorStore()
        for eid in ("e3", "e1", "e2"):
            store.add(VectorEntry(id=eid, text=eid, embedding=[1.0, 0.0]))
        hits = HybridSearch(store).search("query", [1.0, 0.0], top_k=5)
        assert [h.entry_id for h in hits] == ["e1", "e2", "e3"]

    def test_semantic_only_when_no_lexical_match(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="python", embedding=[1.0, 0.0]))
        store.add(VectorEntry(id="e2", text="java", embedding=[0.0, 1.0]))
        hits = HybridSearch(store).search("zzz", [1.0, 0.0], top_k=5)
        assert [h.entry_id for h in hits] == ["e1", "e2"]

    def test_lexical_only_when_no_embedding(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="python is great", embedding=[1.0, 0.0]))
        store.add(VectorEntry(id="e2", text="rust is fast", embedding=[0.0, 1.0]))
        hits = HybridSearch(store).search("rust", None, top_k=5)
        assert [h.entry_id for h in hits] == ["e2"]

    def test_lexical_only_when_empty_embedding(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="python is great", embedding=[1.0, 0.0]))
        store.add(VectorEntry(id="e2", text="rust is fast", embedding=[0.0, 1.0]))
        hits = HybridSearch(store).search("rust", [], top_k=5)
        assert [h.entry_id for h in hits] == ["e2"]

    def test_overlapping_results_deduped(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="python async", embedding=[1.0, 0.0]))
        store.add(VectorEntry(id="e2", text="java", embedding=[0.0, 1.0]))
        hits = HybridSearch(store).search("python async", [1.0, 0.0], top_k=5)
        assert [h.entry_id for h in hits] == ["e1", "e2"]
        assert len({h.entry_id for h in hits}) == len(hits)
        assert hits[0].score > hits[1].score

    def test_no_results_when_both_empty(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="python", embedding=[1.0, 0.0]))
        assert HybridSearch(store).search("zzz", None, top_k=5) == []
        assert HybridSearch(VectorStore()).search("zzz", None, top_k=5) == []

    def test_result_limit(self) -> None:
        store = VectorStore()
        for i in range(3):
            store.add(VectorEntry(id=f"e{i}", text=f"python {i}", embedding=[1.0, 0.0]))
        assert len(HybridSearch(store).search("python", [1.0, 0.0], top_k=1)) == 1
        assert HybridSearch(store).search("python", [1.0, 0.0], top_k=0) == []

    def test_blank_query_uses_dense_only(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="python", embedding=[1.0, 0.0]))
        store.add(VectorEntry(id="e2", text="java", embedding=[0.0, 1.0]))
        hits = HybridSearch(store).search("   ", [1.0, 0.0], top_k=5)
        assert [h.entry_id for h in hits] == ["e1", "e2"]

    def test_large_candidate_set(self) -> None:
        store = VectorStore()
        for i in range(200):
            store.add(VectorEntry(
                id=f"e{i}", text=f"python keyword{i}", embedding=[1.0, 0.0],
            ))
        hs = HybridSearch(store)
        first = [h.entry_id for h in hs.search("python keyword0", [1.0, 0.0], top_k=5)]
        second = [h.entry_id for h in hs.search("python keyword0", [1.0, 0.0], top_k=5)]
        assert first == second
        assert len(first) == 5
        assert first[0] == "e0"

    def test_bm25_failure_falls_back_to_dense(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="python", embedding=[1.0, 0.0]))
        store.add(VectorEntry(id="e2", text="java", embedding=[0.0, 1.0]))

        def _boom(corpus: object, **kwargs: object) -> object:
            raise RuntimeError("bm25 failed")

        monkeypatch.setattr("app.infrastructure.search.BM25Index", _boom)
        hits = HybridSearch(store).search("python", [1.0, 0.0], top_k=5)
        assert [h.entry_id for h in hits] == ["e1", "e2"]

    def test_min_score_filters_rrf_scores(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="e1", text="python", embedding=[1.0, 0.0]))
        store.add(VectorEntry(id="e2", text="java", embedding=[0.0, 1.0]))
        hs = HybridSearch(store)
        assert [h.entry_id for h in hs.search("python", [1.0, 0.0], min_score=0.02)] == ["e1"]
        assert hs.search("python", [1.0, 0.0], min_score=0.05) == []

    def test_provenance_preserved(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(
            id="doc.md::chunk_0", text="python async",
            embedding=[1.0, 0.0], source="doc.md", source_type="markdown",
            chunk_index=3, start_char=8, end_char=21, metadata={"heading": "Intro"},
        ))
        hit = HybridSearch(store).search("python async", [1.0, 0.0], top_k=1)[0]
        assert hit.entry_id == "doc.md::chunk_0"
        assert hit.source == "doc.md"
        assert hit.source_type == "markdown"
        assert hit.chunk_index == 3
        assert hit.start_char == 8
        assert hit.end_char == 21
        assert hit.metadata == {"heading": "Intro"}


# ---------------------------------------------------------------------------
# Search Service (P5-101/P5-102 hybrid retrieval facade)
# ---------------------------------------------------------------------------

class TestSearchService:
    @staticmethod
    def _make_store() -> VectorStore:
        store = VectorStore()
        store.add(VectorEntry(
            id="doc.py::chunk_0", text="python is great",
            embedding=[1.0, 0.0, 0.0], source="doc.py", source_type="pdf",
            chunk_index=0, start_char=0, end_char=16,
            metadata={"heading": "Intro"},
        ))
        store.add(VectorEntry(
            id="doc.py::chunk_1", text="rust is fast",
            embedding=[0.0, 1.0, 0.0], source="doc.py", source_type="pdf",
            chunk_index=1, start_char=16, end_char=30,
            metadata={"heading": "Outro"},
        ))
        store.add(VectorEntry(
            id="other.md::chunk_0", text="java is okay",
            embedding=[0.9, 0.1, 0.0], source="other.md", source_type="markdown",
            chunk_index=0, start_char=0, end_char=13,
        ))
        return store

    def test_empty_index(self) -> None:
        svc = SearchService(VectorStore(), embed=lambda q: [1.0, 0.0])
        assert svc.search("python") == []

    def test_empty_and_blank_query(self) -> None:
        svc = SearchService(self._make_store(), embed=lambda q: [1.0, 0.0])
        assert svc.search("") == []
        assert svc.search("   ") == []

    def test_single_doc_multi_chunk(self) -> None:
        svc = SearchService(self._make_store(), embed=lambda q: [1.0, 0.0, 0.0])
        hits = svc.search("python", top_k=5)
        assert len(hits) == 3
        assert hits[0].entry_id == "doc.py::chunk_0"
        assert hits[0].text == "python is great"
        assert hits[0].source == "doc.py"
        assert hits[0].source_type == "pdf"
        assert hits[0].chunk_index == 0
        assert hits[0].start_char == 0
        assert hits[0].end_char == 16
        assert hits[0].metadata == {"heading": "Intro"}
        assert hits[0].parent_section is None

    def test_multi_doc_retrieval(self) -> None:
        svc = SearchService(self._make_store(), embed=lambda q: [1.0, 0.0, 0.0])
        hits = svc.search("python", top_k=5)
        assert {"doc.py", "other.md"} <= {h.source for h in hits}

    def test_top_k(self) -> None:
        svc = SearchService(self._make_store(), embed=lambda q: [1.0, 0.0, 0.0])
        hits = svc.search("python", top_k=2)
        assert len(hits) == 2
        assert hits[0].entry_id == "doc.py::chunk_0"
        assert hits[1].entry_id == "other.md::chunk_0"

    def test_filter(self) -> None:
        svc = SearchService(self._make_store(), embed=lambda q: [1.0, 0.0, 0.0])
        hits = svc.search("python", top_k=5, filter={"source_type": "markdown"})
        assert [h.entry_id for h in hits] == ["other.md::chunk_0"]
        hits = svc.search("python", top_k=5, filter={"heading": "Intro"})
        assert [h.entry_id for h in hits] == ["doc.py::chunk_0"]

    def test_min_score_filters_rrf_scores(self) -> None:
        svc = SearchService(self._make_store(), embed=lambda q: [1.0, 0.0, 0.0])
        hits = svc.search("python", top_k=5, min_score=0.016)
        assert [h.entry_id for h in hits] == ["doc.py::chunk_0", "other.md::chunk_0"]

    def test_deterministic(self) -> None:
        store = VectorStore()
        for eid in ("e3", "e1", "e2"):
            store.add(VectorEntry(id=eid, text=eid, embedding=[1.0, 0.0]))
        svc = SearchService(store, embed=lambda q: [1.0, 0.0])
        first = [h.entry_id for h in svc.search("q")]
        second = [h.entry_id for h in svc.search("q")]
        assert first == second == ["e1", "e2", "e3"]

    def test_embed_failure_falls_back_to_lexical(self) -> None:
        def _fail(_q: str) -> list[float]:
            raise RuntimeError("no ollama")

        svc = SearchService(self._make_store(), embed=_fail)
        hits = svc.search("python")
        assert [h.entry_id for h in hits] == ["doc.py::chunk_0"]

    def test_embed_disabled_falls_back_to_lexical(self) -> None:
        svc = SearchService(self._make_store(), embed=lambda q: None)
        hits = svc.search("python")
        assert [h.entry_id for h in hits] == ["doc.py::chunk_0"]

    def test_lexical_match_outranks_pure_semantic(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(id="a", text="python async", embedding=[1.0, 0.0, 0.0]))
        store.add(VectorEntry(id="b", text="async internals", embedding=[0.0, 1.0, 0.0]))
        store.add(VectorEntry(id="c", text="neural nets", embedding=[0.9, 0.1, 0.0]))
        svc = SearchService(store, embed=lambda q: [1.0, 0.0, 0.0])
        hits = svc.search("python async", top_k=3)
        # b scores 0.0 semantically but matches "async" lexically, so it
        # outranks c (cosine 0.99, no keyword overlap) — roadmap 4.1.
        assert [h.entry_id for h in hits] == ["a", "b", "c"]

    def test_filter_applies_to_both_legs(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(
            id="e1", text="python async", embedding=[1.0, 0.0], source_type="pdf",
        ))
        store.add(VectorEntry(
            id="e2", text="python sync", embedding=[1.0, 0.0], source_type="markdown",
        ))
        svc = SearchService(store, embed=lambda q: [1.0, 0.0])
        hits = svc.search("python", top_k=5, filter={"source_type": "markdown"})
        assert [h.entry_id for h in hits] == ["e2"]

    def test_malformed_metadata_filter_is_safe(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(
            id="e1", text="python", embedding=[1.0, 0.0],
            metadata={"heading": "Intro", "odd": 123},
        ))
        svc = SearchService(store, embed=lambda q: [1.0, 0.0])
        assert svc.search("python", filter={"odd": "nope"}) == []
        assert [h.entry_id for h in svc.search("python", filter={"heading": "Intro"})] == ["e1"]


# ---------------------------------------------------------------------------
# Domain model integration
# ---------------------------------------------------------------------------

class TestDomainIntegration:
    def test_document_chunk_dataclass(self) -> None:
        c = DocumentChunk(
            chunk_id="c1", text="hello", source="t.md",
            source_type="markdown", chunk_index=0, start_char=0, end_char=5,
        )
        assert c.text == "hello"
        assert c.chunk_index == 0

    def test_vector_entry_dataclass(self) -> None:
        e = VectorEntry(id="e1", text="hello", embedding=[0.1])
        assert e.id == "e1"

    def test_search_result_dataclass(self) -> None:
        e = VectorEntry(id="e1", text="hello", embedding=[0.1])
        r = SearchResult(entry=e, score=0.95)
        assert r.score == 0.95


# ---------------------------------------------------------------------------
# Knowledge Graph Persistence
# ---------------------------------------------------------------------------

class TestKnowledgeGraphPersistence:
    def test_save_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "graph.json"
        g = KnowledgeGraph()
        g.add_node(KnowledgeNode(id="n1", label="A", node_type="concept", source="t.md"))
        g.add_node(KnowledgeNode(id="n2", label="B", node_type="entity", source="t.md"))
        g.add_edge(KnowledgeEdge(source_id="n1", target_id="n2", edge_type="related_to", weight=0.8))
        g.save(path)

        loaded = KnowledgeGraph.load(path)
        assert len(loaded.nodes) == 2
        assert "n1" in loaded.nodes
        assert "n2" in loaded.nodes
        assert len(loaded.edges) == 1
        assert loaded.edges[0].weight == 0.8

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "dir" / "graph.json"
        g = KnowledgeGraph()
        g.add_node(KnowledgeNode(id="n1", label="X", node_type="note"))
        g.save(path)
        assert path.exists()

    def test_load_empty_graph(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.json"
        path.write_text('{"nodes": [], "edges": []}', encoding="utf-8")
        g = KnowledgeGraph.load(path)
        assert len(g.nodes) == 0
        assert len(g.edges) == 0

    def test_save_is_atomic(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = tmp_path / "graph.json"
        g = KnowledgeGraph()
        g.add_node(KnowledgeNode(id="n1", label="A", node_type="concept"))
        g.save(path)
        assert path.exists()
        assert not path.with_suffix(".json.tmp").exists()

        original = path.read_bytes()

        def _boom(*args: object, **kwargs: object) -> object:
            raise RuntimeError("serialization failed")

        monkeypatch.setattr("json.dumps", _boom)
        with pytest.raises(RuntimeError):
            g.save(path)
        assert path.read_bytes() == original
        assert not path.with_suffix(".json.tmp").exists()

    def test_merge_and_persist(self, tmp_path: Path) -> None:
        path = tmp_path / "graph.json"
        g1 = KnowledgeGraph()
        g1.add_node(KnowledgeNode(id="a", label="A", node_type="concept"))
        g1.save(path)

        g2 = KnowledgeGraph()
        g2.add_node(KnowledgeNode(id="b", label="B", node_type="entity"))

        builder = KnowledgeGraphBuilder()
        existing = KnowledgeGraph.load(path)
        merged = builder.merge_graphs(existing, g2)
        merged.save(path)

        final = KnowledgeGraph.load(path)
        assert "a" in final.nodes
        assert "b" in final.nodes


# ---------------------------------------------------------------------------
# Placeholder Notes
# ---------------------------------------------------------------------------

class TestPlaceholderNotes:
    def test_create_placeholder(self, tmp_path: Path) -> None:
        from app.infrastructure.vault.wiki_manager import WikiManager
        notes_dir = tmp_path / "Notes"
        notes_dir.mkdir()
        manager = WikiManager(tmp_path)
        path = manager.create_placeholder("Quantum Computing", "Physics Note")
        assert path is not None
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "Quantum Computing" in text
        assert "Physics Note" in text
        assert "## Backlinks" in text

    def test_create_placeholder_no_duplicate(self, tmp_path: Path) -> None:
        from app.infrastructure.vault.wiki_manager import WikiManager
        notes_dir = tmp_path / "Notes"
        notes_dir.mkdir()
        manager = WikiManager(tmp_path)
        path1 = manager.create_placeholder("Test", "Source")
        path2 = manager.create_placeholder("Test", "Source")
        assert path1 is not None
        assert path2 is None

    def test_placeholder_has_stub_tag(self, tmp_path: Path) -> None:
        from app.infrastructure.vault.wiki_manager import WikiManager
        notes_dir = tmp_path / "Notes"
        notes_dir.mkdir()
        manager = WikiManager(tmp_path)
        path = manager.create_placeholder("My Topic", "Parent")
        text = path.read_text(encoding="utf-8")
        assert "stub" in text
        assert "auto-generated" in text

    def test_vault_writer_create_placeholder(self, tmp_path: Path) -> None:
        from app.infrastructure.vault.writer import VaultWriter
        writer = VaultWriter(tmp_path)
        writer.create_placeholder("Test Note", "Source Note")
        note_path = tmp_path / "Notes" / "Test Note.md"
        assert note_path.exists()


# ---------------------------------------------------------------------------
# Pipeline Integration (mocked)
# ---------------------------------------------------------------------------

class TestPipelineKnowledgeEngine:
    def test_workflow_result_has_kg_fields(self) -> None:
        from app.domain.documents import DocumentMetadata, SourceDocument
        from app.domain.notes import ObsidianNote
        from app.infrastructure.vault.wiki_manager import WikiUpdateResult
        from app.pipelines.ingest_workflow import IngestionWorkflowResult

        doc = SourceDocument(
            source="t.md", filename="t.md", source_type="text", text="x",
            metadata=DocumentMetadata(),
        )
        from unittest.mock import MagicMock
        ai = MagicMock()
        ai.analysis = _analysis()
        from datetime import UTC, datetime
        note = ObsidianNote(
            title="T", filename="t.md", source="t.md", markdown="# T",
            generated_at=datetime.now(tz=UTC), source_type="text",
        )
        wr = WikiUpdateResult(note_path=Path("t.md"), created=True, updated=False,
                              index_path=Path("i.md"), overview_path=Path("o.md"),
                              log_path=Path("l.md"))

        result = IngestionWorkflowResult(
            document=doc, ai_result=ai, note=note, write_result=wr,
        )
        assert result.knowledge_graph is None
        assert result.chunks_stored == 0
        assert result.cross_links_added == 0

    def test_workflow_accepts_kg_params(self) -> None:
        from unittest.mock import MagicMock

        from app.pipelines.ingest_workflow import IngestionWorkflow

        writer = MagicMock()
        writer.save.return_value = MagicMock(
            note_path=Path("t.md"), created=True, updated=False,
            index_path=Path("i.md"), overview_path=Path("o.md"),
            log_path=Path("l.md"),
        )
        ollama = MagicMock()
        wf = IngestionWorkflow(
            ingestion_service=MagicMock(),
            ollama_client=ollama,
            note_generator=MagicMock(),
            writer=writer,
            chunker=MagicMock(),
            embedding_service=MagicMock(),
            vector_store=MagicMock(),
            knowledge_graph_builder=MagicMock(),
        )
        assert wf._chunker is not None
        assert wf._vector_store is not None

    def test_knowledge_engine_skips_when_no_components(self) -> None:
        from unittest.mock import MagicMock

        from app.domain.documents import DocumentMetadata, SourceDocument
        from app.pipelines.ingest_workflow import IngestionWorkflow

        writer = MagicMock()
        wf = IngestionWorkflow(
            ingestion_service=MagicMock(),
            ollama_client=MagicMock(),
            note_generator=MagicMock(),
            writer=writer,
        )
        doc = SourceDocument(
            source="t.md", filename="t.md", source_type="text", text="hello",
            metadata=DocumentMetadata(),
        )
        kg, stored, links = wf._run_knowledge_engine(doc, _analysis())
        assert kg is None
        assert stored == 0
        assert links == 0


# ---------------------------------------------------------------------------
# Cross-Document Linking
# ---------------------------------------------------------------------------

class TestCrossDocumentLinking:
    def test_find_similar_chunks(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(
            id="doc1::chunk_0", text="python is a programming language",
            embedding=[0.9, 0.1, 0.0], source="doc1.py",
        ))
        store.add(VectorEntry(
            id="doc2::chunk_0", text="python is widely used in data science",
            embedding=[0.85, 0.15, 0.0], source="doc2.md",
        ))

        from app.infrastructure.search import SemanticSearch
        search = SemanticSearch(store)
        query_emb = [0.88, 0.12, 0.0]
        hits = search.search(query_emb, top_k=3, min_score=0.7)
        sources = {h.source for h in hits}
        assert len(hits) >= 2
        assert "doc1.py" in sources
        assert "doc2.md" in sources

    def test_no_cross_links_for_identical_source(self) -> None:
        store = VectorStore()
        store.add(VectorEntry(
            id="doc1::chunk_0", text="hello world",
            embedding=[1.0, 0.0], source="doc1.md",
        ))
        store.add(VectorEntry(
            id="doc1::chunk_1", text="hello world again",
            embedding=[0.95, 0.05], source="doc1.md",
        ))

        from app.infrastructure.search import SemanticSearch
        search = SemanticSearch(store)
        hits = search.search([1.0, 0.0], top_k=5, min_score=0.7)
        different_source = [h for h in hits if h.source != "doc1.md"]
        assert len(different_source) == 0
