"""Semantic chunking for knowledge engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.domain.semantic_chunking import DocumentChunk
from app.infrastructure.sentence_tokenizer import SentenceTokenizer, get_sentence_tokenizer

logger = get_logger(__name__)

_HEADING_PATTERN = re.compile(r"^#{1,6}\s+.+", re.MULTILINE)
_LIST_ITEM_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+")  # mirrors ingestion.utils._LIST_PATTERN
_LIST_ITEM_RE_M = re.compile(_LIST_ITEM_RE.pattern, re.MULTILINE)  # boundary scan for overlap snap
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")  # CommonMark code fence
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
_CODE_TERMINATORS = ".!?"  # sentence characters masked inside inline code spans
_TABLE_SEPARATOR_RE = re.compile(  # mirrors ingestion.utils:13 and detector.py:82
    r"^\s*\|?[\s:-]+(?:\|[\s:-]+)+\|?\s*$"
)
_OPEN_TABLE_RE = re.compile(r"<\s*table\b", re.IGNORECASE)
_CLOSE_TABLE_RE = re.compile(r"</\s*table\s*>", re.IGNORECASE)
_CALLOUT_RE = re.compile(r"^\[[ \t]*![ \t]*([A-Za-z][A-Za-z0-9-]*)[ \t]*\]")
_DD_RE = re.compile(r"^\s*:[ \t]")  # Pandoc-style definition-list marker
_ATOMIC_KINDS = frozenset(
    {"code", "table", "html_table", "blockquote", "callout", "definition"}
)


@dataclass(frozen=True)
class ChunkingPolicy:
    """Adaptive chunking knobs (P3-205).

    All defaults reproduce P3-204 output exactly:

    - ``heading_size_step``: dynamic chunk sizing — the effective chunk budget
      for a section shrinks by this many characters per heading level below 1
      (``# Title`` keeps the base ``max_chunk_chars``; ``### Title`` loses
      ``2 * heading_size_step``). ``0`` (default) keeps fixed sizing.
    - ``min_chunk_chars``: floor for the dynamic budget.
    - ``snap_overlap``: paragraph/list-aware overlap — the prepended tail
      starts at the last paragraph (blank-line) or list-item boundary at or
      before the raw cut instead of mid-paragraph / mid-list-item.
    - ``snap_max_back``: how far back the snap search may extend.
    - ``heading_overlap_boundary``: heading-aware overlap — a chunk whose text
      begins with a heading is a hard boundary: no tail is prepended into it.
    """

    heading_size_step: int = 0
    min_chunk_chars: int = 200
    snap_overlap: bool = False
    snap_max_back: int = 2000
    heading_overlap_boundary: bool = False


def _is_structured_line(line: str) -> bool:
    """True when a line can only belong to structured content.

    Drives the ``chunk()`` shortcut: a section containing any such line routes
    through the block path so structured blocks are emitted atomically with
    their structure metadata even when the whole section fits the budget.
    """
    stripped = line.strip()
    return (
        bool(_FENCE_RE.match(line))
        or stripped.startswith((">", "|", ":"))
        or bool(_OPEN_TABLE_RE.search(line))
    )


def _mask_inline_code(text: str, spans: list[tuple[int, int]]) -> str:
    """Replace sentence terminators inside backtick spans with same-length
    neutral characters so a tokenizer never sees a boundary inside inline code."""
    chars = list(text)
    for start, end in spans:
        for p in range(start, end):
            if text[p] in _CODE_TERMINATORS:
                chars[p] = "_"
    return "".join(chars)


def _split_blocks(text: str) -> list[tuple[str, str, dict[str, str]]]:
    """Split into ``("kind", block_text, extra_metadata)`` blocks.

    Blank lines end a block. Block kinds, in detection order: fenced ``code``
    (CommonMark, swallows everything until the matching close); ``html_table``
    (``<table>`` through ``</table>``, case-insensitive, or end of text);
    ``table`` (a ``|``-leading pipe run that contains a GFM separator row —
    mirrors ``ingestion.utils:13``/the structure detector, so a pipe run without
    a separator stays a ``paragraph``); ``blockquote`` / ``callout`` (``>``-
    leading lines grouped verbatim; a first line whose content is ``[!TAG]``
    makes it a ``callout`` carrying ``callout_type``); ``definition`` (Pandoc
    ``Term`` / ``: definition`` lists, keeping indented continuation lines);
    ``list``; and ``paragraph``. All structured kinds are atomic and keep their
    content byte-for-byte. Never raises; purely derived from ``text``, so the
    output is deterministic.
    """
    lines = text.split("\n")
    blocks: list[tuple[str, str, dict[str, str]]] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        fence = _FENCE_RE.match(lines[i])
        if fence:
            run = [lines[i]]
            i += 1
            fence_char = fence.group(1)[0]
            while i < len(lines):
                run.append(lines[i])
                candidate = _FENCE_RE.match(lines[i])
                if (
                    candidate is not None
                    and candidate.group(1)[0] == fence_char
                    and len(candidate.group(1)) >= len(fence.group(1))
                    and not candidate.group(2).strip()
                ):
                    i += 1
                    break
                i += 1
            info = fence.group(2).strip()
            lang = info.split()[0] if info else ""
            blocks.append(("code", "\n".join(run), {"language": lang}))
            continue
        if _OPEN_TABLE_RE.search(lines[i]):
            run = [lines[i]]
            i += 1
            while i < len(lines) and not _CLOSE_TABLE_RE.search(lines[i - 1]):
                run.append(lines[i])
                i += 1
            blocks.append(
                ("html_table", "\n".join(run), {"structure_type": "html_table"})
            )
            continue
        if stripped.startswith("|"):
            run = [lines[i]]
            has_separator = bool(_TABLE_SEPARATOR_RE.match(stripped))
            i += 1
            while i < len(lines) and lines[i].strip().startswith("|"):
                run.append(lines[i])
                has_separator = has_separator or bool(
                    _TABLE_SEPARATOR_RE.match(lines[i].strip())
                )
                i += 1
            if has_separator:
                blocks.append(("table", "\n".join(run), {"structure_type": "table"}))
            else:
                blocks.append(("paragraph", "\n".join(run), {}))
            continue
        if stripped.startswith(">"):
            run = [lines[i]]
            i += 1
            while i < len(lines) and lines[i].strip().startswith(">"):
                run.append(lines[i])
                i += 1
            first_content = re.sub(r"^>+[ \t]*", "", run[0]).strip()
            callout = _CALLOUT_RE.match(first_content)
            if callout:
                blocks.append((
                    "callout",
                    "\n".join(run),
                    {
                        "structure_type": "callout",
                        "callout_type": callout.group(1).lower(),
                    },
                ))
            else:
                blocks.append(
                    ("blockquote", "\n".join(run), {"structure_type": "blockquote"})
                )
            continue
        if _DD_RE.match(lines[i]) or (
            i + 1 < len(lines) and _DD_RE.match(lines[i + 1])
        ):
            run = [lines[i]]
            i += 1
            while i < len(lines):
                next_stripped = lines[i].strip()
                if not next_stripped or not (
                    _DD_RE.match(lines[i]) or lines[i].startswith((" ", "\t"))
                ):
                    break
                run.append(lines[i])
                i += 1
            blocks.append(
                ("definition", "\n".join(run), {"structure_type": "definition_list"})
            )
            continue
        kind = "list" if _LIST_ITEM_RE.match(lines[i]) else "paragraph"
        run = [lines[i]]
        i += 1
        while i < len(lines):
            next_line = lines[i]
            next_stripped = next_line.strip()
            if not next_stripped or next_stripped.startswith((">", "|")):
                break
            if _FENCE_RE.match(next_line) or _OPEN_TABLE_RE.search(next_line):
                break
            if i + 1 < len(lines) and _DD_RE.match(lines[i + 1]):
                break
            if kind == "paragraph" and _LIST_ITEM_RE.match(next_line):
                break
            run.append(next_line)
            i += 1
        blocks.append((kind, "\n".join(run), {}))
    return blocks


@dataclass
class SemanticChunker:
    """Split text into semantic chunks by headings, then by max size.

    Sentence splitting delegates to the ``sentence_tokenizer`` engine resolved
    once at construction (D8): ``"auto"`` (default) prefers the NLTK
    ``punkt_tab`` engine when available and otherwise degrades to the stdlib
    heuristic engine with one logged warning (D4); ``"heuristic"`` and
    ``"nltk"`` select an engine explicitly.
    """

    max_chunk_chars: int = 2000
    overlap_chars: int = 200
    sentence_tokenizer: str = "auto"
    policy: ChunkingPolicy = field(default_factory=ChunkingPolicy)

    _tokenizer: SentenceTokenizer = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._tokenizer = get_sentence_tokenizer(self.sentence_tokenizer)
        logger.debug(
            "Sentence tokenizer resolved.",
            extra={
                "engine": self.sentence_tokenizer,
                "resolved": type(self._tokenizer).__name__,
            },
        )

    def chunk(
        self,
        text: str,
        source: str,
        source_type: str,
    ) -> list[DocumentChunk]:
        if not text.strip():
            return []

        sections = self._split_by_headings(text)
        chunks: list[DocumentChunk] = []
        chunk_index = 0

        for section_start, section_text, heading_meta in sections:
            meta = dict(heading_meta) if heading_meta else {}
            budget = self._budget_for_level(meta)
            has_structured = any(
                _is_structured_line(line) for line in section_text.split("\n")
            )
            if len(section_text) <= budget and not has_structured:
                chunks.append(DocumentChunk(
                    chunk_id=f"{source}::chunk_{chunk_index}",
                    text=section_text.strip(),
                    source=source,
                    source_type=source_type,
                    chunk_index=chunk_index,
                    start_char=section_start,
                    end_char=section_start + len(section_text),
                    metadata=meta,
                ))
                chunk_index += 1
            else:
                sub_chunks = self._split_long_section(section_text, section_start, budget)
                for start, end, sub_text, extra in sub_chunks:
                    chunks.append(DocumentChunk(
                        chunk_id=f"{source}::chunk_{chunk_index}",
                        text=sub_text.strip(),
                        source=source,
                        source_type=source_type,
                        chunk_index=chunk_index,
                        start_char=start,
                        end_char=end,
                        metadata={**meta, **extra},
                    ))
                    chunk_index += 1

        chunks = self._apply_overlap(chunks)

        logger.debug(
            "Document chunked.",
            extra={"source": source, "chunks": len(chunks), "text_length": len(text)},
        )
        return chunks

    def _apply_overlap(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        """Prepend the previous chunk's tail to each chunk after the first.

        Structured chunks (fenced code, tables, blockquotes, callouts, definition
        lists — anything carrying ``language`` or ``structure_type`` metadata) are
        hard boundaries: their text is never prefixed with prose and never leaks
        its own tail into the next chunk, so structured formatting stays verbatim
        even under overlap. With ``heading_overlap_boundary`` (P3-205) a chunk
        whose text begins with a heading is likewise a hard boundary — no tail is
        prepended into a fresh section.
        """
        if self.overlap_chars <= 0 or len(chunks) < 2:
            return chunks

        overlapped: list[DocumentChunk] = []
        previous_is_structured = False
        for index, chunk in enumerate(chunks):
            is_structured = "language" in chunk.metadata or "structure_type" in chunk.metadata
            text = chunk.text
            heading_boundary = (
                self.policy.heading_overlap_boundary
                and _HEADING_PATTERN.match(chunk.text) is not None
            )
            if index > 0 and not previous_is_structured and not is_structured:
                if not heading_boundary:
                    text = self._overlap_tail(chunks[index - 1].text) + text
            previous_is_structured = is_structured
            overlapped.append(DocumentChunk(
                chunk_id=chunk.chunk_id,
                text=text,
                source=chunk.source,
                source_type=chunk.source_type,
                chunk_index=chunk.chunk_index,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                metadata=chunk.metadata,
            ))
        return overlapped

    def _budget_for_level(self, meta: dict[str, str]) -> int:
        """Effective chunk budget for a section, shrunk by heading depth (P3-205).

        ``# Title`` keeps the base ``max_chunk_chars``; each level below 1 loses
        ``heading_size_step`` chars, floored at ``min_chunk_chars``. A step of
        ``0`` (default) keeps fixed sizing.
        """
        if self.policy.heading_size_step <= 0:
            return self.max_chunk_chars
        level = 1
        raw_level = meta.get("heading_level")
        if raw_level and raw_level.isdigit():
            level = int(raw_level)
        return max(
            self.max_chunk_chars - self.policy.heading_size_step * (level - 1),
            self.policy.min_chunk_chars,
        )

    def _overlap_start(self, text: str) -> int:
        """Start of the prepended tail, snapped to a semantic boundary (P3-205).

        With ``snap_overlap`` the raw cut is pushed back to the last paragraph
        (blank-line) or top-level list-item boundary at or before it within
        ``snap_max_back``, so the tail never begins mid-paragraph or
        mid-list-item. The default (``snap_overlap=False``) keeps the raw cut.
        """
        cut = max(0, len(text) - self.overlap_chars)
        if not self.policy.snap_overlap:
            return cut
        search_from = max(0, cut - self.policy.snap_max_back)
        boundaries: list[int] = []
        blank = text.rfind("\n\n", search_from, cut)
        if blank >= 0:
            boundaries.append(blank + 2)
        for match in _LIST_ITEM_RE_M.finditer(text, search_from, cut):
            boundaries.append(match.start())
        return max(boundaries) if boundaries else cut

    def _overlap_tail(self, text: str) -> str:
        return text[self._overlap_start(text):]

    def _split_by_headings(
        self, text: str,
    ) -> list[tuple[int, str, dict[str, str] | None]]:
        """Split into ``(start, section_text, heading_meta)`` sections.

        Each heading-led section carries its own heading metadata; the preamble
        (text before the first heading) is ``None``. Metadata is derived purely
        from the text scan, so the output is deterministic. A heading's parent
        is the nearest preceding heading with a strictly lower level (a level
        skip such as ``# A`` -> ``### C`` makes A the parent of C), matching
        the structure detector's D4 rule.
        """
        matches = list(_HEADING_PATTERN.finditer(text))
        if not matches:
            return [(0, text, None)]

        sections: list[tuple[int, str, dict[str, str] | None]] = []
        if matches[0].start() > 0:
            sections.append((0, text[: matches[0].start()], None))

        stack: list[tuple[str, str, int]] = []  # open headings: (title, path, level)
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            raw = match.group(0)
            hashes = raw[: len(raw) - len(raw.lstrip("#"))]
            title = raw[len(hashes):].strip()
            level = len(hashes)
            while stack and stack[-1][2] >= level:
                stack.pop()
            parent_title = stack[-1][0] if stack else ""
            path = f"{stack[-1][1]}/{title}" if stack else title
            meta = {
                "heading": title,
                "heading_level": str(level),
                "heading_path": path,
                "parent_heading": parent_title,
            }
            stack.append((title, path, level))
            sections.append((start, text[start:end], meta))

        return sections

    def _split_long_section(
        self, text: str, base_offset: int, budget: int | None = None,
    ) -> list[tuple[int, int, str, dict[str, str]]]:
        budget = self.max_chunk_chars if budget is None else budget
        blocks = _split_blocks(text)
        result: list[tuple[int, int, str, dict[str, str]]] = []
        current = ""
        current_start = base_offset

        for kind, block, extra in blocks:
            if kind in _ATOMIC_KINDS:
                if current:
                    result.append((current_start, current_start + len(current), current, {}))
                    current_start += len(current)
                    current = ""
                result.append(
                    (current_start, current_start + len(block), block, extra)
                )
                current_start += len(block)
                continue
            if len(current) + len(block) + 2 <= budget:
                current = f"{current}\n\n{block}" if current else block
            else:
                if current:
                    result.append((current_start, current_start + len(current), current, {}))
                    current_start += len(current)
                if len(block) <= budget:
                    current = block
                elif kind == "list":
                    sub_chunks = self._split_list_block(block, current_start, budget)
                    if sub_chunks:
                        result.extend((s, e, t, {}) for s, e, t in sub_chunks)
                        current_start = sub_chunks[-1][1]
                    current = ""
                else:
                    sentence_chunks = self._split_by_sentences(block, current_start, budget)
                    if sentence_chunks:
                        result.extend((s, e, t, {}) for s, e, t in sentence_chunks)
                        current_start = sentence_chunks[-1][1]
                    else:
                        result.append(
                            (current_start, current_start + len(block), block, {})
                        )
                        current_start += len(block)
                    current = ""

        if current:
            result.append((current_start, current_start + len(current), current, {}))

        return result

    def _split_list_block(
        self, text: str, base_offset: int, budget: int | None = None,
    ) -> list[tuple[int, int, str]]:
        """Split an over-long list block at whole top-level items, never mid-item.

        A top-level item is a base-indentation item line plus all its indented
        nested/continuation lines; splits happen only at base-level item boundaries,
        so ordered/unordered/nested list structure is preserved and no sentence
        splitter ever runs inside a list block.
        """
        budget = self.max_chunk_chars if budget is None else budget
        lines = text.split("\n")
        base_match = _LIST_ITEM_RE.match(lines[0])
        base_indent = len(base_match.group(1)) if base_match else 0
        item_starts: list[int] = []
        for idx, line in enumerate(lines):
            match = _LIST_ITEM_RE.match(line)
            if match is not None and len(match.group(1)) == base_indent:
                item_starts.append(idx)
        items = [
            "\n".join(lines[start:end])
            for start, end in zip(
                item_starts,
                [*item_starts[1:], len(lines)],
                strict=False,
            )
        ]

        result: list[tuple[int, int, str]] = []
        current = ""
        offset = base_offset
        for item in items:
            if len(current) + len(item) + 1 <= budget:
                current = f"{current}\n{item}" if current else item
            else:
                if current:
                    result.append((offset, offset + len(current), current))
                    offset += len(current)
                current = item

        if current:
            result.append((offset, offset + len(current), current))

        return result

    def _split_by_sentences(
        self, text: str, base_offset: int, budget: int | None = None,
    ) -> list[tuple[int, int, str]]:
        budget = self.max_chunk_chars if budget is None else budget
        spans = [m.span() for m in _INLINE_CODE_RE.finditer(text)]
        masked = _mask_inline_code(text, spans) if spans else text
        sentences = self._tokenizer.split(masked)
        result: list[tuple[int, int, str]] = []
        current = ""
        offset = base_offset
        search_from = 0

        for sentence in sentences:
            if spans:
                index = masked.find(sentence, search_from)
                restored = list(sentence)
                for start, end in spans:
                    low = max(start, index)
                    high = min(end, index + len(sentence))
                    for p in range(low, high):
                        restored[p - index] = text[p]
                sentence = "".join(restored)
                search_from = index + len(sentence)
            if len(current) + len(sentence) + 1 <= budget:
                current = f"{current} {sentence}" if current else sentence
            else:
                if current:
                    result.append((offset, offset + len(current), current))
                    offset += len(current)
                current = sentence

        if current:
            result.append((offset, offset + len(current), current))

        return result
