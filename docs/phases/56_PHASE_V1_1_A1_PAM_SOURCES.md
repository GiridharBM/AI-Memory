# PAM V1.1-A1 — IMPLEMENT `pam sources`

**Report:** `56_PHASE_V1_1_A1_PAM_SOURCES.md`
**Type:** Implementation (ONE feature) — `pam sources`
**Scope lock:** source-listing helper + CLI command + tests only
**Baseline:** published `v1.0.0 → a4e5b2a`; `origin/main → 198823d`; local HEAD `97197e2`

---

## 1. Objective (VERIFIED)

Implement a truthful, read-only `pam sources` command that lists the sources currently indexed by PAM, with useful metadata, without an LLM, retrieval, or network access, and without mutating any corpus/state.

---

## 2. Current Architecture (VERIFIED)

| Component | File | Role |
|-----------|------|------|
| Vector store | `app/infrastructure/vector_store.py`, `app/domain/vector_store.py` | Authoritative index of what is searchable; persisted `data/manifests/vector_store.json` as `{"entries":[{source,source_type,chunk_index,...}]}` |
| Manifest ledger | `app/infrastructure/state/manifest.py`, `models.py` | Durable per-source record: status (`processed`/`skipped_duplicate`/`failed`), `processed_at`, `sha256`, `chunks_stored`, `embedding_succeeded`/`indexing_succeeded` |
| Knowledge graph | `app/domain/knowledge_graph.py`, `infrastructure` | Per-source nodes/edges; `remove_source(source)` semantics |
| CLI | `app/cli/entry.py` | Commands: status/remove/doctor/config/config-show/watch/search/ask/ingest; helpers `_indexed_sources`, `_indexed_chunks`, `_source_forms`, `_manifest_entry_matches` |
| Config | `app/core/config.py`, `config/default.yaml` | `paths.manifest_root`, `manifest.path`, `manifest.enabled` |

**Existing `status`** already reports `Sources indexed` as a **count** (`_indexed_sources`, entry.py). **No `pam sources` command existed** (VERIFIED).

---

## 3. Source-of-Truth Decision (VERIFIED)

**Primary authority:** the persistent **vector store** (`data/manifests/vector_store.json`) — it defines what is currently indexable/searchable.

**Enrichment:** the **manifest ledger** annotates each source with ingestion `status`, last successful `processed_at`, and (via matching) `sha256`. This reuses existing durable state; **no second source database was created.**

Live store: 195 entries / 24 distinct sources (matches the frozen Phase-5 corpus of 24 sources / 195 chunks). **PASS.**

---

## 4. Command Contract (IMPLEMENTED)

```
pam sources
```

- Lists indexed sources, one row per distinct `source` value.
- Columns: **SOURCE · TYPE · CHUNKS · STATUS · LAST INGESTED (UTC)**.
- Deterministic ordering: ascending by source string.
- Empty store → human-readable message, exit 0.
- Unreadable store → "unavailable" panel, exit 1.
- No LLM, no retrieval query, no network, no corpus mutation.

---

## 5. Output Design (IMPLEMENTED)

Rich `Table(title="Indexed Sources")` with 5 columns (as above). Data derived solely from the vector store (source/type/chunk count) + manifest (status/last-ingested via `_source_forms`/`_manifest_entry_matches` matching). Missing fields show `—`; unreadable state shows `unavailable`, never fabricated `0`. 

| Column | Source | Fabrication risk |
|--------|--------|------------------|
| SOURCE | vector `source` | none (from durable state) |
| TYPE | vector `source_type` | none |
| CHUNKS | vector entry count per source | none |
| STATUS | manifest `status` (failed > processed > skipped_duplicate > indexed) | none |
| LAST INGESTED | manifest `processed_at` (most recent successful) | none |

Status styling: `failed` and `indexed (no ledger)` are surfaced plainly; consistent with `status` output.

---

## 6. Source Identity Handling (IMPLEMENTED — VERIFIED)

Reuses the **existing** identity rules — no new identity mechanism:

- Group by the canonical `source` value (vector store key) — the same key `pam remove` / re-ingest use.
- Manifest matching via `_source_forms(source, project_root)` + `_manifest_entry_matches(original_path, original_filename, sha256, targets)` — exactly the `pam remove` semantics.
- **Duplicate content / identical SHA-256:** two distinct paths with the same content have distinct `source` strings → listed as separate rows (never silently merged).
- **Failed / retryable entries:** status reported as `failed` even if a later re-ingest succeeded, because failure is the more actionable state (per-row logic: failed > processed > skipped_duplicate > indexed).
- **Placeholders:** no reliance on vault note scanning (avoids touching corpus); a source with no ledger match reports `indexed (no ledger)` truthfully. Placeholder distinction is NOT fabricated.
- **URLs:** kept verbatim (existing remote source identity).

---

## 7. Empty State (IMPLEMENTED)

No `vector_store.json` (or zero valid entries) → prints:

```
No sources are indexed yet. Run `pam ingest file <path>` to add one.
```

exits **0**. No fake table, no fabricated `0` sources.

---

## 8. Error Behavior (IMPLEMENTED)

- Vector store present but unreadable/parse error → Panel `"The vector store could not be read; source listing is unavailable."`, exit **1**. No traceback leaks; follows the application convention (`Panel.fit`, `typer.Exit`).
- Manifest unreadable → manifest is enriched only; rows still show vector-derived data with status `indexed (no ledger)` (no fabrication).
- Malformed entries within store → skipped (mirrors `VectorStore._load` tolerance).

---

## 9. Security (VERIFIED — PASS)

Added code touches **only**: `source`, `source_type`, `status`, `processed_at`, `original_path`, `original_filename`, `sha256`. It **never reads** `text`, `embedding`, or arbitrary `metadata`. Therefore no secret file contents, credentials, environment variables, tokens, or API keys can be exposed. Only source metadata is displayed. **PASS.**

---

## 10. Implementation (IMPLEMENTED)

Files changed:

1. **`app/cli/entry.py`** (167 insertions / 1 deletion):
   - Added `SourceRow` dataclass (`source`, `type`, `chunks`, `status`, `last_ingested`, `manifest_matches`).
   - Added `sources()` command.
   - Added `_read_vector_store_sources(settings)` → `list[SourceRow] | None` (None = unreadable; sorted deterministically; grouped by canonical source).
   - Added `_annotate_source_ledger(rows, manifest, project_root)` (manifest status + last-ingested via existing matching).
   - Added `_source_status_style(status)`.
   - Import added: `dataclass, field`, `ManifestEntry`, `is_successful_status`; import block sorted (ruff I001 fixed).

2. **`tests/unit/test_cli_sources.py`** (new, 12 tests).

**mypy:** new code clean (the ONE remaining mypy finding — `entry.py:891` `hash_for_path` in `_run_ingest` — is a **pre-existing** latent issue present in committed HEAD, in code I did not touch).

**ruff:** new code clean (the 2 remaining E501 findings are **pre-existing** in `remove_source` lines 379/415, not touched).

---

## 11. Tests (IMPLEMENTED — 12 PASS)

`tests/unit/test_cli_sources.py` (all hermetic, temp stores/files only):

| Test | Covers |
|------|--------|
| `test_groups_and_sorts_sources` | multiple sources, deterministic ordering, chunk counts, types |
| `test_empty_when_store_missing` | empty state |
| `test_none_when_store_unreadable` | read failure → None |
| `test_none_when_entries_not_list` | malformed payload → None |
| `test_type_defaults_from_first_entry` | source_type from first entry |
| `test_processed_status_and_last_ingested` | processed status + timestamp |
| `test_failed_takes_precedence` | failed/retryable precedence |
| `test_skipped_duplicate` | skipped_duplicate status |
| `test_indexed_when_no_ledger_entry` | no-manifest → indexed (no ledger) |
| `test_lists_indexed_sources` | CLI end-to-end, exit 0, table output |
| `test_empty_state_message` | CLI empty message |
| `test_unavailable_store_exits_nonzero` | CLI exit 1 + unavailable message |

**No LLM/retrieval/network invocation:** the command imports no embedding/search/Ollama path; tests assert pure JSON+manifest reads. **VERIFIED.**

---

## 12. Regression Results (PASS)

Targeted (CLI + sources + manifest + knowledge engine + ingestion-lifecycle + ingest-engine-outcome): **301 passed**.

Full unit suite (`pytest tests/unit`, standard addopts `-m 'not integration'`):
- **1623 passed / 1 deselected / 7 failed**
- All 7 failures are the **known pre-existing stale `test_eval_dataset.py`** (v2.0 assertions vs frozen v3.0 dataset: "3D vs 5D", 160 queries, etc.) — unchanged, matches documented baseline.
- Reconciliation: 1587 (baseline non-eval) + 24 (stale-eval passing) + 12 (new) = 1623. ✅
- **No new failures.** Baseline preserved.

---

## 13. Live Smoke Result (VERIFIED — PASS, read-only)

`pam sources` against live state reports the **24 indexed sources / 195 entries** with truthful types and chunk counts. The corpus sources (indexed by the Phase-5 eval harness) carry no manifest ledger entry → correctly shown as `indexed (no ledger)` (honest — the command reports exactly what durable state holds).

**Read-only proof:** SHA-256 of `vector_store.json`, `knowledge_graph.json`, `processed_files.json` **identical** before and after the run. No corpus, store, KG, or manifest mutation. **PASS.**

---

## 14. Retrieval Freeze Verification (PASS — UNCHANGED)

`git diff HEAD -- embeddings.py search.py bm25.py reranker.py semantic_chunking.py` → **NO DIFF**. Config flags unchanged: `reranker.enabled=false`, `hyde.enabled=false`, `answerability.enabled=false`, production `min_cosine=0.25`. **PASS.**

---

## 15. Corpus Safety (VERIFIED — PASS)

No re-ingestion, no source deletion, no manifest modification, no vector-store rebuild, no KG change. All tests use temporary stores. Live smoke was read-only (hash-verified). **PASS.**

---

## 16. Git Safety (VERIFIED)

| Item | State |
|------|-------|
| New intended artifact | `56_PHASE_V1_1_A1_PAM_SOURCES.md` only |
| Code change | `app/cli/entry.py` (+167/−1) — the feature |
| New test file | `tests/unit/test_cli_sources.py` |
| Pre-existing dirty files | intact (vault, .obsidian, docs, eval, etc.) — untouched |
| Staged/committed/pushed/tagged | none |
| HEAD / tags | `97197e2` unchanged; `v1.0.0`, `v2.0.0` intact |

No Git history operations performed.

---

## 17. Known Limitations (KNOWN LIMITATION)

1. **Sources indexed outside the ledger** show `indexed (no ledger)` — truthful, but the current live corpus (eval-harness ingested) will show this for all sources until re-ingested or recorded. Not a bug.
2. `_run_ingest` has a pre-existing latent mypy finding (`entry.py:891`) and `remove_source` has 2 pre-existing E501 lines — **not introduced by this phase**; flagged for a future cleanup phase (V1.1-A5 CLI hygiene).
3. No per-source KG node/edge counts or note association in the compact table (deferred to A1.5/detail view if requested) — out of the compact scope.
4. No filtering/search flags in v1 (per design; `--failed` deferred to a later iteration).

---

## 18. Final Verdict (VERIFIED — PASS)

`pam sources` is **IMPLEMENTED**, tested (12 hermetic unit tests), regression-clean, read-only-verified, retrieval-freeze-preserved, and security-checked. Ready for review; V1.1-A2 (ingestion UX) awaits explicit approval.

---

*Labels: IMPLEMENTED, VERIFIED, PASS, UNCHANGED, DEFERRED, KNOWN LIMITATION.*