# Phase 1 Remediation Report

**Scope:** Resolve every finding in `docs/ENGINEERING_REVIEW_PHASE_1.md` (verdict: ❌ NOT READY).
**Date:** 2026-08-01
**Result:** ✅ ALL FINDINGS RESOLVED — 432 tests pass (422 unit / 10 integration), 1 deselected
(live `integration` smoke test, opt-in), coverage 86.02% (floor 80%).

---

## BLOCKER 1 — G05: Non-atomic persistence writes

| Field | Value |
|-------|-------|
| **Description** | `VectorStore.save()` and `KnowledgeGraph.save()` wrote directly to the target path — a crash mid-write corrupts or truncates the store/graph (silent knowledge loss). |
| **Root cause** | Direct `path.write_text(...)` with no temp-file-then-rename. |
| **Files affected** | `app/infrastructure/vector_store.py`, `app/domain/knowledge_graph.py`, `tests/unit/test_knowledge_engine.py` |
| **Risk** | High — data loss on partial write. |
| **Effort** | ~1 day (planned) — actual: <1 hr. |
| **Resolution** | Both saves now write to `<path>.tmp`, `os.replace()` into place, and clean up the temp file in a `finally` (suppressing `FileNotFoundError`). |
| **Verification** | `test_save_is_atomic` added to both `TestVectorStore` and `TestKnowledgeGraphPersistence`: asserts content survives, no `.tmp` left behind, and the previous file is byte-identical when serialization raises (via monkeypatched `json.dumps`). 2/2 pass. |

## BLOCKER 2 — G06: PyMuPDF not required for scanned-PDF OCR

| Field | Value |
|-------|-------|
| **Description** | Scanned-PDF OCR silently returned `""` when `fitz` was missing — documents silently lose all text (MEDD G06 + roadmap item unimplemented; not excluded by spec §4). |
| **Root cause** | `_ocr_extract_from_pdf()` swallowed `ImportError` and returned empty text. |
| **Files affected** | `app/infrastructure/routing/processor_impls.py`, `pyproject.toml`, `tests/unit/test_processors.py` |
| **Risk** | Medium — new required runtime dependency; resolves a silent data-loss path. |
| **Effort** | ~1 hr (planned) — actual: <1 hr. |
| **Resolution** | `PyMuPDF>=1.24.0` added to `pyproject.toml`; missing `fitz` now raises a clear `ImportError` with install instructions (chained via `from exc`). |
| **Verification** | `test_scanned_pdf_requires_pymupdf` (simulates `fitz` absent via `sys.modules`) asserts `ImportError` with "PyMuPDF" in the message. Pass. |

## WARN 3 — 5 missing DoD tests

| Field | Value |
|-------|-------|
| **Description** | Implementation completed code without the spec's required regression tests (P1-10, P1-11 ×2, P1-12, P1-13, P1-20). |
| **Root cause** | DoD test scaffolding skipped during implementation. |
| **Files affected** | `tests/unit/test_routing.py`, `tests/unit/test_manifest.py`, `tests/unit/test_model_routing_settings.py`, `tests/unit/test_queue_worker.py`, `tests/integration/smoke_test.py` |
| **Risk** | Low — test-only. |
| **Effort** | ~0.5 day (planned) — actual: <1 hr. |
| **Resolution** | Added: |
| | - **P1-10:** `test_every_mapped_extension_classifies_to_its_kind` + `test_all_processable_extensions_are_mapped` (programmatic coverage loop over `EXTENSION_KIND_MAP`/`PROCESSABLE_EXTENSIONS`). |
| | - **P1-11:** `test_loaded_flag_set_on_save_success` + `test_loaded_flag_not_set_on_save_failure` (the latter forces a save failure and confirms the `_loaded` flag stays `False`). |
| | - **P1-12:** `test_model_for_unknown_logs_warning` (`caplog` asserts the warning is emitted, not just the fallback value). |
| | - **P1-13:** `test_worker_rejects_unsupported_extension` (`.xyz` → FAILED via the unsupported-extension path, file moved to failed/). |
| | - **P1-20:** the only live-service test (`smoke_test.py`) was converted into a pytest test marked `@pytest.mark.integration` — skipped by default, runnable via `-m integration`. The `integration` mark was already registered in `tests/conftest.py` and `pyproject.toml` already defaults to `-m 'not integration'`; the YouTube ingestor tests were already mock-based (no network). |
| **Verification** | 11 new tests, all passing. `pytest -m integration` collects the marked smoke test; default run skips it (1 deselected). |

## WARN 4 — Phase introduced 4 new lint errors

| Field | Value |
|-------|-------|
| **Description** | Four new ruff errors on phase-created lines violated Quality Gate §13.4 ("no new errors"). |
| **Root cause** | Long lines / a `typing`-import regression introduced during implementation. |
| **Files affected** | `app/core/config.py:332,338`, `app/queue/worker.py:181`, `app/pipelines/ingest_workflow.py:410`, `app/infrastructure/embeddings.py:7` |
| **Risk** | Low — quality-gate compliance only. |
| **Effort** | ~30 min (actual). |
| **Resolution** | Wrapped the three E501 lines to ≤100 chars; moved `Callable` from `typing` to `collections.abc` (UP035). |
| **Verification** | `ruff check` on all four files: the 4 flagged errors are gone. Remaining repo-wide lint debt is the documented pre-existing 73 (not introduced by Phase 1). |

## WARN 5 — Completion-report inaccuracies

| Field | Value |
|-------|-------|
| **Description** | `docs/PHASE_1_COMPLETION_REPORT.md` reported a wrong test split, mislabeled lint debt origin, and a stale uncommitted claim. |
| **Root cause** | Report written before the final verification pass. |
| **Files affected** | `docs/PHASE_1_COMPLETION_REPORT.md` |
| **Risk** | Low — documentation accuracy. |
| **Effort** | ~15 min. |
| **Resolution** | §3 split corrected to **411 unit / 10 integration** (= 421); §5.1 qualifies the lint claim (73 pre-existing + 4 phase-introduced, now fixed); §2/§5.4/§6/§7 updated to the committed state (`3378d87`, 4 commits ahead of `origin/main`). |

## WARN 6 — Test suite not hermetic

| Field | Value |
|-------|-------|
| **Description** | Running integration tests overwrote the **tracked fixture** `tests/integration/sample_note.md`. |
| **Root cause** | `smoke_test.py:84` wrote its output to the repo path instead of a temp path. |
| **Files affected** | `tests/integration/smoke_test.py` |
| **Risk** | Low — dirty working tree on every test run. |
| **Effort** | ~15 min (folded into WARN 3 / P1-20). |
| **Resolution** | Rewritten as a pytest test writing to `tmp_path`; the tracked `sample_note.md` is never written by tests. |
| **Verification** | `git status` clean of fixture modifications after the full suite run. |

## INFO 7 — Minor spec-vs-code deviations

| Finding | Resolution |
|---------|-----------|
| **P1-01 overlap edge** — overlap was taken from the *already-overlapped* predecessor; chunks shorter than `overlap_chars` could leak text from two chunks back. | `app/infrastructure/semantic_chunking.py` now takes the overlap from the **original** predecessor (`chunks[index-1]`). Added `test_chunk_overlap_uses_original_predecessor` proving no two-back leak. All 6 overlap tests pass. |
| **P1-07 watcher drift + alias** — watcher's runtime set came only from `config/default.yaml` (drift risk vs `PROCESSABLE_EXTENSIONS`); spec DoD alias removal not done (`worker.SUPPORTED_PROCESSING_EXTENSIONS`, `filters.SUPPORTED_EXTENSIONS`). | DoD completed: both aliases **removed** (imports point at `PROCESSABLE_EXTENSIONS` directly). Watcher runtime set is now `PROCESSABLE_EXTENSIONS | settings.watcher.supported_extensions` — canonical set always watched, user overrides still honored. Added drift-guard test `test_supported_extensions_always_include_canonical_set`. |
| **`tests/unit/test_processors.py:75` dead code** — unreachable `assert`/F821 in `_tmp_pdf()`. | Removed. |

---

## Final verification

```
python -m pytest tests -q -p no:cacheprovider --cov=app --cov-report=term
→ 432 passed, 1 deselected (live integration smoke test, opt-in)
→ coverage 86.02% (floor 80%)
ruff check on all changed files → only documented pre-existing debt remains
```

## Sign-off

Phase 1 now satisfies all review exit criteria. The remaining repo-wide lint/format/mypy debt is
pre-existing (documented in §5 of the completion report and §7 recommendations) and does not block
Phase 2. **Awaiting approval to begin Phase 2.**
