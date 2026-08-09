# P2-303 Engineering Review Report — Block detector

**Reviewer:** Principal Engineering Reviewer
**Task:** P2-303 (Milestone 2.3 — Document Structure Analysis; wave 2)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` (🔒 FROZEN) — §4.3 (internal API `_detect_blocks`), §6 (data flow), §8 AC3 (five block kinds), §10 R1/D9, §12 (parser suite ≥ 90%), §13, §14
**Implementation spec:** `docs/PHASE_2_MILESTONE_2_3_P2-303_IMPLEMENTATION_SPECIFICATION.md` (spec-review ✅ Ready for Implementation; findings O1–O5 closed)
**Spec review:** `docs/PHASE_2_MILESTONE_2_3_P2-303_SPECIFICATION_REVIEW.md`
**Implementation report:** `docs/PHASE_2_MILESTONE_2_3_P2-303_IMPLEMENTATION_REPORT.md`
**Date:** 2026-08-02
**Scope:** P2-303 only. Review-only — no code modified.

## Verdict

✅ **Approved** — the implementation matches the frozen §4.3 `_detect_blocks`
contract (five typed kinds, exact char offsets, never-raises, classification
precedence mirroring `_normalize_line`), honors all three behavior-fixing
findings of the spec review (O1 pipe-run verdict at run end, O2 `nonlocal`,
O3 lone-fence → one `code` block), and passes every gate on independent re-run
(AC1–AC8, DoD, ruff, mypy, coverage). Backward compatibility holds by
construction: `detector.py` is append-only, `SemanticChunker` and the domain
models are byte-identical, and nothing in `app/` calls `_detect_blocks`.

---

## Verification by Area

### 1. Specification compliance — ✅ PASS

Line-by-line against the frozen spec, the implementation spec, and its review:

| Spec element | Implemented | Verdict |
|--------------|-------------|---------|
| §4.3 internal API `_detect_blocks(text, ranges)` | `detector.py:88` — exact name, `str` + `Sequence[tuple[int, int]]` → `list[Block]` | ✅ |
| §4.3 `BlockKind` = the five types | `Literal["paragraph", "list", "code", "blockquote", "table"]` (line 70) — string values byte-identical to `document_intelligence.py:20` `BlockType` members | ✅ |
| §4.3 `Block` record (type/text/start_char/end_char, id-less) | `@dataclass` lines 78–85; no `block_id` (deferred to P2-304 per D5) | ✅ |
| §8 AC3 / impl §5.2 precedence 1–9 | fence toggle (line 128) → fenced content (141) → outside-ranges (145) → blank/heading (149) → list + best-effort continuation (153) → blockquote (163) → pipe run (171) → paragraph (179) — matches `_normalize_line` (`utils.py:101–119`) | ✅ |
| R1 / slice exactness | `emit` computes `end = start + len(joined)` (line 112); invariant `text[start:end] == block.text` verified by `TestSliceInvariant` and fixture exact offsets | ✅ |
| Offsets via `split("\n")` | `pos` accumulated as `len(line) + 1` per line; no `line_index` passed through | ✅ |
| Half-open section ranges | `in_ranges` = `start <= offset < end` (lines 107–108); `not in_ranges` flushes (line 146) — blocks never span sections | ✅ |
| Document-global fence toggle | `in_fence` (line 97) shared across ranges, identical to `_detect_headings` (lines 46–53) — a heading-unsafe fence boundary cannot be created | ✅ |
| `_LIST_RE` / `_TABLE_SEPARATOR_RE` | lines 72–75 mirror `utils.py:11` and `utils.py:13` exactly | ✅ |
| **Spec-review O1** — pipe-run flush at entry contradicted §5.2 item 8 | fixed: `if not pipe_run: flush()` (lines 172–173) — pipe verdict fires at run end, not entry; `pipe_has_separator` OR-accumulates (line 176) | ✅ |
| **Spec-review O2** — `flush()` closure rebinding | fixed: `nonlocal run_type, pipe_has_separator` (line 115); only rebound names declared, the rest are method-mutated | ✅ |
| **Spec-review O3** — lone ``` contradictory note | pseudocode governs: unclosed fence → single `code` block to EOF (lines 187–188) | ✅ |
| Never raises | all classification on `match`/`startswith`/regex-match results; `.append` on guaranteed lists; no indexing, slicing, or arithmetic beyond `len`/`+` | ✅ |

### 2. Architecture — ✅ PASS

- Pure module, **no module-level mutable state** (reentrant, consistent with the
  frozen O-2 pattern established in P2-302); all run state is call-local to
  `_detect_blocks`.
- `Block` is a plain `@dataclass`, **not** a pydantic model, **not** exported —
  consistent with P2-302's `Heading`; the domain surface stays `BlockType`
  (P2-301) until P2-304 maps these records.
- **No wiring:** grep confirms the only reference to `_detect_blocks` in `app/`
  is its own definition (`detector.py:88`). Only consumers are the unit tests.
  Matches impl spec §4 ("not wired") and keeps P2-304 the sole wiring point.
- The pipe-run buffer (`pipe_run`/`pipe_start`/`pipe_has_separator`) is a
  locally scoped lookahead for the table-or-paragraph verdict — no separate
  module, no config surface. Correctly scoped to the function.
- Reuses `_HEADING_RE` (line 149) for heading-skip instead of duplicating the
  D9 rule — consistent classification across the two detectors.

### 3. Regression safety — ✅ PASS

`git status` confirms P2-303 changed exactly: `app/infrastructure/document_intelligence/structure/detector.py`
(append-only), `tests/fixtures/structure/` (new fixtures), `tests/unit/test_structure_analysis.py`
(append-only), and the P2-303 docs. The P2-302 block (lines 1–65) is
byte-identical to its shipped state — the sole addition is the `from typing
import Literal` import (line 8), which is additive and cannot affect `_detect_headings`.
`SemanticChunker` is unchanged (`git status` shows no modification; AC5
byte-identical). The 46 P2-301/302 tests pass unchanged inside the 89-test
file run. No existing production file outside `document_intelligence/` was
touched.

### 4. Test coverage — ✅ PASS

43 new tests across 13 classes, every spec §12 row and every AC exercised:

| Area | Tests |
|------|-------|
| Five block kinds (type values) | `TestBlockTypes` (6) |
| Exact offsets / slice invariant / section ranges | `TestBlockOffsets` (1), `TestSliceInvariant` (2), `TestRanges` (4) |
| List + nesting + best-effort continuation | `TestListNesting` (1), `TestListContinuation` (4) |
| Blockquote | `TestBlockquote` (4) |
| Table (separator verdict, two-table blank separation) | `TestTable` (4) |
| Code fence (toggle, unclosed → code, language tags, fence/heading interplay) | `TestCodeFence` (5), `TestFenceStateConsistency` (1) |
| Paragraph (incl. no paragraph-blank-nesting) | `TestParagraph` (4) |
| Clean-text boundary (fixtures are stable snapshots of `clean_text`) | `TestCleanTextBoundary` (3) |
| Never raises (empty/whitespace/odd/out-of-bounds ranges) | `TestNeverRaises` (4) |

Fixtures (`blocks.md`, `lists_and_quotes.md`, `table_block.md`) are committed
and each exercised; `blocks.md` pins exact offsets (paragraph 17–65, list
66–134, blockquote 135–169, code 170–219, table 220–281, paragraph 297–313).
`detector.py` coverage independently measured at **100% (132/132 statements)**.

### 5. Acceptance Criteria (impl spec §10) — ✅ PASS

| # | Criterion | Evidence |
|---|-----------|----------|
| AC1 | Five block kinds classified | `TestBlockTypes` |
| AC2 | Exact char offsets, slice-exact | `TestBlockOffsets` + `TestSliceInvariant` + fixture exact offsets |
| AC3 | List nesting + continuation | `TestListNesting` + `TestListContinuation` |
| AC4 | Blockquote | `TestBlockquote` |
| AC5 | Table; chunker byte-identical | `TestTable` + `TestCleanTextBoundary` + `git status` (semantic_chunking.py untouched) |
| AC6 | Code fence; unclosed → code block | `TestCodeFence` + `TestFenceStateConsistency` |
| AC7 | Ranges respected; no paragraph-blank-nesting | `TestRanges` + `TestParagraph` |
| AC8 | No changes outside listed files; chunker byte-identical | `git status` + full-suite green (below) |

### 6. Definition of Done (impl spec §11) — ✅ PASS (one pending process item)

All code-side checkboxes verified: `_detect_blocks` matches the frozen §4.3
contract with all five kinds and exact offsets; every AC unit-tested (43 new
tests); fixtures committed and exercised; no production code outside
`structure/detector.py` changed, `SemanticChunker` byte-identical; all tests
pass, coverage ≥ 80% (**detector 100%**, exceeding the frozen §12 parser-suite
≥ 90% target), ruff/mypy zero new. The final checkbox (single atomic commit,
§14) is pending — see O2, a post-review commit-time step consistent with the
P2-302 precedent. Spec-review findings O1–O3 are correctly implemented in code
and O4/O5 (documentation-only) are reflected in the report's Known Limitations.

### 7–9. Ruff / Mypy / Coverage — ✅ PASS (independently re-run)

| Gate | Independent result |
|------|--------------------|
| `python -m ruff check` (2 changed source files) | **All checks passed** |
| `python -m ruff format --check` (2 changed source files) | **2 files already formatted** |
| `python -m mypy app/infrastructure/document_intelligence/structure/detector.py` | **Success: no issues found** |
| `python -m pytest tests/unit/test_structure_analysis.py --cov=.../structure` | **89 passed** (46 P2-301/302 + 43 P2-303); `detector.py` **100%** (132/132), `__init__.py` 100% |
| `python -m pytest tests --cov=app --cov-report=term` | **708 passed, 8 deselected**, total coverage **88.36%** ≥ 80% gate (baseline 665/88.13%; +43, +0.23pp — a fraction of the delta is measurement noise, reproduced across runs) |

### 10. Backward compatibility — ✅ PASS

Additive-only by construction: one file appended, new fixtures, test-file
append, docs. `SemanticChunker`, `BlockType`/P2-301 models, config, and all
other production files byte-identical (`git status` clean for them). M2.1/M2.2
suites green inside the full run. `_detect_blocks` is unreferenced in
production, so a revert (frozen §14) is a zero-blast-radius removal. No config
keys, no `metadata.extra` writes, no new dependencies.

---

## Findings

### O1 — Spec-review findings O1–O3 are correctly closed in code — ✅

O1 (pipe-run flush at entry): the implemented `if not pipe_run: flush()`
(lines 172–173) means the table-vs-paragraph verdict is only decided at run
end (`flush()` at EOF/blank/section-edge) via `pipe_has_separator`. This is the
behavior §5.2 item 8 requires and the buggy pseudocode contradicted;
`test_two_tables_blank_separated` would fail under the buggy pseudocode and
passes. O2 (`nonlocal run_type, pipe_has_separator`, line 115) resolves the
`UnboundLocalError` the pseudocode's closure would raise; the path is exercised
by every flush-through test (`TestParagraph`, `TestListContinuation`,
`TestBlockquote`, `TestTable`) — a regression would fail all of them. O3 (lone
` ``` ` → one `code` block to EOF, lines 187–188) is governed by the
pseudocode per AC6 and asserted by `TestCodeFence.test_unclosed_fence_runs_to_end`
and `TestNeverRaises.test_lone_fence_toggle`. All three verified by trace and test.

### O2 — Atomic commit pending (process, not code)

No git commit exists for P2-303 yet (`structure/`, `tests/fixtures/structure/`,
`test_structure_analysis.py`, and the P2-303 docs are untracked; the milestone
artifacts are held in a single working-tree commit alongside M2.1/M2.2 and
P2-301/302). The DoD's final checkbox and §14's "each task = one atomic
commit" are satisfied at commit time, per the milestone convention established
for P2-301 and P2-302. Non-blocking.

### O3 — Report accuracy — ✅

Every gate number in the implementation report was independently reproduced:
89 tests (46 + 43), 708 passed / 8 deselected, 88.36% total, `detector.py`
100% (132/132), ruff check + format clean on changed files, mypy zero-new.
The 43-test class/size arithmetic (6+1+2+1+4+4+4+5+1+4+4+4+3) and the
known-limitations text are accurate and consistent with the collected output.
The report's coverage row correctly notes 88.36 ↔ 88.38 run-to-run variance as
measurement noise, both ≥ 80%.

---

## Summary

The frozen §4.3 `_detect_blocks` contract is implemented exactly: the five
typed kinds, exact char offsets, section-range scoping, and the
`_normalize_line`-mirroring classification precedence are present and
behaviorally verified by trace; both spec-review behavior defects (O1 pipe-run
verdict, O2 closure rebinding) are fixed in code exactly as recommended, and
the lone-fence rule (O3) follows the governing pseudocode. Every gate passes on
independent re-run — AC1–AC8, the full DoD checklist, ruff (zero new), mypy
(zero new), and 88.36% coverage with the parser suite at 100% (≥ 90% frozen
target). Backward compatibility holds by construction (append-only file,
chunker byte-identical, P2-302 code intact, nothing wired). No remediation
required.
