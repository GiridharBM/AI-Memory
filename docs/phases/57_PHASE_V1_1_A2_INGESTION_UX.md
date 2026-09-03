# 57 — V1.1-A2 INGESTION UX HARDENING

**Phase:** V1.1-A2  
**Status:** Implemented  
**Date:** 2026-09-01

---

## 1. Objective

Harden the `pam ingest file <source>` CLI ingestion output so that
every outcome — success, duplicate, blocked-secret, unsupported source,
partial index, knowledge-graph failure — is presented with a truthful,
actionable, and distinct panel, and that no secret content, traceback,
or "Ingestion Complete" is shown when the ledger records failure.

---

## 2. Flow Trace (current CLI path for `ingest file`)

```
pam ingest file <path>
  → _run_ingest(source, expected_source_type=None)
    → _load_configured_settings()
    → manifest.hash_for_path(source)           # may raise ValueError → digested=None
    → duplicate check (hash or path)            # skip → panel, return exit 0
    → IngestionWorkflow.create_default(settings)
    → workflow.run(source)
        → DocumentIngestionService.ingest(source)
            → is_secret_bearing → BlockedSourceError
            → _select_ingestor → UnsupportedSourceError
            → ingestor.ingest → IngestionError / success
        → if not succeeded: IngestionWorkflowError(reason, category=...)
    → on exception: _record_failed_ingest → _print_ingest_failure → exit 1
    → on success: add_processed_file → _print_ingest_success → exit 0
      (partial-index: "Ingestion incomplete" panel, exit 1)
      (KG failure: yellow warning panel, exit 0)
```

---

## 3. Outcome Taxonomy (truthful state)

| Outcome | Panel Title | Exit | Ledger Status | Graph |
|---|---|---|---|---|
| **Success** (fully indexed + graph OK) | "Ingestion Complete" | 0 | processed | ✓ |
| **Duplicate** (identical hash or path) | "Ingest skipped (duplicate)" | 0 | skipped_duplicate | ✓ |
| **Retryable failure** (Ollama/AI/OS/workflow) | "Processing failed" | 1 | failed | — |
| **Blocked secret** | "Ingest blocked (security)" | 1 | failed | — |
| **Unsupported file** | "Unsupported source" | 1 | failed | — |
| **Partial index** (note written, not indexed) | "Ingestion incomplete" | 1 | failed | — |
| **KG failure** (note + index OK, graph failed) | "Knowledge graph warning" + success table | 0 | processed | ✗ |
| **Missing file** | (click/typer message) | 2 | — | — |

---

## 4. UX Contract (per outcome)

### 4.1 Success
```
┌────────────────────────── Ingestion Complete ──────────────────────────┐
│ Source      │ <path>                                                   │
│ Source type │ markdown                                                 │
│ Note        │ <title>                                                  │
│ Chunks indexed │ 12                                                   │
│ Indexed        │ yes                                                  │
└───────────────────────────────────────────────────────────────────────┘
```

### 4.2 Duplicate
```
┌──────────────────────── Ingest skipped (duplicate) ──────────────────────────┐
│ This file was already processed successfully (identical content);           │
│ skipping. Existing note, index, and knowledge-graph data for this source   │
│ was left untouched.                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Retryable failure
```
┌────────────────── Processing failed ──────────────┐
│ <reason>. You can retry after resolving the       │
│ underlying issue (e.g. Ollama offline, model      │
│ unavailable, or transient error).                  │
└───────────────────────────────────────────────────┘
```

### 4.4 Blocked secret
```
┌────────────────── Ingest blocked (security) ──────────────────┐
│ Source '/path/.env' is blocked: it appears to be a            │
│ secret-bearing or credential file... The file was not read    │
│ and no contents were indexed.                                 │
└──────────────────────────────────────────────────────────────┘
```

### 4.5 Unsupported source
```
┌─────────────── Unsupported source ───────────────────┐
│ Unsupported source type for 'file.xyz'.              │
│ Ingest a supported file type and try again.          │
└──────────────────────────────────────────────────────┘
```

### 4.6 Partial index failure
```
┌─────────────── Ingestion incomplete ─────────────────────┐
│ The note was written, but the source was not fully       │
│ indexed (index backend down). The ledger records this    │
│ attempt as failed; you can retry ingestion to complete   │
│ the index.                                               │
└──────────────────────────────────────────────────────────┘
```

### 4.7 Knowledge graph warning
Shown in yellow below the success table:
```
┌────────────────── Knowledge graph warning ──────────────────────────────┐
│ The note and chunks were indexed, but the knowledge graph could not     │
│ be updated for this source. Everything else was saved.                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Exit-Code Contract

| Code | Meaning |
|---|---|
| 0 | Success or duplicate skip |
| 1 | Any failure (blocked, unsupported, retryable, partial index) |
| 2 | Missing source path (typer `exists=True` argument validation) |

---

## 6. Truthful-Outcome Rules

- The string "Ingestion Complete" is **never** shown when the ledger entry is
  status `"failed"`.
- Duplicate panels explicitly say "existing data was left untouched".
- Blocked-secret panels name the source path only, never its contents.
- Partial-index shows "Ingestion incomplete" and exit 1 (ledger status
  `"failed"` is recorded).
- KG failure is shown as a yellow warning below the success table (exit 0):
  the note and vectors ARE indexed; only graph enrichment degraded.
- No traceback or exception details appear in the console output for any
  failure category; tracebacks are logged to the log file only.

---

## 7. Implementation Summary

### 7.1 Classification plumbing (minimal supporting app code)

| File | Change |
|---|---|
| `app/domain/documents.py` | Added `category: str = "ingestion"` to `DocumentIngestionError` (default keeps all existing constructors green) |
| `app/infrastructure/ingestion/service.py` | Added `_failure_category(exc)` → "blocked" / "unsupported" / "ingestion"; set on `DocumentIngestionError` |
| `app/pipelines/ingest_workflow.py` | `IngestionWorkflowError.__init__` gains `category: str = "retryable"` kwarg; `run()` passes service category; `KnowledgeEngineResult` gains `graph_succeeded: bool = True`; KG except sets `outcome.graph_succeeded = False`; `IngestionWorkflowResult` gains `graph_succeeded` |

### 7.2 CLI rework (`app/cli/entry.py`)

- `_run_ingest`: wraps `manifest.hash_for_path` in `ValueError` try/except (unsupported ext no longer leaks before workflow)
- Duplicate panel body adds "left untouched" wording (title unchanged)
- Failure path: `except (IngestionWorkflowError, AIProcessingError, OllamaClientError, OSError)` + fallback `except Exception` → `_record_failed_ingest` + `_print_ingest_failure(category, reason)`
- Partial-index (`not fully_indexed`): shows "Ingestion incomplete" red panel, exit 1, instead of old truthfulness-defect path ("Ingestion Complete" + exit 0)
- KG warning: if `graph_succeeded=False` and `chunks_stored>0`, yellow warning panel below success table
- `_print_ingest_success`: gains `source` parameter; new "Source" row
- `_print_ingest_failure`: category-branched panels (blocked/unsupported/generic-retryable)

---

## 8. Tests (`tests/unit/test_cli_ingest_ux.py`)

| # | Test | Validates |
|---|---|---|
| 1 | `test_success_exit_zero_and_truthful_table` | Source row, exit 0, "Ingestion Complete", no "Processing failed" |
| 2 | `test_duplicate_skips_workflow_and_exits_zero` | "Ingest skipped (duplicate)", "untouched", workflow not run |
| 3 | `test_duplicate_records_skipped_duplicate_in_ledger` | Ledger [processed, skipped_duplicate] |
| 4 | `test_blocked_secret_surfaces_truthful_panel` | "Ingest blocked (security)", no "Processing failed" |
| 5 | `test_unsupported_source_surfaces_panel` | "Unsupported source", "supported file type" |
| 6 | `test_generic_failure_keeps_processing_failed_contract` | "Processing failed", exit 1 |
| 7 | `test_generic_failure_records_ledger_and_error_reason` | Ledger status failed, error_reason contains "IngestionWorkflowError" |
| 8 | `test_partial_index_failure_exits_one_and_not_complete` | "Ingestion incomplete", no "Ingestion Complete", exit 1 |
| 9 | `test_partial_index_failure_records_failed_in_ledger` | Ledger failed, indexing_succeeded=False |
| 10 | `test_kg_failure_warns_but_exits_zero` | "Knowledge graph warning", exit 0 |
| 11 | `test_unexpected_exception_has_no_traceback_leak` | "Traceback" NOT in output, exit 1 |
| 12 | `test_missing_source_rejected_by_typer` | exit != 0, "does not exist" |

All 12 tests pass. All 12 are hermetic (temp file + temp manifest, FakeWorkflow, no Ollama, no real vault).

---

## 9. Regression Results

```
python -m pytest tests/unit/ -p no:cacheprovider -q
1635 passed, 1 deselected, 7 failed (67s)
```

- 1623 baseline (pre-A2) + 12 A2 new tests = **1635 passed**
- 7 failures: all pre-existing stale `test_eval_dataset.py` (dataset v3.0 vs test expects v2.0)
- 1 deselected: `test_eval_dataset.py::test_dataset_file_exists` (stale)
- **Zero regressions introduced by A2**

---

## 10. Live Smoke Results

| Smoke | Setup | Expected | Result |
|---|---|---|---|
| A. Success | temp `.md` file, real workflow, temp storage | exit 0, "Ingestion Complete", "Source" row | ✓ PASS |
| B. Duplicate | re-ingest same file | exit 0, "Ingest skipped (duplicate)", "untouched" | ✓ PASS |
| C. Blocked secret | `.env` file | exit 1, "Ingest blocked (security)", no "super-secret" in output | ✓ PASS |
| D. Unsupported | `.xyz` file | exit 1, clean error panel, no traceback | ✓ PASS |

No artifacts left behind.

---

## 11. Retrieval Freeze Verification

```
git diff --name-only HEAD -- \
  app/infrastructure/embeddings.py \
  app/infrastructure/search.py \
  app/infrastructure/bm25.py \
  app/infrastructure/reranker.py \
  app/infrastructure/semantic_chunking.py \
  app/infrastructure/hyde.py \
  eval/dataset.json \
  tests/unit/test_eval_dataset.py
```

**Result:** Only `eval/dataset.json` shows a diff — a **pre-existing** dirty working-tree file (not caused by A2). All 5 frozen infrastructure files: **NO DIFF**. Retrieval flags: `reranker.enabled=false`, `hyde.enabled=false`, `answerability.enabled=false`, `min_cosine=0.25` — **UNCHANGED**.

---

## 12. Corpus Safety

- No vault files touched during smoke tests.
- Blocked-secret test confirms: raw content of `.env` never appears in output.
- No real vector store modified.

---

## 13. Limitations / Known Items

| Item | Impact |
|---|---|
| Missing-file UX uses typer/click `exists=True` → generic error message + exit 2 | Acceptable: consistent with PAM conventions; no custom wording needed |
| KG failure surfaces as a yellow warning, not a hard failure exit 1 | By design: the note and vectors ARE indexed; graph is enrichment-only. User can retry enrichment by re-ingesting. |
| Worker (`queue/worker.py`) already treats partial-index as FAILED for retry — no worker changes needed | Worker behavior was already truthful; A2 only fixed the CLI presentation |

---

## 14. Git Audit

```
$ git log -1 --oneline
97197e2 Fix: manifest status invariant for partial failures

$ git diff --name-only
app/cli/entry.py                    ← A1 (sources) + A2 (UX)
app/domain/documents.py             ← A2
app/infrastructure/ingestion/service.py ← A2
app/pipelines/ingest_workflow.py    ← A2
tests/unit/test_cli_ingest_ux.py    ← A2 (NEW)
56_PHASE_V1_1_A1_PAM_SOURCES.md     ← A1 (NEW)
tests/unit/test_cli_sources.py      ← A1 (NEW)
[13 pre-existing modified tracked files including eval/dataset.json]
```

Nothing staged. Nothing committed. Nothing pushed. Tags `v1.0.0` (→ a4e5b2a) and `v2.0.0` (→ 4f97684) intact.

---

## 15. Verdict

**A2 DELIVERED.** All truthfulness defects in the CLI ingestion UX are resolved:

1. ✅ Partial-index failure: "Ingestion Complete" + exit 0 → "Ingestion incomplete" + exit 1 + ledger failed
2. ✅ Blocked-secret: indistinguishable from generic → distinct "Ingest blocked (security)" panel
3. ✅ Unsupported: indistinguishable → distinct "Unsupported source" panel
4. ✅ Retryable: no guidance → explicit retry hint
5. ✅ Traceback leakage: broad `except Exception` catches all + logs to file only
6. ✅ Secret content: `.env` content never surfaces in output (verified by smoke)
7. ✅ KG failure: invisible → yellow warning panel
8. ✅ Duplicate: says "existing data was left untouched"
9. ✅ Success: shows Source row

**Next step:** A3 (Phase-A title) — awaits explicit user approval.
