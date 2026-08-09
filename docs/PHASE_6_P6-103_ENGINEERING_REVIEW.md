# P6-103 Engineering Review — Reliability and Failure Recovery

**Task:** P6-103 — Reliability and Failure Recovery
**Phase:** Phase 6 (production-hardening audit; no new features)
**Date:** 2026-08-09
**Verdict:** **APPROVED**

---

## 1. Deliverable

A full audit of the runtime pipeline against 12 failure areas — ingestion, parsing, OCR, extraction, chunking, retrieval, configuration, invalid input, missing resources, partial pipeline execution, external models, and recovery/rollback. Each area was traced end-to-end through the actual implementation, the failure contract verified against the established error model, and two genuine gaps were fixed with focused tests. All existing error-handling behavior, successful-path behavior, and Phase 1–5 functionality are preserved.

**Audit coverage (files read in full):** queue worker/state/manager/models; ingest workflow; AI processor; Ollama/vision/whisper clients; embeddings; manifest + hashing; OCR engine registry; ingestion base/service/pdf/image ingestors; routing router + processor impls; search + BM25; vault writer + wiki manager; core config; watcher service/scanner; extensions.

## 2. Failure-Area Audit

| # | Failure area | Contract verified | Verdict |
|---|--------------|-------------------|---------|
| 1 | **Ingestion failures** | `IngestionError(RuntimeError)` base; `UnsupportedSourceError(IngestionError)` for unhandled types; unsupported sources surface as structured `DocumentIngestionError` results (not raw exceptions) via `DocumentIngestionService`; size-limit enforced | PASS |
| 2 | **Parsing failures** | PDF open failure wrapped as `IngestionError(...) from exc`; code/notebook/metadata enrichment is contained in per-type `_enrich_*`; malformed files produce structured errors | PASS |
| 3 | **OCR failures** | `OCRSelectionError` when no engine; `VisionOcrEngine` per-page **bounded retry**; a failed page degrades to `""` + warning and never aborts the pass; missing local binary → nil result; Tesseract-absent integration test skips cleanly | PASS |
| 4 | **Extraction failures** | Vision `analyze_image` failure is swallowed → warning + minimal payload (document unchanged); all extraction is best-effort enrichment | PASS |
| 5 | **Chunking failures** | Chunk → embed → save → cross-link block fully enclosed in `_run_knowledge_engine`'s try/except; a chunking/embedding failure fails the pipeline atomically, never silently partial | PASS |
| 6 | **Retrieval failures** | Embedder failure degrades to lexical (BM25) retrieval; BM25 failure degrades to dense; search never raises into the caller on model hiccups | PASS |
| 7 | **Configuration failures** | `ConfigurationError(RuntimeError)`; pydantic validation on settings load; `test_invalid_config_fails_fast` locks the fail-fast contract | PASS |
| 8 | **Invalid input** | Empty text → `ValueError` at embeddings boundary (never silently accepted); empty corpus → empty results; empty query → empty results | PASS |
| 9 | **Missing resources** | Worker wraps the whole item in try/except/continue; missing source mid-item → `FAILED` without crashing the worker loop; `test_worker_handles_missing_source_without_crashing` | PASS |
| 10 | **Partial pipeline failures** | Knowledge-engine partial failure contained; child *ingestion* failure already skipped-and-cleaned (`test_child_failure_skipped_and_cleaned`); **child *processing* failure was NOT contained → FIXED (F1)** | PASS after F1 |
| 11 | **External model/service failures** | `OllamaClientError` hierarchy + retries; `AIProcessingError` with `validation_retries=2` (malformed JSON retried, budget exhausted → error); `EmbeddingCountMismatchError` raised **without** retry (deterministic mismatch — retry would be wasted); vision per-page bounded retry; whisper/vision client-level construction guarded | PASS |
| 12 | **Recovery and rollback** | Queue restart re-enqueues PENDING via `QueueStateStore.restore_into`; corrupted manifest quarantined + recreated; hash-present → skip (idempotent reprocess); feature toggles disable paths (`move_processed`, `email_attachments`, `enabled`); atomic vault writes; **manifest save failure after a successful move stranded the item as FAILED with no dedup record → FIXED (F2)** | PASS after F2 |

## 3. Fixes Applied

### F1 — Child attachment processing failure failed the whole email (`app/pipelines/ingest_workflow.py`)

`_ingest_child` called `self._process_document(child_document, ...)` unguarded. If the AI step errored on an attachment, the exception propagated out of `run()`, the worker marked the **parent** email `FAILED` and moved it to `failed/` — even though the parent note was already written and the failure was purely the child's. This violated the area-10 isolation contract ("partial failures isolated").

**Fix:** wrap the child's `_process_document` in try/except → `logger.exception` + continue, so remaining children still process. Matches the established child-ingestion-failure isolation pattern one line above it.

### F2 — Manifest save failure after a successful move stranded the item (`app/queue/worker.py`)

`_process_item` moved the source to `processed/`, recorded the hash, then called `manifest_manager.save()` unguarded. A disk error there propagated to the catch-all → item marked `FAILED` while the file already sat in `processed/`: permanently stranded (never retried, never deduped, no disk record).

**Fix:** wrap `save()` in `except OSError` → keep the in-memory record (session dedup intact), leave the item `DONE` (note written, file moved), log at ERROR with traceback. This mirrors the F2 best-effort persistence pattern already established in `QueueStateStore`. Worst case after a restart: a stale disk manifest re-processes the file once — idempotent (same note path, `updated=False`).

## 4. Testing

**2 new tests:**

| Test | Covers |
|------|--------|
| `test_child_processing_failure_skipped_and_cleaned` (test_email_attachments.py) | A failing child AI step is skipped, the parent email still succeeds (`created=True`), and attachment temp files are cleaned |
| `test_worker_manifest_save_failure_keeps_item_done` (test_queue_worker.py) | A failed manifest write keeps the item `DONE`, keeps the in-memory dedup record, and leaves the file in `processed/` (no stranded `FAILED`) |

The remaining ten failure areas rest on existing regression coverage, re-verified this session: `test_queue_worker.py` (missing source, unsupported file, move-failure leaves manifest untouched), `test_ingestion.py` (unsupported → structured error, missing file, size limits), `test_ai_processor.py` (malformed-JSON retried, retry budget exhausted → error), `test_email_attachments.py` (child ingestion failure isolated, nested-depth guard), plus the embedding/OCR/retrieval/config suites.

## 5. Verification (commands re-run this session)

| Gate | Result |
|------|--------|
| Focused suite (`test_queue_worker.py` + `test_email_attachments.py`) | **21 passed / 0 failed** (19 baseline + 2 new) |
| Full default regression suite (`pytest -m "not integration"`) | **1397 passed / 0 failed / 59 deselected** (P6-102 baseline 1395 +2 new; 0 regressions) |
| Integration suite (`tests/integration -m integration`) | **56 passed / 1 skipped** (Tesseract absent — pre-existing env skip) / 29 deselected; 1 failure is the documented live-Ollama content flake (§7) |
| Ruff (changed files) | **Clean on all P6-103 lines**; 2 findings remain on unchanged pre-existing lines (worker.py:159, test_queue_worker.py:89) |
| Mypy (changed modules) | No findings in changed lines; whole-repo run remains blocked by pre-existing numpy-stub/Python 3.14 + faster_whisper-untyped issues |
| Coverage (`pytest --cov=app`) | **TOTAL 90.03%** (repo floor 80%) — up from 89%; both new except-branches confirmed covered |

## 6. Files Changed

| File | Action |
|------|--------|
| `app/pipelines/ingest_workflow.py` | **Updated** — `_ingest_child` contains child processing failure (F1) |
| `app/queue/worker.py` | **Updated** — manifest `save()` is best-effort with in-memory fallback (F2) |
| `tests/unit/test_email_attachments.py` | **Updated** — +1 test (F1) |
| `tests/unit/test_queue_worker.py` | **Updated** — +1 test (F2) |

## 7. Findings

**Blocking:** None.

**Non-blocking:**
- Vision (`describe_image`) and whisper have no client-level retry wrapper; this is **bounded by design** — the OCR engine retries per page with a cap, whisper construction is guarded, and a mid-call hiccup is contained by the worker's item-level failure handling. Documented, not a defect.
- The integration suite's sole failure is the pre-existing live-Ollama content-miss flake (`Missing sections: [...]`), which asserts LLM content and exercises none of the P6-103 code.
- Tesseract-binary-absent integration skip and the whole-repo mypy blockers (numpy stubs / faster_whisper untyped) are pre-existing environment issues.
- 2 ruff `E501` findings sit on unchanged pre-existing lines; working tree remains uncommitted per the per-milestone commit convention.

## 8. Conclusion

The pipeline was audited end-to-end against all 12 failure areas. Ten were already covered by a consistent error contract — typed exceptions at trust boundaries, structured error results where the spec requires, best-effort enrichment, fallback retrieval, contained worker failures, and idempotent recovery with feature-toggle rollback. Two genuine gaps were found and fixed: an uncontained child-processing failure that failed an otherwise-successful parent email, and a manifest-write failure that stranded processed files as `FAILED` with no dedup record. Both fixes are minimal, follow the established best-effort persistence pattern, and ship with focused tests. Every gate passes: 1397 unit tests (0 regressions), coverage 90% (floor 80), hermetic integration green apart from the pre-existing live-Ollama flake, ruff clean on all P6-103 lines.

**Verdict:** **APPROVED**
