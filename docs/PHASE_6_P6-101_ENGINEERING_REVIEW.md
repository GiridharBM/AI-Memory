# P6-101 Engineering Review — Production Hardening

**Task:** P6-101 — Production Hardening
**Phase:** Phase 6 (production-hardening audit; no new features)
**Date:** 2026-08-09
**Verdict:** **APPROVED**

---

## 1. Deliverable

A production-hardening pass over the complete application, performed as an audit of 12 hardening areas against the live repository followed by a small, targeted set of fixes. No working functionality was redesigned or rewritten; the changes are confined to five surfaces and are strictly behavior-preserving for valid inputs.

| Fix | Surface | Problem | Change |
|-----|---------|---------|--------|
| F1 | `app/infrastructure/embeddings.py` | `_embed_batch` silently mis-paired chunks with embeddings when Ollama returned a different vector count | New `EmbeddingCountMismatchError` (a `ValueError`); `embed_batch` validates `len(embeddings) == len(texts)` and raises; `_with_retry` re-raises it immediately (a deterministic mismatch is not transient) |
| F2 | `app/queue/state.py` | Two threads (watcher observer + worker) wrote the same `.tmp` file concurrently; an unwritable state file could raise inside `process_next`'s `finally` and kill the worker | `save()` serialized under a `threading.Lock` and made best-effort (OSError logged, never raised); `load()` tolerates invalid UTF-8 and OS errors alongside bad JSON |
| F3 | `app/infrastructure/vector_store.py` | A corrupt or partially malformed `vector_store.json` crashed `VectorStore.__init__` (constructor used by both search and ingest) | `_load()` tolerates unreadable/corrupt files and non-dict roots; malformed entries are skipped individually; norm is computed before insertion so a bad embedding can never leave a norm-less entry behind |
| F4 | `app/core/logging.py` | `JsonFormatter` dropped every structured `extra` field the codebase logs with (`path`, `sha256`, …), gutting JSON-file diagnostics | Reserved LogRecord attributes are excluded; all other `record.__dict__` extras are serialized with `default=str` (robust to `Path`/datetime extras) |
| F5 | `app/queue/worker.py` | Manifest recorded the file as processed *before* the move to `processed/`; a failed move left the item FAILED but permanently marked — the file would never be retried | Move happens first; only a successful move is followed by the manifest record. A failed move leaves the manifest untouched so the file retries on the next scan |

## 2. Audit Coverage (12 Areas)

Each area was verified against live code; findings are the state *after* P6-101 fixes.

| # | Area | Status | Evidence (live code) |
|---|------|--------|----------------------|
| 1 | Configuration handling | PASS | pydantic `Settings`/sub-settings (`app/core/config.py`) with validators (e.g. `LoggingSettings`), typed path settings, no hardcoded paths; `tmp_settings` fixture exercises the full schema |
| 2 | Input validation | PASS | Size caps (`max_file_size_mb`), empty-text guards (`embed("")` → `ValueError`), supported-extension gate (watcher filters + worker `_source_type_for_extension`), unsupported-hash `ValueError`, `suggested_note_title` validator |
| 3 | Error handling | PASS | Bounded retries with exponential backoff (embedding `_with_retry`, Ollama `request_retries`), typed exceptions (`IngestionWorkflowError`, `AIProcessingError`, `OllamaClientError`), worker containment of `OSError`/`ValueError`; F1 adds a non-retried mismatch error |
| 4 | Resource cleanup | PASS | Atomic writes everywhere via tmp-file + `os.replace` with `finally` unlink (`manifest`, `queue state`, `vector store`); F2 makes the queue-state write serialized and best-effort |
| 5 | File/resource lifecycle | PASS | Queue-state restart recovery (`restore_into`, in-flight items), manifest quarantine of corrupt files, processed/failed file routing; F5 fixes move/manifest ordering |
| 6 | Logging & diagnostics | PASS | `get_logger` convention, component log files (watcher/processing/errors), rotating files; F4 fixes structured `extra` loss in JSON format; no secrets logged (warnings log exception types, not payloads) |
| 7 | Timeout handling | PASS | `OllamaSettings.timeout_seconds=300`, `request_retries=3`, `retry_backoff_seconds=1.0`; vision client uses settings timeout; embedding retries capped at 2 |
| 8 | Boundary conditions | PASS | Empty queue → no-op; empty text/batch → `[]`/`ValueError`; empty store/empty query → `[]`; dim mismatch → `0.0` score; `min_score`/`top_k` honored; `None` config paths → disabled behavior |
| 9 | Large-input handling | PASS | File size caps, chunking, `max_structure_text_bytes`, `max_code_chars`, table row/column caps, image byte caps — verified present and unchanged |
| 10 | Failure isolation | PASS | Per-item try/except in worker, `_fail_item` routes to `failed/`, knowledge-engine stage failures do not abort the document, `QueueStateStore.save` no longer propagates; F2 hardens this |
| 11 | Graceful shutdown | PASS | `QueueWorker.stop(drain=True)` drains before exit, state saved on stop, `WatchService.run` handles `KeyboardInterrupt` → `stop(drain=True)` |
| 12 | Rollback / feature-disable | PASS | `manifest.enabled=False`, disabled embedder → `[]` with pipeline short-circuit, `move_processed=False` leaves sources in place; persisted stores from prior versions load via `.get` defaults |

## 3. Backward Compatibility

- **Public APIs unchanged.** All five fixes preserve signatures and valid-input behavior. `EmbeddingCountMismatchError` is a new additive exception subclass.
- **Persisted files compatible.** Valid queue-state and vector-store files load exactly as before (F2/F3 only broaden the failure handling for corrupt input). Successful `process_next` outcomes are observably identical; only the failure path ordering changes (F5).
- **Logging output stable.** Records without `extra` serialize byte-for-byte identically (reserved attributes are excluded); records with `extra` now additionally include those fields.
- **No config schema changes, no new dependencies, no CLI/API changes, no MEDD version bump.**

## 4. Testing

**9 new tests** (production-oriented edge/failure cases):

| Test | Fix | Covers |
|------|-----|--------|
| `test_embed_batch_count_mismatch_raises_without_retry` | F1 | Mismatched vector count raises `EmbeddingCountMismatchError` and is **not** retried (client called once) |
| `test_load_corrupt_file_starts_empty` | F3 | Invalid UTF-8/JSON store file → empty store, no raise |
| `test_load_non_dict_root_starts_empty` | F3 | Non-dict root JSON → empty store |
| `test_load_skips_malformed_entries` | F3 | One bad entry (missing embedding) and one malformed embedding skipped; good entry retained |
| `test_queue_state_load_ignores_invalid_utf8` | F2 | Invalid UTF-8 state file → `[]` |
| `test_queue_state_save_is_best_effort_when_path_unwritable` | F2 | `os.replace` target is a directory → no raise |
| `test_queue_state_save_is_thread_safe` | F2 | 4 threads × 25 concurrent saves → valid final state, no errors |
| `test_setup_logging_json_preserves_structured_extra` | F4 | `extra` fields (incl. a `Path`) appear in JSON log output |
| `test_worker_move_failure_does_not_record_manifest` | F5 | Failed move → item FAILED, manifest empty, file in `failed/` |

Existing duplicate-detection tests (`test_duplicate_detection.py`, `test_queue_worker_pipeline.py`) continue to assert duplicates are **not** moved and never reach the workflow — unaffected by F5.

## 5. Verification (commands re-run this session)

| Gate | Result |
|------|--------|
| Focused suite (changed modules + duplicate detection) | **246 passed** |
| Full default regression suite (`pytest tests -q -p no:cacheprovider`) | **1393 passed / 0 failed / 59 deselected** (baseline 1384 +9 new; 0 regressions) |
| Integration suite (`tests/integration -m integration --ignore=tests/integration/smoke_test.py`) | **56 passed / 1 skipped** (Tesseract binary absent — pre-existing env skip) / **29 deselected** |
| Ruff (9 changed files) | **Clean on all P6-101 lines**; 6 findings remain on unchanged pre-existing lines in those files (baseline debt, not introduced here) |
| Mypy (`--follow-imports=skip`, 5 changed source modules) | **Success: no issues found** (env-wide mypy remains blocked by the pre-existing numpy-stub issue under Python 3.14) |
| Coverage (`pytest tests --cov=app`) | **TOTAL 90%** (repo floor 80%). Changed modules: `embeddings.py` **100%**, `vector_store.py` **97%**, `logging.py` **98%**, `queue/state.py` **93%** (uncovered lines 50/55/106–107 are pre-existing defensive branches, not P6-101 code) |

## 6. Files Changed

| File | Action |
|------|--------|
| `app/infrastructure/embeddings.py` | **Updated** — `EmbeddingCountMismatchError`, no-retry path, batch count guard |
| `app/queue/state.py` | **Updated** — thread-safe best-effort `save`, broader `load` exceptions |
| `app/infrastructure/vector_store.py` | **Updated** — tolerant `_load` (per-entry skip, norm-before-insert, non-dict root guard) |
| `app/core/logging.py` | **Updated** — `JsonFormatter` preserves structured `extra` fields |
| `app/queue/worker.py` | **Updated** — move-to-processed before manifest record |
| `tests/unit/test_knowledge_engine.py` | **Updated** — +4 tests |
| `tests/unit/test_queue_state.py` | **Updated** — +3 tests |
| `tests/unit/test_queue_worker.py` | **Updated** — +1 test |
| `tests/unit/test_logging.py` | **Updated** — +1 test |

## 7. Findings

**Blocking:** None.

**Non-blocking:**
- The 6 ruff findings (5 × `E501`, 1 × `F841`) sit on unchanged pre-existing lines inside the touched test/source files (Phase 2–5 worktree debt, uncommitted per repo convention); they predate and are unrelated to P6-101.
- `worker.py` line coverage is 83% (pre-existing); the newly reordered move/manifest path is exercised by the new test, the remaining uncovered lines are legacy branches.
- `tests/integration/smoke_test.py` (live-Ollama) is excluded from the gate — pre-existing nondeterministic model-output flake, exercises no P6-101 code.
- Whole-repo mypy remains blocked by the pre-existing numpy-stub/Python 3.14 incompatibility; scoped run on the changed modules is clean.
- Working tree remains uncommitted (Phase 1–5 + this milestone), consistent with the per-milestone commit convention.

## 8. Conclusion

The audit inspected all 12 hardening areas against live code and confirmed the application already enforced config validation, size caps, bounded retries, atomic writes, failure isolation, graceful drain/shutdown, and feature-disable behavior. Five genuine production gaps were identified and fixed without changing any public API, config schema, dependency, or valid-input behavior: silent chunk/embedding misalignment on vector-count mismatch, a concurrent-write race and worker-killing failure path in queue-state persistence, constructor crashes on corrupt vector-store files, loss of all structured log context in JSON output, and a file-lifecycle ordering bug that could permanently mark a failed file as processed. Each fix has a dedicated production-edge test. All gates pass — 1393 unit tests (0 regressions), hermetic integration green, ruff clean on all P6-101 lines, mypy clean on changed modules, 90% coverage — and the git diff contains only the intended changes.

**Verdict:** **APPROVED**
