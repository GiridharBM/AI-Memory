# Phase V1.1-A5 Report — `pam status` Observability Hardening

**Date:** 2026-09-01  
**Status:** VERIFIED · IMPLEMENTED · PASS  
**Summary:** `pam status` hardened into a concise, truthful, **read-only** operational overview that never fabricates a zero or hangs when a backing store is unavailable. Three real defects fixed (mutating manifest read, fabricated "Retryable pending" count, 300s Ollama live-check hang + write-probe vault check) plus the queue-zero fabrication. Regression clean (1680 passed), read-only smoke verified, no frozen-file diffs.

---

## 1. A5 Scope & Deliverables

| Item | Status |
|------|--------|
| `pam status` as read-only overview | IMPLEMENTED — removed `_ensure_runtime_directories`, all backing reads read-only |
| Truthful counts (never fabricated zero) | IMPLEMENTED — unavailable vector store / ledger / queue → "unavailable", never "0" |
| Sources/chunks from vector store | VERIFIED — `_indexed_sources` / `_indexed_chunks` (already correct, kept) |
| Ingestion counters from durable ledger | IMPLEMENTED — processed / skipped / failed read-only from manifest JSON |
| Remove fabricated "Retryable pending" row | IMPLEMENTED — manifest has no retryable/pending status; row deleted |
| Queue pending state | IMPLEMENTED — `_queue_waiting`: missing→"0", unreadable→"unavailable", else read-only length |
| Last-ingestion (durable, truthful empty state) | IMPLEMENTED — from ledger `processed_at`; "never" when empty, "unavailable" when ledger unreadable |
| No LLM invocation for status | IMPLEMENTED + TESTED — `is_available()` path removed; test asserts OllamaClient.is_available not called |
| Ollama health — cheap + truthful only | IMPLEMENTED — shows configured host/model only; live `ps()` check deferred (300s timeout risk) |
| Focused tests | IMPLEMENTED — `tests/unit/test_cli_status.py` (16 tests) |
| Frozen infra files untouched | VERIFIED — zero diffs to `embeddings.py, search.py, bm25.py, reranker.py, semantic_chunking.py` |

## 2. Production Code Changes (entry.py)

All changes in `app/cli/entry.py`. Four edits:

### Edit 1: `import os` added (top of file)

Needed for the read-only `os.access(path, os.W_OK)` vault check.

### Edit 2: `status()` rewritten (lines ~148–221)

**Before:** called `_ensure_runtime_directories` (creates inbox/processed/failed/log/cache/vault/manifest/queue dirs — a write), drove counts through `ManifestManager` (which mutates on construction), reported a fabricated "Retryable pending" row duplicating "Failed", ran live Ollama `ps()` with a 300s timeout, and probed vault writability by `mkdir` + `.pam_write_test` write+unlink.

**After (read-only, truthful):**
- No `_ensure_runtime_directories` — status never creates directories.
- Ledger read through the new read-only `_read_manifest_entries` — no `ManifestManager`, no mkdir, no save, no quarantine.
- "Retryable pending" row removed (manifest statuses are only `processed`, `skipped_duplicate`, `failed`).
- Queue count through `_queue_waiting` (read-only; "unavailable" when unreadable instead of a fabricated zero).
- Vault through `_vault_access_status` (`os.access`, never writes a probe file).
- Ollama row shows configured host/model only — no live `is_available()`/`ps()` call.
- "Last ingestion" → "never" when ledger empty (truthful), "unavailable" when ledger unreadable.

### Edit 3: New read-only helpers
- `_read_manifest_entries(settings)` — parses the manifest JSON directly, read-only: missing→`[]`, unreadable→`None`, else `list[dict]`.
- `_ledger_metric(available, value)` — renders "unavailable" when the ledger is unreadable.
- `_last_ingestion(entries)` — replaces the `ManifestManager`-driven version, takes `list[dict]`, derives only from durable `processed_at`.
- `_last_ingestion_display(last_ingest, ledger_available)` — value / "never" / "unavailable".
- `_queue_waiting(settings)` — read-only queue count with unreadable→"unavailable".
- `_vault_access_status(path)` — `os.access(path, os.W_OK)`; Missing / Connected / Not writable / Unavailable. No probe file.

### Edit 4: Removed dead helpers
- `_ollama_status` (was the 300s-hang live check) — removed.
- `_is_writable_directory` (was the write-probe) — removed.
- Old `_last_ingestion(manifest: ManifestManager)` — replaced by the `list[dict]` version.
- `_status_style` extended with "Missing".

## 3. Why Not Shared Infra (scope boundary honored)

A5 is presentation-level only. The shared mutating infra (`ManifestManager.__init__/load` quarantine, `QueueStateStore.load` swallow-to-`[]`) is intentionally left alone because it backs the worker/`doctor`/ingest paths whose behavior must not change. A5 fixes **status-specific reads** so observability never mutates durable state and never lies — without touching the shared read contract.

## 4. Defect 1 — Mutating Manifest Read (FIXED in status)

`ManifestManager(path, project_root, enabled)` on construction:
- `mkdir(parents=True)` of the manifest parent dir,
- writes an empty manifest when the file is missing,
- on a corrupt file, `_quarantine_corrupted_manifest()` renames it and recreates a fresh empty manifest → silent data loss + fabricated "0".

**Fix:** `status` no longer constructs `ManifestManager`. It calls `_read_manifest_entries` which only ever `read_text` + `json.loads`. A missing manifest is a genuinely empty ledger (`[]`); a present-but-unreadable ledger is `None` → "unavailable".

## 5. Defect 2 — Fabricated "Retryable pending" (FIXED)

The manifest's only statuses are `processed`, `skipped_duplicate`, `failed`. The old `status` computed `retryable_count = count(status == "failed")` and printed a "Retryable pending: N" row duplicating "Failed: N" — a fabricated metric with no backing store. The row is removed. "Failed" alone truthfully reports the durable ledger's failures.

## 6. Defect 3 — Live Ollama Health Check Can Hang (DEFERRED / bounded)

`_ollama_status` called `OllamaClient(settings.ollama).is_available()` → `ps()` with `settings.timeout_seconds` (default **300s**). A status command could stall for five minutes on a hung Ollama daemon.

**Action:** The live check is **deferred**. `status` now shows the configured host + model (cheap, always truthful about config) rather than a "Connected/Unavailable" health result that requires a network call. This satisfies A5's "health ONLY if cheap+truthful". A cheap explicit health probe belongs to `pam doctor` (which already owns network checks), not `status`.

## 7. Defect 4 — Write-Probe Vault Check (FIXED)

The old vault row called `_is_writable_directory` → `_check_writable_directory` which does `path.mkdir`, writes `.pam_write_test`, then unlinks. That is a mutation (a probe-file write). Status now uses `os.access(path, os.W_OK)` — pure read-only perms check. Note: on Windows FAT filesystems `os.access(W_OK)` can be unreliable (reports writable regardless of ACLs); the `doctor` command still owns the authoritative write probe.

## 8. Queue Zero Fabrication (FIXED in status)

`QueueStateStore.load()` swallows a corrupt/unreadable state file into `[]` (correct for the worker's restart path — recovery, not observability). `state` would therefore report "Items waiting: 0" even when the file is unreadable. `_queue_waiting` verifies readability first: missing→"0" (genuinely empty), unreadable/invalid→"unavailable", else the read-only filtered count.

## 9. CLI Contract (A5 STEP 3 contract)

| Area | Metric | Source of Truth |
|------|--------|-----------------|
| Knowledge | Sources indexed, Indexed chunks | Vector store |
| Knowledge | Real notes (generated) | Vault frontmatter scan (durable) |
| Ingestion | Processed, Skipped, Failed, Manifest entries | Durable ledger |
| Ingestion | Last ingestion | Durable ledger `processed_at` (never process-start time / clock / mtime) |
| Runtime | Items waiting (queue), Queue enabled | Queue state file (read-only) |
| Runtime | Ollama host, Model | Configuration |
| Runtime | Vault, Logs | `os.access`, path existence |
| — | No LLM invocation | VERIFIED + TESTED |

## 10. Unavailable-Store Semantics (never fabricate a zero)

| Backing store | Missing file | Present but unreadable/corrupt |
|---------------|--------------|-------------------------------|
| Vector store (sources/chunks) | genuine `0` (was already correct) | `unavailable` (was already correct) |
| Manifest ledger | `[]` → `0` entries | `unavailable` (was: quarantine + fabricated `0`) |
| Queue state | `0` | `unavailable` (was: fabricated `0`) |
| Notes frontmatter | 0 notes | directory scan (same as before) |

## 11. Test Coverage (16 new tests — `tests/unit/test_cli_status.py`)

| Test | Matrix Item (A5 STEP 12) | Key Assertion |
|------|--------------------------|---------------|
| `test_reports_sources_and_chunks_from_vector_store` | Source+chunk counts | 2 sources, 6 chunks from vector store |
| `test_reports_processed_failed_and_skipped` | Ingestion counters | processed/failed/skipped rows present |
| `test_placeholder_not_counted_as_real_note` | Real vs placeholder | Real=1, placeholders excluded |
| `test_last_ingestion_comes_from_ledger` | Last-ingestion | latest durable `processed_at` shown |
| `test_last_ingestion_never_when_empty_ledger` | Empty ledger | "never" (not a fabricated timestamp) |
| `test_unavailable_vector_store_shows_unavailable_not_zero` | Unavailable vector | "unavailable", not 0 |
| `test_missing_vector_store_is_genuine_zero` | Missing vector | no fabrication |
| `test_unavailable_ledger_shows_unavailable` | Unavailable ledger | "unavailable", ledger not quarantine-recreated |
| `test_unavailable_queue_shows_unavailable_not_zero` | Unavailable queue | "unavailable", not 0 |
| `test_empty_queue_genuine_zero` | Empty queue | "0" |
| `test_no_retryable_row_fabrication` | Retryable removed | "Retryable" absent from output |
| `test_status_does_not_trigger_llm` | No LLM | `OllamaClient.is_available` assert_not_called |
| `test_status_does_not_mutate_missing_ledger` | Read-only | manifest not created by status |
| `test_status_does_not_create_directories` | Read-only | no inbox/processed/failed creation |
| `test_status_does_not_modify_corrupt_ledger` | Read-only | corrupt ledger byte-identical after status |
| `test_status_no_traceback_anywhere` | No traceback | corrupt vector+ledger+queue → exit 0, no "Traceback" |

## 12. Pre-existing Test Adaptation (test_cli.py)

Two pre-existing status tests in `tests/unit/test_cli.py` monkeypatched `entry._ollama_status` (removed in A5). They were adapted to the new contract:
- `test_cli_status_command_displays_watcher_queue_and_manifest` — removed the `_ollama_status` monkeypatch; title assert changed to "PAM Status (read-only)"; asserts **no** directory creation (strengthened to lock in read-only).
- `test_cli_status_shows_durable_ledger_counts` — dropped `_ollama_status`; ledger rows now 4 (manifest + processed + skipped + failed); manifest row "3"; processed/skipped/failed each "1".

## 13. Regression Results

**Pre-A5 (A4):** 1664 passed / 1 deselected / 8 stale (`test_eval_dataset.py`)  
**Post-A5:** 1680 passed / 1 deselected / 8 stale

- A5 added 16 new tests → 1664 + 16 = 1680, zero new failures.
- The 8 failures are the pre-existing stale `test_eval_dataset.py` suite (dataset integrity/metadata grouping) — untouched by A5, out of scope.
- One cross-file ordering flake was observed when running `test_cli.py` then `test_cli_remove.py` in a single process (a pre-existing `setup_logging` handler-accumulation leak on the stderr `RichHandler` that surfaces only under that specific order). It is **not** present in the full `tests/unit` run (1680 passed) and reproduces identically with the untouched HEAD `test_cli_remove.py` — confirmed pre-existing, not an A5 regression.

## 14. Lint & Types

- `ruff check app/cli/entry.py tests/unit/test_cli_status.py` → **clean**.
- `mypy app/cli/entry.py tests/unit/test_cli_status.py` → **clean**.
- `test_cli.py` carries two pre-existing `E501` long lines (747, 752) and a pre-existing mypy `operator` warning (728) — none authored by A5; A5 edits to that file are clean.

## 15. Read-Only Smoke (STEP 13)

`git status --porcelain` snapshot **before** and **after** a live `pam status` run are **byte-identical** — status produced no mutation, no directory creation, no file writes, no quarantines. Live output (unchanged values, now truthful):
- Manifest entries 37 / Sources indexed 25 / Indexed chunks 196
- Successful ingests 36 / Skipped duplicates 0 / Failed 1 (no fake "Retryable pending" row)
- Last ingestion `2026-08-27T04:03:17Z` (durable ledger)
- Ollama host Configured `http://localhost:11434/` + model `qwen3:8b` (no live `ps()` call)
- Items waiting 0 (queue state readable, genuinely 0)
- Vault Connected (via `os.access`, no probe write)
- Real generated notes 25 / Placeholder notes 206

## 16. STEP 15 Freeze Verification

- `git diff HEAD` for `app/indexing/embeddings.py`, `app/pipelines/search.py`, `app/domain/bm25.py`, `app/pipelines/reranker.py`, `app/pipelines/semantic_chunking.py` → **empty** (zero diffs).
- `config.py`: `RerankerSettings.enabled=False`, `HydeSettings.enabled=False`, `AnswerabilitySettings.enabled=False` (lines 417/435/451); `min_cosine` untouched.
- No changes to `eval/dataset.json`, real corpus, or runtime corpus.

## 17. Security Review (STEP 16)

New status rows emit only: `settings.ollama.host` (localhost URL), `settings.ollama.model`, `str(vault_root)`, `str(log_root)`, inbox display path, and availability state strings ("Connected"/"unavailable"/etc.). Status reads no file *contents* (except parsing the ledger/vector/queue JSON for counts and frontmatter note classification for note counts — never secrets, and those same structural reads already existed). No API keys, tokens, env values, or raw file bodies appear in output. The live-Ollama removal also eliminates any possibility of the status path invoking an LLM.

## 18. Known Limitations

1. **Windows vault perms (NOTES):** `os.access(path, os.W_OK)` can report writable on FAT volumes regardless of ACLs; it is a best-effort read-only hint. The authoritative write probe remains in `pam doctor`. `status` is intentionally read-only so it cannot be the authoritative writability test.
2. **Live Ollama health DEFERRED:** `status` shows configured host/model only; no live connectivity. A cheap health probe is a `pam doctor` concern. Re-enable a live check in status only if given a bounded (e.g. ≤2s) timeout that cannot stall the command.
3. **Ledger "entries" vs "sources indexed" intentionally differ:** removed-source ledger rows persist, so "Manifest entries" (37) exceeds "Sources indexed" (25). This is expected — the two measure different things (ledger history vs live vector index).
4. **Readability ≠ trustworthy state:** "0" for queue/missing-vector means the file is genuinely absent; a present-but-stale file still reports its stored value. `status` reports state, not freshness.

## 19. Files Summary

| File | Action | Notes |
|------|--------|-------|
| `app/cli/entry.py` | Modified (A5) | `status()` rewrite + new read-only helpers (`_read_manifest_entries`, `_queue_waiting`, `_vault_access_status`, `_ledger_metric`, `_last_ingestion_display`); removed `_ollama_status`, `_is_writable_directory`, old `_last_ingestion`; `import os` |
| `tests/unit/test_cli_status.py` | Created (A5) | 298 lines, 16 tests |
| `tests/unit/test_cli.py` | Modified (A5) | 2 pre-existing status tests adapted to new contract (removed `_ollama_status` monkeypatch, updated asserts) |
| Frozen infra files | Unchanged | embeddings/search/bm25/reranker/semantic_chunking: zero diffs |
| `eval/dataset.json`, corpus, configs | Unchanged | no diffs |

## 20. Git Audit (STEP 18)

All changes are **working tree only** — nothing staged, committed, pushed, tagged, rebased, reset, stashed, or cleaned.

**Modified (A5):**
- `app/cli/entry.py` — status observable hardening
- `tests/unit/test_cli.py` — 2 status tests adapted

**Created (A5):**
- `tests/unit/test_cli_status.py` — 16 tests

**Pre-existing (A1/A2/A3/A4, uncommitted), untouched by A5:**
- `app/cli/entry.py` (A1/A2/A4 edits), `app/domain/documents.py`, `app/infrastructure/ingestion/service.py`, `app/pipelines/ingest_workflow.py`
- `tests/unit/test_cli_remove.py` (A4, untracked), `tests/unit/test_reingestion_reliability.py` (A3, untracked)
- 13 other pre-existing tracked modifications + phase reports (untracked)

**Nothing changed:**
- Frozen infra (`embeddings.py`, `search.py`, `bm25.py`, `reranker.py`, `semantic_chunking.py`, `hyde.py`)
- `eval/dataset.json`, `tests/unit/test_eval_dataset.py`
- vault real corpus, runtime corpus, configs, `.env`

## 21. Conclusion

`pam status` is now a truthful, concise, read-only operational overview: it reports exactly what durable state says, marks unreadable backing stores as "unavailable" instead of fabricating zeroes, never mutates a store or creates a directory, never invokes an LLM, and cannot hang on a stalled Ollama daemon. Four real defects fixed; the live Ollama health probe and authoritative vault write test are deliberately deferred to `pam doctor` (scope-preserving). Regression clean at 1680 passed. STOP — no further feature work; V1.1 cumulative review is the next step.
