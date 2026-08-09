# P2-304 Implementation Report — Structure tree builder + analyzer entry

**Task:** P2-304 (Milestone 2.3 — Document Structure Analysis; wave 3)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` v1.1 (🔒 FROZEN 2026-08-01) — §4.1 (normative `StructureAnalyzer.analyze` + public APIs), §4.2 (domain models), §4.3 (package layout + composition root), §5.1/§6 (data flow), §7 (`MAX_SECTIONS`, C-4), §8 (R8 stable IDs), §9 (offsets contiguous, degenerate → empty), §10 R2/R8, §11.1 (P2-304 row), §12, §13, §14
**Implementation spec:** `docs/PHASE_2_MILESTONE_2_3_P2-304_IMPLEMENTATION_SPECIFICATION.md`
**Spec review:** `docs/PHASE_2_MILESTONE_2_3_P2-304_SPECIFICATION_REVIEW.md` (✅ Ready for Implementation, findings O1–O6 non-blocking)
**Date:** 2026-08-02
**Status:** Ready for engineering review

## Implementation Summary

Combined the P2-302 heading hierarchy and the P2-303 block detector into the
milestone's nested `DocumentStructure`: heading-delimited sections containing
their blocks, stable path-style IDs (D4/D5), contiguous non-overlapping char
offsets, degenerate input → empty structure, and the `MAX_SECTIONS` cap
truncating with a `UserWarning` — never raising. Delivered the public entry
points the frozen spec mandates (`StructureAnalyzer`, `analyze_document_structure`,
`get_default_structure_analyzer`) and exposed the two functions from the
composition root `app/infrastructure/document_intelligence/__init__.py`
(frozen §4.3). All P2-302/303 code is untouched; nothing in `app/` calls the
analyzer yet (P2-305 is the first production caller).

- **`MAX_SECTIONS = 10_000`** (frozen §7 / D6 / C-4) — code constant, `warnings.warn`
  `UserWarning` + `sections[:MAX_SECTIONS]` when the tree exceeds it; degenerate →
  `DocumentStructure(sections=[])`. Parents precede children in document order, so
  truncation keeps every `parent_id` reference valid (no dangling refs, asserted).
- **`StructureAnalyzer.analyze(text, source) -> DocumentStructure`** (frozen §4.1) —
  `text.split("\n")` + `pos += len(line) + 1` line-start accumulation (the D1 seam
  shared by P2-302/303); D4 IDs via `child_counts: dict[str | None, int]` keyed by
  parent id (`None` = root): root `s-{n}`, nested `{parent_id}-{n}`; section spans
  start at the heading line and end at the next heading's line (last section →
  `len(text)`); body range `[min(line_starts[li] + len(lines[li]) + 1, len(text)),
  next_start)` excludes the heading line; D5 block IDs `b-<section.id>-<n>` with `n`
  restarting per section. `ids_by_heading` keyed by `id(heading)` (spec §5.5 —
  `Heading` is a mutable `@dataclass`, hence unhashable).
- **`_build_tree(sections)`** (frozen §4.3 internal API) — wraps the assembled
  `DocumentSection` list into `DocumentStructure`, applies `MAX_SECTIONS` truncation
  with the warning, empty → empty.
- **Composition root** — `app/infrastructure/document_intelligence/__init__.py`
  re-exports `analyze_document_structure` + `get_default_structure_analyzer`
  (frozen §4.3; reconciliation documented in spec §4 vs §11.1 file list).
- **`source` accepted-unused** (spec §5.6) — public-API contract parameter for the
  shared M2.4/2.5/2.6 call site; `TestAnalyzerEntry.test_source_accepted_unused`
  pins that it does not affect output.
- **Preamble dropped** (spec §5.6, documented limitation) — text before the first
  heading is not covered by any section; pinned by `TestPreambleDropped`.

## Spec Pseudocode Deviations (normative-prose compliant)

One structural deviation from the spec §5.5 pseudocode was required:

1. **Single all-ranges `_detect_blocks` call + containment attribution, instead of
   one per-section call.** Spec §5.3 asserts per-section calls
   `_detect_blocks(text, [(body_start, end_char)])` are "behaviorally identical to a
   single all-ranges call." They are **not**: `_detect_blocks` scans the whole text
   from `pos 0` with a document-global fence toggle that runs *before* the
   range-membership check, and emits a `code` block on fence close regardless of
   where the fence opened. A fence closed in an earlier section therefore re-opens
   and re-closes during a later section's call, leaking a code block into the wrong
   section. Caught by `TestBlockIDs.test_blocks_md_fixture_section_blocks`: the
   `blocks.md` fixture's `code` block (start 170) was attributed to `s-2` (which
   starts at 282). Fix: one `_detect_blocks(text, body_ranges)` call over the body
   partition, then attribute each block to the section whose body range contains
   `block.start_char` (blocks are emitted in document order; body ranges tile the
   body in order, so one advancing pointer suffices). This implements the spec's
   stated §5.3 invariant exactly and satisfies AC1/AC2, with fewer calls than the
   pseudocode. A block that begins outside every body range (e.g. a fence opened in
   the dropped preamble) is discarded — consistent with the preamble-dropped
   limitation, pinned by `TestPreambleDropped.test_preamble_fence_blocks_dropped`.

No other deviations. The spec's §5.5 `next_start`, `parent_id`, `child_counts`,
`body_start`, and D5 numbering semantics are implemented verbatim; `_build_tree`
matches §5.4 line-for-line.

## Files Modified

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/structure/detector.py` | **modified (append)** — `MAX_SECTIONS`, `_build_tree`, `StructureAnalyzer`, `analyze_document_structure`, `get_default_structure_analyzer`, `DocumentBlock`/`DocumentSection`/`DocumentStructure` imports; P2-302/303 code byte-unchanged |
| `app/infrastructure/document_intelligence/__init__.py` | **modified** — composition root: re-export `analyze_document_structure` + `get_default_structure_analyzer` (frozen §4.3); package docstring kept |
| `tests/unit/test_structure_analysis.py` | **modified (append)** — 35 tests across 9 classes (89 P2-301/302/303 tests untouched) |
| `tests/fixtures/structure/empty.md` | **new** — 0-byte committed fixture (frozen §13; deferred from P2-303 spec §8) |

No other files changed. Explicitly **not** modified (spec §8 / AC5 / AC8):
`app/domain/document_intelligence.py`, `app/domain/processed_document.py` (R-1),
`app/infrastructure/semantic_chunking.py` (byte-identical),
`app/infrastructure/document_intelligence/structure/__init__.py`,
`app/infrastructure/ingestion/utils.py`, `app/core/config.py`,
`config/default.yaml`, `app/pipelines/ingest_workflow.py`, and no existing test or
fixture. `oversize_text.txt` remains P2-306's (generated in-test).

## Test Results

| Gate | Result |
|------|--------|
| `python -m pytest tests/unit/test_structure_analysis.py` | **124 passed** (89 P2-301/302/303 + 35 P2-304; 0 regressions) |
| `python -m pytest tests -q -p no:cacheprovider --cov=app --cov-report=term` | **743 passed, 8 deselected** (integration-marked); total coverage **88.45%** ≥ 80% gate ✓ (baseline was 708 passed / 88.36%) |
| `python -m ruff check` (new/changed files) | **All checks passed** |
| `python -m ruff format --check` (new/changed files) | **3 files already formatted** (one I001 import-sort auto-fixed) |
| `python -m mypy app/infrastructure/document_intelligence/structure/detector.py` | **Success: no issues found** |

Coverage delta: `detector.py` at **99%** (181/182 statements) — exceeds the frozen
§12 parser-suite target of ≥ 90% (P2-302/303 precedent, 100%). The single uncovered
statement is the defensive `break` when a block starts past the last body range
(`detector.py:283`) — unreachable by construction (the last section's range ends at
`len(text)` and block starts are always `< len(text)`); kept as a guard against
future range regressions. Total coverage 88.45% (up from 88.36%); 743 > 708
baseline, +35 tests, no regressions, no out-of-scope file touched (AC8).

## Tests Added (35)

- **`TestAnalyzerEntry`** (5) — `StructureAnalyzer().analyze` returns a
  `DocumentStructure`; `analyze_document_structure` delegates; both
  composition-root and detector import paths resolve to the same objects;
  `get_default_structure_analyzer` returns a fresh working instance per call;
  `source` accepted-unused (identical `model_dump` across sources).
- **`TestSectionAssembly`** (4) — nested chain `# A → ## B → ### C` ⇒
  `s-1`/`s-1-1`/`s-1-1-1`; siblings `# A`/`# B` ⇒ `s-1`/`s-2`; level-skip
  `# A → ### C` ⇒ `C.parent_id == "s-1"`, `s-1-1`; full 11-section tree from
  `nested_headings.md` (IDs, titles, levels, parent_ids).
- **`TestBlockIDs`** (5) — D5 IDs with per-section restart (`b-s-1-1`, `b-s-2-1`);
  `blocks.md` → `s-1` has 5 blocks `b-s-1-1..b-s-1-5` and `s-2` has `b-s-2-1`;
  `blocks.md` block types (paragraph/list/blockquote/code/table); a fenced block is
  one `code` block inside one section; an unclosed fence swallows following `#`
  lines into the last section (spec risk 4).
- **`TestOffsetsContiguity`** (6) — sections tile without gaps
  (`section[j].end_char == section[j+1].start_char`); last section ends at
  `len(text)`; each section slice starts with its own heading line; block slices
  are exact (`text[start:end] == block.text`); heading lines never appear in
  non-code block text; every block lies within its section's span.
- **`TestDegenerate`** (7) — `_build_tree([])` → empty; empty text; whitespace-only;
  no headings; `empty.md` fixture → empty; lone ` ``` `; `\r`-embedded lines never
  raise.
- **`TestMaxSections`** (4) — constant == 10_000; exactly `MAX_SECTIONS` → no
  warning (via `warnings.simplefilter("error")`); `MAX_SECTIONS + 1` → `pytest.warns`
  + 10_000 sections; truncation keeps parent references valid.
- **`TestIDStability`** (1) — same text analyzed twice → identical `model_dump` (R8).
- **`TestPreambleDropped`** (2) — text before the first heading not in any section;
  a fence opened in the dropped preamble is discarded (not attributed).
- **`TestSerializationRoundTrip`** (1) — `model_dump(mode="json")` round-trips via
  `DocumentStructure.model_validate` (the P2-305 `metadata.extra["structure"]`
  channel).

Existing fixtures (`nested_headings.md`, `blocks.md`, `fenced_code.md`,
`lists_and_quotes.md`, `table_block.md`) are fed **through `analyze()`** (not the
`_detect_*` functions directly) to assert end-to-end tree behavior, per spec §12.
No integration tests (P2-305 owns the ingestion path); no performance tests
(P2-306 owns cap/timing).

## Known Limitations / Notes

- **Preamble text is dropped** (spec §5.6, pinned limitation) — the frozen models
  define no heading-less section, so text before the first heading is not in the
  tree. A fence opened entirely in the preamble is likewise discarded. Phase 3
  chunking must not expect a preamble node (spec-review finding O2 forwarded).
- **`source` is accepted, not read** (spec §5.6) — a frozen §4.1 signature contract
  for the shared M2.4/2.5/2.6 call site, not dead code.
- **`MAX_SECTIONS` ownership** — truncated sections take the first 10_000 in
  document order; parents precede children so references stay valid. `MAX_HEADING_LEVEL`
  enforcement needs no new code (P2-302 clamp + P2-301 `Field(le=6)`), per spec §5.2
  reconciliation.
- **Per-section `_detect_blocks` note (spec-review O6)** — P2-306's timing test
  should use a section-dense sample; the single all-ranges call here is O(n) with a
  one-pass attribution pointer.
- **Composition root change is two additive re-exports** (frozen §4.3); nothing in
  `app/` imports the analyzer, so rollback (spec §13) is a clean removal.

## Milestone Readiness Assessment

P2-304 lands the frozen §4.1/§4.3 analyzer contract: a never-raising O(n) tree
builder over the two approved detectors with D4/D5 stable IDs, contiguous offsets,
degenerate → empty, and `MAX_SECTIONS` warn+truncate, plus the public entry points
reachable from the composition root. One spec-pseudocode deviation (single
all-ranges `_detect_blocks` call) implements the spec's own §5.3 invariant exactly
and is covered by a fixture test that caught the per-section leak. Zero blast
radius: additive append to `detector.py` (P2-302/303 byte-unchanged), two additive
re-exports, additive tests + one 0-byte fixture; no wiring, no config, no
dependency change, `SemanticChunker` byte-identical (AC5/AC8). Ready for
engineering review; P2-305 (enrichment wiring, `metadata.extra["structure"]`) can
import the analyzer with a single import. The §14 atomic commit remains pending
(consistent with the P2-302 O1/O2 notes).
