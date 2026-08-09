# Milestone 2.3 — P2-303 Implementation Specification: Block Detector

**Milestone:** 2.3 — Document Structure Analysis
**Task:** P2-303 — Block detector (paragraph/list/code fence/blockquote/table)
**Status:** Implementation specification (no code implemented by this document)
**Governing contract:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` v1.1 (🔒 FROZEN 2026-08-01) — §4.3 (internal API `_detect_blocks`), §6 (data flow), §7 (R2 offsets), §8 AC3, §10 R1/R2, §11.1 (P2-303 row), §12, §13, §14.
**Design decisions:** `docs/PHASE_2_MILESTONE_2_3_IMPLEMENTATION_ROADMAP.md` D1 (exact analyzed text), D4/D5 (ID schemes — assigned by P2-304), D6 (caps — P2-306), D9 (heading rule).
**Predecessor:** P2-301 implemented and ✅ approved (`docs/PHASE_2_MILESTONE_2_3_P2-301_ENGINEERING_REVIEW.md`); P2-302 implemented and ✅ approved (`docs/PHASE_2_MILESTONE_2_3_P2-302_ENGINEERING_REVIEW.md`) — `detector.py` exists with `_detect_headings`, `Heading`, `_HEADING_RE`, `MAX_HEADING_LEVEL`, `_normalize_heading_level`.

---

## 1. Objective

Detect typed blocks — **paragraph, list, code fence, blockquote, Markdown table** —
from the exact post-`clean_text` analyzed text, over the text ranges belonging to
each heading section, and produce block records with **accurate `start_char`/`end_char`**
offsets into that exact text (frozen §4.2 offset contract). The block detector is the
second of the two wave-2 detectors (P2-302 ‖ P2-303): it consumes nothing from
`_detect_headings` at runtime (P2-304 feeds it section ranges) but shares the same
fence-state convention so fenced content is never split into heading/paragraph blocks.

**This task delivers the block detector only.** `_build_tree`, `analyze(text, source)`,
`StructureAnalyzer`, composition-root stubs, `TEXT_BEARING_KINDS`, `MAX_SECTIONS`, and
`max_structure_text_bytes` are owned by P2-304 / P2-305 / P2-306 and are **not**
introduced here (frozen §11.1 P2-303 row files = `structure/detector.py`).

## 2. Scope

### 2.1 In scope

- `_detect_blocks(text, ranges)` — line classification (fence / heading / list /
  blockquote / table / paragraph) + block grouping + exact char offsets.
- `Block` internal record: `type`, `text`, `start_char`, `end_char` (id-less —
  `block_id` is P2-304's job, roadmap D5).
- `ranges: Sequence[tuple[int, int]]` — half-open `[start_char, end_char)` body spans
  (heading lines excluded), derived by P2-304 from heading line positions (D1 seam).
- List nesting + best-effort list-continuation; blockquote continuation; pipe-table
  detection on the M2.2 `clean_text`-normalized table form; fenced code = one
  multi-line block; paragraph splitting on blank lines; heading lines never blocks.
- Unit tests appended to `tests/unit/test_structure_analysis.py` + committed fixtures
  `tests/fixtures/structure/blocks.md`, `lists_and_quotes.md`, `table_block.md`
  (roadmap §4/§5, frozen §13 / L6).

### 2.2 Out of scope (explicitly deferred — R10 guard)

- Tree building, section IDs (`s-1`/`s-1-1`), section spans, empty-tree handling,
  block ID assignment (`b-<section.id>-<n>`, D5) → P2-304.
- `StructureAnalyzer` / `analyze()` entry point and composition-root stubs → P2-304.
- `TEXT_BEARING_KINDS`, `enabled` config plumbing, enrichment → P2-305.
- 5 MB size cap, `MAX_SECTIONS`, O(n) timing ceiling → P2-306.
- `~~~`-fenced blocks, HTML/markup parsing, closing-sequence (`# Title #`) handling —
  best-effort only, consistent with P2-302 / frozen §2.2.
- **No change to `_detect_headings`, `Heading`, or `_HEADING_RE`** — P2-302's D9 rule
  already anchors `#` at line start, so a blockquote `> # Title` is already *not* a
  heading; the heading detector is blockquote-tight as delivered and is untouched here.
- Any change to `SemanticChunker` or its `_HEADING_PATTERN` (frozen AC5 — byte-identical).

## 3. Dependencies

| Dependency | Type | Detail |
|------------|------|--------|
| P2-301 models | Required, existing | Conceptual prerequisite (milestone order); `_detect_blocks` returns plain `Block` records and does **not** import the pydantic models — P2-304 maps `Block` → `DocumentBlock` (adding `block_id`) and `BlockType` Literal. |
| P2-302 `detector.py` | Required, existing | Same module; P2-303 appends to it and reuses the module-level `_HEADING_RE` (heading-line skip) and the identical fence-toggle rule. |
| `re`, `dataclasses`, `typing` (stdlib) | Required, existing | `_LIST_RE`, `_TABLE_SEPARATOR_RE`, `Block` record, `BlockKind` Literal, `Sequence`. |
| `app/infrastructure/ingestion/utils.py` | Reference only | `clean_text` normalization conventions (`_normalize_line`, `_LIST_PATTERN`, `_TABLE_SEPARATOR_PATTERN`) define the *input shape*; the detector does **not** import ingestion internals (see §4 classification-regex note). |
| New dependencies | **None** | Zero new runtime or optional packages (frozen §3 — pure stdlib parsing). |

**Input-text contract (D1):** `_detect_blocks` receives `text` = the exact post-`clean_text`
text the pipeline will chunk (`result.extracted_text or document.text`), and `ranges`
are char offsets into that same `text`. P2-304 derives the ranges by re-splitting the
identical text (`text.split("\n")`, the same split P2-302 used) with offset accumulation
to map `Heading.line_index` → `start_char` (frozen R2 — offsets never drift; any other
splitter is forbidden).

## 4. Architecture

- **Placement:** appended to `app/infrastructure/document_intelligence/structure/detector.py` —
  the frozen §4.3 package layout (analyzer + `_detect_headings` + `_detect_blocks` + `_build_tree`
  all live here). P2-303 adds `_detect_blocks` + `Block` + classification regexes next to the
  P2-302 code.
- **Layer:** infrastructure parser over domain models. This task holds **no** domain model
  changes and adds nothing to `app/domain/`.
- **Shape:** one more pure function in the existing module. `_detect_blocks(text, ranges)`
  is the only new public-to-the-task function; `Block` is a plain mutable dataclass (P2-304
  copies its values into `DocumentBlock`; no post-construction mutation is required, but the
  dataclass stays mutable for consistency with `Heading`).
- **Reentrancy (O-2):** pure function, no module-level mutable state — all state (`in_fence`,
  run buffers, `pos`) is local to the call.
- **Failure modes (frozen §3):** never raises. Every non-matching line is skipped; malformed/
  unclosed fences and out-of-bounds ranges degrade gracefully, never an exception.
- **Classification regexes are local copies, not imports (documented decision):** the
  detector re-declares `_LIST_RE` and `_TABLE_SEPARATOR_RE` mirroring `utils.py`'s
  `_LIST_PATTERN` / `_TABLE_SEPARATOR_PATTERN` (the exact strings are pinned in §5.1).
  `structure/` must not reach into `ingestion/` internals (upstream coupling, private names);
  the `clean_text`-boundary test (§12) pins agreement so drift is caught at the seam.
- **No wiring:** nothing in `app/` calls `_detect_blocks` this task; the only consumers are
  its unit tests. P2-304 is the first production caller.

## 5. Algorithms

### 5.1 Input shape (post-`clean_text`, normative)

`clean_text` (`utils.py:16-41`) normalizes every line before the detector sees it; the
detector's classification rules operate on that normalized shape:

| Line kind | Post-`clean_text` form (`utils.py` rule) |
|-----------|------------------------------------------|
| Heading | `# Title` at line start (dedented; marks + single space + collapsed title) |
| List item | `{2-space-indent}{marker} {collapsed}` — marker `[-*+]` or `\d+[.)]` (`_normalize_list_item`) |
| Blockquote | `> ` repeated `quote_depth` times + collapsed content (`_normalize_blockquote`) |
| Table row | `| cell | cell |` — cells joined with ` | `, wrapped in `| ... |` (`_normalize_table_row`) |
| Table separator | `|---|-----|` — all-dash normalized; `:---:` alignment survives (`_normalize_line` separator branch) |
| Paragraph | single collapsed non-blank line (`_collapse_inline_whitespace`) |
| Blank | `""` (blank streaks collapsed to 1) |
| Fenced code | marker lines ` ``` ` + raw content (protected verbatim, incl. ` ```python ` info string) |

**Classification regexes (module constants, exact):**

```python
_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+")            # mirrors utils.py:11
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:-]+(?:\|[\s:-]+)+\|?\s*$")  # mirrors utils.py:13
# blockquote: stripped.startswith(">")                          # mirrors utils.py:110
# fence toggle: stripped.startswith("```")                       # mirrors utils.py:59, P2-302 §5.2
# heading skip: _HEADING_RE (reused from P2-302, line 11)        # D9
```

### 5.2 Per-line classification precedence (normative)

For each line (with its char offset `pos` into `text`), evaluated in this order —
**identical to `_normalize_line`'s precedence** (`utils.py:101-119`), keeping detector and
input consistent by construction:

1. **Fence toggle** — `stripped.startswith("```")` flips a **document-global** `in_fence`
   flag, exactly as in `_detect_headings` (P2-302 §5.2). Runs before the range-membership
   check so fence state is identical across both detectors (frozen AC2/AC3 agreement).
2. **In fence** — the line joins the current `code` block buffer (never evaluated for
   headings/lists/etc.). The `code` block spans the **opening fence line through the closing
   fence line, inclusive** (info string kept in the text); an unclosed fence emits one
   `code` block from the opening fence to end of text.
3. **Range membership** — if `pos` is not inside any `ranges` span, the line is skipped and
   any open block is flushed (blocks never span section ranges).
4. **Blank** — flush open block (blank lines are structural separators, never block content).
5. **Heading (D9)** — `_HEADING_RE.match(line)` → flush, skip. A heading line is **never**
   a block (its title becomes the section title; P2-304).
6. **List** — `_LIST_RE.match(line)` (any indent depth) → list block. Also a **list
   continuation**: any non-blank, non-special line (not heading/fence/blockquote/table)
   immediately following list content with no blank line is absorbed into the same list
   block (best-effort per frozen R1 "list-continuation lines").
7. **Blockquote** — `stripped.startswith(">")` (any depth `>`, `>>`, …) → blockquote block;
   consecutive blockquote lines merge into one block.
8. **Table** — `stripped.startswith("|")` → buffered into a **pipe run**. When the run ends
   (blank / heading / non-`|` line / range edge / EOF): if the run contains ≥ 1 line matching
   `_TABLE_SEPARATOR_RE` → one `table` block for the whole run; otherwise → one `paragraph`
   block (best-effort: a lone `| x | y |` line with no separator is treated as a paragraph).
9. **Paragraph** — anything else non-blank; consecutive paragraph lines (no blank between)
   merge into one paragraph block.

**Grouping invariant:** a block is the maximal run of contiguous lines of the same kind
separated only by content lines; a blank line, a heading line, a range edge, a fence toggle,
or a kind change (e.g. list→paragraph) closes the current block. Blocks are **content-only**:
no leading/trailing blank lines, no heading lines. Blank lines and heading lines are
structural gaps.

### 5.3 Offsets and ranges (normative — R2)

- Offsets are relative to `text` (D1). The scan walks `text.split("\n")` with offset
  accumulation (`pos += len(line) + 1`, the `+1` for the `\n`) — the exact split P2-302
  pins and P2-304 reuses.
- For every block: `start_char` = offset of its first character, `end_char` = one past its
  last character (exclusive), and the **literal-slice invariant** holds by construction:
  `text[start_char:end_char] == block.text` and `len(block.text) == end_char - start_char`
  — matching the `DocumentBlock` validator in P2-301 (start inclusive / end exclusive).
- `ranges` are half-open `[start, end)` spans into `text` (line-aligned in practice —
  derived from heading line positions). Blocks are attributed to a range and **flushed at
  range edges**, so a block never spans two sections. Empty `ranges=()` → `[]`. Out-of-bounds
  or non-line-aligned ranges are handled gracefully (per-line membership check, never raises).
- **Fence/range invariant:** because `_detect_headings` never emits a heading inside a fence,
  no range boundary falls inside a fence; code blocks therefore never span ranges.

### 5.4 Pseudocode (normative shape)

```python
@dataclass
class Block:
    type: BlockKind            # "paragraph" | "list" | "code" | "blockquote" | "table"
    text: str                  # exact slice text[start_char:end_char] (R2)
    start_char: int            # 0-based, inclusive
    end_char: int              # exclusive; len(text) == end_char - start_char

def _detect_blocks(text: str, ranges: Sequence[tuple[int, int]]) -> list[Block]:
    blocks: list[Block] = []
    in_fence = False
    fence_lines: list[str] = []
    fence_start = 0
    run_type: BlockKind | None = None      # open paragraph/list/blockquote run
    run_lines: list[str] = []
    run_start = 0
    pipe_run: list[str] = []               # buffered "|"-leading run awaiting table verdict
    pipe_start = 0
    pipe_has_separator = False

    def in_ranges(offset: int) -> bool:
        return any(start <= offset < end for start, end in ranges)

    def emit(kind: BlockKind, start: int, lines: list[str]) -> None:
        joined = "\n".join(lines)
        blocks.append(Block(kind, joined, start, start + len(joined)))

    def flush() -> None:
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
        if stripped.startswith("```"):                      # 1. fence toggle (global)
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
        if in_fence:                                        # 2. fenced content
            fence_lines.append(line)
            pos += len(line) + 1
            continue
        if not in_ranges(pos):                              # 3. outside any section body
            flush()
            pos += len(line) + 1
            continue
        if not stripped or _HEADING_RE.match(line):         # 4. blank / 5. heading (D9)
            flush()
            pos += len(line) + 1
            continue
        if _LIST_RE.match(line) or (                        # 6. list + continuation
            run_type == "list" and not stripped.startswith((">", "|"))
        ):
            if run_type == "list":
                run_lines.append(line)
            else:
                flush()
                run_type, run_start, run_lines = "list", pos, [line]
            pos += len(line) + 1
            continue
        if stripped.startswith(">"):                        # 7. blockquote
            if run_type == "blockquote":
                run_lines.append(line)
            else:
                flush()
                run_type, run_start, run_lines = "blockquote", pos, [line]
            pos += len(line) + 1
            continue
        if stripped.startswith("|"):                        # 8. pipe run (table verdict)
            flush()
            if not pipe_run:
                pipe_start = pos
            pipe_run.append(line)
            pipe_has_separator = pipe_has_separator or bool(_TABLE_SEPARATOR_RE.match(stripped))
            pos += len(line) + 1
            continue
        if run_type == "paragraph":                         # 9. paragraph
            run_lines.append(line)
        else:
            flush()
            run_type, run_start, run_lines = "paragraph", pos, [line]
        pos += len(line) + 1

    flush()
    if fence_lines:                                         # unclosed fence -> one code block
        emit("code", fence_start, fence_lines)
    return blocks
```

Degenerate inputs: empty `text` → `[]`; empty `ranges` → `[]`; whitespace-only ranges →
`[]`; a lone ` ``` ` → fence state toggled with no content (no blocks); null bytes are
already stripped by `clean_text` and are skipped defensively (never raises).

## 6. Public Interfaces

### 6.1 Internal record (module-scoped, not exported)

```python
@dataclass
class Block:
    type: BlockKind            # "paragraph" | "list" | "code" | "blockquote" | "table"
    text: str                  # exact slice text[start_char:end_char] (R2)
    start_char: int            # 0-based, inclusive
    end_char: int              # exclusive; len(text) == end_char - start_char
```

With `BlockKind = Literal["paragraph", "list", "code", "blockquote", "table"]` — a module-level
type alias mirroring the domain `BlockType` strings (`app/domain/document_intelligence.py:20`)
without importing pydantic. **Deliberately id-less:** `block_id` requires the owning section id
(`b-<section.id>-<n>`, roadmap D5), which only exists after P2-304 builds the tree — assigning
ids here would couple the detector to tree structure.

### 6.2 Internal API (frozen §4.3 name)

```python
def _detect_blocks(text: str, ranges: Sequence[tuple[int, int]]) -> list[Block]: ...
```

- **Import path (tests and later tasks):** `from app.infrastructure.document_intelligence.structure.detector import _detect_blocks, Block`.
- **Contract:** never raises; `text` is the exact post-`clean_text` analyzed text (D1);
  `ranges` are half-open `[start_char, end_char)` spans into `text` (empty → `[]`); output
  blocks are non-overlapping, slice-exact, in document order (stable, R8); `type` ∈ the five
  `BlockKind` strings.
- **Deferred (NOT this task):** `_build_tree(sections)`, `analyze(text, source)`,
  `StructureAnalyzer`, composition-root stubs, `TEXT_BEARING_KINDS`, `MAX_SECTIONS`,
  `max_structure_text_bytes` — P2-304/305/306. `DocumentBlock` construction + `block_id` (D5)
  — P2-304.
- **No `__all__` and no public name added to any existing module** — the only repository
  surface change is inside the existing `structure/detector.py` plus new tests/fixtures.

## 7. Data Flow

```mermaid
flowchart LR
    T[exact text<br/>post-clean_text<br/>D1] --> S[lines = text.split('\n')<br/>+ offset accumulation]
    S --> D[_detect_blocks text, ranges]
    D --> F{fence-toggle?}
    F -- yes --> CODE[code block: open..close fence lines]
    F -- no, in-fence --> CODE
    F -- no --> R{in ranges?}
    R -- no --> SKIP[skip line]
    R -- yes --> H{heading? D9}
    H -- yes --> SKIP2[skip line - never a block]
    H -- no --> L{list / continuation}
    L -- yes --> LIST[list block]
    L -- no --> Q{blockquote? >}
    Q -- yes --> BQ[blockquote block]
    Q -- no --> TBL{pipe run + separator?}
    TBL -- yes --> TABLE[table block]
    TBL -- no --> PARA[paragraph block]
    LIST --> B[Block: type / text / start_char / end_char]
    CODE --> B
    BQ --> B
    TABLE --> B
    PARA --> B
    B -. P2-304 .-> DB[DocumentBlock + block_id b-<section.id>-<n>]
```

**Invariants (frozen §6):**
- Blocks are detected on the **exact analyzed text** (post-ingestion, D1), not the source
  file — offset fidelity (R2); the `clean_text`-boundary test proves the detector consumes
  the normalized shape.
- Fenced content is never a heading (P2-302, AC2) and never a paragraph/list/table block
  (this task, AC6) — both detectors share the identical document-global toggle rule.
- Blocks are non-overlapping, in document order, and never span section ranges.
- Every block satisfies the literal slice `text[start_char:end_char] == block.text` (R2).
- Degenerate input (empty text / empty ranges) → `[]`, never an exception.
- No production path touches this function until P2-304; no ingestion wiring.

## 8. Files to Modify

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/structure/detector.py` | **modify (append)** — `BlockKind`, `Block`, `_LIST_RE`, `_TABLE_SEPARATOR_RE`, `_detect_blocks`; **P2-302 code untouched** (`_detect_headings`, `Heading`, `_HEADING_RE`, `_normalize_heading_level`, `MAX_HEADING_LEVEL` unchanged). |
| `tests/unit/test_structure_analysis.py` | **append** P2-303 test classes (frozen §13 names this file for the milestone's structure unit tests; P2-301/P2-302 already append here). |
| `tests/fixtures/structure/blocks.md` | **new** — committed fixture (roadmap §4 P2-303 / frozen §13 / L6): all five block types in one post-`clean_text` snapshot; the offset-accuracy vehicle. |
| `tests/fixtures/structure/lists_and_quotes.md` | **new** — committed fixture: nested list, list-continuation line, single + multi-line blockquote. |
| `tests/fixtures/structure/table_block.md` | **new** — committed fixture: normalized pipe tables, two tables separated by a blank line, a lone `| x | y |` line (paragraph boundary). |

**Explicitly not modified:** `app/domain/document_intelligence.py` (P2-301 models),
`app/domain/processed_document.py`, `app/infrastructure/semantic_chunking.py` (AC5 —
byte-identical), `app/infrastructure/document_intelligence/__init__.py` (composition root
is P2-304/305), `app/infrastructure/ingestion/utils.py` (reference only), `app/core/config.py`,
`config/default.yaml`, any existing test. `empty.md` and `oversize_text.txt` from the frozen
§13 fixture list are owned by P2-304 (`_build_tree` empty-tree) and P2-306 (cap guard) —
**not** created here.

## 9. Configuration Impact

**None.** P2-303 declares no config keys and consumes no settings (frozen §7 / L5).
`TEXT_BEARING_KINDS`, `MAX_SECTIONS`, and `max_structure_text_bytes` stay code constants owned
by P2-305/306; `intelligence.structure.*` is untouched until P2-305. No `default.yaml` change.

## 10. Acceptance Criteria

| # | Criterion | Source | Evidence |
|---|-----------|--------|----------|
| AC1 | Blocks of all five types — paragraph / list / code / blockquote / table — are detected. | frozen §8 AC3 | `TestBlockTypes` (inline) + `blocks.md` fixture: one block per type in the committed snapshot. |
| AC2 | Every block carries accurate `start_char`/`end_char`; literal-slice integrity `text[start:end] == block.text` and `len(text) == end - start` hold. | frozen §8 AC3 / R2 | `TestBlockOffsets` (exact hard-coded offset tuples on `blocks.md`) + `TestSliceInvariant` (property check over all fixtures). |
| AC3 | List nesting (indented sub-lists) and best-effort list-continuation lines form one `list` block. | roadmap P2-303 / frozen R1 | `TestListNesting`, `TestListContinuation` + `lists_and_quotes.md`. |
| AC4 | Consecutive blockquote lines (incl. `>>` depth) form one `blockquote` block. | roadmap P2-303 / R1 | `TestBlockquote` + `lists_and_quotes.md`. |
| AC5 | Pipe tables are detected on the post-`clean_text` normalized form (a `\|`-run containing a separator row → one `table` block; lone pipe line → paragraph). | roadmap P2-303 "after clean_text normalization" | `TestTable` + `table_block.md` + `TestCleanTextBoundary` (raw markdown → `clean_text` → `_detect_blocks`). |
| AC6 | A fenced code block is one multi-line `code` block (info string kept; unclosed fence → to end of text); fence state is identical to `_detect_headings`, so fenced `#` content is never a heading *or* a block. | frozen §8 AC2/AC3 | `TestCodeFence` + `TestFenceStateConsistency` (same fenced text through both detectors). |
| AC7 | Paragraphs split on blank lines; heading lines never become blocks; blocks never span section ranges. | roadmap P2-303 / R2 | `TestParagraph`, `TestHeadingLineSkipped`, `TestRanges`. |
| AC8 | No changes outside the listed files; `_detect_headings`/`Heading`/`_HEADING_RE` unchanged; chunker byte-identical; full existing suite green. | frozen §9/§12/AC5 | Gate: full `tests` suite passes unchanged; ruff/mypy zero new; git status shows only the listed files. |

## 11. Definition of Done

- [ ] `_detect_blocks(text, ranges)` implemented in `structure/detector.py` matching §5.1–§5.4
      (classification precedence, grouping, offsets, ranges, fence state), with `Block`
      (`type`, `text`, `start_char`, `end_char`).
- [ ] All five types (AC1), slice integrity (AC2), list nesting/continuation (AC3), blockquote
      (AC4), tables (AC5), fence consistency (AC6), paragraph/range semantics (AC7) unit-tested.
- [ ] Fixtures `tests/fixtures/structure/blocks.md` + `lists_and_quotes.md` + `table_block.md`
      committed (frozen §13 / L6) and each exercised by ≥ 1 test; exact offsets asserted
      against `blocks.md`.
- [ ] No production code outside `structure/detector.py` changed; P2-302 detector code
      unchanged; nothing wired; `SemanticChunker` byte-identical (AC5 / AC8).
- [ ] All existing tests pass unchanged; coverage ≥ 80% with `detector.py` parser suite ≥ 90%
      (frozen §12 / R7, P2-302 precedent); `ruff` zero new errors; `mypy` zero new type errors.
- [ ] Single atomic commit per the milestone rollback contract (frozen §14).

## 12. Test Strategy

| Layer | Scope | Details |
|-------|-------|---------|
| Unit — block types | One test per type: paragraph, list, code fence, blockquote, table | inline strings + `blocks.md` fixture read for the offset assertions |
| Unit — offsets | Exact `start_char`/`end_char` on `blocks.md`; literal-slice property across all three fixtures | hard-coded expected tuples pinned to the committed fixture bytes (frozen fixture = frozen offsets) |
| Unit — list | Nested sub-lists → one block; continuation lines absorbed (best-effort) | inline + `lists_and_quotes.md` |
| Unit — blockquote | Single, multi-line continuation, `>>` depth → one block | inline + `lists_and_quotes.md` |
| Unit — table | Normalized pipe table → `table` block; separator-row rule; lone `\|` line → paragraph; two tables separated by blank → two blocks | inline + `table_block.md` |
| Unit — fence | Multi-line fence = one `code` block; info string kept; unclosed fence → to end; fenced `#`/`-`/`\|` never blocks | inline |
| Unit — paragraph | Split on blank lines; heading line in-range skipped | inline |
| Unit — ranges | Whole-doc `[(0, len(text))]`; two section-body ranges → blocks don't span; `ranges=()` → `[]` | inline |
| Unit — never-raises | Odd input: lone ` ``` `, `\r`-embedded lines, out-of-bounds ranges, null byte | inline |
| Unit — clean_text boundary | Raw Markdown → `clean_text` → `_detect_blocks`; asserts the detector consumes the normalized shape (roadmap "after clean_text normalization") | inline raw text |
| Unit — fence/heading consistency | Same fenced text through `_detect_headings` and `_detect_blocks` → no heading, one code block | inline |
| Regression | Full existing suite unchanged (chunker AC5, M2.2 suites, P2-301/302 tests) | `python -m pytest tests -q -p no:cacheprovider --cov=app --cov-report=term` |

**Fixtures:** `tests/fixtures/structure/blocks.md`, `lists_and_quotes.md`, `table_block.md`
(committed). All fixtures are **post-`clean_text` snapshots** — tests feed file contents
directly to `_detect_blocks` (D1: the analyzer receives the already-cleaned text); the single
`clean_text`-boundary test bridges raw→normalized. No integration tests this task (P2-305 owns
the ingestion-path integration). No performance tests this task (P2-306 owns cap/timing).

## 13. Rollback Strategy

| Level | Mechanism | Detail |
|-------|-----------|--------|
| Per-task | Git revert of the single atomic P2-303 commit | Additive-only: new function + fixtures + tests; **nothing in `app/` references `_detect_blocks` yet** (first consumer is P2-304), so a revert is a clean removal with zero blast radius. |
| Data | No persistence touched | The detector writes nothing; no `metadata.extra` key exists yet. |
| Code | No legacy branch | No existing component's behavior changes; `_detect_headings` and `SemanticChunker` untouched (AC8); P2-301 models untouched. |
| Dependency | None | No new packages. |
| Process | Frozen §14 | `intelligence.structure.enabled: false` flag rollback is not applicable until P2-305; the §14 per-task atomic-commit mechanism applies now. |

## 14. Risks

| # | Risk | L/I | Mitigation |
|---|------|-----|------------|
| 1 | List/paragraph ambiguity on list-continuation (wrapped) lines — a paragraph could be absorbed into a list or vice-versa. | M/M | Blank-line boundary is the hard rule; continuation absorption is best-effort per frozen R1/§2.2 and documented; never raises; behavior frozen by `TestListContinuation`. |
| 2 | Pipe-in-paragraph vs table after `clean_text` (both normalize to `\|`-leading lines). | M/M | Table requires a separator row in the run (`_TABLE_SEPARATOR_RE`); a lone pipe line → paragraph (best-effort); boundary pinned by `TestTable` + `TestCleanTextBoundary`. |
| 3 | Offset drift if P2-304 computes ranges on a different split or normalizes text. | M/M | D1 seam pinned: identical `text`, identical `text.split("\n")`, offset accumulation; literal-slice invariant asserted for every block in every fixture (AC2); P2-304 handoff note. |
| 4 | Fence-state divergence from `_detect_headings` (fenced `#` becomes a heading *or* a block). | M/M | Identical toggle rule (`stripped.startswith("```")`), document-global state, toggle checked before range membership; `TestFenceStateConsistency` runs both detectors on the same text. |
| 5 | Premature block-id / section coupling (D5 ids need section ids). | L/M | `Block` is deliberately id-less; P2-304 assigns `b-<section.id>-<n>` only at tree build. |
| 6 | A block spans two section ranges. | M/L | Flush at range edges + per-line membership; ranges are line-aligned (derived from heading lines); the fence/range invariant (no heading inside a fence ⇒ no range boundary inside a fence) prevents code blocks from spanning; `TestRanges`. |
| 7 | Detector regexes drift from `clean_text` conventions (classification-regex copies). | L/M | Exact regex strings pinned in §5.1; `clean_text`-boundary test (raw → clean → detect) catches divergence at the seam; no import of ingestion internals (documented decision §4). |

## 15. Complexity Estimate

**Medium — 1 dev-day** (frozen §11.1 P2-303 row). Split: ~0.5 d algorithm (line
classification + grouping + document-global fence state + range-boundary flushing) and
~0.5 d tests + fixtures. No infrastructure, no wiring, no config, no dependency changes.
The table-run verdict (separator lookahead) and list-continuation rule are the only
genuinely non-trivial logic; everything else is single-pass line grouping.

---

## 16. Consistency Verification (frozen M2.3 spec)

| Spec element | Frozen source | Consistency |
|--------------|---------------|-------------|
| Deliverable = block detector only, file = `structure/detector.py` | §11.1 P2-303 row | ✅ `_detect_blocks(text, ranges)` appended to the frozen package file; tree builder / analyzer / composition root deferred to P2-304 |
| Internal API name `_detect_blocks(text, ranges)` | §4.3 | ✅ kept verbatim |
| Five block types: paragraph / list / code / blockquote / table | §2.1 / §4.2 `DocumentBlock.type` | ✅ `BlockKind` Literal matches the domain `BlockType` strings exactly (document_intelligence.py:20) |
| Blocks typed with accurate char offsets (AC3) | §8 AC3 / §12 checklist | ✅ §5.3 literal-slice contract + `blocks.md` offset fixture; §10 AC1/AC2 |
| Offsets relative to the exact analyzed text (R2) | §3 / §6 / §10 R2 | ✅ D1 seam: same `text`, same split, offset accumulation; §5.3 |
| Fenced `#` never mis-split (AC2) + fence-state before classification | §8 AC2 / §10 R1 | ✅ toggle rule identical to `_detect_headings` (P2-302 §5.2); §5.2 item 1, §10 AC6 |
| Deeply nested lists / list-continuation lines (R1) | §10 R1 | ✅ best-effort continuation, blank-line boundary; §5.2 item 6, §10 AC3 |
| Pipe-table detection on normalized form | roadmap P2-303 / M2.2 tables | ✅ separator-row run verdict; §5.2 item 8, §10 AC5 |
| List/blockquote fixtures committed (L6) | §13 / roadmap §5 | ✅ `lists_and_quotes.md`, `table_block.md`; offset fixture `blocks.md` (roadmap §4) |
| No chunker change (AC5) | §8 AC5 / §9 / §14 | ✅ explicit not-modified list §8 |
| No wiring, no `metadata.extra` writes this task | §11.1 DoD / §5.4 | ✅ §4 "no wiring"; rollback §13 |
| No config keys; caps as code constants (L5) | §7 / D6 | ✅ §9 |
| Test file + committed fixtures | §13 | ✅ `test_structure_analysis.py` + `blocks.md`/`lists_and_quotes.md`/`table_block.md` |
| Waves / ordering (P2-302 ‖ P2-303 after P2-301) | §11.2 | ✅ independent of P2-302 at runtime (ranges supplied by P2-304); appends to the same module |
| Atomic commit + rollback | §14 | ✅ §13 |

---

*End of P2-303 Implementation Specification. No code implemented by this document.*
