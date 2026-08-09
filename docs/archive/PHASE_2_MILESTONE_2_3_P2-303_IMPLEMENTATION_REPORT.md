# P2-303 Implementation Report — Block detector (paragraph/list/code fence/blockquote/table)

**Task:** P2-303 (Milestone 2.3 — Document Structure Analysis; wave 2)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` v1.1 (🔒 FROZEN 2026-08-01) — §4.3 (internal API `_detect_blocks`), §6 (data flow), §7 (R2 offsets), §8 (AC1/AC2/AC3), §10 (R-1 rows D9/R1/R2), §11.1 (P2-303 row), §12 (frozen parser-suite ≥ 90%), §13 (test file/fixtures), §14 (rollback)
**Implementation spec:** `docs/PHASE_2_MILESTONE_2_3_P2-303_IMPLEMENTATION_SPECIFICATION.md`
**Date:** 2026-08-01
**Status:** Ready for engineering review

## Implementation Summary

Implemented the block detector exactly per the frozen §4.3 contract: a pure,
never-raising line classifier that groups typed blocks — **paragraph, list,
code fence, blockquote, Markdown table** — over the exact post-`clean_text`
analyzed text (D1), restricted to the half-open `ranges` body spans, with
slice-exact `start_char`/`end_char` offsets (R2). Appended to the existing
`structure/detector.py`; the P2-302 heading code is untouched.

- **`Block`** — plain mutable `@dataclass` (id-less by design, D5): `type:
  BlockKind`, `text`, `start_char`, `end_char`. `BlockKind = Literal["paragraph",
  "list", "code", "blockquote", "table"]` mirrors the domain `BlockType` strings
  (document_intelligence.py:20) without importing pydantic.
- **`_detect_blocks(text, ranges) -> list[Block]`** (frozen §4.3 name) —
  classification precedence identical to `ingestion.utils._normalize_line`
  (`utils.py:101-119`): fence toggle → in-fence → range membership → blank /
  heading (D9 skip, never a block) → list + best-effort continuation →
  blockquote → `|`-pipe run (table iff ≥ 1 separator row else paragraph) →
  paragraph.
- **Classification regexes are local copies, not imports** (spec §4 decision):
  `_LIST_RE` mirrors `utils.py:11`, `_TABLE_SEPARATOR_RE` mirrors `utils.py:13`;
  the `clean_text`-boundary test pins agreement at the seam.
- **Fence machine identical to `_detect_headings`** — a
  `stripped.startswith("```")` line toggles a document-global `in_fence` flag
  *before* the range-membership check, so fenced `#`/`-`/`|` content is never a
  heading or a block in either detector (`TestFenceStateConsistency`). Code
  blocks span the opening fence line through the closing fence line inclusive;
  an unclosed fence runs to end of text.
- **Offsets (R2)** — single scan over `text.split("\n")` with
  `pos += len(line) + 1` accumulation (the split P2-304 reuses). Every block
  satisfies the literal-slice invariant `text[start:end] == block.text` and
  `len(block.text) == end_char - start_char` (the `DocumentBlock` validator's
  contract, start inclusive / end exclusive).
- **Range semantics** — per-line membership (`any(start <= pos < end)`);
  blocks flush at range edges and never span sections; `ranges=()` → `[]`;
  out-of-bounds ranges degrade gracefully, never raise.
- **No wiring** — nothing in `app/` calls `_detect_blocks`; P2-304 is the first
  production consumer (spec §4). No config, no pydantic, no domain imports, no
  changes to `SemanticChunker` (AC5 byte-identical).

## Spec Pseudocode Deviations (normative-prose compliant)

Three deviations from the spec §5.4 pseudocode were required; all implement the
spec's *normative prose* (§5.2 items 1–9, §5.3, AC6) and are behavior-pinning tests:

1. **`nonlocal` in `flush()`** — the pseudocode's `flush()` rebinds `run_type`
   and `pipe_has_separator` (closure locals), which raises
   `UnboundLocalError` at runtime. Added `nonlocal run_type,
   pipe_has_separator` (one line); logic otherwise identical.
2. **Pipe-run verdict at run end, not at pipe entry** — the pseudocode called
   `flush()` unconditionally on every `|`-leading line, which emitted each pipe
   line as its own `paragraph`/`table` *before* the separator verdict was known
   (violates §5.2 item 8: "if the run contains ≥ 1 separator → one table block
   for the whole run"). Fixed to flush only when a *new* pipe run starts
   (`if not pipe_run: flush()`); the run's verdict fires when the run ends
   (blank / heading / non-`|` line / range edge / EOF), which `flush()` already
   handles. `TestTable.test_two_tables_blank_separated` and the
   `table_block.md` fixture pin the behavior.
3. **Lone ` ``` ` emits one code block** — the §5.4 degenerate note ("a lone
   ` ``` ` → no blocks") contradicts the normative pseudocode (`if fence_lines:
   emit("code", ...)`) and §5.2 item 2 (unclosed fence → one code block to end
   of text). The pseudocode governs: a lone ` ``` ` is an unclosed fence and
   yields one `code` block (`TestNeverRaises.test_lone_fence_toggle`).

## Files Modified

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/structure/detector.py` | **modified (append)** — `BlockKind`, `Block`, `_LIST_RE`, `_TABLE_SEPARATOR_RE`, `_detect_blocks`; P2-302 code (`_detect_headings`, `Heading`, `_HEADING_RE`, `_normalize_heading_level`, `MAX_HEADING_LEVEL`) byte-unchanged |
| `tests/unit/test_structure_analysis.py` | **modified (append)** — 43 tests across 13 classes (46 P2-301/302 tests untouched) |
| `tests/fixtures/structure/blocks.md` | **new** — committed fixture: all five block types in one post-`clean_text` snapshot; the exact-offset vehicle |
| `tests/fixtures/structure/lists_and_quotes.md` | **new** — committed fixture: nested list, continuation line, single + multi-line + depth-nested blockquote |
| `tests/fixtures/structure/table_block.md` | **new** — committed fixture: two normalized tables blank-separated, lone pipe line → paragraph |

No other files changed. Explicitly **not** modified (spec §8 / AC5 / AC8):
`app/domain/document_intelligence.py`, `app/domain/processed_document.py`,
`app/infrastructure/semantic_chunking.py` (byte-identical),
`app/infrastructure/document_intelligence/__init__.py` (composition root),
`app/infrastructure/ingestion/utils.py` (reference only), `app/core/config.py`,
`config/default.yaml`, and no test baseline files. `empty.md` and
`oversize_text.txt` are owned by P2-304/P2-306 (spec §8) and were not created.

**Fixture fidelity:** all three fixtures are genuine post-`clean_text`
snapshots — each is `clean_text`-stable (`clean_text(fixture) == fixture`,
asserted by `TestCleanTextBoundary.test_fixtures_are_clean_text_stable`). This
forced two snapshot corrections during implementation: `Lone pipe | line.`
normalizes to `| Lone pipe | line. |` (a pipe-containing line becomes a
`| cell | cell |` row), and `>> nested depth quote` normalizes to
`> > nested depth quote` (`_normalize_blockquote`).

## Test Results

| Gate | Result |
|------|--------|
| `python -m pytest tests/unit/test_structure_analysis.py` | **89 passed** (46 P2-301/302 + 43 P2-303; 0 regressions) |
| `python -m pytest tests -q --cov=app --cov-report=term` | **708 passed, 8 deselected** (integration-marked); total coverage **88.36%** ≥ 80% gate ✓ (baseline was 665 passed / 88.13%) |
| `python -m ruff check` (new/changed files) | **All checks passed** |
| `python -m ruff format` (new/changed files) | **2 files reformatted** (style only); subsequent check clean |
| `python -m mypy app/infrastructure/document_intelligence/structure/detector.py` | **Success: no issues found** |

Coverage delta: `detector.py` at **100%** (132/132 statements) — exceeds the
frozen §12 parser-suite target of ≥ 90% (P2-302 precedent, 100%). Total
coverage 88.36% (up from 88.13%); 708 > 665 baseline, +43 tests, no
regressions, no out-of-scope file touched (AC8). (Coverage re-run 2026-08-01;
the 88.36–88.38% spread across runs is measurement noise, both well above the
80% gate.)

## Tests Added (43)

- **`TestBlockTypes`** (6) — one test per type inline (paragraph, list, code
  fence, blockquote, table) + `blocks.md` fixture: all five types detected in
  one document.
- **`TestBlockOffsets`** (1) — hard-coded exact `(type, text, start_char,
  end_char)` tuples pinned to the committed `blocks.md` bytes (frozen fixture =
  frozen offsets): 6 blocks, e.g. `list` at 66–134, `code` at 170–219, `table`
  at 220–281.
- **`TestSliceInvariant`** (2) — `text[start:end] == block.text` +
  `len(text) == end - start` over every block of all three fixtures, and over
  P2-304-style section-body ranges (derived from `_detect_headings` line
  positions with offset accumulation) — the D1 seam.
- **`TestListNesting`** (1) — indented sub-list merges into one `list` block.
- **`TestListContinuation`** (4) — wrapped line absorbed (best-effort, R1);
  blank line, heading line, and pipe line each end the list run.
- **`TestBlockquote`** (4) — single line; consecutive lines merge; depth
  (`> >` normalized form) merges; blank line separates.
- **`TestTable`** (4) — normalized pipe table (header + separator + rows) →
  one `table` block; lone `| just | pipes |` (no separator) → paragraph;
  two tables blank-separated → two blocks (separator-row verdict at run end);
  pipe-in-paragraph line that does not start with `|` stays a paragraph.
- **`TestCodeFence`** (5) — multi-line fence = one block; info string kept;
  unclosed fence runs to end of text; fenced `#`/`-`/`|` content never a block;
  two fences → two code blocks.
- **`TestFenceStateConsistency`** (1) — same fenced text through
  `_detect_headings` and `_detect_blocks`: no heading, one `code` block (AC6).
- **`TestParagraph`** (4) — split on blank lines (incl. collapsed streaks);
  consecutive lines merge; heading-only documents → `[]`; heading line splits
  paragraphs.
- **`TestRanges`** (4) — `ranges=()` → `[]`; whole-document range; blocks do
  not span two disjoint ranges; out-of-bounds range → `[]`.
- **`TestNeverRaises`** (4) — lone ` ``` `, `\r`-embedded lines (heading rule on
  `## title\r`), null-byte line, odd range values.
- **`TestCleanTextBoundary`** (3) — raw Markdown → `clean_text` →
  `_detect_blocks` (list/blockquote/table); heading marks survive and produce no
  block; all three fixtures are `clean_text`-stable.

## Known Limitations / Notes

- **`~~~` fences not recognized** (frozen convention, matches `clean_text` and
  P2-302).
- **Single-column pipe tables have no separator form** — `_TABLE_SEPARATOR_RE`
  (mirroring `utils.py:13`) requires ≥ 2 columns, so a `|:---|`-style line is
  not a table separator; identical to `clean_text`'s own classification. This is
  a pre-existing ingestion convention, not a P2-303 change.
- **A pipe-leading run containing a separator absorbs all its rows** — including
  a trailing `| lone | pipe |` line in the same run (§5.2 item 8: table = whole
  run containing ≥ 1 separator). The "lone pipe → paragraph" case applies only
  when the run has no separator (e.g. `table_block.md`'s blank-separated
  `| lone | pipe |`).
- **`Block` is id-less** — `block_id` (`b-<section.id>-<n>`, D5) is assigned by
  P2-304 at tree build; coupling ids here would couple the detector to tree
  structure (spec §5 risk).
- **Offsets overcount past EOF on trailing-newline text** — `pos += len(line)
  + 1` may exceed `len(text)` after the last line, but `end_char` is always
  derived from the joined block text (`start + len(joined)`), so the literal
  slice invariant holds regardless; ranges derived by P2-304 use the same split
  and are unaffected.
- **Fixture content reconciled to `clean_text` normalization** during
  implementation (pipe-line wrapping, `>>` → `> >`); see Fixture fidelity note
  above. All three fixtures are committed post-`clean_text` snapshots (L6).

## Milestone Readiness Assessment

P2-303 lands the frozen §4.3 block-detector contract — a pure, never-raising
classifier with slice-exact offsets, a document-global fence machine that agrees
with `_detect_headings` and `clean_text` by construction, and classification
precedence that matches `_normalize_line` line-for-line. Zero blast radius: one
file appended (P2-302 code byte-unchanged), additive tests/fixtures, no
production wiring, no domain/config/dependency change. Ready for engineering
review; P2-304 (tree builder — `_build_tree`, `analyze`, `StructureAnalyzer`,
`Block` → `DocumentBlock` mapping with `block_id`, section-body range derivation
from `Heading.line_index`) can build directly on the frozen interfaces. The
§14 atomic commit remains pending (consistent with the P2-302 O2 note).
