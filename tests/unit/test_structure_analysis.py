"""Unit tests for Milestone 2.3 P2-301 structure domain models (frozen spec §4.2)."""

from __future__ import annotations

import time
import warnings
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

import app.infrastructure.document_intelligence as document_intelligence_root
from app.domain.document_intelligence import (
    DocumentBlock,
    DocumentSection,
    DocumentStructure,
    MetadataExtraction,
)
from app.infrastructure.document_intelligence.structure.detector import (
    MAX_HEADING_LEVEL,
    MAX_SECTIONS,
    Block,
    Heading,
    StructureAnalyzer,
    _build_tree,
    _detect_blocks,
    _detect_headings,
    _normalize_heading_level,
    analyze_document_structure,
    get_default_structure_analyzer,
    max_structure_text_bytes,
)
from app.infrastructure.ingestion.utils import clean_text


def _block(**overrides: object) -> DocumentBlock:
    base: dict[str, object] = {
        "block_id": "b-s-1-1",
        "type": "paragraph",
        "text": "First paragraph.",
        "start_char": 0,
        "end_char": 16,
    }
    base.update(overrides)
    return DocumentBlock(**base)


def _section(**overrides: object) -> DocumentSection:
    base: dict[str, object] = {
        "id": "s-1",
        "title": "Introduction",
        "level": 1,
        "parent_id": None,
        "start_char": 0,
        "end_char": 16,
        "blocks": [_block()],
    }
    base.update(overrides)
    return DocumentSection(**base)


def _structure(**overrides: object) -> DocumentStructure:
    base: dict[str, object] = {"sections": [_section()]}
    base.update(overrides)
    return DocumentStructure(**base)


# ── Construction ───────────────────────────────────────────────────────


class TestConstruction:
    def test_flat_structure(self) -> None:
        structure = _structure()
        section = structure.sections[0]
        assert section.id == "s-1"
        assert section.title == "Introduction"
        assert section.level == 1
        assert section.parent_id is None
        assert section.start_char == 0
        assert section.end_char == 16
        assert len(section.blocks) == 1

    def test_nested_structure_and_block_fields(self) -> None:
        structure = DocumentStructure(
            sections=[
                DocumentSection(
                    id="s-1",
                    title="Introduction",
                    level=1,
                    parent_id=None,
                    start_char=0,
                    end_char=120,
                    blocks=[
                        DocumentBlock(
                            block_id="b-s-1-1",
                            type="paragraph",
                            text="First paragraph.",
                            start_char=0,
                            end_char=16,
                        )
                    ],
                ),
                DocumentSection(
                    id="s-1-1",
                    title="Background",
                    level=2,
                    parent_id="s-1",
                    start_char=16,
                    end_char=120,
                    blocks=[
                        DocumentBlock(
                            block_id="b-s-1-1-1",
                            type="list",
                            text="- item",
                            start_char=16,
                            end_char=22,
                        )
                    ],
                ),
            ]
        )
        top = structure.sections[0]
        nested = structure.sections[1]
        assert top.id == "s-1"
        assert top.level == 1
        assert top.parent_id is None
        assert top.blocks[0].block_id == "b-s-1-1"
        assert top.blocks[0].type == "paragraph"
        assert top.blocks[0].text == "First paragraph."
        assert top.blocks[0].start_char == 0
        assert top.blocks[0].end_char == 16
        assert nested.id == "s-1-1"
        assert nested.level == 2
        assert nested.parent_id == "s-1"
        assert nested.blocks[0].type == "list"

    def test_all_block_types_accepted(self) -> None:
        for block_type in ("paragraph", "list", "code", "blockquote", "table"):
            block = _block(block_id=f"b-{block_type}", type=block_type)
            assert block.type == block_type

    def test_sections_required(self) -> None:
        with pytest.raises(ValidationError):
            DocumentStructure()

    def test_parent_id_optional_for_root(self) -> None:
        assert _section(parent_id=None).parent_id is None


# ── Type / value constraints ───────────────────────────────────────────


class TestBlockType:
    def test_rejects_unknown_type(self) -> None:
        with pytest.raises(ValidationError):
            _block(type="heading")
        with pytest.raises(ValidationError):
            _block(type="image")


class TestLevelBounds:
    def test_level_out_of_range_rejected(self) -> None:
        for bad in (0, 7, -1):
            with pytest.raises(ValidationError):
                _section(level=bad)

    def test_level_boundaries_accepted(self) -> None:
        assert _section(level=1).level == 1
        assert _section(level=6).level == 6


class TestOffsetValidation:
    def test_negative_offsets_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _block(start_char=-1)
        with pytest.raises(ValidationError):
            _block(end_char=-1)
        with pytest.raises(ValidationError):
            _section(start_char=-1)

    def test_end_before_start_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _block(start_char=10, end_char=5)
        with pytest.raises(ValidationError):
            _section(start_char=100, end_char=50)

    def test_span_must_match_text_length(self) -> None:
        with pytest.raises(ValidationError):
            _block(text="First paragraph.", start_char=0, end_char=120)
        block = _block(text="Hello", start_char=10, end_char=15)
        assert block.text == "Hello"

    def test_empty_text_empty_span(self) -> None:
        block = _block(text="", start_char=5, end_char=5)
        assert block.text == ""


class TestIdentifierValidation:
    def test_empty_ids_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _block(block_id="")
        with pytest.raises(ValidationError):
            _section(id="")

    def test_empty_parent_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _section(parent_id="")


class TestExtraForbid:
    def test_unknown_keys_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DocumentBlock(
                block_id="b-1",
                type="paragraph",
                text="t",
                start_char=0,
                end_char=1,
                bogus=True,
            )
        with pytest.raises(ValidationError):
            _structure(bogus=1)


# ── Serialization (R-1 channel) ────────────────────────────────────────


class TestSerialization:
    def test_json_round_trip(self) -> None:
        structure = _structure()
        dumped = structure.model_dump(mode="json")
        assert DocumentStructure.model_validate(dumped) == structure

    def test_empty_structure_round_trip(self) -> None:
        empty = DocumentStructure(sections=[])
        assert empty.model_dump(mode="json") == {"sections": []}
        assert DocumentStructure.model_validate({"sections": []}) == empty

    def test_section_round_trip(self) -> None:
        section = _section(parent_id="s-0")
        dumped = section.model_dump(mode="json")
        assert DocumentSection.model_validate(dumped) == section


# ── Backward compatibility ─────────────────────────────────────────────


class TestBackwardCompatibility:
    def test_metadata_extraction_unaffected(self) -> None:
        extraction = MetadataExtraction(source_type="pdf", values={"a": 1}, extractor="pdf")
        assert extraction.extractor == "pdf"
        assert extraction.values == {"a": 1}


# ── P2-302 heading detector (frozen spec §5/§6/§10) ────────────────────


def _detect(text: str) -> list[Heading]:
    return _detect_headings(text.split("\n"))


def _fixture(name: str) -> str:
    return (Path(__file__).resolve().parents[1] / "fixtures" / "structure" / name).read_text(
        encoding="utf-8"
    )


class TestHeadingHierarchy:
    def test_nested_chain(self) -> None:
        headings = _detect("# A\n## B\n### C\n")
        assert [h.title for h in headings] == ["A", "B", "C"]
        assert [h.level for h in headings] == [1, 2, 3]
        assert headings[0].parent is None
        assert headings[1].parent is headings[0]
        assert headings[2].parent is headings[1]

    def test_level_skip_attaches_to_nearest_lower(self) -> None:
        headings = _detect("# A\n### C\n")
        assert headings[0].parent is None
        assert headings[1].parent is headings[0]

    def test_sibling_detachment(self) -> None:
        headings = _detect("# A\n## B\n# D\n")
        assert headings[0].parent is None
        assert headings[1].parent is headings[0]
        assert headings[2].parent is None

    def test_shallower_after_deeper_reroots(self) -> None:
        headings = _detect("## B\n# A\n## C\n")
        assert headings[0].parent is None
        assert headings[1].parent is None
        assert headings[2].parent is headings[1]

    def test_same_level_siblings_all_root(self) -> None:
        headings = _detect("# A\n# B\n# C\n")
        assert [h.parent is None for h in headings] == [True, True, True]

    def test_fixture_nested_headings(self) -> None:
        headings = _detect(_fixture("nested_headings.md"))
        assert len(headings) == 11
        first = (headings[0].title, headings[0].level, headings[0].parent)
        assert first == ("Project Notes", 1, None)
        assert headings[2].title == "Windows"
        assert headings[2].parent is headings[1]
        assert headings[9].title == "Skipped Level"
        assert headings[9].parent is headings[8]
        assert headings[10].title == "Child Section"
        assert headings[10].parent is headings[8]


class TestFenceDisambiguation:
    def test_fenced_hash_not_heading(self) -> None:
        headings = _detect("# Real\n```\n# not a heading\n```\n# After\n")
        assert [h.title for h in headings] == ["Real", "After"]

    def test_language_tagged_fence(self) -> None:
        headings = _detect("# Real\n```python\n# not a heading\n```\n")
        assert [h.title for h in headings] == ["Real"]

    def test_fence_toggles_open_and_close(self) -> None:
        headings = _detect("# A\n```\n# x\n```\n## B\n```\n# y\n```\n")
        assert [h.title for h in headings] == ["A", "B"]

    def test_unclosed_fence_suppresses_rest(self) -> None:
        headings = _detect("# A\n```\n# not a heading\n## also not\n")
        assert [h.title for h in headings] == ["A"]

    def test_headings_after_fence_close(self) -> None:
        headings = _detect("```\n# in fence\n```\n# after\n")
        assert [h.title for h in headings] == ["after"]

    def test_blockquote_backticks_not_a_fence(self) -> None:
        headings = _detect("> ```\n> # quoted\n# real\n")
        assert [h.title for h in headings] == ["real"]

    def test_fixture_fenced_code(self) -> None:
        headings = _detect(_fixture("fenced_code.md"))
        assert [h.title for h in headings] == ["Top Level", "After Fences"]


class TestHeadingRule:
    def test_content_required_after_marks(self) -> None:
        for line in ("#", "# ", "#\t"):
            assert _detect(line) == []

    def test_no_space_after_marks_not_heading(self) -> None:
        assert _detect("#NoSpace\n") == []
        assert _detect("##NoSpace\n") == []

    def test_seven_marks_not_heading(self) -> None:
        assert _detect("####### X\n") == []

    def test_indented_heading_not_heading(self) -> None:
        assert _detect("  # Indented\n") == []

    def test_whitespace_only_input_no_headings(self) -> None:
        assert _detect("") == []
        assert _detect("   \n  \n") == []

    def test_level_and_title_extracted(self) -> None:
        headings = _detect("### My Section\n")
        assert headings[0].level == 3
        assert headings[0].title == "My Section"

    def test_inline_whitespace_collapsed(self) -> None:
        headings = _detect("# My   Wide  Title\n")
        assert headings[0].title == "My Wide Title"

    def test_trailing_and_leading_content_preserved(self) -> None:
        headings = _detect("# A B (c)\n")
        assert headings[0].title == "A B (c)"


class TestDepthCap:
    def test_normalize_helper_bounds(self) -> None:
        assert _normalize_heading_level(7) == 6
        assert _normalize_heading_level(6) == 6
        assert _normalize_heading_level(1) == 1
        assert _normalize_heading_level(0) == 1
        assert _normalize_heading_level(5) == 5

    def test_six_marks_accepted(self) -> None:
        headings = _detect("###### Deep\n")
        assert headings[0].level == 6

    def test_max_heading_level_constant(self) -> None:
        assert MAX_HEADING_LEVEL == 6


class TestLineIndexOffsets:
    def test_line_index_matches_split(self) -> None:
        text = "para\n## Section\nbody\n# Root\n"
        lines = text.split("\n")
        headings = _detect_headings(lines)
        assert [h.line_index for h in headings] == [1, 3]
        assert lines[headings[0].line_index].startswith("##")

    def test_empty_input_no_headings(self) -> None:
        assert _detect("") == []
        assert _detect("\n\n") == []

    def test_never_raises_on_odd_input(self) -> None:
        assert _detect("```") == []
        assert _detect("```python\n# x\n```\n```") == []
        assert _detect("#\n\x00\n``` ```\n  \n") == []
        assert _detect("a\rb\n## title\r\n")[0].title == "title"


# ── P2-303 block detector (frozen spec §5/§6/§10) ──────────────────────


def _detect_blocks_in(text: str, ranges: Sequence[tuple[int, int]] | None = None) -> list[Block]:
    if ranges is None:
        ranges = [(0, len(text))]
    return _detect_blocks(text, ranges)


class TestBlockTypes:
    def test_paragraph(self) -> None:
        blocks = _detect_blocks_in("Just a paragraph line.\n")
        assert [(b.type, b.text) for b in blocks] == [("paragraph", "Just a paragraph line.")]

    def test_list(self) -> None:
        blocks = _detect_blocks_in("- item one\n- item two\n")
        assert [(b.type, b.text) for b in blocks] == [("list", "- item one\n- item two")]

    def test_code_fence(self) -> None:
        blocks = _detect_blocks_in("```\ncode\n```\n")
        assert [(b.type, b.text) for b in blocks] == [("code", "```\ncode\n```")]

    def test_blockquote(self) -> None:
        blocks = _detect_blocks_in("> quoted\n> more\n")
        assert [(b.type, b.text) for b in blocks] == [("blockquote", "> quoted\n> more")]

    def test_table(self) -> None:
        blocks = _detect_blocks_in("| a | b |\n|:---|---:|\n| 1 | 2 |\n")
        assert [(b.type, b.text) for b in blocks] == [
            ("table", "| a | b |\n|:---|---:|\n| 1 | 2 |")
        ]

    def test_fixture_all_five_types(self) -> None:
        blocks = _detect_blocks_in(_fixture("blocks.md"))
        assert [b.type for b in blocks] == [
            "paragraph",
            "list",
            "blockquote",
            "code",
            "table",
            "paragraph",
        ]


class TestBlockOffsets:
    def test_blocks_md_exact_offsets(self) -> None:
        text = _fixture("blocks.md")
        blocks = _detect_blocks(text, [(0, len(text))])
        expected = [
            ("paragraph", "First paragraph line one.\nSecond paragraph line.", 17, 65),
            (
                "list",
                "- item one\n- item two\n  - nested sub-item\nwrapped list continuation.",
                66,
                134,
            ),
            ("blockquote", "> quoted line\n> second quoted line", 135, 169),
            ("code", '```python\nprint("hi")\n# fenced, not a heading\n```', 170, 219),
            (
                "table",
                "| col A | col B |\n|:---|---:|\n| a | b |\n| Lone pipe | line. |",
                220,
                281,
            ),
            ("paragraph", "Final paragraph.", 297, 313),
        ]
        actual = [(b.type, b.text, b.start_char, b.end_char) for b in blocks]
        assert actual == expected


class TestSliceInvariant:
    def test_every_fixture_block(self) -> None:
        for name in ("blocks.md", "lists_and_quotes.md", "table_block.md"):
            text = _fixture(name)
            for block in _detect_blocks(text, [(0, len(text))]):
                assert text[block.start_char : block.end_char] == block.text
                assert len(block.text) == block.end_char - block.start_char

    def test_section_ranges_slices(self) -> None:
        text = _fixture("blocks.md")
        lines = text.split("\n")
        line_starts: list[int] = []
        pos = 0
        for line in lines:
            line_starts.append(pos)
            pos += len(line) + 1
        headings = _detect_headings(lines)
        ranges = []
        for i, heading in enumerate(headings):
            start = line_starts[heading.line_index] + len(lines[heading.line_index]) + 1
            end = line_starts[headings[i + 1].line_index] if i + 1 < len(headings) else len(text)
            ranges.append((start, end))
        blocks = _detect_blocks(text, ranges)
        assert len(blocks) == 6
        for block in blocks:
            assert text[block.start_char : block.end_char] == block.text


class TestListNesting:
    def test_nested_sublist_single_block(self) -> None:
        blocks = _detect_blocks_in("- top\n  - nested\n- other\n")
        assert [(b.type, b.text) for b in blocks] == [("list", "- top\n  - nested\n- other")]


class TestListContinuation:
    def test_wrapped_line_absorbed(self) -> None:
        blocks = _detect_blocks_in("- item\ncontinued without blank\n")
        assert [(b.type, b.text) for b in blocks] == [("list", "- item\ncontinued without blank")]

    def test_blank_line_ends_list(self) -> None:
        blocks = _detect_blocks_in("- item\n\nNew paragraph.\n")
        assert [(b.type, b.text) for b in blocks] == [
            ("list", "- item"),
            ("paragraph", "New paragraph."),
        ]

    def test_heading_ends_list(self) -> None:
        blocks = _detect_blocks_in("- item\n# Heading\nAfter.\n")
        assert [(b.type, b.text) for b in blocks] == [
            ("list", "- item"),
            ("paragraph", "After."),
        ]

    def test_pipe_line_ends_list(self) -> None:
        blocks = _detect_blocks_in("- item\n| lone | pipe |\n")
        assert [(b.type, b.text) for b in blocks] == [
            ("list", "- item"),
            ("paragraph", "| lone | pipe |"),
        ]


class TestBlockquote:
    def test_single_line(self) -> None:
        blocks = _detect_blocks_in("> quote\n")
        assert [(b.type, b.text) for b in blocks] == [("blockquote", "> quote")]

    def test_consecutive_lines_merge(self) -> None:
        blocks = _detect_blocks_in("> one\n> two\n")
        assert [(b.type, b.text) for b in blocks] == [("blockquote", "> one\n> two")]

    def test_nested_depth_merges(self) -> None:
        blocks = _detect_blocks_in("> outer\n> > inner\n")
        assert [(b.type, b.text) for b in blocks] == [("blockquote", "> outer\n> > inner")]

    def test_blank_line_separates(self) -> None:
        blocks = _detect_blocks_in("> one\n\n> two\n")
        assert [b.type for b in blocks] == ["blockquote", "blockquote"]


class TestTable:
    def test_normalized_table(self) -> None:
        blocks = _detect_blocks_in("| a | b |\n|:---|---:|\n| 1 | 2 |\n")
        assert [(b.type, b.text) for b in blocks] == [
            ("table", "| a | b |\n|:---|---:|\n| 1 | 2 |")
        ]

    def test_lone_pipe_line_is_paragraph(self) -> None:
        blocks = _detect_blocks_in("| just | pipes |\n")
        assert [(b.type, b.text) for b in blocks] == [("paragraph", "| just | pipes |")]

    def test_two_tables_blank_separated(self) -> None:
        text = "| a | b |\n|:---|---:|\n| 1 | 2 |\n\n| c | d |\n|:---|---:|\n| 3 | 4 |\n"
        blocks = _detect_blocks_in(text)
        assert [b.type for b in blocks] == ["table", "table"]
        assert blocks[0].end_char < blocks[1].start_char

    def test_pipe_in_paragraph_stays_paragraph(self) -> None:
        blocks = _detect_blocks_in("Not a pipe-start line | anyway.\n")
        assert [(b.type, b.text) for b in blocks] == [
            ("paragraph", "Not a pipe-start line | anyway.")
        ]


class TestCodeFence:
    def test_multiline_fence_single_block(self) -> None:
        blocks = _detect_blocks_in("```\nline1\nline2\n```\n")
        assert [(b.type, b.text) for b in blocks] == [("code", "```\nline1\nline2\n```")]

    def test_info_string_kept(self) -> None:
        blocks = _detect_blocks_in("```python\nprint('hi')\n```\n")
        assert blocks[0].type == "code"
        assert blocks[0].text == "```python\nprint('hi')\n```"

    def test_unclosed_fence_runs_to_end(self) -> None:
        blocks = _detect_blocks_in("Before.\n```\ncode\nmore")
        assert [(b.type, b.text) for b in blocks] == [
            ("paragraph", "Before."),
            ("code", "```\ncode\nmore"),
        ]

    def test_fenced_content_never_a_block(self) -> None:
        text = "```\n# not heading\n- not list\n| not table\n```\n"
        blocks = _detect_blocks_in(text)
        assert [(b.type, b.text) for b in blocks] == [
            ("code", "```\n# not heading\n- not list\n| not table\n```")
        ]

    def test_two_fences_two_code_blocks(self) -> None:
        blocks = _detect_blocks_in("```\na\n```\nText.\n```\nb\n```\n")
        assert [(b.type, b.text) for b in blocks] == [
            ("code", "```\na\n```"),
            ("paragraph", "Text."),
            ("code", "```\nb\n```"),
        ]


class TestFenceStateConsistency:
    def test_same_text_both_detectors(self) -> None:
        text = "# Real\n```\n# fenced\n## also fenced\n```\n# After\n"
        assert [h.title for h in _detect(text)] == ["Real", "After"]
        blocks = _detect_blocks(text, [(0, len(text))])
        assert [(b.type, b.text) for b in blocks] == [
            ("code", "```\n# fenced\n## also fenced\n```")
        ]


class TestParagraph:
    def test_split_on_blank_lines(self) -> None:
        blocks = _detect_blocks_in("One.\n\nTwo.\n\n\nThree.\n")
        assert [b.text for b in blocks] == ["One.", "Two.", "Three."]

    def test_consecutive_lines_merge(self) -> None:
        blocks = _detect_blocks_in("Line one.\nLine two.\n")
        assert [b.text for b in blocks] == ["Line one.\nLine two."]

    def test_heading_never_a_block(self) -> None:
        for text in ("# H\n", "## Sub\n### Deep\n"):
            assert _detect_blocks_in(text) == []

    def test_heading_splits_paragraphs(self) -> None:
        blocks = _detect_blocks_in("Before.\n# Heading\nAfter.\n")
        assert [b.text for b in blocks] == ["Before.", "After."]


class TestRanges:
    def test_empty_ranges(self) -> None:
        assert _detect_blocks("any text\n", ()) == []

    def test_whole_document_range(self) -> None:
        text = "- item\n\nAfter.\n"
        blocks = _detect_blocks(text, [(0, len(text))])
        assert [b.type for b in blocks] == ["list", "paragraph"]

    def test_blocks_do_not_span_ranges(self) -> None:
        text = "One.\nTwo.\nThree.\n"
        blocks = _detect_blocks(text, [(0, 5), (10, len(text))])
        assert [b.text for b in blocks] == ["One.", "Three."]

    def test_out_of_bounds_range_graceful(self) -> None:
        assert _detect_blocks("Hello.\n", [(100, 200)]) == []


class TestNeverRaises:
    def test_lone_fence_toggle(self) -> None:
        assert [b.type for b in _detect_blocks("```", [(0, 3)])] == ["code"]
        assert [b.type for b in _detect_blocks("```\n", [(0, 4)])] == ["code"]

    def test_cr_embedded_lines(self) -> None:
        blocks = _detect_blocks("a\rb\n## title\r\n", [(0, 100)])
        assert [(b.type, b.text) for b in blocks] == [("paragraph", "a\rb")]

    def test_null_byte_line(self) -> None:
        blocks = _detect_blocks("before\x00after\n", [(0, 100)])
        assert [b.type for b in blocks] == ["paragraph"]

    def test_odd_range_values(self) -> None:
        assert _detect_blocks("x\n", [(5, 10)]) == []
        assert _detect_blocks("x\n", [(-5, -1)]) == []


class TestCleanTextBoundary:
    def test_raw_markdown_through_clean_text(self) -> None:
        raw = "- item one\n- item two\n\n> quote\n\n| a | b |\n|---|----|\n| 1 | 2 |\n"
        cleaned = clean_text(raw)
        blocks = _detect_blocks(cleaned, [(0, len(cleaned))])
        assert [b.type for b in blocks] == ["list", "blockquote", "table"]

    def test_heading_marks_survive_clean_text(self) -> None:
        cleaned = clean_text("# Title\nBody text.\n")
        blocks = _detect_blocks(cleaned, [(0, len(cleaned))])
        assert [(b.type, b.text) for b in blocks] == [("paragraph", "Body text.")]

    def test_fixtures_are_clean_text_stable(self) -> None:
        for name in ("blocks.md", "lists_and_quotes.md", "table_block.md"):
            assert clean_text(_fixture(name)) == _fixture(name)


# ── P2-304 structure tree builder (frozen spec §4.1/§4.3/§5) ───────────


def _analyze(text: str) -> DocumentStructure:
    return analyze_document_structure(text, "test-source")


class TestAnalyzerEntry:
    def test_analyze_returns_structure(self) -> None:
        tree = StructureAnalyzer().analyze("# A\n", "src")
        assert isinstance(tree, DocumentStructure)
        assert [s.id for s in tree.sections] == ["s-1"]

    def test_function_delegates_to_factory(self) -> None:
        tree = analyze_document_structure("# A\n", "src")
        assert [s.id for s in tree.sections] == ["s-1"]

    def test_composition_root_reexports(self) -> None:
        assert document_intelligence_root.analyze_document_structure is analyze_document_structure
        assert (
            document_intelligence_root.get_default_structure_analyzer
            is get_default_structure_analyzer
        )

    def test_factory_returns_fresh_instance(self) -> None:
        assert get_default_structure_analyzer() is not get_default_structure_analyzer()

    def test_source_accepted_unused(self) -> None:
        text = "# A\nbody\n"
        assert analyze_document_structure(text, "a.pdf").model_dump() == (
            analyze_document_structure(text, "b.docx").model_dump()
        )


class TestSectionAssembly:
    def test_nested_chain(self) -> None:
        tree = _analyze("# A\n## B\n### C\n")
        assert [(s.id, s.title, s.level, s.parent_id) for s in tree.sections] == [
            ("s-1", "A", 1, None),
            ("s-1-1", "B", 2, "s-1"),
            ("s-1-1-1", "C", 3, "s-1-1"),
        ]

    def test_siblings(self) -> None:
        tree = _analyze("# A\n# B\n")
        assert [(s.id, s.parent_id) for s in tree.sections] == [
            ("s-1", None),
            ("s-2", None),
        ]

    def test_level_skip_uses_nearest_parent(self) -> None:
        tree = _analyze("# A\n### C\n")
        assert [(s.id, s.title, s.parent_id) for s in tree.sections] == [
            ("s-1", "A", None),
            ("s-1-1", "C", "s-1"),
        ]

    def test_nested_headings_fixture_tree(self) -> None:
        tree = _analyze(_fixture("nested_headings.md"))
        assert [(s.id, s.title, s.level, s.parent_id) for s in tree.sections] == [
            ("s-1", "Project Notes", 1, None),
            ("s-1-1", "Installation", 2, "s-1"),
            ("s-1-1-1", "Windows", 3, "s-1-1"),
            ("s-1-1-2", "Linux", 3, "s-1-1"),
            ("s-1-2", "Configuration", 2, "s-1"),
            ("s-1-3", "Deep Dive", 2, "s-1"),
            ("s-1-3-1", "Even Deeper", 3, "s-1-3"),
            ("s-1-3-1-1", "Deepest", 4, "s-1-3-1"),
            ("s-2", "Second Document", 1, None),
            ("s-2-1", "Skipped Level", 3, "s-2"),
            ("s-2-2", "Child Section", 2, "s-2"),
        ]


class TestBlockIDs:
    def test_block_ids_restart_per_section(self) -> None:
        tree = _analyze("# A\none\n# B\ntwo\n")
        assert [(s.id, [b.block_id for b in s.blocks]) for s in tree.sections] == [
            ("s-1", ["b-s-1-1"]),
            ("s-2", ["b-s-2-1"]),
        ]

    def test_blocks_md_fixture_section_blocks(self) -> None:
        tree = _analyze(_fixture("blocks.md"))
        assert [(s.id, [b.block_id for b in s.blocks]) for s in tree.sections] == [
            ("s-1", ["b-s-1-1", "b-s-1-2", "b-s-1-3", "b-s-1-4", "b-s-1-5"]),
            ("s-2", ["b-s-2-1"]),
        ]

    def test_blocks_md_fixture_block_types(self) -> None:
        tree = _analyze(_fixture("blocks.md"))
        assert [b.type for b in tree.sections[0].blocks] == [
            "paragraph",
            "list",
            "blockquote",
            "code",
            "table",
        ]

    def test_fenced_block_is_one_code_block_in_one_section(self) -> None:
        tree = _analyze("# Top\n```\n# not a heading\n```\n")
        assert [s.title for s in tree.sections] == ["Top"]
        assert [b.type for b in tree.sections[0].blocks] == ["code"]

    def test_unclosed_fence_swallows_following_headings(self) -> None:
        tree = _analyze("# A\n```\n# B\n## C\n")
        assert [s.title for s in tree.sections] == ["A"]
        assert [b.type for b in tree.sections[0].blocks] == ["code"]


class TestOffsetsContiguity:
    def test_sections_tile_without_gaps(self) -> None:
        text = _fixture("nested_headings.md")
        tree = _analyze(text)
        sections = tree.sections
        for j in range(len(sections) - 1):
            assert sections[j].end_char == sections[j + 1].start_char

    def test_last_section_ends_at_text_length(self) -> None:
        text = _fixture("nested_headings.md")
        tree = _analyze(text)
        assert tree.sections[-1].end_char == len(text)

    def test_section_slice_contains_heading_line(self) -> None:
        text = _fixture("nested_headings.md")
        tree = _analyze(text)
        for section in tree.sections:
            start = text[section.start_char : section.end_char]
            assert start.startswith(f"{'#' * section.level} ")

    def test_block_slices_exact(self) -> None:
        text = _fixture("blocks.md")
        tree = _analyze(text)
        for section in tree.sections:
            for block in section.blocks:
                assert text[block.start_char : block.end_char] == block.text

    def test_heading_lines_never_in_non_code_block_text(self) -> None:
        text = _fixture("blocks.md")
        tree = _analyze(text)
        for section in tree.sections:
            for block in section.blocks:
                if block.type == "code":
                    continue
                assert not any(line.startswith("#") for line in block.text.split("\n"))

    def test_blocks_within_section_span(self) -> None:
        text = _fixture("blocks.md")
        tree = _analyze(text)
        for section in tree.sections:
            for block in section.blocks:
                assert section.start_char <= block.start_char
                assert block.end_char <= section.end_char


class TestDegenerate:
    def test_build_tree_empty(self) -> None:
        assert _build_tree([]).sections == []

    def test_empty_text(self) -> None:
        assert _analyze("").sections == []

    def test_whitespace_only(self) -> None:
        assert _analyze("  \n\n\t\n").sections == []

    def test_no_headings(self) -> None:
        assert _analyze("just a paragraph\nno headings\n").sections == []

    def test_empty_fixture(self) -> None:
        assert _analyze(_fixture("empty.md")).sections == []

    def test_lone_fence_toggle(self) -> None:
        assert _analyze("```\n").sections == []

    def test_cr_lines_never_raise(self) -> None:
        tree = _analyze("a\rb\n# title\r\n")
        assert [s.title for s in tree.sections] == ["title"]


class TestMaxSections:
    def test_constant_value(self) -> None:
        assert MAX_SECTIONS == 10_000

    def test_exactly_max_no_warning(self) -> None:
        text = "# h\n" * MAX_SECTIONS
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            tree = _analyze(text)
        assert len(tree.sections) == MAX_SECTIONS

    def test_over_cap_truncates_with_warning(self) -> None:
        text = "# h\n" * (MAX_SECTIONS + 1)
        with pytest.warns(UserWarning, match="MAX_SECTIONS"):
            tree = _analyze(text)
        assert len(tree.sections) == MAX_SECTIONS

    def test_truncation_keeps_parent_references_valid(self) -> None:
        text = "# root\n## child\n" * (MAX_SECTIONS // 2) + "# extra\n"
        with pytest.warns(UserWarning):
            tree = _analyze(text)
        assert len(tree.sections) == MAX_SECTIONS
        kept_ids = {s.id for s in tree.sections}
        for section in tree.sections:
            if section.parent_id is not None:
                assert section.parent_id in kept_ids


class TestIDStability:
    def test_same_text_same_dump(self) -> None:
        text = _fixture("nested_headings.md")
        assert _analyze(text).model_dump() == _analyze(text).model_dump()


class TestPreambleDropped:
    def test_text_before_first_heading_not_in_any_section(self) -> None:
        text = "Preamble one.\nPreamble two.\n# Real\nBody.\n"
        tree = _analyze(text)
        assert [s.title for s in tree.sections] == ["Real"]
        assert [b.text for b in tree.sections[0].blocks] == ["Body."]

    def test_preamble_fence_blocks_dropped(self) -> None:
        text = "```\npre\n```\n# Real\nBody.\n"
        tree = _analyze(text)
        assert [s.title for s in tree.sections] == ["Real"]
        assert [b.text for b in tree.sections[0].blocks] == ["Body."]


class TestSerializationRoundTrip:
    def test_model_validate_round_trips(self) -> None:
        text = _fixture("blocks.md")
        tree = _analyze(text)
        restored = DocumentStructure.model_validate(tree.model_dump(mode="json"))
        assert restored == tree


# ── P2-306 performance + cap guard (frozen spec §7 / §13 perf row) ───────


class TestMaxStructureBytes:
    def test_constant_value(self) -> None:
        assert max_structure_text_bytes == 5_000_000

    def test_oversize_text_skipped_with_single_warning(self) -> None:
        text = "x" * (max_structure_text_bytes + 1)
        with pytest.warns(UserWarning, match="max_structure_text_bytes"):
            tree = _analyze(text)
        assert tree.sections == []

    def test_exactly_at_cap_is_not_skipped(self) -> None:
        text = "x" * max_structure_text_bytes
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            tree = _analyze(text)
        assert tree.sections == []


class TestTimingCeiling:
    def test_one_megabyte_within_ceiling(self) -> None:
        paragraph = "lorem ipsum dolor sit amet consectetur adipiscing elit\n" * 8
        text = "".join(f"# section {i}\n{paragraph}" for i in range(2600))
        assert len(text) >= 1_000_000
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            start = time.perf_counter()
            tree = _analyze(text)
            elapsed = time.perf_counter() - start
        assert tree.sections
        assert elapsed <= 1.0
