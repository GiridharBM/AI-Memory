# Phase 6G Report — Application-Layer Production Readiness Discovery

**Date:** 2026-08-31
**HEAD:** `9f282b41b6c558b0dbea857c95e24beb3ff63f9a` (confirmed unchanged, frozen)
**Mode:** DISCOVERY ONLY — no production code modified, no retrieval/embeddings/chunking/BM25/RRF/reranker/HyDE/answerability changes, no dataset/corpus changes, no config changes, no commits.

**Validated runtime state (this inspection):**
- Real corpus: **195 chunks / 24 distinct sources** (`data/manifests/vector_store.json`)
- `eval/dataset.json` v3.0: **199 queries** (157 positive, 42 negative)
- Manifest ledger: 37 `processed`, 0 `skipped_duplicate`, 0 `failed`
- Queue: 0 pending items
- Notes in vault: **231 total** — 25 carry a `source` frontmatter, **206 are auto-generated placeholders** (`source_type: placeholder`)
- `qa.timeout_seconds = 120` (true wall-clock deadline active, Phase 6F-A)
- `OLLAMA_CONTEXT_LENGTH = 8192` (permanent host env var, Phase 6F-D); `qwen3:8b` at 8192 context, 5.2 GB, 100% GPU
- `reranker.enabled=false`, `hyde.enabled=false`, `answerability.enabled=false`, `min_cosine=0.45`

---

## 1. Current Application Surface (STEP 1)

Commands exposed by the CLI (`app/cli/entry.py`):

| Command | Entry point | What a user can do |
|---|---|---|
| `pam ingest file <path>` | entry.py:95 | Generic ingest, type auto-detected |
| `pam ingest pdf/markdown/txt <path>` | entry.py:107/114/121 | Typed local-file ingest |
| `pam ingest github <url>` | entry.py:128 | GitHub README ingest (network) |
| `pam ingest youtube <url>` | entry.py:135 | YouTube transcript ingest (network) |
| `pam watch` | entry.py:372 | Foreground watchdog + queue worker (Ctrl+C to stop) |
| `pam ask <question>` | entry.py:447 | RAG answer with validated citations |
| `pam search <query>` | entry.py:395 | Hybrid retrieval preview |
| `pam status` | entry.py:142 | Vault/ledger/queue/index/Ollama status table |
| `pam doctor` | entry.py:198 | Dependency/path/Ollama/model diagnostics |
| `pam config [--json]` | entry.py:323 | Resolved configuration display |

Core pipeline (verified by reading the code):
- **Ingestion:** `DocumentIngestionService` (21 adapters: pdf, markdown, text, code, notebook, csv, spreadsheet, images, audio, video, email w/ attachments, databases, archives, docx/pptx/epub, GitHub, YouTube…) → `IngestionWorkflow` (classify → route → OCR/vision/audio → AI analysis → enrich structure/entities/relationships/graph/tables/images/code → chunk → embed → vector store → KG → write Obsidian note with managed block).
- **Retrieval:** `SearchService` → `HybridSearch` (dense cosine + BM25 → RRF k=60), embedder degrade-to-lexical fallback; `AbstentionGate` min_cosine filtering; QA generation via `OllamaClient.generate_text` bound by `qa.timeout_seconds` wall-clock deadline.
- **Ledger:** `ManifestManager` (JSON, crash-safe tmp+os.replace, corruption quarantine). Queue state persisted for crash recovery.
- **Logging:** rich console→stderr (never pollutes stdout), rotating `application.log` + `errors.log`/`watcher.log`/`processing.log` component files, optional JSON format.

## 2. User Journeys (STEP 2)

| # | Journey | Result | Friction / risk observed |
|---|---|---|---|
| A | First-time setup | `pam doctor` surfaces config/deps/Ollama; dirs auto-created; vault `index/overview/log` initialized on first note | No one-command bootstrap (works, but multi-step) |
| B | Add a document | `pam ingest file x.pdf` or drop into inbox; note written, chunks indexed, ledger "processed" | ✓ clean; success table reports `Indexed: yes` |
| C | Re-add existing file | Hash dedup → "Ingest skipped (duplicate)", `skipped_duplicate` ledger entry | ✓ (entry.py:639, worker.py:158) |
| D | Modify an existing document | New hash → re-processed; vault note **updated** (managed block merge) | ⚠️ **stale chunks/KG nodes not removed** (see STEP 3) |
| E | Ingestion failure | Panel "Processing failed", exit 1, ledger `failed` + reason; watcher moves file to `data/failed/` | ✓ retryable (failed hashes excluded from dedup) |
| F | Ollama unavailable | `OllamaClientError` → "Ask failed" panel / ingest failure with reason | ✓ clear error text; exit 1 |
| G | Ask a question | `pam ask` → answer panel + verified-sources table | ✓ |
| H | Question with insufficient evidence | Abstention panel ("Insufficient evidence") + gate reason | ✓ never invokes LLM |
| I | Question producing citations | "[ANSWERED — SOURCES VERIFIED]" + numbered source table | ✓ invalid numbers reported, never remapped |
| J | Long-running QA request | 120s wall-clock deadline; at 8192 max measured 81.6s | ✓ no timeout tripped since 6F-A (0/0 in 6F-C) |
| K | Restart PAM | Queue state restored, manifest re-loaded | ✓ (watcher `restore_into`, queue_state.json) |
| L | Restart Ollama | Next command fails cleanly then recovers; `qa` client reconnects | ✓ |
| M | Check status | Table shows chunks/ledger/queue/Ollama | ⚠️ **notes count is inflated (206 placeholders)**, no last-ingestion, no QA health line |

**Highest-friction findings:** (D) modify-and-re-ingest leaves stale retrieval/KG data; (M) status does not truthfully convey "how much real knowledge exists".

## 3. Ingestion Reliability (STEP 3)

- **Deduplication** — PASS for local files: SHA-256 streaming hash; `contains_successful_hash` excludes `failed` so re-drops retry (manifest.py:93). URL sources (github/youtube) are **not hashed** (`hash_for_path` is Path-only, entry.py:637): dedup for URLs falls back to `contains_path` on a mangled `Path(URL)` (entry.py:654) → same URL re-ingest is skipped, but **server-side content changes are never detected** (URL content cannot be content-addressed). PARTIAL.
- **Retry behavior** — PASS: retries live in `OllamaClient` (3 retries, backoff) and `EmbeddingService` (2 retries); a failed item is ledgered `failed` and retried on next drop (both CLI and watcher paths).
- **Failed-item handling** — PASS: watcher moves to `data/failed/` with reason; ledger keeps `error_reason`; CLI exits 1.
- **Stale manifests** — PASS: corrupted manifest quarantined + recreated (manifest.py:54–65). Corrupted vector store loads empty silently (vector_store.py:163–172) — **status then shows 0 chunks with no warning** (PARTIAL).
- **Re-ingestion / source replacement** — **PARTIAL/FAIL.** Chunk ids are `{source}::chunk_{index}` (semantic_chunking.py:262). `VectorStore` is an id-keyed dict with **no source-scoped removal** (vector_store.py:68–91). Re-ingesting a modified file:
  - same chunk count → chunks silently overwritten in place (acceptable), but
  - smaller chunk count → **old high-index chunks remain as orphans and stay retrievable**, and
  - the knowledge graph merge (`merge_graphs`, ingest_workflow.py:1002–1010) **keeps stale nodes** for removed content.
  - Ledger accumulates a second `processed` row for the same source (honest, but status "Processed files 37" vs 24 unique sources reads misleading).
- **Partial failures** — PASS with note: note written but embedding/indexing failed → ledger `failed` + `Indexed: no` + retryable; tested by `test_ingest_engine_outcome.py`.
- **Knowledge-graph / vector-store / BM25 consistency** — BM25 rebuild is version-tracked (search.py:160–174) ✓; but no repair/reconcile tool exists for the orphan/stale-data case (DEFERRED).

## 4. QA Reliability (STEP 4)

Measured baseline (Phase 6F-C, 35-query bounded sample at 8192): 35/35 answered, **0 failed, 0 timeouts**, 88.6% ≥1 valid citation, 11.4% zero-citation (all insufficiency soft-abstentions), **0 invalid citations**, mean latency 33.4s (p95 64.8s, max 81.6s < 120s).

| Failure class | Handling | Residual gap |
|---|---|---|
| ANSWERED | Verbatum answer + validated `[SOURCE N]` citations | Factual correctness never judge-validated (DEFERRED) |
| ABSTAINED | Fixed message, LLM not invoked, gate reason surfaced | none |
| FAILED | `QAError`/`QATimeoutError`/`QAEmptyAnswerError` hierarchy; never returned as an answer | Timeout leaves the worker thread generating server-side (pool `shutdown(wait=False)`, qa_workflow.py:597) — a subsequent `pam ask` can stack a second generation against the same model (sequencing risk, matches 6D host lesson) |
| Empty answers | `QAEmptyAnswerError` (Phase 6C) | none |
| Malformed output | Invalid citations reported, never remapped | none |
| Duplicate citations | Counted + benign (list-format), reported in CLI | none |
| Insufficiency language | Measurement-only heuristic; never influences outcome | none |

## 5. Status / Observability (STEP 5)

`pam status` truthfully reports: Ollama connection/`model`, `indexed chunks` (reads vector_store.json, entry.py:793), manifest `processed/skipped/failed` counts, queue items, vault writability. **Misleading or missing:**
- **"Generated notes"** = literal `*.md` count in `vault/Notes` (entry.py:153) → **231, of which 206 are auto-created placeholder stubs** (`source_type: placeholder`). Massively overstates real content. FAIL on truthfulness.
- **"Processed files 37"** counts ledger *attempts*, not *unique sources* (24). Confusing, not wrong.
- No **QA health / retrieval-health** line (only generic "Ollama Connected").
- No **last ingestion timestamp**, no per-source breakdown, no per-source failure drill-down.
- **Watcher row is hardcoded "Configured"** (entry.py:178) — never reflects the live `pam watch` process (which is a separate foreground process; `pam status` cannot see it). Acceptable given the architecture, but the label overpromises.
- No display of the **actual applied context length** (`ollama ps` 8192) vs config model.

## 6. Data Safety (STEP 6)

- **Delete/overwrite knowledge:** managed-block note merge preserves user-written content (wiki_manager.py:260–278) — PASS.
- **Duplicate knowledge:** re-ingest-after-modify can duplicate/orphan chunks (STEP 3) — PARTIAL.
- **Orphan chunks / stale manifest entries:** orphans possible by mechanism (no source-scoped removal), no stale manifest path (failed excluded from dedup) — PARTIAL.
- **Sensitive content in logs:** user **questions** are logged verbatim (`qa_workflow.py:462-464`, harness rows), full **absolute source paths** logged; **document text is never logged**. Ingest failure writes exception text into `error_reason` (may embed a source snippet from parsing errors — low risk, not observed). PARTIAL (local-only).
- **Network:** only localhost Ollama (default `http://localhost:11434`) + explicit `pam ingest github|youtube` (urllib with 15s timeout, github_readme_ingestor.py:122). Metadata extractors perform **no URL fetching**. No telemetry/external calls. PASS.
- **Credentials/secrets:** `pam ingest file` on `.env`/`config.yaml`/`*.json`/`.db` is accepted by `ConfigIngestor`/`DatabaseIngestor`/generic adapters (service.py registry) → **API keys/tokens can be accidentally indexed and become searchable**. No secret-aware guard. FAIL (low-likelihood, high-consequence).
- **`.gitignore`:** `data/cache|logs|staging|inbox|processed|failed|manifests/*` all ignored with `.gitkeep` preserved; `vault/Notes/` is explicitly tracked (`?? vault/Notes/`), so vault content would be committed — intended Obsidian vault ownership, but a user must whitelist what they want shared. PASS with note.

## 7. CLI UX (STEP 7)

Strengths: consistent rich tables/panels, stderr-only logging, exit code 1 on failure, clear abstention vs failure vs answered, explicit invalid-citation transparency, `--json` config display, `doctor` for diagnosis.
Gaps (no redesign yet): `pam ask` shows **no progress indicator** during the 10–80s generation; no `--json` output mode for `ask/search/status`; `pam watch` help/table says "Markdown" while it processes ~50 extensions (worker.py:265, watcher.py:151); no per-command `--merge`/`--force` ingest knobs; nothing surfaces the orphan-chunk condition.

## 8. Performance (STEP 8)

From existing measured evidence (no new benchmarks):

| Metric | Evidence |
|---|---|
| Retrieval | 2–6.5 s (embedding + dense/BM25/RRF) — 6E diagnostics |
| QA generation at 8192 | mean 33.4s, p50 31.3s, p95 64.8s, **max 81.6s** (6F-C, 35 queries) |
| Class worst tail | multi_chunk mean 72.8s / max 81.6s; factoid mean 19.5s — all < 120s deadline |
| Ollama 8192 | 5.2 GB, 100% GPU, context 8192 (permanent env, 6F-D) |
| 120s wall-clock | **0 timeouts** in 6F-C; max 81.6s leaves ~38s headroom |
| Memory | long-session free-RAM drift (486MB observed) flagged as host watch item; no latency fallout |

Actionable application-level concerns: (1) sequential-only `pam ask` under memory pressure is the safe default and worth documenting; (2) a session-length watch/restart habit on the host; (3) nothing in-app blocks or warns when free RAM is pathologically low.

## 9. Test Coverage (STEP 9)

Covered today: ingestion lifecycle (`test_ingestion`, `test_ingest_engine_outcome`, `test_knowledge_engine`, integration e2e/complete_workflow/queue_worker_pipeline), dedup (`test_duplicate_detection`, `test_manifest`, `test_hashing`), retries (`test_ollama_client`, `test_answerability_gate`), QA outcomes & citations (`test_qa_workflow`), timeout incl. CLI exit (`test_qa_timeout`, `test_cli` QATimeoutError→exit1), measurement (`test_qa_measurement`), CLI (`test_cli` incl. status/ledger), watcher (`test_watcher_service`, `test_watcher_filters`), queue (`test_queue_*`), manifest (`test_manifest`).
Baseline at 6F close: 1575 passed / **7 stale `test_eval_dataset.py` failures** / coverage 89.35%.

**The 7 failures are stale dataset assertions, deliberately not fixed** (full suite was executed once; verified individually this phase): the test module still targets dataset v2.0/Phase 3D (expects 160 queries, 37 negatives, version "2.0", phase "3D", no `precise_detail`/`multi_chunk` categories, v1 source-key set), but the shipped dataset is the frozen v3.0 (199 queries, 42 negatives, 7 categories, new sources). **High-value missing tests:** (1) `pam status` truthfulness against a controlled ledger (placeholder-aware note count, unique-source count); (2) URL-source dedup for github/youtube re-ingest; (3) **re-ingest-of-modified-source semantics** — asserting no orphan chunks/stale KG nodes (currently *unasserted behavior*, first test would fail against the implementation); (4) vector-store corruption → status "unavailable"; (5) question-field logging for privacy (a regression guard, not a fix).

## 10. Security / Privacy Review (STEP 10)

- Network egress inventory: **only** (a) Ollama at configured host (localhost default), (b) `pam ingest github`, (c) `pam ingest youtube`. Embeddings and all enrichments are local/deterministic. No analytics/telemetry.
- What gets logged: timestamps/levels/logger/module/line; file paths; user question text; exception messages (`exc_info` in dev environment). Document body is not logged.
- Secrets: searchable if a secret-bearing file is ingested (see STEP 6). Credential files also live in `config/*.yaml` (tracked) — repo hygiene separate from runtime.
- `.gitignore` protects all runtime data dirs; `vault/Notes/` is tracked by design.
- User-controlled files are handled safely: reads only, stable-file check before queueing (watcher), tmp+atomic-replace persistence, corruption quarantine.

## 11. V1 Completeness Check (STEP 11)

| Capability | Verdict | Evidence |
|---|---|---|
| Add personal knowledge | **PASS** | 21 adapters, watcher + manual ingest, GitHub/YouTube |
| Wait for ingestion | **PASS** | queue + progress bars + ledger status |
| Ask questions | **PARTIAL** | Works (0 failed/0 timeout/0 invalid cites); factual correctness unjudged |
| Grounded answers, verifiable sources | **PASS** | citation validation + invalid-reporting + dedup |
| Understand failures | **PARTIAL** | Clear errors/ledger, but status hides placeholder inflation & orphan condition |
| Recover from failures | **PARTIAL** | Retryable ledger ✓; no repair/cleanup tooling for orphan/stale data |

## 12. Prioritized Gaps (STEP 12)

| Gap | Severity | Evidence | User impact | Complexity | Recommended phase |
|---|---|---|---|---|---|
| Re-ingest of modified source leaves orphan chunks/stale KG nodes | **High** | chunk id `{source}::chunk_i`; no source-scoped removal (vector_store.py); KG merge only (ingest_workflow.py:1002) | Answers silently go stale/duplicated over time; no recovery path | Medium | 6H ingest-lifecycle hardening |
| `pam status` "Generated notes" counts 206 stubs as content | Medium | entry.py:153; live: 231 vs 25 real notes | User misreads KB health; trust erosion | Low | 6H (same direction) |
| URL sources (github/youtube) cannot be content-hashed → stale-content re-ingest skipped | Medium | entry.py:637/654; hashing.py Path-only | Modified remote content never refreshed | Low | 6H (same direction) |
| Secret-bearing files ingestible & searchable (config/.env/.db) | **High** | ConfigIngestor/DatabaseIngestor in registry; no guard | Credentials leak into the retriable KB | Low-Med | 6H privacy gate (same direction, lower priority) |
| Factual correctness of answers never judge-validated | Medium | no LLM judge by design | Running QA "works" with unverified truth | High | 6I correctness evaluation |
| No per-source delete / rebuild command | Medium | VectorStore has no source-scoped API | Orphans cannot be repaired | Low-Med | 6H (same direction) |
| `pam ask` has no progress indicator (10–80s wait) | Low | entry.py:447 | UX friction | Low | 6H/6I |
| Logged question text (privacy paper-trail) | Low | qa_workflow.py:462 | Local-only; fine w/ explicit note | Low | 6I |
| Stale `test_eval_dataset.py` (7 failures) | Low | live run | Failing suite obscures real regressions | Low | 6H (housekeeping) |

## 13. Next Direction (STEP 13)

**Chosen: A — Ingestion lifecycle hardening** (with a status-truthfulness component listed as part of it, not a second direction): make re-ingestion of a modified source safe, make the ledger/status truthful about actual knowledge, and remove the one High-severity data-consistency gap (STEP 12 #1). This directly targets the goal statement's *"safely add… recover from failures"* better than any cosmetic option, and it is the only High-severity evidence-backed direction.

## 14. Proposed Phase 6H — Definition (STEP 14)

Not implemented. Proposed contract for approval:

- **Objective:** re-ingesting a modified source never leaves orphaned/stale retrievable data; `pam status` reports real knowledge (unique sources, real notes, last ingest) and offers a source-delete/rebuild path.
- **Files likely to change:** `app/infrastructure/vector_store.py` (+ `remove_by_source`, `rebuild`), `app/infrastructure/knowledge_graph.py` (+ `remove_by_source` or recompute), `app/pipelines/ingest_workflow.py` (replacing step), `app/cli/entry.py` (`pam status` truthful counts, `pam ingest --replace/--delete`, per-source removal command), possibly `app/infrastructure/state/manifest.py` (unique-source aggregation helper), plus tests.
- **Behavior:** on ingest of content with a known-but-changed `source`, delete prior chunks + KG nodes for that source before adding new; status shows unique sources, real (non-stub) note count, last-ingestion time; new `pam ingest delete <source>`/rebuild action.
- **Tests:** re-ingest mutation keep chunk count → identity overwrite; reduce chunk count → no orphans (old ids removed); raise chunk count → clean add; KG node removal; status counts vs controlled fixtures; URL re-ingest refresh.
- **Acceptance:** a modified-and-re-ingested file yields a vector store whose source-set chunks exactly match the new content (no old `::chunk_i` ids addressable), KG has no stale nodes for that source, status shows truthful numbers, full suite green (except the 7 stale eval-dataset tests, which are cleaned in the same phase).
- **Rollback:** additive ops only (remove_by_source / rebuild are new), single commit, `git revert` on the two CLI/vector-store touches restores today's behavior.
- **Risks:** destructive-source-delete surface (mitigate with `--dry-run` + ledger log); rebuild cost on large corpora (bounded, 195-chunk corpus).
- **Must remain frozen:** retrieval math (BM25/RRF/min_cosine/metrics), embeddings model, chunking policy, reranker/HyDE/answerability, corpus, dataset, `qa.timeout_seconds=120`, 8192 context.

## 15. Report Labels (STEP 15)

- **VERIFIED** — HEAD `9f282b4` unchanged; corpus 195/24; dataset 199 v3.0; ledger 37/0/0; queue 0; 231 notes = 25 real + 206 stubs; 8192/100% GPU/5.2GB live; 6F-C perf (mean 33.4s, max 81.6s, 0 timeouts, 0 invalid cites).
- **PASS** — local-file dedup & retryable failure ledger; corruption quarantine; note merge preserves user content; citation-integrity contract; abstention-before-LLM; local-first network surface; `.gitignore` of runtime data; 120s deadline & 8192 validated; CLI exit codes.
- **PARTIAL** — URL-source content detection; orphan/stale-data handling on re-ingest; status truthfulness (notes/chunks-vs-attempts); no QA/progress/context observability; long-session RAM drift (watch item only); vector-store corruption silent-empty.
- **FAIL** — status narrator counts (231 notes) misrepresents real knowledge; orphan chunks have no cleanup/repair path; secret-bearing files are ingestible with no guard.
- **DEFERRED** — factual-correctness judging (6I), per-source delete/rebuild (folded into 6H), OLLAMA keep-alive/session watchdog (host ops), exhaustive multi-node/per-source health report.
- **PROPOSED** — Phase 6H ingestion-lifecycle hardening as defined in STEP 14.

## 16. Safety Audit (STEP 16)

- `git status --short`: 33 modified + ~70 untracked — the **cumulative pre-existing working-copy set** from prior phases (6A–6F code + eval/results + phase reports + vault state + Obsidian files + `nope.json`). Nothing new from Phase 6G. No files staged.
- `git diff --stat`: 33 files changed (identical set to 6F-C's report) — production diffs are the pre-existing 6A/6F code (`qa_workflow.py`, `config`, `entry.py`, etc.); **no retrieval/embedding/chunking/dataset/corpus changes this phase**.
- **HEAD** `9f282b41b6c558b0dbea857c95e24beb3ff63f9a` — unchanged; **no commits, no pushes** (pre-existing stash `stash@{0}` untouched).
- No temp scripts were created this phase; nothing to delete.
- The only new artifact this phase: this report (STEP 15 deliverable).

## 17. STOP (STEP 17)

Phase 6G discovery complete. **No implementation has been performed and none will begin.** The recommended next step is **Phase 6H: ingestion lifecycle hardening** (STEP 14 contract). Awaiting explicit approval before any further action.