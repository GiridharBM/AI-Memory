# Phase 6A — Application Architecture & Interface (CLI-First) Substrate

**Status:** IMPLEMENTATION / VALIDATION — the approved Phase 6A application-layer substrate is implemented and validated. Retrieval state untouched and re-verified. No commits; no pushes. STOP after this report for the next approval.
**Date:** 2026-08-28
**Head input gates:** report 34 (Phase 6 discovery, §16 roadmap, 6A exit objective: *A3 A4 A5 A7 substrate in place; A6 verified*); frozen retrieval V1 (reports 30/33); user-approved A–F scope from the 6A plan.

---

## 1. Objective

Convert the three highest-value V1 MUSTs from report 34 into application-layer substrate **without touching retrieval**:

1. **A4 — truthful `pam status`**: a durable processing ledger backing real counters (no more runtime-reset 0s).
2. **A3 — no silent loss**: durable failed/duplicate outcomes, retryable failure semantics, generic `pam ingest <path>` closed through the manifest.
3. **A7 — QA generation guard**: a QA-scoped timeout replacing the 3600 s Ollama default for the answer call.
4. Error taxonomy with clean separations (ingestion vs embedding/indexing vs duplicate vs timeout vs unavailable) — substrate for A5.

**Constraint honored (frozen retrieval):** nothing below modifies chunking, embeddings, BM25/RRF, the reranker/HyDE/answerability enablement, `VectorStore`/`SearchService`, `eval/dataset.json`, or any frozen artifact. Retrieval files were verified unchanged (`git diff` classification, §12).

## 2. Frozen retrieval state (given, unchanged — re-verified this phase)

| Item | Value | Verified this phase |
|---|---|---|
| HEAD | `9f282b4` (frozen) | unchanged in working tree (retrieval files untouched) |
| Dataset | `eval/dataset.json` v3.0 — 199 queries (157 pos / 42 neg, q001–q202) | pre-existing uncommitted state untouched |
| Corpus | 24 sources / 195 chunks, nomic-embed-text 768-dim | untouched |
| Config | top_k=5, min_cosine=0.45, BM25 k1=1.5/b=0.75, RRF k=60; reranker/hyde/answerability all `false` | unchanged |
| Baseline | Hit@1 0.841, Hit@5 0.924, MRR 0.877, FPR 0.857, FNR 0.000, p95 47.1 ms | not re-run (retrieval not re-opened) |

**Application-layer reading of the frozen world (from report 34):** FPR 0.857 means evidence must be *transparent*, failures must be *already-seen-proofed* (durable), and nothing may pretend a runtime counter is a real number. Every Phase 6A design decision below follows from that.

## 3. Durable processing ledger (IMPLEMENTED)

**File:** `data/manifests/processed_files.json` (existing manifest path; format extended, backward compatible).

**Schema per entry (`app/infrastructure/state/models.py`, `ManifestEntry`):**

- Existing keys preserved: `sha256`, `original_filename`, `original_path`, `processed_at`, `extension`, `generated_note`, `metadata`.
- **New:** `status` ∈ `processed | failed | skipped_duplicate`; `error_reason` (str, present on failures); `chunks_stored`; `embedding_succeeded`; `indexing_succeeded`. `to_dict` omits `None` optional fields (older readers and the on-disk format stay valid; a `chunks_stored=0` survives, so "engine ran, 0 chunks" is distinguishable from "no engine run"). `from_dict` coerces the new fields for older ledger files.

**Manager (`app/infrastructure/state/manifest.py`):**

- `SUCCESSFUL_STATUSES = {processed, skipped_duplicate}` + `is_successful_status`.
- `add_processed_file(... status=…)` gains the outcome kwargs; new `add_failed_file(path, sha256, extension, error_reason)` shorthand.
- **`contains_successful_hash(sha256)`** — dedup now counts only successful outcomes. A `failed` entry does **not** block a re-drop: the file is retried. `contains_hash` keeps old semantics (any entry) for backward compatibility.
- `count()` = number of ledger entries (all outcomes) — used by `status` for "Manifest entries"; the truthful per-status numbers come from `list_entries()` filtering.

**Semantic decision (locked):** the ledger is an *attempt* ledger — every ingest attempt reaches exactly one durable status (processed / skipped_duplicate / failed). This is the A3 "exactly one durable outcome" substrate.

## 4. Knowledge-engine outcome surfacing (IMPLEMENTED)

**File:** `app/pipelines/ingest_workflow.py`.

A processed note can still fail below the note-write layer: embeddings may be partial, the vector store may be unwritable, the embedding backend may throw mid-run — and fragmentation (transcription, OCR) and partial-write paths can succeed silently with a `note` that was never embedded. `IngestionWorkflowResult` now carries the knowledge-engine verdict explicitly:

- **`KnowledgeEngineResult`** (`chunks_created`, `chunks_stored`, `embedding_succeeded`, `indexing_succeeded`, `error`): `succeeded` is vacuously `True` when `chunks_created == 0` (a legitimate 0-chunk short document is NOT a failure) and otherwise `embedding_succeeded and indexing_succeeded`.
- `IngestionWorkflowResult` adds `embedding_succeeded`, `indexing_succeeded`, `engine_error` (defaults `True`/`None` — existing fakes and callers keep working). The engine's 3-tuple return signature is preserved for test compatibility; the outcome is also exposed via `self._last_knowledge_result`.
- `_run_knowledge_engine` now runs in two try blocks: (1) chunk → embed → store with outcome tracking (`embedding_succeeded = all(emb.embedding ...)`, `indexing_succeeded = chunks_stored == len(chunks)`, error set on exception or partial outcome); (2) knowledge-graph build + cross-document links remain warning-only, unchanged behavior — except it now runs even when embedding fails.
- **Documented divergence (improvement):** graph persistence survives an embedding failure, so a partially-indexed document still contributes structural knowledge. Cross-links are gated on `chunks_created and outcome.succeeded` (short-circuit equivalent of the previous embedding check).

## 5. Worker retry / skip / failure semantics (IMPLEMENTED)

**File:** `app/queue/worker.py`.

| Inbox event | Outcome | Ledger entry |
|---|---|---|
| New file → workflow succeeded | move to `data/processed/`, `DONE` | `processed` + `chunks_stored`/`embedding_succeeded`/`indexing_succeeded` |
| Re-drop identical content (hash already in ledger as processed/skipped) | skip, `DONE`, file untouched | `skipped_duplicate` |
| Workflow raised (`IngestionWorkflowError`/`AIProcessingError`/`OllamaClientError`/`OSError`) | move to `data/failed/`, `FAILED` | `failed`, `error_reason = "<ExceptionClassName>: <msg>"` |
| Note written but **not embedded/indexed** (`embedding_succeeded=False` or `indexing_succeeded=False`) | move to `data/failed/`, `FAILED` | `failed`, `error_reason` prefixed `EMBEDDING/INDEXING FAILURE: <engine_error>` |
| Unexpected exception / unsupported / missing input on the drive | existing `_fail_item` behavior | none — the relocated file in `data/failed/` is the audit trail (documented limitation, §11) |

Dedup now uses `contains_successful_hash`, so a crashed-mid-embedding file (recorded `failed`) retries on the next drop instead of being silently skipped. A new OSError-tolerant `_try_save_manifest(item)` keeps the in-memory ledger authoritative if the disk write fails (existing `test_worker_manifest_save_failure_keeps_item_done` still passes).

## 6. CLI: truthful status + generic ingest (IMPLEMENTED)

**Files:** `app/cli/entry.py` (+ `config/default.yaml`, `app/core/config.py`).

**`pam status`** now reports real numbers:
- Rows: Watcher, Inbox, Queue, Items waiting, Manifest entries, **Processed files / Skipped duplicates / Failed** (all durable-ledger backed), **Indexed chunks** (from the persisted vector store), Ollama, Model, Vault, Generated notes, Logs.
- The fabricated "Processed today"/"Failed today" rows (runtime `RuntimeStats` counters that reset on restart) are removed. Nothing in the table pretends to be a number it is not.
- `Indexed chunks` reads `data/manifests/vector_store.json` (`{"entries": [...]}`) — `"0"` when absent, the real count when readable, `"unavailable"` on a read/parse failure. Presentation-only; retrieval state is never modified.

**`pam ingest file <path>`** — the generic, auto-detect ingest command (any supported extension → `DocumentIngestionService`), matching the watcher's own coverage. `pdf`/`markdown`/`txt`/`github <url>`/`youtube <url>` remain. The direct path now:
- routes **through the manifest** (SHA-256 dedup for files, path dedup for URLs) — closing the report-34 "direct path bypasses dedup" gap (risk 5, §17);
- records `processed` (with outcome fields) on success, `failed` (with reason) on any caught pipeline exception, and `skipped_duplicate` when dedup fires;
- prints "Ingest skipped (duplicate)" instead of silently re-running; failures exit 1 with a clean "Processing failed" panel.

**New config:** `qa.timeout_seconds: 120` (§7).

## 7. QA generation timeout guard (IMPLEMENTED)

**Files:** `app/core/config.py` (`QaSettings`), `config/default.yaml`, `app/application/qa_workflow.py`.

Ollama's configured timeout is **3600 s** (report 34, risk 2): a hung QA generation can stall `ask` and, in watch mode, the single worker thread for over an hour (retries ×3 ⇒ worse). The application layer now bounds **only the QA generation call**:

- `QaSettings.timeout_seconds` (default 120, `ge=1`), set in `config/default.yaml` as `qa.timeout_seconds: 120`.
- `QAWorkflow.create_default` builds the **generation** `OllamaClient` from `settings.ollama` overridden with `timeout_seconds=settings.qa.timeout_seconds`; the **answerability gate** client (frozen-inactive in V1) keeps the default Ollama timeout so the gate is never throttled by the generation bound.
- `ask` catches `OllamaTimeoutError` first → `QATimeoutError` ("…request timed out after the configured QA timeout (qa.timeout_seconds)."); other `OllamaClientError` → the existing QAError "Ollama server is unavailable…". The timeout-and-unavailable split is A7 + the error-vs-abstention separation substrate (§8).

## 8. Error taxonomy (IMPLEMENTED)

Failure kinds are now distinguishable end-to-end (CLI panels, CLI exit codes, worker outcome, and durable `error_reason`):

| Kind | Where it surfaces | Ledger `status` / reason |
|---|---|---|
| INGESTION FAILURE (pipeline exception: ingest, analyze, write) | CLI red panel + exit 1; worker → `data/failed/` | `failed` / `"<ExceptionClassName>: <msg>"` |
| EMBEDDING / INDEXING FAILURE (note written, store not updated) | CLI exit 1; worker → `data/failed/` | `failed` / `"EMBEDDING/INDEXING FAILURE: <engine_error>"` |
| DUPLICATE / SKIPPED (successful hash or URL already recorded) | "Ingest skipped (duplicate)" / worker log | `skipped_duplicate` |
| LLM TIMEOUT (QA generation) | `QATimeoutError` panel | n/a (no ingest ledguer write) |
| LLM UNAVAILABLE (Ollama down during ingest/QA) | "Failed to connect to Ollama…" panel; exit 1 | `failed` |

No user-facing stack traces: CLI panels show the message; the log file keeps the full traceback (`logger.exception`), preserving the dev tier separately from the user face (report 34 §13 gap 4).

## 9. Tests added (VALIDATED)

**18 new tests + 3 updated for the intentional semantic change** (dirs must run with the phase's Windows `--basetemp` workaround; see §12).

| Test file | Content | Result |
|---|---|---|
| `tests/unit/test_manifest.py` (+4) | `contains_successful_hash` ignores failed entries; outcome fields round-trip (`chunks_stored=0` and `False` flags survive); `add_failed_file` records a durable failure; skipped-duplicate records a ledger entry | pass |
| `tests/unit/test_queue_worker.py` (+3) | failed ledger entry → re-drop retries (workflow runs again); duplicate-`processed` re-drop → DONE + `skipped_duplicate` entry, workflow NOT run; note-written-but-not-indexed → FAILED + moved to `data/failed/` + `EMBEDDING/INDEXING FAILURE` reason + not dedup-blocking | pass |
| `tests/unit/test_ingest_engine_outcome.py` (new, +4) | all-stored → `succeeded`; partial embedding → flags `False` + `"embedding/indexing incomplete"` + only the embedded chunk stored; embedding exception → flags `False` + error; zero chunks → vacuously successful | pass |
| `tests/unit/test_qa_timeout.py` (new, +4) | `QaSettings` default 120; `OllamaTimeoutError` → `QATimeoutError` while `OllamaClientError` → distinct QAError; `QATimeoutError <: QAError`; `create_default` builds generation client at 120 s / gate client at the Ollama default | pass |
| `tests/unit/test_cli.py` (+3, 1 modified) | generic `ingest file` route + dedup + ledger (`processed`→`skipped_duplicate`), workflow not re-run; failed ingest records `failed` entry and exits 1; `status` shows durable ledger counts + indexed-chunk count from a seeded store; existing markdown test now points the ledger at tmp (it would otherwise write the real default ledger) | pass |
| `tests/unit/test_duplicate_detection.py` (updated) | duplicate skip now asserts the durable `skipped_duplicate` ledger entry (count 2) instead of count 1 — the Phase 6A semantic change | pass |
| `tests/integration/test_queue_worker_pipeline.py` (updated) | same intent in the integration path | pass |

## 10. Full-suite and coverage verification (VALIDATED)

| Metric | Baseline (report 34 plan) | After Phase 6A | Verdict |
|---|---|---|---|
| Full suite | 1508 passed / 7 failed / 57 deselected | **1526 passed / 7 failed / 57 deselected** | +18 new tests; **identical failure set** (only the 7 pre-existing `test_eval_dataset.py` stale assertions, §11) |
| Coverage | 88.90% (≥ 80% required) | **89.13%** | met, improved |

The 7 failures are strictly the pre-existing ones — `tests/unit/test_eval_dataset.py` asserts the v2.0 dataset contract (160 queries, phase "3D", version "2.0") while the working-tree `eval/dataset.json` is the v3.0 freeze (199/157/42). Both artifacts are pre-existing, uncommitted, and **intentionally untouched** (documented limitation, §11).

## 11. Offline CLI smoke test (VALIDATED)

A scripted offline smoke (`C:\Users\girid\AppData\Local\Temp\opencode\p6a_smoke.py`, temp working set via `PAM_*` env overrides, Ollama pointed at a dead host so failure is deterministic) verified, against a throwaway temp tree — no real vault/data/corpus touched:

1. `pam status` on an empty tree → truthful zeroed durable rows ("Processed files 0 / Skipped duplicates 0 / Failed 0 / Indexed chunks 0"), "Ollama Unavailable".
2. `pam ingest file <doc>` with Ollama down → clean "Processing failed" panel, exit 1, **durable `failed` ledger entry written** with an `error_reason`.
3. Re-drop of the same file → **retried** (failed entries are dedup-exempt), second `failed` entry written.
4. `pam status` after the failures → "Failed 2 │ Durable ledger" and "Manifest entries 2", matching the file on disk.
5. `pam status` against the running local Ollama (first smoke run) displayed the connected store state and real vectors — read-only.

This exercises A3 (no silent loss on the direct path), A4 (status matches the persisted ledger), and the A7-adjacent failure separation, all without a single retrieval-file modification.

## 12. Known limitations and deferred items (DEFERRED)

Introduced-here limitations (honest labels):

1. **`_fail_item` worker paths** (unexpected exception, unsupported extension, missing input file) still record **no ledger entry** — the relocated file in `data/failed/` is the audit trail. Full durability for those three cases is deferred (worker-run outcomes were the 6A scope).
2. **Graph persistence now runs even when embedding fails** — documented as an intentional improvement (§4), divergence from the previous sk-branch behavior.
3. **`status` "Indexed chunks" reads the store JSON directly** — a durable count with no retrieval-code change; if the store file is unreadable it reports `unavailable`, never a fabricated number.
4. **QA timeout** bounds generation only; the (frozen-inactive) answerability gate inherits the 3600 s Ollama timeout by design.

Pre-existing, deliberately untouched:

5. **7 stale `test_eval_dataset.py` failures** against the v3.0 working-tree dataset (subset of report 34's A8-adjacent debt). Fixing them is a pool-side (5B-era) change and out of 6A scope.
6. **`eval/dataset.json` v3.0 is pre-existing uncommitted** working-tree state. Untouched; the retrieval freeze protocol will settle it at the 6G/6H freeze point.
7. **`RuntimeStats` in-memory counters still exist** but are no longer shown in `status`; they remain true runtime-only signals for the watch loop.

**Phase-34 roadmap deferred (not 6A scope):** evidence-preserving abstention rendering and `[SOURCE N]`/note-link/`--location` source UX (**6B/6C**), per-condition error map + watch-path ergonomics (**6D/6E**), e2e watch/crash-recovery scripted flows (**6F**), stale-chunk invalidation on re-ingest, single-watcher parallelism, and the web UI/REST decision (all V1.1).

## 13. Coherence with report 34 and next steps

**6A exit objective mapping ("A3 A4 A5 A7 substrate in place; A6 verified"):**

| Report-34 criterion | 6A delivery | Status |
|---|---|---|
| A4 — truthful status | durable ledger rows (processed/skipped/failed), indexed-chunk count, fabricated rows removed; unit + smoke verified | **substrate delivered** |
| A3 — no silent loss | attempt-ledger for every direct-path and worker-run outcome; retryable failures; `skipped_duplicate` recorded | **substrate delivered** (3 `_fail_item` corners deferred, §12.1) |
| A7 — QA latency guard | `qa.timeout_seconds=120` bounds generation; timeout/error surfaced, never swallowed; timeout-vs-unavailable split tested | **delivered + tested** |
| A5 — failure clarity | error taxonomy (§8) separates ingestion/embedding/indexing/duplicate/timeout/unavailable with consistent exit codes and clean panels | **substantially delivered** (full per-condition message map = 6E) |
| A6 — privacy invariant | verified in spirit: all smoke paths offline via temp overrides; no retrieval/network change | **unchanged, still holds** |
| A1/A2 — citation + abstention UX | presentation layer, explicitly out of 6A | **6B/6C** |

**Next steps (order per report 34 §16):** 6B (QA output contract + verifiable sources + note-link + `--location`), 6C (evidence-preserving abstention + error/abstention separation rendering), then 6D/6E/6F toward the A1–A5 test coverage, 6G e2e validation, and 6H application freeze — all on this substrate, all with retrieval still frozen.

---

*Truth preamble: every test count, coverage figure, row, and smoke assertion in this report was produced this phase against the working tree described; the retrieval baseline numbers are quoted frozen values from reports 30/33 and were not re-run (retrieval not re-opened). No commits, no pushes. STOP after this report — Phase 6B implementation awaits explicit approval.*