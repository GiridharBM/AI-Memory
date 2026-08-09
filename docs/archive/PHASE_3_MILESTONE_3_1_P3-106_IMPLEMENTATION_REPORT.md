# Milestone 3.1 — P3-106 Implementation Report

**Task:** P3-106 — Regression + fixture suite (all engine paths)
**Status:** DONE — implemented, tested, not yet engineering-reviewed
**Date:** 2026-08-06
**Contract:** `docs/PHASE_3_MILESTONE_3_1_IMPLEMENTATION_ROADMAP.md` (P3-106 block, §5 R-2 row, AC/DoD)
**Scope rule honored:** ONLY P3-106 implemented; no future task work. P3-101…P3-105 behavior preserved (determinism, rollback, backward compat). No engine, config, or pipeline code changed by P3-106 — this task is tests + committed fixtures only.

---

## 1. What Was Implemented

Per the frozen task block (Objective / Files expected to change / AC / DoD):

| Deliverable | Location | Notes |
|-------------|----------|-------|
| **R-2 parametrized regression** | `tests/unit/test_knowledge_engine.py` — new `TestSemanticChunkingAllEnginePaths(TestSemanticChunking)` | Re-runs the **full existing 15-test `TestSemanticChunking` suite** under `"heuristic"`, `"nltk"`, and `"auto"` (an autouse parametrized fixture monkeypatches `SemanticChunker.__init__` to `setdefault("sentence_tokenizer", engine)`). `"nltk"` is import-guarded (skips only when nltk/`punkt_tab` absent; `"auto"` always runs). **Existing parent tests byte-identical and untouched** — the parent class still runs under the default `"auto"`. |
| Engine-aware offset override | `tests/unit/test_knowledge_engine.py` — inside the R-2 subclass | One existing test, `test_sentence_chunk_offsets_accurate_single_spaces`, asserts **NLTK's** segmentation of the `a.m.` + capitalized-word boundary (nltk splits after the abbreviation; the heuristic keeps `a.m.` with its sentence per the D7 abbreviation rule). The parent test is unchanged; the R-2 subclass overrides the name to assert each resolved engine's own spec-correct segmentation while keeping the identical D5a offset math (contiguity + accurate per-chunk length). This is the one and only segmentation-coupled existing test. |
| **D9 byte-exact boundary test** | `tests/unit/test_sentence_tokenizer.py` — `test_d9_punkt_tab_reproduces_governing_fixture_byte_exact` in `TestNltkTokenizer` | `"".join(spans) == "AAAA.BBBB.CCCC.DDDD."` — the byte-exact source of the `test_chunk_overlap_uses_original_predecessor` chunker contract (R-1), asserted directly on `punkt_tab` (nltk-only, import-guarded). |
| **Fixture span-reconstruction** | `tests/unit/test_sentence_tokenizer.py` — `TestCommittedFixtureSpanReconstruction` | Parametrized over `abbreviations.md` + `cjk.md` × `"heuristic"`/`"nltk"`/`"auto"`; each case reads the committed fixture (UTF-8) and asserts D5 reconstruction (`text == s1 + w1 + s2 + … + sn`, whitespace normalized only at boundaries) via the module's `_assert_d5_reconstruction`. |
| **Performance** | `tests/unit/test_sentence_tokenizer.py` — `TestPerformance` | 1 MB text (`"The quick brown fox…"` × 24000) split ≤ 1.0 s, `time.perf_counter`-measured, heuristic + nltk (Baseline §8.4 pattern; generous ceiling). |
| **Integration engine parity** | `tests/integration/test_chunking_pipeline.py` (new, `@pytest.mark.integration`) | Real markdown doc (> 2000 chars → forces sentence-level splitting) through `IngestionWorkflow.create_default` with `"auto"` vs `"heuristic"` → both produce chunks; chunk counts **equal when nltk absent** (auto→heuristic fallback); plus heuristic determinism through the pipeline. Uses the `FakeEmbeddingService` seam (`_run_knowledge_engine`); no live Ollama. |
| **Committed fixtures** | `tests/fixtures/chunking/abbreviations.md`, `tests/fixtures/chunking/cjk.md` | Real-world sentences exercising abbreviations (Dr., a.m., U.S.A., St., Mr., decimal 3.14, quotes, "Really!", "He paused…") and CJK text with 。！？ and 「」 quotes (Phase 2 C-4 precedent: committed, not generated). |

No source code changed. `get_sentence_tokenizer`, both engines, the chunker, config, and the ingestion pipeline are untouched by P3-106.

## 2. Test Results

**New tests:** 54 (45 R-2 + 9 tokenizer-suite) — all in the default run; the 2 integration tests are `@pytest.mark.integration` (deselected by default, run explicitly).

| Test area | Verifies | Result |
|-----------|----------|--------|
| `TestSemanticChunkingAllEnginePaths` (15 tests × 3 engines) | R-2 frozen criterion | **45/45 passed, 0 skipped** (nltk installed in this env, so all three paths executed for real) |
| D9 byte-exact boundary | governing contract on `punkt_tab` | passed |
| `TestCommittedFixtureSpanReconstruction` (2 × 3) | D5 reconstruction on committed fixtures | **6/6 passed** |
| `TestPerformance` (2) | 1 MB ≤ 1 s | **2/2 passed** (heuristic ~0.05 s, nltk ~0.14 s per prior 900 KB probe) |
| `TestNltkTokenizer` existing + new | all nltk cases | passed unchanged |
| `test_chunk_overlap_uses_original_predecessor` (R-1, existing) | `"AAAA.BBBB."` byte-exact | passed unchanged |

| Gate | Result |
|------|--------|
| Full default suite | **1059 passed / 33 deselected** (P3-105 baseline 1005/31; **+54 net new, 0 regressions**) |
| Integration (`-m integration`, live-flagged) | **30 passed / 1 skipped (Tesseract binary) / 1 failed** — the single failure is the pre-existing live-Ollama `smoke_test::test_live_ollama_analysis_and_note_generation` flake (O-3, documented at P3-105 review: environmental, nondeterministic model output, no path to P3-106). The 2 new chunking-pipeline integration tests pass. |
| Tokenizer suite coverage | **97%** on `app/infrastructure/sentence_tokenizer.py` (DoD target ≥ 90%) |
| Full-suite coverage | **89%** total (`--fail-under=80` gate passes) |
| Ruff | **Zero new findings** on all changed files. The 4 remaining `test_knowledge_engine.py` findings (E501 ×3 at 372/397/843, F841 at 533) are the **pre-existing** findings from the P3-105 baseline (303/328/774/464), line numbers shifted +69 by the inserted regression block — untouched |
| Mypy | **Zero new findings.** Only the pre-existing environmental errors remain (`faster_whisper` missing stubs; `numpy/__init__.pyi` syntax on Python 3.14) plus the pre-existing `ingest_workflow.py` `object`-injection findings; no P3-106 source is mypy-checked (test-only change) |

## 3. Acceptance Criteria / DoD Verification

| Criterion (frozen) | Status |
|--------------------|--------|
| AC of §5 all met | ✅ sentence boundaries respect abbreviations (Dr., Mr., U.S.A. — heuristic + nltk suites); "Dr. Smith…" → 2 sentences (AC1 unchanged); all existing chunking tests pass under every engine path (R-2, below) |
| **Full suite green under all three engine paths (R-2)** | ✅ `TestSemanticChunkingAllEnginePaths` re-runs the full existing 15-test `TestSemanticChunking` suite under `"heuristic"`, `"nltk"`, `"auto"` — 45/45 green, 0 skips. Both runtime paths execute whenever nltk is installed (`"nltk"` and `"auto"`→nltk, plus `"heuristic"`); nltk path import-guarded |
| **Governing byte-exact contract holds** | ✅ `test_chunk_overlap_uses_original_predecessor` (R-1) still passes unchanged; the new D9 boundary test asserts `punkt_tab` reproduces `"AAAA.BBBB.CCCC.DDDD."` byte-exact |
| **Span-reconstruction on committed fixtures per D5** | ✅ 6/6 (both fixtures × all three engines) — `text == s1 + w1 + s2 + … + sn`, whitespace normalized only at boundaries |
| **DoD — regression + integration + performance tests green** | ✅ full default suite 1059 passed; integration parity green; perf ≤ 1 s per 1 MB |
| **DoD — parametrized suite green under heuristic/nltk/auto (nltk path import-guarded)** | ✅ as above; the `"nltk"` param is `skipif`-guarded on `_NLTK_ENGINE_AVAILABLE` |
| **DoD — fixtures committed** | ✅ `tests/fixtures/chunking/abbreviations.md` + `cjk.md` present in-tree (Phase 2 C-4 precedent); oversize 1 MB text generated in-test, not committed |
| **DoD — ruff/mypy zero new errors** | ✅ (Section 2) |
| **DoD — coverage ≥ 80% (tokenizer suite ≥ 90%)** | ✅ 89% total / 97% tokenizer |

## 4. Notes

- **One existing test is nltk-segmentation-coupled.** `test_sentence_chunk_offsets_accurate_single_spaces` (P3-104) asserts NLTK's segmentation of `a.m.` + capitalized word. Under the heuristic engine, `a.m.` is correctly kept with its sentence (D7 abbreviation rule), giving a valid 3-chunk split where nltk gives 4. The parent test is byte-identical and runs under `"auto"`; the R-2 subclass overrides the name with an engine-aware version that asserts each engine's own spec-correct segmentation **and** the same D5a offset math (contiguous `start_char`/`end_char`, accurate per-chunk length). This is the documented, deliberate difference — the milestone contract (D9 byte-exact) holds identically across all engines.
- **R-2 design:** the regression runs the *full* existing suite by subclassing — no existing test was modified or removed, and the `"auto"` param always runs (nltk-absent envs exercise the auto→heuristic fallback; nltk-present envs the auto→nltk path).
- **Integration marker:** `test_chunking_pipeline.py` is `@pytest.mark.integration` per roadmap §5 (marker registered in `tests/conftest.py`; deselected by default via pyproject `addopts`), run explicitly with `-m integration`.
- **Environment:** suite runs on the global `C:\Python314` interpreter (holds the `intelligence` extras incl. nltk 3.10.2 + `punkt_tab`), so `"auto"` resolves to nltk and all three R-2 params execute — no skips. Under an nltk-absent interpreter, `"nltk"` skips and `"auto"` exercises the fallback.
- **O-1/O-2 findings (P3-105 review, non-blocking) remain out of P3-106 scope:** the env-invalid test gap and the `__name__` coupling were not reopened; the pre-existing smoke-test flake (O-3) is environmental with no path to this task.

## 5. Files Changed

| File | Action |
|------|--------|
| `tests/unit/test_sentence_tokenizer.py` | **modified** — D9 byte-exact test in `TestNltkTokenizer`; `TestCommittedFixtureSpanReconstruction`; `TestPerformance`; `_register_real_engines()`/fixture-dir helpers. All P3-101…P3-103 tests unchanged |
| `tests/unit/test_knowledge_engine.py` | **modified** — `TestSemanticChunkingAllEnginePaths(TestSemanticChunking)` + engine-aware offset override. All existing tests byte-identical |
| `tests/integration/test_chunking_pipeline.py` | **new** — engine parity through `IngestionWorkflow` (`@pytest.mark.integration`) |
| `tests/fixtures/chunking/abbreviations.md` | **new** — committed fixture |
| `tests/fixtures/chunking/cjk.md` | **new** — committed fixture |

No production code, config, dependency, or public API change.

## 6. Rollback Plan

P3-106 is test-only. Rollback = remove the P3-106 tests/fixtures and restore the pre-P3-106 versions of the two modified test files (the P3-101…P3-105 features live in source untouched by this task).

**Verified (surgical revert with temp backup + restore, SHA-256 byte-verified):** with the P3-106 edits reversed (R-2 class + imports removed from `test_knowledge_engine.py`; D9/fixture/perf blocks + `time`/`Path` imports removed from `test_sentence_tokenizer.py`; `test_chunking_pipeline.py` and `tests/fixtures/chunking/` deleted), the full default suite returns to **exactly 1005 passed / 31 deselected — the P3-105 baseline** — i.e. zero collateral damage to P3-101…P3-105 behavior; the only loss is the P3-106 coverage itself. Restored afterward and byte-verified identical (SHA-256 match on all three test files), suite re-confirmed at 1059 passed / 33 deselected.

## 7. Next Steps (NOT part of this task)

Awaiting engineering review of P3-106. This is the final implementation task of Milestone 3.1; after review, the milestone gates (§9) close and Milestone 3.2 may begin.

---

*End of P3-106 implementation report. Implementation stopped — awaiting engineering review.*
