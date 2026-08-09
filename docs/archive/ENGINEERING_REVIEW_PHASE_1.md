# Phase 1 Engineering Review

**Date:** 2026-08-01
**Scope:** Independent review of Phase 1 (Foundation Fixes) against `PHASE_1_IMPLEMENTATION_SPECIFICATION.md` and the MEDD Phase 1 roadmap (`MASTER_ENGINEERING_DESIGN_DOCUMENT.md` §5).
**Method:** Source-vs-spec verification of all 21 tasks (subagent pass), test rerun, `ruff check` / `ruff format --check` / `mypy` runs, Phase 2 leakage scan, completion-report accuracy audit. **No code was modified.**

---

## Verdict

# ❌ NOT READY for Phase 2

Two items from the phase's **own scope** (the spec's Priority-1 table and the MEDD Phase 1 roadmap) are unimplemented, and the spec's Quality Gate §13.4 is violated by new lint errors the phase introduced. The outstanding work is small (~1.5 days) — listed in Remediation below.

---

## What passed

- **All 21 code changes are present and functionally correct.** 17/21 are fully COMPLETE including the spec-required tests (per-task source verification table in §6).
- **Full suite: 421 passed / 0 failed.** Actual split: unit 411, integration 10 (rerun this session).
- **Coverage 86.07%** (> 80% floor); `ingest_workflow.py` 61% → 83%.
- **Deferrals documented:** FAISS (G01), token counting (G02), MIME detection, language detection are explicitly "Out of Scope — Phase 2" in spec §4 (lines 99–117). No Phase 2 features leaked into `app/` (no faiss/tiktoken/token_count/hybrid).
- **mypy:** blocked only by environment (missing `types-PyYAML`, stubs for `docx`/`pptx`/`faster_whisper`/`fitz`, `numpy` `.pyi` incompatible with Python 3.14). No genuine type errors in Phase 1 code.

## Findings

### BLOCKER 1 — G05 "atomic vector store writes" never implemented (in-scope, zero trace)

- Spec §3 Priority-1 (line 75): **"atomic write audit"** is a listed data-loss fix. No P1 task implements it.
- MEDD Phase 1 roadmap (lines 1371, 1547): *"Add atomic vector store writes (G05) — 1 day"*.
- `VectorStore.save()` (`app/infrastructure/vector_store.py`) and `KnowledgeGraph.save()` (`app/domain/knowledge_graph.py:96-110`) both write directly via `write_text()` — a partial write corrupts/loses all data.
- MEDD Phase 1 success criterion *"No silent data loss paths remain"* is therefore objectively **not met**, and the phase's stated goal #1 ("Eliminate data-loss paths") is only partially achieved.
- `os.replace` atomicity exists only in `queue/state.py` and `state/manifest.py` — the audit/fix was scoped to vector store and did not happen.

### BLOCKER 2 — G06 "PyMuPDF required with clear error" never implemented

- MEDD Phase 1 roadmap (line 1372, 1548, 1562): *"Make PyMuPDF required with clear error — 1 hr"*.
- Not excluded anywhere in spec §4. Unimplemented: scanned-PDF OCR still silently falls back to empty text when `fitz` is missing (`app/infrastructure/routing/processor_impls.py`).
- This is a silent data-loss path — same class of issue the phase exists to eliminate.

### WARN 3 — Spec-required DoD/AC tests missing on 5 tasks

| Task | Missing (per spec DoD/AC) |
|------|---------------------------|
| P1-10 | `test_all_extensions_mapped` — programmatic coverage loop over every extension in `extensions.py` |
| P1-11 | `test_loaded_flag_not_set_on_save_failure` + `test_loaded_flag_set_on_save_success` |
| P1-12 | Warning-log assertion (only fallback value is asserted) |
| P1-13 | `.xyz`-type unsupported-extension test; existing test uses `.csv`, which is **supported**, so it exercises `except Exception`, not the new `ValueError` path |
| P1-20 | No test anywhere carries `@pytest.mark.integration`; `pytest -m integration` would run nothing (moot only because no live tests remain) |

### WARN 4 — Phase introduced new lint errors, violating Quality Gate §13.4

Spec §13.4: *"`ruff check app/ tests/` — no new errors."* Completion report §5.1 claims the 77 errors are "pre-existing debt, not introduced by Phase 1" — **inaccurate.** These are on lines created by the phase (E501 is not auto-fixable by `--fix`):

- `app/core/config.py:332,338` (P1-09 `_resolve_relative_paths`, 106/102 chars)
- `app/queue/worker.py:181` (P1-13 `ValueError` addition pushed except clause to 103 chars)
- `app/pipelines/ingest_workflow.py:410` (P1-03 KG merge line, 115 chars)
- `app/infrastructure/embeddings.py:7` UP035 (P1-14 retry `Callable` import from `typing`)

### WARN 5 — Completion report inaccuracies

- §3 test split "407 unit / 14 integration" is wrong — actual is **411 / 10** (totals agree at 421).
- §5.1 "pre-existing debt, not introduced by Phase 1" — contradicted by WARN 4.
- §2 "all UNCOMMITTED" is stale — the work was committed as `3378d87` (49 files, +8644/−468) and is now 4 commits ahead of `origin/main`.

### WARN 6 — Test suite is not hermetic

Running the integration tests overwrites the **tracked fixture** `tests/integration/sample_note.md` (observed this session; restored with `git checkout`). Some test writes its output over a tracked file instead of a tmp path.

### INFO 7 — Minor spec-vs-code deviations (non-blocking)

- **P1-01:** overlap is taken from the *already-overlapped* predecessor (`semantic_chunking.py:81`); for chunks shorter than `overlap_chars` a prefix can include text from two chunks back. Spec intended the previous chunk's original tail. Unguarded edge case.
- **P1-07:** watcher's runtime extension set comes from `config/default.yaml` (`service.py:65,126`), not the shared `PROCESSABLE_EXTENSIONS` constant — drift risk. Spec DoD removal of `worker.SUPPORTED_PROCESSING_EXTENSIONS` not done (kept as alias, `worker.py:43`).
- `tests/unit/test_processors.py:75` F821 (`expected_source_type`) — unreachable dead code.

---

## Remediation checklist (before Phase 2)

1. **G05:** implement atomic write (temp file + `os.replace`) for `VectorStore.save()` and `KnowledgeGraph.save()`, + 1 test each. ~1 day.
2. **G06:** make PyMuPDF a required dependency with a clear `ImportError` on scanned-PDF OCR, + 1 test. ~1 hr.
3. **Add the 5 missing DoD tests** (P1-10, P1-11 ×2, P1-12, P1-13, P1-20 mark). ~0.5 day.
4. **Fix the 4 new lint errors** (wrap/ignore the E501s, `from collections.abc import Callable`).
5. **Make tests hermetic:** point the overwriting test at a tmp path.
6. **Correct the completion report:** test split (411/10), lint-origin claim, committed state.
7. **Carry-forward (already deferred):** FAISS G01 and token counting G02 to Phase 2; enforce Phase 2 dependency on them per MEDD.

After items 1–6, Phase 1 is ready and Phase 2 may proceed.

---

## Appendix: Per-task source verification (subagent pass)

| Task | Status | Evidence | Notes |
|------|--------|----------|-------|
| P1-01 | COMPLETE | `semantic_chunking.py:64,72-92` | Edge case: overlap from overlapped predecessor (INFO 7) |
| P1-02 | COMPLETE | `versioning.py:23,62` | exact-digest test at `test_knowledge_engine.py:635` |
| P1-03 | COMPLETE | `ingest_workflow.py:181-189,409-413`; callers `worker.py:87`, `entry.py:337` | integration tests `test_knowledge_engine_persistence.py:59,71` |
| P1-04 | COMPLETE | `stats.py:40-43` | 4 tests `test_queue_stats.py:8,15,22,29` |
| P1-05 | COMPLETE | `knowledge_graph.py:50-62` | tests `test_knowledge_engine.py:277,285,292,299` |
| P1-06 | COMPLETE | `service.py:88,125-144` | tests `test_watcher_service.py:290-338` |
| P1-07 | COMPLETE | `extensions.py:65-67`, `filters.py:9`, `worker.py:43` | watcher runtime set from YAML (INFO 7) |
| P1-08 | COMPLETE | `ingest_workflow.py:147-190`; `_build_workflow` gone | both callers use factory |
| P1-09 | COMPLETE | `config.py:332-339`, call sites :254-282 | new E501s (WARN 4) |
| P1-10 | COMPLETE code / PARTIAL test | `classifier.py:30-54,105-112` | DoD coverage loop missing (WARN 3) |
| P1-11 | COMPLETE code / MISSING test | `manifest.py:44,57,60` | 2 required tests absent (WARN 3) |
| P1-12 | COMPLETE code / PARTIAL test | `config.py:202-206` | log assertion missing (WARN 3) |
| P1-13 | COMPLETE code / PARTIAL test | `worker.py:181` | `.xyz` test missing (WARN 3); new E501 (WARN 4) |
| P1-14 | COMPLETE | `embeddings.py:16-17,54-62`; used `embed()` :47, `embed_batch()` :52 | tests `test_knowledge_engine.py:437,461,473`; new UP035 (WARN 4) |
| P1-15 | COMPLETE | `processor_impls.py:11`; `logging.py:1-14` | only `config.py:14` bare getLogger (permitted) |
| P1-16 | COMPLETE | `service.py:119-123` | tests `test_watcher_service.py:180,186` |
| P1-17 | COMPLETE | `manager.py:112-116` | test `test_queue_manager.py:89` |
| P1-18 | COMPLETE | `hashing.py:22-36` | |
| P1-19 | COMPLETE | `events.py` deleted; `service.py:190-194` | zero references |
| P1-20 | PARTIAL | `conftest.py:32-37`, `pyproject.toml:49` | no test carries the mark (WARN 3) |
| P1-21 | COMPLETE | `analysis.py:144-156`, used :201,208,213 | tests `test_document_intelligence.py:87,95` |
