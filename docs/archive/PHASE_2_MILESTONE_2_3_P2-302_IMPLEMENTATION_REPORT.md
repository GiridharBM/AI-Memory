# P2-302 Implementation Report — Heading hierarchy detector

**Task:** P2-302 (Milestone 2.3 — Document Structure Analysis; wave 1)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` v1.1 (🔒 FROZEN 2026-08-01) — §4.3 (normative `_detect_headings`), §6 (analysis flow), §8 (AC1/AC2), §10 (R-1 row D9), §11.1 (P2-302 row), §12 (frozen parser-suite ≥ 90%), §13 (test file/fixtures), §14 (rollback)
**Implementation spec:** `docs/PHASE_2_MILESTONE_2_3_P2-302_IMPLEMENTATION_SPECIFICATION.md`
**Spec review:** `docs/PHASE_2_MILESTONE_2_3_P2-302_SPECIFICATION_REVIEW.md` — ✅ Ready for Implementation (findings O1/O2/O3)
**Date:** 2026-08-01
**Status:** Ready for engineering review

## Implementation Summary

Implemented the heading detector exactly per the frozen §4.3 contract: a pure,
never-raising line-scan that extracts nested ATX headings from the exact
post-`clean_text` text (`exact_text.split("\n")`, D1). New package
`app/infrastructure/document_intelligence/structure/` holds a single
substantive module `detector.py`.

- **`_detect_headings(lines: Sequence[str]) -> list[Heading]`** (frozen §4.3) —
  scans one line at a time; never raises; returns headings in document order.
- **`Heading`** — plain mutable `@dataclass` (NOT pydantic; frozen §4.3) with
  `level: int`, `line_index: int`, `title: str`, `parent: Heading | None = None`.
  `from __future__ import annotations` satisfies the forward reference.
- **D9 heading rule** (spec §5.1) — `_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*)$")`,
  line-anchored, no `re.M`. Requires whitespace after the marks and non-blank
  content (`#`, `# `, `#\t`, `#NoSpace`, `####### X`, and indented `  # X` all
  rejected). Title collapses inline whitespace runs to single spaces.
- **Fence machine** (spec §5.2) — a `stripped.startswith("```")` line toggles an
  `in_fence` flag; heading evaluation is suppressed while fenced; an unclosed
  fence treats the rest of the text as code. This mirrors
  `clean_text._protect_code_blocks` (utils.py), so detector and input agree on
  fence boundaries by construction. `~~~` fences are intentionally not
  recognized (frozen convention). A `> ``` ` blockquote line is *not* a toggle —
  identical to `clean_text`.
- **D4 hierarchy scan** (spec §5.3) — a stack pops while the top is `>=` the new
  heading's level; the parent is the new stack top (or `None` for roots). Level
  skips (`# A` → `### C`) attach to the nearest preceding strictly-lower heading.
- **Depth cap** (spec §5.4, frozen D6) — `MAX_HEADING_LEVEL = 6` module constant;
  `_normalize_heading_level(level) = min(max(level, 1), 6)` extracted as a pure
  helper (defense-in-depth; D9 alone makes out-of-range levels unreachable).
- **No logging surface added** (spec §3 permits but does not require it); no
  pydantic/domain imports; nothing wired into the pipeline yet (composition
  root, `StructureAnalyzer`, block/tree building, and enrichment are P2-303/304/305).

## Files Modified

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/structure/__init__.py` | **new** — docstring-only package marker |
| `app/infrastructure/document_intelligence/structure/detector.py` | **new** — the only substantive production file: `MAX_HEADING_LEVEL`, `_HEADING_RE`, `_collapse_inline_whitespace`, `_normalize_heading_level`, `Heading`, `_detect_headings` |
| `tests/unit/test_structure_analysis.py` | **modified** — appended 27 tests across 5 classes (19 P2-301 tests untouched) |
| `tests/fixtures/structure/nested_headings.md` | **new** — committed fixture (frozen §13/L6): nested `#`/`##`/`###`/`####`, same-level siblings, level skip |
| `tests/fixtures/structure/fenced_code.md` | **new** — committed fixture: language-tagged fences, `# not a heading` inside fences, unclosed trailing fence |

No other files changed. Explicitly **not** modified (spec §8 / AC5):
`app/infrastructure/semantic_chunking.py` (byte-identical — its divergent
`_HEADING_PATTERN` copy is a frozen known-known for later harmonization),
`app/domain/document_intelligence.py`, `app/domain/processed_document.py`,
`app/infrastructure/document_intelligence/__init__.py` (composition root),
`app/core/config.py`, `config/default.yaml`, and no test baseline files.

## Test Results

| Gate | Result |
|------|--------|
| `python -m pytest tests/unit/test_structure_analysis.py` | **46 passed** (19 P2-301 + 27 P2-302; 0 regressions) |
| `python -m pytest tests -q --cov=app --cov-report=term` | **665 passed, 8 deselected** (integration-marked); total coverage **88.13%** ≥ 80% gate ✓ (baseline was 638 passed / 88.04%) |
| `python -m ruff check` (new/changed files) | **All checks passed** |
| `python -m ruff format --check` (new/changed files) | **3 files already formatted** |
| `python -m mypy app/infrastructure/document_intelligence/structure/detector.py` | **Success: no issues found** |
| `python -m mypy app` | 4 pre-existing environment errors (missing `fitz`/`pptx`/`faster_whisper` stubs; numpy stub/Python-version syntax mismatch) — all in untouched files; **zero new from P2-302** |

Coverage delta: `detector.py` at **100%** (39/39 statements) — exceeds the frozen
§12 parser-suite target of ≥ 90% (spec-review finding O3 satisfied).
`structure/__init__.py` 100% (0 executable statements).

## Tests Added (27)

- **`TestHeadingHierarchy`** (6) — nested chain parent/level/title wiring;
  level-skip attaches to nearest preceding lower; same-level siblings detach
  (re-root); shallower-after-deeper re-roots the subtree; `nested_headings.md`
  fixture end-to-end (11 headings, level-skip parent linkage).
- **`TestFenceDisambiguation`** (7) — `# not a heading` inside a fence is
  suppressed; language-tagged fence (` ```python `) opens; open/close toggling
  across multiple blocks; unclosed fence suppresses the rest; headings after a
  close are detected; `> ``` ` blockquote line is not a toggle; `fenced_code.md`
  fixture (only "Top Level" and "After Fences" detected).
- **`TestHeadingRule`** (8) — D9 negatives (`#`, `# `, `#\t`, `#NoSpace`,
  `##NoSpace`, `####### X`, indented `  # Indented`); whitespace-only input → `[]`;
  level/title extraction; inline-whitespace collapse; content preservation.
- **`TestDepthCap`** (3) — `_normalize_heading_level` bounds (7→6, 6→6, 1→1, 0→1,
  5→5); `###### Deep` accepted at level 6; `MAX_HEADING_LEVEL == 6` constant.
- **`TestLineIndexOffsets`** (3) — `line_index` matches `text.split("\n")`
  enumeration; empty input; never-raises on odd input (lone ` ``` `, null byte,
  `\r`-embedded lines, fence-ish content).

## Known Limitations / Notes

- **`~~~` fences not recognized** (frozen convention, matches `clean_text`).
- **Unclosed fence → rest is code** (not an error, matches `clean_text`).
- **`line_index` is an index into `lines`** — the exact post-`clean_text`
  split; byte offsets for `DocumentSection.start_char/end_char` are the tree
  builder's responsibility (P2-304).
- **Spec-review O1/O2 (documentation wording only, non-blocking):** §5.2's claim
  that post-`clean_text` text cannot contain a `> ``` ` line is imprecise — such
  lines survive as blockquote lines; the detector's own
  `stripped.startswith("```")` rule still treats them as non-toggles, so
  behavior is correct as specified. §5.1's "divergence" phrasing is garbled; the
  real divergence is `.` (chunker) vs `\S` (detector) for the first content
  character. Both are word-level fixes to the spec doc, not code changes.
- **Spec-review O3 honored:** detector parser-suite coverage is 100% vs the frozen
  §12 ≥ 90% target (recorded above).
- **Chunker harmonization is out of scope:** `semantic_chunking.py` keeps its own
  `re.MULTILINE` heading regex (AC5 byte-identical); reconciling the two regexes
  belongs to the later chunker task.

## Milestone Readiness Assessment

P2-302 lands the frozen §4.3 detector contract — a pure, never-raising line scan
with a fence machine that agrees with `clean_text` by construction, a D4
stack-based hierarchy, and a D9 heading rule that matches the pipeline input.
Zero blast radius: one new package, additive tests, no production wiring, no
existing file touched. Ready for engineering review; P2-303 (block detection /
blockquote-tightened `_detect_headings`) and P2-304 (tree builder) can build
directly on the frozen interfaces.
