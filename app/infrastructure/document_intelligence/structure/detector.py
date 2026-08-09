"""Heading hierarchy detector for document structure analysis (frozen §4.3)."""

from __future__ import annotations

import re
import warnings
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.domain.document_intelligence import (
    DocumentBlock,
    DocumentSection,
    DocumentStructure,
)

MAX_HEADING_LEVEL = 6  # frozen §7 / D6: ATX heading depth cap (code constant)
TEXT_BEARING_KINDS = frozenset({"markdown", "text"})  # frozen §7 / D3: kinds enriched in M2.3

_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*)$")  # D9 heading rule


def _collapse_inline_whitespace(value: str) -> str:
    """Collapse runs of inline whitespace to a single space (defensive)."""
    return re.sub(r"\s+", " ", value.strip())


def _normalize_heading_level(level: int) -> int:
    """Clamp a heading level into 1..MAX_HEADING_LEVEL (frozen §7)."""
    # ponytail: defense-in-depth — D9 makes levels > 6 unreachable; the clamp is the frozen guard
    return min(max(level, 1), MAX_HEADING_LEVEL)


@dataclass
class Heading:
    """A detected ATX heading with resolved parent linkage (P2-302)."""

    level: int  # 1..6 (clamped, D6)
    line_index: int  # 0-based index into lines = exact_text.split("\n") (D1)
    title: str  # heading text without '#' marks, inline whitespace collapsed
    parent: Heading | None = None  # nearest preceding lower-level heading (D4); None = root


def _detect_headings(lines: Sequence[str]) -> list[Heading]:
    """Detect nested ATX headings from a line scan of the exact text (AC1/AC2).

    ``lines`` must be ``exact_text.split("\\n")`` of the post-clean text the
    pipeline will chunk (D1). Triple-backtick fenced blocks (the ``clean_text``
    convention) suppress heading detection inside them; each heading attaches to
    the nearest preceding heading with a strictly lower level (D4). Never raises.
    """
    headings: list[Heading] = []
    stack: list[Heading] = []
    in_fence = False
    for line_index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_RE.match(line)
        if match is None:
            continue
        level = _normalize_heading_level(len(match.group(1)))
        title = _collapse_inline_whitespace(match.group(2))
        heading = Heading(level=level, line_index=line_index, title=title)
        while stack and stack[-1].level >= level:
            stack.pop()
        heading.parent = stack[-1] if stack else None
        stack.append(heading)
        headings.append(heading)
    return headings


# ── P2-303 block detector (frozen §4.3 / §8 AC3) ───────────────────────

BlockKind = Literal["paragraph", "list", "code", "blockquote", "table"]

_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+")  # mirrors utils.py:11
_TABLE_SEPARATOR_RE = re.compile(  # mirrors utils.py:13
    r"^\s*\|?[\s:-]+(?:\|[\s:-]+)+\|?\s*$"
)


@dataclass
class Block:
    """A typed text block with exact char offsets into the analyzed text (P2-303)."""

    type: BlockKind  # "paragraph" | "list" | "code" | "blockquote" | "table"
    text: str  # exact slice text[start_char:end_char] (R2)
    start_char: int  # 0-based, inclusive
    end_char: int  # exclusive; len(text) == end_char - start_char


def _detect_blocks(text: str, ranges: Sequence[tuple[int, int]]) -> list[Block]:
    """Detect typed blocks over the analyzed text's section ranges (AC1–AC7).

    ``text`` is the exact post-``clean_text`` analyzed text (D1) and ``ranges``
    are half-open ``[start_char, end_char)`` body spans into it. Classification
    precedence matches ``ingestion.utils._normalize_line``; the fence toggle is
    document-global and identical to ``_detect_headings``. Never raises.
    """
    blocks: list[Block] = []
    in_fence = False
    fence_lines: list[str] = []
    fence_start = 0
    run_type: BlockKind | None = None  # open paragraph/list/blockquote run
    run_lines: list[str] = []
    run_start = 0
    pipe_run: list[str] = []  # buffered "|"-leading run awaiting table verdict
    pipe_start = 0
    pipe_has_separator = False

    # ponytail: bisect membership instead of a per-line `any()` scan over every
    # range — that is O(lines * sections), which breaks the frozen O(n) ceiling
    # (spec §3) once the document is section-dense. Ranges partition the body,
    # so bisect on sorted starts finds the one candidate in O(log k).
    ordered_ranges = sorted(ranges)
    range_starts = [start for start, _ in ordered_ranges]

    def in_ranges(offset: int) -> bool:
        index = bisect_right(range_starts, offset) - 1
        return index >= 0 and offset < ordered_ranges[index][1]

    def emit(kind: BlockKind, start: int, lines: list[str]) -> None:
        joined = "\n".join(lines)
        blocks.append(Block(kind, joined, start, start + len(joined)))

    def flush() -> None:
        nonlocal run_type, pipe_has_separator
        if pipe_run:
            emit("table" if pipe_has_separator else "paragraph", pipe_start, pipe_run)
            pipe_run.clear()
            pipe_has_separator = False
        if run_type is not None:
            emit(run_type, run_start, run_lines)
            run_type = None
            run_lines.clear()

    pos = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):  # 1. fence toggle (document-global)
            flush()
            if in_fence:
                fence_lines.append(line)
                emit("code", fence_start, fence_lines)
                fence_lines = []
                in_fence = False
            else:
                in_fence = True
                fence_start = pos
                fence_lines = [line]
            pos += len(line) + 1
            continue
        if in_fence:  # 2. fenced content
            fence_lines.append(line)
            pos += len(line) + 1
            continue
        if not in_ranges(pos):  # 3. outside any section body
            flush()
            pos += len(line) + 1
            continue
        if not stripped or _HEADING_RE.match(line):  # 4. blank / 5. heading (D9)
            flush()
            pos += len(line) + 1
            continue
        if _LIST_RE.match(line) or (  # 6. list + best-effort continuation
            run_type == "list" and not stripped.startswith((">", "|"))
        ):
            if run_type == "list":
                run_lines.append(line)
            else:
                flush()
                run_type, run_start, run_lines = "list", pos, [line]
            pos += len(line) + 1
            continue
        if stripped.startswith(">"):  # 7. blockquote
            if run_type == "blockquote":
                run_lines.append(line)
            else:
                flush()
                run_type, run_start, run_lines = "blockquote", pos, [line]
            pos += len(line) + 1
            continue
        if stripped.startswith("|"):  # 8. pipe run (table verdict)
            if not pipe_run:
                flush()  # close any open run; pipe_run is empty, so nothing emitted
                pipe_start = pos
            pipe_run.append(line)
            pipe_has_separator = pipe_has_separator or bool(_TABLE_SEPARATOR_RE.match(stripped))
            pos += len(line) + 1
            continue
        if run_type == "paragraph":  # 9. paragraph
            run_lines.append(line)
        else:
            flush()
            run_type, run_start, run_lines = "paragraph", pos, [line]
        pos += len(line) + 1

    flush()
    if fence_lines:  # unclosed fence -> one code block
        emit("code", fence_start, fence_lines)
    return blocks


# ── P2-304 structure tree builder + analyzer entry (frozen §4.1/§4.3) ──

MAX_SECTIONS = 10_000  # frozen §7 / D6 / C-4: warn + truncate in tree order, never raise
max_structure_text_bytes = 5_000_000  # frozen §7 / D6 / C-4: skip analysis above this (R5)


def _build_tree(sections: Sequence[DocumentSection]) -> DocumentStructure:
    """Wrap assembled sections into a DocumentStructure (frozen §4.3)."""
    if not sections:
        return DocumentStructure(sections=[])
    if len(sections) > MAX_SECTIONS:
        warnings.warn(
            f"structure: {len(sections)} sections exceed MAX_SECTIONS={MAX_SECTIONS}; "
            "truncating in tree order",
            UserWarning,
            stacklevel=2,
        )
        sections = sections[:MAX_SECTIONS]
    return DocumentStructure(sections=list(sections))


class StructureAnalyzer:
    """Detect and build the hierarchical structure of source text (frozen §4.1)."""

    def analyze(self, text: str, source: str) -> DocumentStructure:
        if len(text.encode("utf-8")) > max_structure_text_bytes:
            # frozen §7 / P2-306: skip analysis for oversize text with a single warning
            warnings.warn(
                f"structure: skipping analysis; text exceeds "
                f"max_structure_text_bytes={max_structure_text_bytes}",
                UserWarning,
                stacklevel=2,
            )
            return DocumentStructure(sections=[])
        lines = text.split("\n")
        headings = _detect_headings(lines)
        if not headings:
            return DocumentStructure(sections=[])  # empty / whitespace-only / no headings

        line_starts: list[int] = []  # D1 seam: identical split + accumulation
        pos = 0
        for line in lines:
            line_starts.append(pos)
            pos += len(line) + 1

        sections: list[DocumentSection] = []
        ids_by_heading: dict[int, str] = {}  # id(heading) -> section id
        child_counts: dict[str | None, int] = {}
        ranges: list[tuple[int, int]] = []

        for j, heading in enumerate(headings):
            next_start = (
                line_starts[headings[j + 1].line_index] if j + 1 < len(headings) else len(text)
            )
            parent_id = ids_by_heading[id(heading.parent)] if heading.parent is not None else None
            child_counts[parent_id] = child_counts.get(parent_id, 0) + 1
            sid = (
                f"s-{child_counts[parent_id]}"
                if parent_id is None
                else f"{parent_id}-{child_counts[parent_id]}"
            )
            ids_by_heading[id(heading)] = sid

            body_start = min(
                line_starts[heading.line_index] + len(lines[heading.line_index]) + 1,
                len(text),
            )
            # ponytail: one all-ranges _detect_blocks call (frozen §5.3) — per-section
            # calls re-scan from pos 0 and leak closed fences from earlier sections
            # into later ones; a single call partitions the body region correctly.
            ranges.append((body_start, next_start))
            sections.append(
                DocumentSection(
                    id=sid,
                    title=heading.title,
                    level=heading.level,
                    parent_id=parent_id,
                    start_char=line_starts[heading.line_index],
                    end_char=next_start,
                    blocks=[],
                )
            )

        if any(start < end for start, end in ranges):
            # Attribute each block to the section whose body range contains its start.
            # Blocks are emitted in document order and ranges tile the body in order,
            # so a single advancing pointer suffices.
            section_index = 0
            for block in _detect_blocks(text, ranges):
                while (
                    section_index < len(sections) and block.start_char >= ranges[section_index][1]
                ):
                    section_index += 1
                if section_index >= len(sections):
                    break
                if block.start_char < ranges[section_index][0]:
                    continue  # block began outside any body (e.g. preamble fence) -> dropped
                section = sections[section_index]
                section.blocks.append(
                    DocumentBlock(
                        block_id=f"b-{section.id}-{len(section.blocks) + 1}",
                        type=block.type,
                        text=block.text,
                        start_char=block.start_char,
                        end_char=block.end_char,
                    )
                )

        return _build_tree(sections)


def get_default_structure_analyzer() -> StructureAnalyzer:
    """Return a StructureAnalyzer (frozen §4.3 composition root)."""
    return StructureAnalyzer()  # stateless; fresh instance is reentrant-safe (O-2)
