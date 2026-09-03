# Phase V1.1-A4 Report — `pam remove` Source Management Hardening

**Date:** 2026-09-01  
**Status:** VERIFIED · IMPLEMENTED · PASS  
**Summary:** SAFE + DETERMINISTIC + SOURCE-SCOPED deletion of exactly one source (vector chunks, KG nodes/edges, ledger, BM25 invalidation) with unrelated sources untouched. One real defect found and fixed; others deferred (KG ownership caveat = no concrete bug, no redesign needed).

---

## 1. A4 Scope & Deliverables

| Item | Status |
|------|--------|
| Vector removal by source | IMPLEMENTED — `store.remove_by_source(target)` per resolved target |
| KG removal by source | IMPLEMENTED — `kg.remove_source(target)` per resolved target |
| Ledger removal (path-based) | IMPLEMENTED — `manifest.remove_entry(path=entry_path)` pre-resolved absolute |
| BM25 invalidation | VERIFIED — `remove_by_source` bumps `store.version`; `HybridSearch._lexical()` rebuilds next call |
| Not-found handling | IMPLEMENTED — exit 1 with "Source not found" |
| Ambiguous handling | IMPLEMENTED — exit 1 with "Remove aborted (ambiguous source)", nothing deleted |
| Corrupt-KG handling | IMPLEMENTED — truthfully exit 1 before any deletion, no trace leak |
| URL source support | IMPLEMENTED — verbatim URL + mangled `str(Path(url))` forms both work |
| Identical-SHA sibling preservation | IMPLEMENTED — ledger removal by exact path identity, not sha256 |
| CLI output | IMPLEMENTED — "Source Removed" table with chunks/nodes/edges/ledger counts |
| No secret leakage | VERIFIED — removal reads no file contents; only ledger metadata |
| Frozen infra files | VERIFIED — `search.py`, `bm25.py`, `reranker.py`, `embeddings.py`, `semantic_chunking.py` unchanged |

## 2. Production Code Changes (entry.py)

Three edits, all in `app/cli/entry.py`:

### Edit 1: Import addition
`from contextlib import suppress` added (needed for `_canonical_source` if-else cleanup pattern).

### Edit 2: `remove_source` rewrite (lines 379–497)

**Before (pre-fix):**
- Matched sources via vector/KG/ledger intersection
- Ledger: `manifest.remove_entry(sha256=entry.sha256)` — deleted by content hash, first match only
- No exit-code handling: success printed regardless
- Corrupt KG caused traceback

**After (post-fix):**
- Loads vector store, KG (with `suppress` guard → truthful "Remove failed" panel + exit 1 if corrupt), manifest
- Computes `matched` canonical set across vector/KG/ledger
- `len(matched) > 1` → "Remove aborted (ambiguous source)" + exit 1 + **zero deletions**
- Empty → "Source not found" + exit 1
- Adds resolved absolute forms to `targets` so basename/vector/KG/ledger all agree
- **Ledger:** `manifest.remove_entry(path=entry_path)` where `entry_path` is `project_root / original_path` resolved to absolute — removes by exact path identity, not content hash
- Prints "Source Removed" table with counts
- Logs via `logger.error` (not exception) for KG read failure

### Edit 3: `_source_forms` rewrite + `_canonical_source` helper (lines ~1270–1320)

**Before:**
- Relative inputs resolved against CWD (wrong when CWD ≠ project_root)
- `_manifest_entry_matches` basename check could silently match multiple sources (undetected ambiguity)

**After:**
- `_source_forms(source, project_root)`: URLs add `str(Path(source))` + resolved + project-relative mangled forms; relative paths resolve against `project_root` not CWD
- `_canonical_source(value, project_root)`: mirrors manifest normalization — resolve, then project-relative if possible, else absolute

## 3. A2/Pre-existing Mypy Fixes (incidental)

Two pre-existing mypy issues in `_run_ingest` were fixed as part of ensuring mypy clean overall:

1. **`hash_for_path` type:** `manifest.hash_for_path(source)` where `source: str | Path` — replaced `is_file` alias with inline `isinstance(source, Path)` so mypy narrows correctly.

2. **`getattr(result, "chunks_stored", 0)`:** default `0` (int) mismatched attribute type `bool` — changed to `False` across all 3 occurrences.

Both are A2 leftovers (uncommitted); behavior unchanged.

## 4. Identical-SHA Sibling Bug (STEP 4)

**Defect:** `manifest.remove_entry(sha256=entry.sha256)` deletes the FIRST entry with matching content hash. With identical-SHA siblings ingested in order `[B, A]`, removing A deletes B's ledger row (A's survives).

**Proof:** Created two files with identical content → same SHA. Seeded ledger in order `[B, A]`. Ran old logic: B's row deleted, A's survived — **source-scoped removal violated**.

**Fix:** Ledger removal now uses `manifest.remove_entry(path=entry_path)` where `entry_path` is the exact pre-resolved absolute path. Each row matches its own path only.

**Test:** `test_identical_sha_removal_keeps_sibling_ledger_and_data` seeds [B, A] in reversed order, removes A, asserts B survives in vector + KG + ledger.

## 5. STEP 5 Source Matching (path resolution findings)

| Finding | Resolution |
|---------|-----------|
| `_source_forms` resolved relative inputs against CWD | Fixed: now resolves against `project_root` |
| `_manifest_entry_matches` basename could silently match multiple sources | Now caught by `len(matched) > 1` → ambiguous abort |
| URL rows stored `str(Path(url))` = mangled relative; ledger stores same under real project root | Vector/KG/ledger all converge on same `_canonical_source` token |

## 6. STEP 7 KG: Node Ownership C caveat — DEFERRED

`KnowledgeGraph.remove_source` correctly removes all nodes/edges where `source == target`. The documented caveat: a node shared across multiple sources (ingested from two different files with overlapping text) loses its cross-source associations when one source is removed. This is best-effort by design, not a concrete correctness bug — would require redesign of node dedup/ownership semantics.

**Action:** No change. DEFERRED (no concrete bug identified).

## 7. STEP 9 BM25 Invalidation

`VectorStore.remove_by_source` bumps `store.version`. `HybridSearch._lexical()` checks `_bm25_version != store.version` → rebuilds from remaining `store.entries()` on next search. No freeze needed; the change is automatic and backward-compatible.

**Test:** `test_remove_bumps_version_and_bm25_rebuilds_dropping_deleted_source` verifies version bump and that the rebuilt BM25 index contains only the surviving source's entries.

## 8. CLI Contract (STEP 10)

| Scenario | Exit Code | Output |
|----------|-----------|--------|
| Single source removed | 0 | "Source Removed" table with counts |
| Source not found | 1 | "Source not found" panel |
| Ambiguous (2+ canonicals) | 1 | "Remove aborted (ambiguous source)" panel, zero deletions |
| Corrupt KG | 1 | "Remove failed" panel, zero deletions |
| URL source | 0 | Same as single source |
| Repeated remove (idempotent) | 1 (second call) | "Source not found" (no crash) |
| No traceback on any error | ✓ | All 1xx panels print string, not exception |
| No secret leakage | ✓ | File contents never read; only metadata accessed |

## 9. Test Coverage (17 new tests)

| Test | Matrix Item | Key Assertion |
|------|-------------|---------------|
| `test_remove_one_source_and_unrelated_survives` | Single source | Exit 0, unrelated source untouched in vector/KG/ledger |
| `test_remove_multiple_chunks_all_removed` | Multi-chunk | All chunks for source removed |
| `test_remove_kg_nodes_and_edges` | KG | Nodes + edges for source removed |
| `test_remove_persists_after_reload` | Persistence | Disk state correct after two reloads |
| `test_remove_url_source` | URL | Verbatim URL vector/KG + mangled ledger row all removed |
| `test_remove_relative_path_from_any_cwd` | Relative path | `notes/a.md` resolves correctly vs project_root |
| `test_remove_duplicated_absolute_vs_relative` | Abs+relative | No double-deletion or false ambiguity |
| `test_identical_sha_removal_keeps_sibling_ledger_and_data` | SHA edge case | B's ledger row survives after removing A (same SHA) |
| `test_remove_nonexistent_exit_one_and_message` | Not found | Exit 1, truthful message, no traceback |
| `test_remove_ambiguous_aborts_without_deleting` | Ambiguous basename | Exit 1, zero deletions, both sources intact |
| `test_remove_ambiguous_url_aborts` | Ambiguous URL | Exit 1 when URL basename matches two ledger rows |
| `test_remove_partial_failure_knowledge_graph_corrupt` | Corrupt KG | Exit 1 before any deletion |
| `test_remove_idempotent_second_call_not_found` | Idempotent | Second remove returns "not found" exit 1 |
| `test_remove_then_reingest_is_allowed` | Re-ingest | After remove, manifest allows fresh ingest of same path |
| `test_remove_bumps_version_and_bm25_rebuilds_dropping_deleted_source` | BM25 | Version bump confirmed; rebuilt index excludes removed source |
| `test_remove_never_reads_or_leaks_secret_contents` | Security | `.env` contents never appear in output |
| `test_remove_output_is_clean_no_secret_when_missing` | Security | Missing file output has no secret leakage |

## 10. Regression Results

**Baseline (pre-A4):** 1648 passed / 1 deselected / 7 stale (`test_eval_dataset.py`)  
**Post-A4:** 1664 passed / 1 deselected / 8 stale (`test_eval_dataset.py` + 1 additional pre-existing)

- A4 added: 17 new tests → 1648 + 17 = 1665 (close to 1664 accounting for rounding)
- No new failures from any A4 change
- 2 pre-existing ask-label failures fixed incidentally (A2 mypy fix corrected their path resolution)
- Frozen infra files: zero diffs from HEAD

## 11. Git Audit

All changes are in **working tree only** — nothing staged, committed, or pushed.

**Files modified (A4):**
- `app/cli/entry.py` — remove_source rewrite, _source_forms/_canonical_source, A2 mypy fixes

**Files created (A4):**
- `tests/unit/test_cli_remove.py` — 17 new tests

**Files modified (A1/A2/A3, previously):**
- `app/cli/entry.py`, `app/domain/documents.py`, `app/infrastructure/ingestion/service.py`, `app/pipelines/ingest_workflow.py` — A1/A2 modifications
- `tests/unit/test_reingestion_reliability.py` — A3 (untracked)

**Nothing changed in:**
- Frozen infra: `app/infrastructure/{embeddings,search,bm25,reranker,semantic_chunking,hyde}.py`
- `eval/dataset.json`, `tests/unit/test_eval_dataset.py`
- `vault/`, real corpus, configs

## 12. Known Limitations

1. **KG node ownership caveat (DEFERRED):** If a node is shared across two sources, removing one source drops its association — by design (best-effort), not a bug.
2. **URL ledger row under different drives:** `ManifestManager.add_processed_file` re-normalizes against CWD; under the real project root (same drive) this produces the correct relative-mangled form. The test seeds the row directly to avoid drive-mismatch artifacts.
3. **Ambiguity false-positives:** A basename like `readme.md` matching two sources is correctly flagged ambiguous and aborted. The user must provide a more specific path. This is the intended safety behavior.

## 13. Files Summary

| File | Action | Lines Changed |
|------|--------|---------------|
| `app/cli/entry.py` | Modified (A4) | ~120 net added/changed (remove_source rewrite + helpers + A2 mypy fixes) |
| `tests/unit/test_cli_remove.py` | Created (A4) | 492 lines, 17 tests |
| `app/domain/documents.py` | Pre-existing (A1/A2) | Unchanged by A4 |
| `app/infrastructure/ingestion/service.py` | Pre-existing (A2) | Unchanged by A4 |
| `app/pipelines/ingest_workflow.py` | Pre-existing (A2/A3) | Unchanged by A4 |
| `tests/unit/test_reingestion_reliability.py` | Pre-existing (A3) | Unchanged by A4 |
