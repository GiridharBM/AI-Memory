# Milestone 3.1 — P3-104 Implementation Report

**Task:** P3-104 — `SemanticChunker` integration (wire the sentence tokenizer in)
**Status:** DONE — implemented, tested, not wired into config (per scope)
**Date:** 2026-08-06
**Contract:** `docs/PHASE_3_MILESTONE_3_1_IMPLEMENTATION_ROADMAP.md` (P3-104 block, D5/D5a/D8, AC/DoD)
**Scope rule honored:** ONLY P3-104 implemented; no future task work. P3-105 (config plumbing), P3-106 (regression + fixture suite) not started. No config, routing, or pipeline changes. P3-101/P3-102/P3-103 behavior preserved (full suite +3 tests from the P3-103 baseline, 0 regressions).

---

## 1. What Was Implemented

Per the frozen task block (Objective / Interfaces / D8 / D5a):

| Deliverable | Location | Notes |
|-------------|----------|-------|
| `sentence_tokenizer: str = "auto"` dataclass field | `app/infrastructure/semantic_chunking.py` | New public field with default — `SemanticChunker()` / `SemanticChunker(max_chunk_chars=…)` / `SemanticChunker(2000, 200)` still construct identically (backward compatible; only keyword usages exist in the repo) |
| **Engine resolution once per instance (D8)** | `__post_init__` | Resolves via `get_sentence_tokenizer(self.sentence_tokenizer)` at construction and logs the resolved engine at DEBUG. Stored in a private `_tokenizer` field (`init=False, repr=False, compare=False` — invisible to dataclass equality/repr, no constructor arg). Fail-fast: an unknown engine name raises `SentenceTokenizerSelectionError` at construction |
| **`_split_by_sentences` delegation** | `_split_by_sentences` | Replaced `_SENTENCE_END.split(text)` with `self._tokenizer.split(text)`. Heading/paragraph/overlap logic untouched; the single-space re-join and `start_char`/`end_char` math untouched (D5a) |
| `_SENTENCE_END` regex removed | module top | Dead after the delegation (sole consumer was `_split_by_sentences`); removed to avoid dead code |
| Module/class docstring | same module | Documents the new field and D8 resolution semantics |

The resolution helper (`get_sentence_tokenizer`, P3-101) is consumed here unchanged; `app/infrastructure/sentence_tokenizer.py` itself needed **no change** for P3-104.

## 2. Test Results

**New tests:** 3 added to `tests/unit/test_knowledge_engine.py` `TestSemanticChunking` (existing 12 cases **unchanged**):

| Test | Verifies |
|------|----------|
| `test_sentence_aligned_chunks_ac1_fixture` | **AC** — an over-long AC1 paragraph (`"Dr. Smith went to Washington. He arrived at 9:00 a.m."`, `max_chunk_chars=20`, no overlap) splits into exactly **2** sentence-aligned chunks. This is a genuine behavioral gate: the old `_SENTENCE_END` regex produced **3** (it splits after `"Dr."`), so the test fails against pre-P3-104 code |
| `test_sentence_chunk_offsets_accurate_single_spaces` | **AC** — a multi-chunk long paragraph yields 4 exact sentence-aligned chunks with contiguous, length-consistent `start_char`/`end_char` (the D5a offset invariant) |
| `test_heuristic_engine_deterministic` | **AC** — `sentence_tokenizer="heuristic"` constructs and chunking is deterministic across calls |

| Gate | Result |
|------|--------|
| `TestSemanticChunking` (12 existing + 3 new) | **15/15 passed** |
| Tokenizer + knowledge-engine unit files | **138 passed** (51 tokenizer + 87 knowledge-engine incl. the 3 new) |
| Full default suite | **1001 passed / 31 deselected** (P3-103 baseline 998/31; **+3 net new, 0 regressions**) |
| Integration suite | **30 passed / 1 skipped** (Tesseract not installed) — the live-Ollama `smoke_test` **passed** on this run (it is environmental; identical code touched nothing in its path). No P3-104 impact |
| Mypy | No issues on `semantic_chunking.py` |
| Ruff | **Zero new findings** on the changed files (see §4) |

## 3. Acceptance Criteria / DoD Verification

| Criterion (frozen) | Status |
|--------------------|--------|
| Chunk boundaries align with true sentence boundaries | ✅ live probe + `test_sentence_aligned_chunks_ac1_fixture` (2 chunks, not the old regex's 3 or a naive 6) |
| Governing byte-exact case reproduces `"AAAA.BBBB."` exactly (R-1) | ✅ `test_chunk_overlap_uses_original_predecessor` passes unchanged with default `"auto"`; live probe confirms `['AAAA.', 'AAAA.BBBB.', 'BBBB.CCCC.', 'CCCC.DDDD.']` under **all three** engine paths (`auto`→nltk, `heuristic`, `nltk`) |
| Offsets preserved | ✅ `test_chunk_overlap_offsets_preserved` passes unchanged; offset math untouched (D5a) |
| Existing `TestSemanticChunking` cases pass unchanged with default `"auto"` | ✅ 12/12 unchanged tests pass (default resolves nltk when present, heuristic otherwise) |
| **DoD — integration + extension tests green** | ✅ above |
| **DoD — chunker still byte-compatible for non-sentence-split paths** | ✅ heading/paragraph/overlap paths untouched; short sections never reach the tokenizer |
| D8 — engine resolved once per instance, logged | ✅ `__post_init__`; live probe confirms `c._tokenizer is c._tokenizer`; DEBUG log with engine + resolved class |
| Deterministic output | ✅ both engines deterministic (P3-102/P3-103); selection fixed per instance; `test_heuristic_engine_deterministic` + live probe |
| Optional-dep degradation (D4) | ✅ nltk-absent subprocess: `SemanticChunker()` constructs, `auto`→heuristic + one warning, governing contract + AC1 both hold, no crash |
| Fail-fast on invalid engine | ✅ live probe: `SemanticChunker(sentence_tokenizer="bogus")` → `SentenceTokenizerSelectionError` at construction |

## 4. Notes

- **Ruff baseline:** the two changed files carry **pre-existing** findings unrelated to P3-104 — `B007` (`for _, end, txt` loop, `semantic_chunking.py:147`, committed code) and `E501`/`F841` (`test_knowledge_engine.py:303/328/464/774`, prior work in the working tree). None of the P3-104 additions are flagged (confirmed against the renumbered findings). These predate P3-104 and were outside the P3-101/102/103 diff scope.
- **Offsets semantics (D5a):** `start_char`/`end_char` are positions in the single-space-rejoined chunk sequence (concatenation positions), **not** raw-text positions — the pre-existing, intentionally-frozen math. Inter-chunk separators are not counted. Unchanged by P3-104.
- **Environment:** suite runs on the global `C:\Python314` interpreter (holds the `intelligence` extras incl. nltk 3.10.2 + `punkt_tab`); the nltk-absent path was verified via an import-blocked subprocess. Both `auto`→nltk and `auto`→heuristic resolutions were exercised.

## 5. Files Changed

| File | Action |
|------|--------|
| `app/infrastructure/semantic_chunking.py` | **modified** — `sentence_tokenizer` field, `__post_init__` resolution (D8) + log, `_split_by_sentences` delegation to the resolved engine, `_SENTENCE_END` removed, docstrings updated (+24/−4) |
| `tests/unit/test_knowledge_engine.py` | **modified** — 3 new `TestSemanticChunking` tests; existing 12 cases unchanged |
| `docs/PHASE_3_MILESTONE_3_1_IMPLEMENTATION_ROADMAP.md` | **modified** — P3-104 closure annotation |

No public API breakage: `SemanticChunker`'s existing constructor calls (bare, `max_chunk_chars=`, `overlap_chars=`) are all unchanged and valid; the new field is additive with a default.

## 6. Rollback Plan

Revert the two code changes:
- `semantic_chunking.py`: drop the `sentence_tokenizer` field + `__post_init__`, restore `_SENTENCE_END.split(text)` in `_split_by_sentences` (restores the P3-103 module exactly);
- `test_knowledge_engine.py`: drop the 3 new tests.

**Verified:** with `semantic_chunking.py` reverted to its pre-P3-104 state (`git show HEAD:`), the tokenizer + knowledge-engine suite runs **136 passed / 2 failed** — the only failures are the 2 new P3-104 tests that require the new field/delegation (the AC1 test fails on old behavior, the heuristic-determinism test fails at construction); all other tests incl. the governing contract pass. The new tests therefore gate exactly the P3-104 behavior, and rollback to the P3-103 chunker is clean. No config, schema, or required-dependency change to unwind.

## 7. Next Steps (NOT part of this task)

Awaiting engineering review of P3-104. Then, in milestone order: P3-105 (config `chunking.sentence_tokenizer` plumbing to `SemanticChunker(sentence_tokenizer=…)` at `ingest_workflow.py:247`) → P3-106 (regression + fixture suite under all three engine paths).

---

*End of P3-104 implementation report. Implementation stopped — awaiting engineering review.*
