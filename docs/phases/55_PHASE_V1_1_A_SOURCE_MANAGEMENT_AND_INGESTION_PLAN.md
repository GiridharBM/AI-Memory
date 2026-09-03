# PAM V1.1-A — SOURCE MANAGEMENT + INGESTION UX (IMPLEMENTATION PLANNING)

**Report:** `55_PHASE_V1_1_A_SOURCE_MANAGEMENT_AND_INGESTION_PLAN.md`
**Type:** Planning / design ONLY — no code changes, no git mutations
**Scope:** `pam sources`, source detail, ingestion UX, re-ingestion safety, `pam remove`, status/observability
**Authoritative predecessor:** `54_PHASE_V1_1_DISCOVERY_AND_PRIORITIZATION.md`

---

## 1. Objective

Design a smallest-coherent V1.1-A that improves **source management, ingestion UX, and observability** against the existing architecture — without touching retrieval, datasets, corpus, or history. This report is the implementation plan; **nothing is implemented here**.

**Scope locked to:** SOURCE MANAGEMENT (`pam sources` + detail) + INGESTION UX + RE-INGESTION SAFETY + `pam remove` improvement + STATUS/OBSERVABILITY.

---

## 2. Git Baseline (VERIFIED, read-only)

| Item | Value | Label |
|------|-------|-------|
| Published V1.0.0 | tag `v1.0.0` → `a4e5b2a` | VERIFIED |
| Remote main | `origin/main` → `198823d` | VERIFIED |
| Local HEAD | `main` → `97197e2` (ahead 6) | VERIFIED |
| Experimental commits on `main` (NOT on origin) | `6a603d8`, `e287226`, `8524caf`, `9f282b4` | VERIFIED |
| Application-hardening commits on `main` (NOT on origin) | `10f74f1`, `97197e2` | VERIFIED |
| Working tree | pre-existing dirty (vault, .obsidian, docs, eval, tests) — UNTOUCHED | VERIFIED |
| Nothing staged / nothing committed / tags unchanged | confirmed | VERIFIED |

`97197e2` is a **later local development state** (6 commits after `origin/main`), NOT the original published V1.0.0. **DO NOT push or rewrite history this phase.**

---

## 3. Current Source Architecture (VERIFIED)

What PAM knows about each indexed source, from where:

**A. Vector store** — `app/infrastructure/vector_store.py` + `app/domain/vector_store.py`
- Persisted at `data/manifests/vector_store.json` (`{"entries": [...]}`), atomic `temp+os.replace` on `save()`.
- `VectorEntry` fields: `id`, `text`, `embedding`, `source`, `source_type`, `chunk_index`, `start_char`, `end_char`, `metadata`.
- `source` = the ingestion-canonicalized source identifier; `source_type` = e.g. pdf/markdown/text/code/csv/etc.
- Per-source info available: `source`, `source_type`, per-chunk `chunk_index`, chunk text (NOT summary), vector IDs.
- `remove_by_source(source)` removes all chunks owned by `source`; bumps `version` so BM25 rebuilds on next use.

**B. Manifest / ledger** — `app/infrastructure/state/manifest.py` + `models.py`
- Persisted at `data/manifests/processed_files.json`, atomic `temp+os.replace`.
- `ManifestEntry` fields (VERIFIED): `sha256`, `original_filename`, `original_path` (project-relative), `processed_at`, `extension`, `status`, `generated_note`, `metadata`, `error_reason`, `chunks_stored`, `embedding_succeeded`, `indexing_succeeded`.
- `status` ∈ `{processed, skipped_duplicate, failed}`; `SUCCESSFUL_STATUSES = {processed, skipped_duplicated}`.
- Failed entries are retryable (excluded from hash-dedup).

**C. Knowledge graph** — `app/domain/knowledge_graph.py` + `app/infrastructure/knowledge_graph.py`
- Persisted at `data/manifests/knowledge_graph.json`.
- `KnowledgeNode.source`, `KnowledgeEdge`; `remove_source(source)` removes nodes+edges; `save(path)` atomic.
- Per-source info available: node count / edge count contributed by source (subject to shared-label attribution caveat).

**D. Source identity canonicalization** — `app/infrastructure/ingestion/service.py:292-305`
- Local file → `Path.expanduser().resolve()` **absolute path** (`document.source`).
- http/https URL → **URL string verbatim**.
- Manifest `original_path` = project-relative path (via `ManifestManager._normalize_path`).

**E. Unique-source count (status)** — `app/cli/entry.py:900-912` `_indexed_sources` reads `vector_store.json`, returns **count** of distinct `source` values (or `unavailable`). It does NOT enumerate the sources in detail.

**F. There is NO `pam sources` command today** (VERIFIED: only status/remove/doctor/config/config-show/watch/search/ask + ingest subcommands).

**Current per-source knowledge summary:**

| Field | Source | Present |
|-------|--------|---------|
| source identifier | vector `source`, manifest `original_path` | VERIFIED |
| source type | vector `source_type`, manifest `extension` | VERIFIED |
| chunk count | manifest `chunks_stored`, vector entries | VERIFIED |
| ingestion status | manifest `status` | VERIFIED |
| timestamps | manifest `processed_at` | VERIFIED |
| hash | manifest `sha256` | VERIFIED |
| failures | manifest `error_reason` | VERIFIED |
| retry state | manifest `status == "failed"` (retryable) | VERIFIED |
| embedding/index success | manifest `embedding_succeeded`/`indexing_succeeded` | VERIFIED |
| note | manifest `generated_note` | VERIFIED |
| KG nodes/edges | `knowledge_graph.json` per source | VERIFIED |
| placeholder vs real | vault note frontmatter `source_type: placeholder` / presence of `source` | VERIFIED (status only) |

---

## 4. Current Ingestion Architecture (VERIFIED)

- **CLI ingest** → `_run_ingest` (`app/cli/entry.py:710`): computes digest, **dedups by successful hash** (skip panel), else runs `IngestionWorkflow.create_default(settings).run(...)`, records ledger entry `processed`/`failed` (with `engine_error` when note-written-but-not-indexed), prints `_print_ingest_success`.
- **IngestionWorkflow** (`app/pipelines/ingest_workflow.py:139`): `_process_document` → routed processor (enrich) → AI analysis → knowledge engine (`_run_knowledge_engine` :919) → note generation → vault write.
- **Knowledge engine** (`:919-1059`): chunk → embed batch → on FULL embed success, `remove_by_source(source)` then `add_batch` + `save`; else preserve old data. KG rebuilt for this source only on success.
- **Queue worker** (`app/queue/worker.py`): dedup by successful hash → skip; failures recorded via `add_failed_file`; `_move_to_processed`/`_move_to_failed`; queue state via `QueueStateStore` (atomic temp+replace). `RuntimeStats` tracks processed/duplicate/failed.
- **Ingestion service** (`app/infrastructure/ingestion/service.py`): `ingest()` normalizes source, enforces size limit, **secret guard** (`is_secret_bearing`, :190-194), selects ingestor, enriches metadata.

---

## 5. `pam sources` Design (PROPOSED)

**A minimal enumeration command — no filtering/search in v1.**

### Command syntax
```
pam sources
```
Team parallel to existing top-level commands (`status`, `remove`). No arguments in v1. (Detail via `pam sources <source>` in §6, which is cleanly supported.)

### Data source (primary)
**Vector store** (`data/manifests/vector_store.json`) — the single authoritative source of "what is currently indexable/searchable." Cross-joins against **manifest** for status/timestamp/hash, and **KG** for node/edge counts.

### Output format
Rich `Table` (consistent with `status`/`_print_ingest_success`):

Columns:
| Source | Type | Chunks | Indexed | Ingested (UTC) | Status | Entries |
|--------|------|--------|---------|----------------|--------|---------|

- **Source**: vector `source` value (displayed via `_display_path`-style shortening vs project root).
- **Type**: vector `source_type`.
- **Chunks**: count of vector entries for that source.
- **Indexed**: from manifest `indexing_succeeded`/`embedding_succeeded` (else `—` if absent).
- **Ingested**: manifest `processed_at` (most recent successful).
- **Status**: manifest `status` for that source: `processed`/`skipped_duplicate`/`failed`; or `indexed (no ledger)` when present in vector store but absent from manifest (e.g. legacy/experimental corpus). Mark failed/absent in yellow via `_status_style`.
- **Entries**: manifest entry count for that source (usually 1; >1 when multiple paths map to same source string).

### Aggregation keys
Group vector entries by `entry.source`. For each, source_type from any entry. Manifest: match by normalized path/url (reuse `_source_forms` + `_manifest_entry_matches` logic) OR by `original_path == source` fallback. KG: `nodes`/`edges` by source field.

### Sorting
Sort by **source string** ascending (deterministic). Optionally group `placeholder` vs `real` via a status row.

### Error behavior
- If `vector_store.json` missing → empty table (0 sources), message "No sources indexed."
- If unreadable (parse/OSError) → print `unavailable` for that column, do NOT fabricate zeros (mirror `_indexed_sources` `unavailable` behavior). Continue to print sources that ARE resolvable.
- If manifest unreadable → show vector counts, status column `unavailable`.
- Non-zero exit on fatal unreadability of both store+manifest only if nothing can be shown; otherwise success.

### Empty-state behavior
Print empty table + "No sources indexed. Run `pam ingest file <path>` to add one." Exit 0.

### Placeholder vs real
Reuse frontmatter detection (`_note_counts`/`_frontmatter_value`) when parsing generated notes is cheap; otherwise mark columns `—` and let KG/source_type suffice. **Keep minimal:** v1 flags placeholder via the note's `source_type` only if a detail lookup is requested; the list shows a `Placeholder` status tag when the source maps to a placeholder note.

### Distinct real/placeholder where applicable
Because corpus sources were curated (24 sources) and placeholder stubs exist, `pam sources` should surface them but NOT overload the list. A footer row: "N indexed · M with ledger entry · K failed/retryable" is the only summary.

---

## 6. Source Detail Design (PROPOSED)

**Justified, cleanly supported:** `pam sources <source>`.

### Syntax
```
pam sources <source>          # one source by path/URL/name (reuse _source_forms)
pam sources --failed          # optional: only failed/retryable sources (small, high-value)
```

### Minimum useful output (single table)
- Source (canonical), Type, Path/URL
- Chunks, Chunk indices range, Chunk IDs (first 3 + "…")
- Manifest status, `processed_at`, `sha256` (truncated), `error_reason` (if failed), `embedding_succeeded`/`indexing_succeeded`
- `generated_note` filename
- KG nodes / KG edges for that source

All derivable from existing state — **no new persistence**. If the source string resolves to multiple manifest entries (identical-content files), list each distinct entry row.

### When it's NOT justified
Any capability requiring new persistence (per-source scan timestamps, per-source tags, per-source exclusion) is **DEFERRED** — do not build a source-management subsystem.

---

## 7. Ingestion UX Plan (PROPOSED)

Problems identified (VERIFIED from `_run_ingest`, `_print_ingest_success`, `worker.py`):

| # | Problem | Current behavior | Proposed UX improvement |
|---|---------|------------------|-------------------------|
| 1 | Unclear **progress** | CLI uses `Panel` only; no per-step progress bar (only queue worker has Rich progress) | Add a light step banner (`Reading → AI → Chunks → Note`) to `_run_ingest`; keep it minimal. |
| 2 | Unclear **failure reason** | Prints `<Class>: <exc>`; generic "Processing failed" | Surface `error_reason` verbatim + a one-line "what to do" hint per cause class (size limit, unsupported type, secret, Ollama down). |
| 3 | Unclear **retryability** | Failed entries are retryable silently | After a failure, print "This source is retryable — re-run `pam ingest file <path>`." |
| 4 | **Duplicate** explanation | "identical content; skipping" panel | Add "Hash (sha256): …" and last `processed_at` line so the user understands WHY. |
| 5 | **Successful re-ingest** not obvious | Panel shows counts but not "replaced previous data" | On successful re-ingest of a source that had prior chunks, print "Replaced N prior chunks for this source." |
| 6 | **Secret-blocked** explanation | `BlockedSourceError` message is detailed but CLI panel shows raw exception | Add explicit "blocked: secret/credential file" hint category (no secret content printed). |
| 7 | **Not-indexed** note-written case | Sets `status="failed"`, `error_reason="EMBEDDING/INDEXING FAILURE: ..."` | Print explicit "Note written but NOT indexed (retryable)" panel + reason; distinguish from hard failures. |

All are **presentation/reporting only** — ingestion behavior is unchanged. The ledger already captures the data needed (error_reason, status, processed_at, chunks_stored).

---

## 8. Re-ingestion Safety Review (VERIFIED, §6H guarantees)

| Guarantee | Current mechanism | Status |
|-----------|-------------------|--------|
| SUCCESS: old source data may be replaced | `_run_knowledge_engine` :979 `remove_by_source(source)` then `add_batch` + save on **full embed success** | VERIFIED — replacement is the intended path |
| FAILURE: old valid data intact | Removal gated on `outcome.embedding_succeeded and entries`; on failure, old chunks/KG preserved | VERIFIED |
| DUPLICATE: safely deduplicated | Hash-based dedup in CLI + worker; `skipped_duplicate` ledger entry | VERIFIED |
| RETRY: failed entries retryable | `failed` status excluded from hash-dedup; re-drop reprocesses | VERIFIED |

**Remaining edge cases (PROPOSED to address):**
1. **Partial embed within a batch:** `embed_batch` may return some empty embeddings. `embedding_succeeded = all(...)`; if any chunk lacks an embedding the batch is skipped entirely (no removal, no partial add) — correct, but no user-facing signal. → surfaced via §7 UX improvement; no logic change.
2. **KG updated but vector failed:** KG is gated independently on `outcome.succeeded` (which includes indexing) — consistent. VERIFIED.
3. **Same-path, identical-content reingest:** duplicate-skip path returns before knowledge engine → no double-add. VERIFIED.
4. **Two different file paths with identical content (distinct sources, same sha256):** each has its own `source` string → both indexed as separate sources (correct; no collision since removal keys on `source`). VERIFIED as intended.
5. **Re-ingest where old source had 0 chunks (note written, nothing indexed):** no removal; `add_batch([])`; no corruption. VERIFIED.

**No remaining correctness gap found.** Re-ingestion safety is already sound (Phase 6H). Only **communication** of these outcomes needs improvement (§7).

---

## 9. `pam remove` Review (VERIFIED)

### Accepted source formats (`_source_forms`, `entry.py:1017`)
- URL → verbatim.
- Path → set of {raw, absolute-resolved, project-relative-resolved, project-relative-raw}.
- Then achieves **exact-form** matching per subsystem.

### Current deletion flow (`remove_source`, `entry.py:213-272`)
1. `_source_forms` builds targets.
2. Vector: `store.remove_by_source(target)` for each target; `store.save()`.
3. KG: `kg.remove_source(target)` for each; `kg.save()`.
4. Manifest: for each entry, `_manifest_entry_matches(original_path, original_filename, sha256, targets)` — removes if `original_path in targets` OR `original_filename in targets` OR resolved path in targets.
5. BM25: rebuilt automatically on next use via vector-store `version` bump.

### Findings / limitations
| # | Limitation | Severity | Proposed smallest fix |
|---|-----------|----------|-----------------------|
| 1 | **No fuzzy/fragment match** — must supply a path/URL that resolves to an exact form; cannot remove by partial filename or by "all sources from directory X" | Low-Med | `pam remove` stays exact; add a `--list`/`pam sources` first to discover exact strings. No fuzzy logic. |
| 2 | **Source does not exist → silent no-op** | Medium | Add clear "No matching source found" exit message + non-zero-ish feedback (currently returns success with 0 removals). |
| 3 | **Manifest matches by `original_filename` too** — a source could be removed if the filename alone is a target (collision risk only if user passes a bare filename). | Low | Keep (it's an intentional convenience); document it. |
| 4 | **Identical-content files (same sha, different paths)** | VERIFIED correct | Each removed by its own source string; no cross-removal. Add a test. |
| 5 | **No confirmation** | Low | Optional `--yes`/confirmation for safe atomic remove. DEFERRED unless trivial. |

### Smallest reliable improvement (PROPOSED)
- Return a clear **"No matching source removed"** panel (and non-zero exit code) when removals == 0.
- Print per-subsystem counts already present (vectors/KG/nodes/edges/ledger) — already done.
- Add a **"Removed" summary** foot line with the canonical target matched (resolve ambiguity).
- **Do NOT** add fuzzy remove, multi-source remove, or source-agnostic purge in V1.1-A (all DEFERRED).

---

## 10. Status / Observability Plan (PROPOSED)

Current `status` (VERIFIED) already shows: watcher, inbox, queue, pending items, manifest entries, sources indexed (count), indexed chunks, successful/skipped/failed/retryable, last ingestion, Ollama, model, vault, real notes, placeholder notes, logs.

**High-value, non-overloading additions (small):**
1. **Per-status breakdown already present** — no change.
2. Add `chunks` and `sources` as **exact numbers from durable state** (already), and ensure a `—`/`unavailable` (NOT `0`) when the store can't be read. (Already handled for chunks/sources; verify consistently.)
3. Add a **single-line "Remedy hint"** footer when `failed > 0` or Ollama unavailable → "Run `pam sources --failed` / `pam doctor`."
4. Do NOT add per-source rows to `status` (that's `pam sources`'s job). Keep `status` a high-level dashboard.

---

## 11. Acceptance Criteria (PROPOSED — measurable)

**SOURCES (`pam sources`)**
- AC1 Lists all indexed sources (count of list == `_indexed_sources`-equivalent of `vector_store.json`).
- AC2 Chunks column sum == total vector entries in `vector_store.json`.
- AC3 No fabricated entries: every row's Source comes from actual `vector_store.json` entries; missing data shown as `—`/`unavailable`, never invented.
- AC4 Empty store → empty table + "No sources indexed." message, exit 0.

**SOURCE DETAIL (`pam sources <source>`)**
- AC5 Resolves a source present in vector store and shows chunks/status/hash/note correctly.
- AC6 Unknown source → clear "no such source" message, no crash.
- AC7 `--failed` lists only manifest `status=="failed"` sources.

**INGESTION UX**
- AC8 Success prints chunk count + note path + (on re-ingest) "Replaced N prior chunks."
- AC9 Duplicate prints reason + sha + prior `processed_at`.
- AC10 Failure prints `error_reason` + retryability hint.
- AC11 Secret-blocked prints "blocked: secret/credential" hint, no secret content.
- AC12 Note-written-not-indexed prints explicit "NOT indexed (retryable)" + reason.

**RE-INGESTION SAFETY**
- AC13 On simulated ingest failure AFTER prior success: old vector chunks + KG nodes/edges for the source remain intact (diff == 0).
- AC14 On simulated ingest success: old chunks replaced (count matches new), KG rebuilt for source, other sources untouched.
- AC15 Duplicate re-drop → `skipped_duplicate`, no double-add.
- AC16 Failed entry remains retryable (re-drop reprocesses).

**REMOVE**
- AC17 Removes exactly the target source across vector+KG+ledger; count of remaining == prior count − target count.
- AC18 Unrelated sources' vectors/KG/ledger byte-identical before/after.
- AC19 Missing source → "No matching source removed" + non-zero-ish exit, nothing deleted.
- AC20 Identical-content two-path case → removing one leaves the other intact.

**STATUS**
- AC21 All numeric values from durable state; unavailable → `unavailable`/`—`, never fabricated `0`.
- AC22 Failed/retryable + Ollama-down hint lines shown appropriately.

**REGRESSION**
- AC23 Existing unit suite stays green (1587 pass excl. stale eval; stale 7 remain unchanged/unmodified).
- AC24 No `eval/dataset.json`, corpus, config, or retrieval files modified.
- AC25 Retrieval byte-identical.

---

## 12. File-Level Implementation Plan (PROPOSED — NO code changed)

| File | Current role | Proposed change | Reason | Risk | Tests |
|------|--------------|-----------------|--------|------|-------|
| `app/cli/entry.py` | CLI commands (status/remove/ingest/ask/search) | Add `sources` command (+ `--failed`); enrich `_run_ingest` UX panels; improve `remove_source` no-match handling; add `status` hint line. Add small helpers: `_load_source_rows`, `_source_detail`, `_ingest_hint` | Deliver P1/P2 with minimal surface | Low (new top-level command; presentation-only changes to existing panels/exit codes) | sour/description/list/detail/empty/remove-no-match/ingest-notes tests |
| `app/infrastructure/vector_store.py` | In-memory store + JSON persistence | (No functional change) Add READ helper `chunk_counts_by_source()` OR reuse existing `entries()` in CLI | Clean per-source chunk counts for `sources` without loading store twice | None (additive read; retrieval untouched) | vector count tests |
| `app/infrastructure/state/manifest.py` | Ledger persistence + queries | Add read query `sources_summary()` / `entry_for_source()` (project-relative ↔ source matching) OR implement in CLI using existing `list_entries` | Join manifest to vector for status/timestamps | Low (additive read) | manifest summary tests |
| `app/infrastructure/knowledge_graph.py` | KG builder + persistence | (No change) Optionally add `node_edge_counts_for_source(source)` read helper | Show KG nodes/edges in detail | None (additive read) | KG count tests |
| `tests/unit/test_cli_source_cmd.py` (new) | — | New unit file for `pam sources` list/detail/empty/failed | AC1-7 | Low | hermeic tmp stores |
| `tests/unit/test_manifest_sources.py` (new) | — | Manifest ↔ source join helpers | AC5 | Low | hermeic |
| `tests/unit/test_ingestion_ux.py` (new) | — | UX helper functions (hints/categories) | AC8-12 | Low | pure functions |
| `tests/unit/test_remove_no_match.py` (new) | — | `remove` no-match + exit | AC19 | Low | hermeic |
| `tests/integration/test_queue_worker_pipeline.py` (existing, dirty) | E2E queue | (No change) Do not rewrite; verify still green | AC15/16 | — | — |

**Implementation strategy:** Prefer **read-only additions to CLI + additive read helpers + presentation**, never altering write paths (vector/KG/manifest save, remove logic, dedup). This keeps retrieval byte-identical and regression surface minimal.

---

## 13. Test Plan (PROPOSED)

Unit tests using **temporary stores/files only** (`tmp_path` + hermeic temp `VectorStore`/`ManifestManager`/`KnowledgeGraph`), matching existing `test_manifest` patterns:

1. **source listing** — build vector store with 2 sources + manifest; assert `pam sources` rows/count.
2. **source metadata** — assert type/chunks/status/timestamp columns populated.
3. **empty source state** — no store → empty table + message, exit 0.
4. **ingestion success** — CLI `_run_ingest` on temp md; assert ledger `processed` + success panel.
5. **ingestion duplicate** — same content re-run → `skipped_duplicate` + sha/prior-time panel.
6. **ingestion failure** — unsupported/big/secret → `failed` + error_reason + retry hint.
7. **ingestion retry** — failed entry re-dropped → reprocesses (not skipped).
8. **re-ingestion success** — chunk count replaced; other source intact.
9. **re-ingestion failure preservation** — simulate failure after success → old chunks/KG intact (diff 0).
10. **source removal** — remove one source; vectors/KG/ledger exact; other sources intact.
11. **missing source removal** — no-match message + nothing deleted.
12. **identical-content edge case** — two paths same sha; remove one, other intact.
13. **status accuracy** — numeric from durable state; `unavailable` not `0`.
14. **secret guard regression** — `.env`/`.pem` blocked; URL passes; existing `test_ingestion`/secret tests still green.

All hermeic; no corpus, no real store, no `eval/dataset.json`.

---

## 14. Risk Assessment

| Risk | Level | Mitigation |
|------|-------|-----------|
| New `pam sources` reads join three files; drift between them | Low | Treat vector store as authoritative for existence; manifest/KG as enrich-only (`—`/`unavailable` fallback) |
| Adding exit-code/non-zero changes to existing `remove` no-match | Low | Code-review scoped; exit-code change documented; tests confirm happy-path unchanged |
| UX panel changes in `_run_ingest` touching failure paths | Low | Presentation-only; no write-path change; tests cover all branches |
| Re-opening retrieval accidentally | None | Explicit non-goal; retrieval files frozen; verification via AC25 |
| History rewritten / push | None | No git operations this phase |
| Regressing existing tests | Low | Full suite must stay green (AC23) |

---

## 15. Explicit Non-Goals (NON-GOAL)

- ❌ Modify retrieval algorithms / embeddings / BM25 / RRF / reranker / HyDE / answerability.
- ❌ Reopen 3G-A / 3G-B / 5F.
- ❌ Implement evidence verification.
- ❌ Implement Agentic AI.
- ❌ Modify `eval/dataset.json` or the real corpus.
- ❌ Push / create-delete-move tags / rewrite `v1.0.0`.
- ❌ Commit anything.
- ❌ Build a full source-management subsystem (tags, exclusions, per-source scan scheduling, fuzzy remove).

---

## 16. Retrieval Freeze Preservation (VERIFIED)

This plan makes **zero** changes to retrieval code, config, dataset, or corpus. `pam sources`/UX/status are **read + presentation** only; `remove` path is unchanged (addressing only no-match feedback, which does not alter vector/KG/ledger write semantics for matched sources). Retrieval remains byte-identical (AC25). All Phase 5 freeze commitments hold.

---

## 17. Git / Release Strategy (RECOMMENDED — NOT performed)

Constraints: published `v1.0.0 → a4e5b2a` must NOT move; `main` at `97197e2` holds 4 experimental commits not on `origin/main`.

**Recommendation (safest):**
1. **Do not fast-forward push** `main` (`97197e2`) — it bundles experimental retrieval commits with app changes.
2. Create a **V1.1 branch** from a clean join point. The cleanest **release** base is `10f74f1` (application hardening, pre experimental) paired with `198823d` (origin/main) — i.e. branch V1.1 off `198823d` **or** `10f74f1`, keeping `97197e2`'s app improvements (System Facts) selectable.
3. **Excluded** from the V1.1 release history: `6a603d8`, `e287226`, `8524caf`, `9f282b4` (experimental retrieval + eval-infra) — keep them on a side branch / behind a research tag, never on the releasable `main`.
4. Apply V1.1-A implementation as **atomic commits on the V1.1 branch** — each commit self-contained + tested (matches the repo's commit discipline).
5. Form the eventual release as a **new commit + new annotated tag `v1.1.0`** (never reuse/move `v1.0.0`). After V1.1 merge, `main` can fast-forward/merge the V1.1 branch (clean history, no experimental commits).
6. Only after V1.1 is verified + tagged should `origin/main` be advanced — with the cleaned history, never the experimental stack.

No history/branch/tag change performed now.

---

## 18. Final Recommendation

Proceed to implement **V1.1-A** after approval, as a set of atomic, tested commits on a dedicated **V1.1 branch** (off `198823d`/`10f74f1`), scoped strictly to: `pam sources` (+ `--failed` + detail), ingestion UX, re-ingestion-safety *communication* (logic already sound), `pam remove` no-match feedback, and small `status` hints — with retrieval frozen and dataset/corpus/config untouched. Success per §11 acceptance criteria and full regression suite (AC23-25).

---

*Labels: VERIFIED, CURRENT, PROPOSED, DEFERRED, NON-GOAL, RISK.*
