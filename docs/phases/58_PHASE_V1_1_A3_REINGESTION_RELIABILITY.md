# Phase V1.1-A3 — Re-Ingestion Reliability Hardening

Status: **COMPLETE — NO CODE CHANGE REQUIRED** · Objective: VERIFIED

## 1. Objective
Harden the existing re-ingestion lifecycle. **Primary invariant: a failed
re-ingestion MUST NOT destroy or replace previously known-good data for that
source; a successful re-ingestion SHOULD atomically replace the previous
representation as far as the current architecture safely permits.** Duplicates
must stay deduplicated; retryable failures must stay retryable. Reliability
hardening only — implement only if a concrete defect exists, plus tests/docs.

## 2. Current lifecycle
The e2e path is: dedup gate (`ManifestManager.contains_successful_hash`) →
`DocumentIngestionService.ingest` → `DocumentProcessor`/AI analysis →
`IngestionWorkflow.run` → `_process_document` → `_run_knowledge_engine`
(re-chunk → re-embed → re-store → rebuild graph → cross-links) → note writer →
ledger `add_processed_file`. Re-ingestion means the same source (same or
modified file) is dropped again; the manifest gate decides skip-vs-reprocess by
content hash.

## 3. Source replacement mechanism
- **Vector store** (`_run_knowledge_engine`, ~lines 987–998): on a successful
  re-ingest of source X, `VectorStore.remove_by_source(str(source))` drops every
  prior chunk owned by X (`vector_store.py:94`), then `add_batch(entries)` and
  `save()`. Removal is gated on `outcome.embedding_succeeded and entries`, so a
  failed embed never removes old data. `remove_by_source` bumps `version` so the
  BM25 index (`HybridSearch`) rebuilds on next use.
- **Knowledge graph** (~lines 1023–1038): when `outcome.succeeded`, load the
  persisted graph, `remove_source(str(source))` (`knowledge_graph.py:66`), merge
  the new subgraph, and `save()` atomically. Unrelated sources are untouched.
- **Persisted disk state** is the true invariant holder: `save()` writes a
  `*.tmp` then `os.replace()` (atomic on the same filesystem), so a crash
  between remove+add and `save()` leaves the previous file intact; the in-memory
  mutation is discarded on restart.

## 4. Reliability invariants (A3 STEP 3)
1. **Success replaces atomically** — remove-by-source + add + atomic `save()`.
   VERIFIED.
2. **Embedding failure preserves old data** — `remove_by_source` gated on full
   embed success; on exception `embedding_succeeded=False`, nothing stored.
   VERIFIED.
3. **Indexing/save failure preserves old data** — in-memory add happens, but an
   exception before `os.replace` leaves the prior file on disk; reload recovers
   old data. VERIFIED.
4. **KG failure = partial-success semantics** — vector still commits (chunks are
   the retrieval source of truth); graph failure sets `graph_succeeded=False`
   only, never destoys prior persisted graph. VERIFIED.
5. **Duplicate stays deduplicated** — ledger `contains_successful_hash` gate plus
   id-overwrite dedup in `add_batch`. VERIFIED.
6. **Retry stays retryable** — failed ledger entries excluded from hash dedup
   (`contains_successful_hash`, `manifest.py:93`); worker treats partial-index as
   FAILED for requeue. VERIFIED.
7. **Unrelated-source isolation** — vector and graph removal are keyed on
   `source` only. VERIFIED.

## 5. Success analysis — VERIFIED
Clean re-ingest of a modified source replaces prior chunks byte-for-byte at the
persistence boundary: `test_reingest_modified_source_replaces_cleanly_on_disk`,
`test_reingest_shrink_removes_stale_chunks_on_disk`,
`test_reingest_grow_has_no_duplicates_on_disk`.

## 6. Embedding-failure analysis — VERIFIED
`embed_batch` raising preserves prior persisted chunks:
`test_embedding_exception_preserves_prior_data_on_disk`. Partial embeddings
(boundary: `all(emb.embedding)`) store nothing and preserve prior data:
`test_partial_embedding_preserves_prior_data_on_disk`.

## 7. Indexing-failure analysis — VERIFIED
A `save()` exception after in-memory add leaves the prior file on disk
(`os.replace` never reached); reload recovers old data:
`test_indexing_save_failure_preserves_prior_data_on_disk`.

## 8. KG-failure analysis — VERIFIED
A graph-build failure sets `graph_succeeded=False` without touching the prior
persisted graph: `test_kg_failure_preserves_prior_graph_on_disk`. A failed
*vector* ingest also leaves the graph untouched (KG gated on `outcome.succeeded`):
`test_failed_vector_ingest_leaves_graph_untouched_on_disk`.

## 9. Duplicate — VERIFIED
`add_batch` overwrites by `entry.id`; no duplicate chunk ids survive a re-ingest
(`test_reingest_grow_has_no_duplicates_on_disk`), and the ledger gate stays hash-
keyed so unchanged drops are skipped.

## 10. Retry — VERIFIED
Failure→success sequence replaces cleanly with no stale chunks:
`test_retry_after_failure_replaces_cleanly_on_disk`.

## 11. Stale-chunk — VERIFIED
A shrink re-ingest removes orphaned chunks owned by the source on disk
(`test_reingest_shrink_removes_stale_chunks_on_disk`); crash-before-save does not
leak them (`test_in_memory_mutation_not_persisted_without_save`).

## 12. Unrelated-source isolation — VERIFIED
Vector: only `source`-owned entries removed. Graph: `remove_source` scoped to one
source, verified by `test_kg_success_replaces_source_nodes_and_keeps_others`.

## 13. SHA identity edge case (A3 STEP 5) — VERIFIED
Two identical-content files in different paths share one SHA. Dedup is keyed on
hash at the ledger gate; *store identity remains path-scoped* (replacement keys
on `source`, the ingested path). Safe because a re-ingested file is processed
under its own path, and `remove_by_source` targets that path's chunks only.
Verified by `test_identical_hash_different_path_dedups_safely`. No identity
redesign needed.

## 14. Non-atomic persistence review (A3 STEP 6) — DEFERRED
Vector store and knowledge graph persist as two separate files; their writes are
not mutually atomic. This is a **known limitation**, not a concrete correctness
bug found in the exercise: each file's own write is atomic (`tmp`+`os.replace`),
and a crash between the two simply leaves the two stores at a prior consistent
point (each independently recoverable — `_load` skips malformed JSON). Fixing
cross-file atomicity requires a transactional/DB redesign, out of scope. Marker:
no transactional design introduced.

## 15. Implementation changes — NO CHANGE REQUIRED
Tracing and 13 new tests confirmed every invariant holds at the persistence
boundary. No production code was modified. Only a new test file was added.

## 16. Tests — IMPLEMENTED
New `tests/unit/test_reingestion_reliability.py` (13 tests) covering persistence-
level replacement, all failure-preservation modes, retry, crash semantics, KG
replacement, and the identical-SHA edge case. All pass; mypy strict and ruff
clean.

## 17. Regression — PASS
Focused suites (A3 + A2 CLI UX + lifecycle + duplicate + manifest + knowledge
engine + sources + outcome): 298 passed. Full unit suite: **1648 passed /
1 deselected / 7 failed** (all 7 = pre-existing stale `test_eval_dataset.py`,
unchanged). 0 NEW failures; baseline was 1635 + 13 new = 1648. ✅

## 18. Live validation — PASS
On isolated temp dirs: 3 chunks persist → failed re-ingest preserves all 3 →
successful shrink re-ingest replaces to 1 chunk, confirmed across store reloads.
Real corpus untouched.

## 19. Security — PASS
No A3 change to `is_secret_bearing`/`BlockedSourceError`/`_failure_category`.
Secret-guard regression green (A2 CLI UX + lifecycle suites). Guard still blocks
before any chunk/KG write.

## 20. Retrieval freeze — PASS
No diff in `app/infrastructure/{embeddings,search,bm25,reranker,semantic_chunking,hyde}.py`.
Flags unchanged (`reranker.enabled=false`, `hyde.enabled=false`,
`answerability.enabled=false`, `min_cosine` unchanged).

## 21. Corpus safety — PASS
Tests and live checks use temporary stores only; real corpus/vault unmodified.

## 22. Git safety — PASS
Only new untracked file: `tests/unit/test_reingestion_reliability.py`. No
production change, nothing staged/committed/pushed. Working-tree tracked diffs
remain the pre-existing A1/A2 modifications.

## 23. Known limitations
- Vector + KG persistence not mutually atomic (STEP 6, DEFERRED).
- Graph node ownership is best-effort (shared labels attribute to last writer) —
  pre-existing, unchanged.

## 24. Final verdict
**VERIFIED / IMPLEMENTED (tests) / NO CODE CHANGE REQUIRED.** The re-ingestion
lifecycle already satisfies the primary invariant: failed re-ingestions preserve
prior known-good data at the persistence boundary; successful re-ingestions
replace atomically and keep duplicates deduplicated, retries retryable, and
unrelated sources isolated. The hardening value delivered is proof via 13
persistence-level edge-case tests plus documentation, closing the gap left by
the in-memory Phase 6H coverage.
