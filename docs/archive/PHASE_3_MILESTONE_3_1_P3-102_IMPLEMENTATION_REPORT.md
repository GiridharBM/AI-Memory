# Milestone 3.1 — P3-102 Implementation Report

**Task:** P3-102 — Heuristic fallback tokenizer (stdlib)
**Status:** DONE — implemented, tested, not wired into ingestion (per DoD)
**Date:** 2026-08-06
**Contract:** `docs/PHASE_3_MILESTONE_3_1_IMPLEMENTATION_ROADMAP.md` (P3-102 block, D5/D7) + P3-101 Engineering Review Recommended R-1
**Scope rule honored:** ONLY P3-102 implemented; no future task work. P3-103 (NLTK engine), P3-104 (chunker wiring), P3-105 (config), P3-106 (regression suite) not started. `SemanticChunker` untouched.

---

## 1. What Was Implemented

Per the frozen task block (Objective / Interfaces / Implementation Steps):

| Deliverable | Location | Notes |
|-------------|----------|-------|
| `_HeuristicSentenceTokenizer` | `app/infrastructure/sentence_tokenizer.py` (new class) | Stdlib, abbreviation-aware engine implementing `SentenceTokenizer.split(text) -> list[str]`; conforms to D5 (whitespace consumed only at boundaries) |
| `_SENTENCE_TERMINATORS` constant | same module | `.`, `!`, `?`, and CJK `。！？` (D7) |
| `_CLOSING_QUOTES` constant | same module | `" ' ” ’ » 」 」』 ) ]` — terminator followed by closing quotes still yields a boundary (quoted sentences) |
| `_ABBREVIATIONS` constant | same module | Module-level abbreviation list (D3 names): titles/honorifics, latin abbreviations (`e.g`, `i.e`, `etc`, `a.m`, `p.m`), degrees, `u.s.a`/`u.s`/`u.k`/`d.c`, months, days |
| `_is_abbreviation` + `_boundary_at` helpers | same module | Boundary decision: ellipsis runs, decimal numbers, abbreviations (backward scan including internal periods, e.g. `a.m`, `u.s.a`), `!?` with closing quotes, CJK empty-separator boundaries |
| **Import-time registration** | `register_sentence_tokenizer("heuristic", _HeuristicSentenceTokenizer)` | Unconditional at module import — heuristic is the guaranteed `"auto"` fallback (stdlib, no deps). **Closes P3-101 Review R-1** (see §2) |
| Unit tests | `tests/unit/test_sentence_tokenizer.py` (extended) | 22 new tests + 1 assertion added to an existing test (trailing-fragment coverage) |

### D5 contract handling
- Spans are contiguous substrings; each separator `wᵢ` is the whitespace run consumed at a boundary — verified by the `_assert_d5_reconstruction` helper across 8 fixtures, including the two governing roadmap examples: `"AAAA. BBBB."` → `["AAAA.", "BBBB."]` and CJK `"甲。乙。"` → `["甲。", "乙。"]` (empty separator, no whitespace inserted — D7).
- Boundary suppression: a `.` is **not** a boundary inside an ellipsis run (`...`), a decimal (`3.14`), or a known abbreviation (`Dr.`, `U.S.A.`, `9:00 a.m.`), unless the abbreviation ends the text (`... 9:00 a.m.` at end-of-text is a boundary).
- Empty / whitespace-only text → `[]` (early return + trailing whitespace consumed as a separator → no trailing empty fragment).

## 2. Design Decisions

- **Abbreviation token scan collects internal periods** (`_is_abbreviation` backward-scans letters *and* `.`), so multi-dot abbreviations resolve as one token: `a.m`, `u.s.a`, `ph.d`, `e.g`. This is what makes the AC2 case `"U.S.A. is large."` → 1 sentence work (each `U.`/`S.`/`A.` period is either a non-boundary period-followed-by-non-whitespace or a suppressed abbreviation).
- **End-of-text exception for abbreviations**: a known abbreviation at the very end of the text is a boundary (`"He arrived at 9:00 a.m."` — the `a.m.` closes the sentence). Mid-text, abbreviation periods are never boundaries ("sentence boundaries never fall mid-abbreviation").
- **CJK terminators are boundaries with an empty separator** (D7): `。！？` do not require following whitespace, so `"甲。乙。"` reconstructs without inserted whitespace.
- **Closing quotes after a terminator** (quoted sentences): `'She said, "Wait here." Then she left.'` → 2 sentences; the closing quote belongs to the first span and the following space is the D5 separator.
- **Import-time registration closes P3-101 R-1**: the factory's empty-registry `"auto"` raise becomes unreachable in production (the defensive error path and its P3-101 test are retained). P3-102 is the task that makes `get_sentence_tokenizer("auto")` return a working tokenizer in every environment, return `[]` for empty/whitespace, and never raise. The roadmap's P3-101 AC block is annotated accordingly.
- **Abbreviation list kept conservative** — entries where sentence-final usage is common (`no`, `vol`, `min`, `hr`, `etc.`-adjacent units) are excluded to avoid suppressing real sentence boundaries. `etc` is retained (the P3-102 fixture uses it mid-sentence).

## 3. Test Results

**New tests:** 22 added to `tests/unit/test_sentence_tokenizer.py` → file now **34 passed**.

| Gate | Result |
|------|--------|
| Unit tests (P3-102 + P3-101) | 34/34 passed |
| Full suite | **981 passed / 31 deselected** (baseline 959/31 after P3-101; +22 net new, 0 regressions) |
| Coverage (module) | **95%** (repo floor 80%); 5 uncovered lines = real `_nltk_available()` true-branch, unexecutable without nltk installed (exercised via the monkeypatched seam in `test_auto_prefers_nltk_when_available`) |
| Ruff | All checks passed on new/modified files |
| Mypy | No issues on the module |
| Integration tests | No integration test touches sentence tokenization (chunker untouched; `tests/integration/test_chunking_pipeline.py` is P3-106). Full default suite green. |

Frozen P3-102 testing-strategy coverage:
- Abbreviation boundary cases ✅ (`test_ac1_dr_smith_splits_into_two`, `test_boundary_never_falls_mid_abbreviation`, `test_e_g_and_etc_mid_sentence`)
- Ellipses ✅ (`test_ellipsis_is_not_a_boundary`)
- Decimal numbers ✅ (`test_ac3_decimals_are_one_sentence`)
- Quoted sentences ✅ (`test_quoted_sentence`)
- `!?` terminators ✅ (`test_exclamation_and_question_terminators`)
- CJK `。！？` ✅ (`test_cjk_terminators_with_empty_separator`, `test_d5_whitespace_only_separators` CJK fixture)
- No trailing empty fragment ✅ (`test_no_trailing_empty_fragment`)
- Determinism ✅ (`test_deterministic`)
- **Normalized-equivalence reconstruction per D5** ✅ (`test_d5_whitespace_only_separators`, 8 fixtures incl. `"AAAA. BBBB."` and `"甲。乙。"`)
- AC1/AC2/AC3 verbatim ✅ (`test_ac1_…`, `test_ac2_usa_is_one_sentence`, `test_ac3_…`)

## 4. Acceptance Criteria / DoD Verification

| Criterion (frozen) | Status |
|--------------------|--------|
| "Dr. Smith went to Washington. He arrived at 9:00 a.m." → exactly 2 sentences | ✅ unit-tested |
| "U.S.A. is large." → 1 sentence | ✅ unit-tested |
| "3.14 and 2.71 are constants." → 1 sentence | ✅ unit-tested |
| Sentence boundaries never fall mid-abbreviation | ✅ unit-tested |
| Whitespace normalized at sentence boundaries only (D5) | ✅ reconstruction test over 8 fixtures |
| CJK `。！？` terminators with empty separator (D7) | ✅ unit-tested |
| `"auto"` never raises / working tokenizer / empty→`[]` (P3-101 AC closure, R-1) | ✅ `TestHeuristicIsDefaultFallback` + live check |
| Heuristic suite green (DoD) | ✅ 34/34 |
| Pass all existing `TestSemanticChunking` cases when wired in | ⏳ proved by P3-104/P3-106 (chunker not wired in this task, per scope) |
| Not wired into ingestion | ✅ `semantic_chunking.py`, `config/`, `routing/`, `pipelines/` untouched |

## 5. Files Changed

| File | Action |
|------|--------|
| `app/infrastructure/sentence_tokenizer.py` | **modified** — added `_HeuristicSentenceTokenizer`, constants, helpers, import-time registration; module docstring updated |
| `tests/unit/test_sentence_tokenizer.py` | **modified** — added `TestHeuristicTokenizer` (13 tests, 1 parametrized ×8), `TestHeuristicIsDefaultFallback` (2), trailing-fragment assertion |
| `docs/PHASE_3_MILESTONE_3_1_IMPLEMENTATION_ROADMAP.md` | **modified** — P3-101 AC closure annotation (R-1 doc item) |

No configuration changes (`pyproject.toml` untouched — no new dependency; nltk remains P3-103's optional extra). No public API changes: `SentenceTokenizer`, `get_sentence_tokenizer`, `register_sentence_tokenizer`, `SentenceTokenizerSelectionError` signatures unchanged. `_HeuristicSentenceTokenizer` is private (reached via the factory).

## 6. Rollback Plan

Pure addition inside the existing P3-101 module, not wired into any ingestion path. Rollback = revert the P3-102 commit range (removes the heuristic class, constants, helpers, and the import-time registration, restoring the P3-101 scaffold state); the P3-101 factory error paths remain intact. No config, no schema, no dependency change to unwind. The `"auto"` fallback warning path is unchanged (D4/C-3 semantics preserved).

## 7. Next Steps (NOT part of this task)

Awaiting engineering review of P3-102. Then, in milestone order: P3-103 (NLTK `punkt_tab` engine, registers `"nltk"` import-guarded) → P3-104 (wire into `SemanticChunker`) → P3-105 (config) → P3-106 (regression + fixtures under all three engine paths).

---

*End of P3-102 implementation report. Implementation stopped — awaiting engineering review.*
