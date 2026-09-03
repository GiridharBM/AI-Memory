# PHASE 6H — INGESTION LIFECYCLE HARDENING — IMPLEMENTATION REPORT

**Status:** COMPLETE (implementation + tests + regression) — awaiting approval
**Reference:** `44_PHASE_6G_APPLICATION_PRODUCTION_READINESS_DISCOVERY.md` (approved)
**Head:** `9f282b4` (unchanged throughout Phase 6H — nothing committed)

---

## 1. OBJECTIVE — IMPLEMENTED

Implement the highest-priority ingestion lifecycle hardening identified by
Phase 6G, in four scoped areas:

- **A. Source-scoped cleanup on re-ingestion** — IMPLEMENTED
- **B. Per-source delete/rebuild capability** — IMPLEMENTED
- **C. Truthful status reporting** — IMPLEMENTED
- **D. Secret-ingestion guard** — IMPLEMENTED

Phase 6I **not** started. Retrieval **not** optimized. No commit/push.

---

## 2. PRE-CHANGE STATE — VERIFIED

Frozen baseline recorded at STEP 1 (all verified against HEAD `9f282b4`):

| Item | Value |
|------|-------|
| Corpus | 195 chunks / 24 distinct sources |
| Manifest ledger | 37 processed / 0 skipped / 0 failed |
| Knowledge graph | 387 nodes / 1464 edges |
| Queue | 0 pending |
| `vault/Notes` | 231 files = 25 with source frontmatter + 206 placeholder stubs |
| Eval dataset | v3.0 / 199 queries (frozen) |
| reranker / hyde / answerability | disabled |
| min_cosine | 0.45 |
| qa.timeout_seconds | 120 |
| OLLAMA_CONTEXT_LENGTH | 8192 / qwen3:8b 100% GPU |

Backups of all runtime manifests created at
`data/manifests/backups/6h_20260831_132933/` (vector_store, processed_files,
processed_files.corrupted, knowledge_graph, queue_state). All under
gitignored `data/` — no git pollution.

---

## 3. SOURCE OWNERSHIP MODEL — VERIFIED

Traced how a source is identified across every subsystem (STEP 2):

| Subsystem | Ownership key | Canonical form |
|-----------|---------------|----------------|
| Vector store (`VectorEntry.source`) | absolute path | `str(resolved_path)` for files; URL verbatim for remote |
| Knowledge graph (`KnowledgeNode.source`) | absolute path | `str(resolved_path)` / URL verbatim |
| Manifest ledger (`processed_files.json`) | `original_path` + `sha256` | project-relative normalized path |
| Generated notes (frontmatter `source`) | absolute path | `str(resolved_path)` |
| Queue / ingestion ledger | per-record | n/a |

**Key finding:** the vector store / KG key on absolute paths while the manifest
keys on project-relative paths. Source-scoped operations must therefore match
BOTH forms. A helper `_source_forms(source, project_root)` canonicalizes a
single user-supplied argument (absolute, relative, or URL) into the candidate
set, and `_manifest_entry_matches` resolves paths to match ledger entries.

**Documented limitations:**
- KG node ownership is best-effort. `KnowledgeGraph.add_node` overwrites a
  same-id node (last writer wins `source`); edges do **not** carry a source. A
  shared concept/entity node label across two sources is attributed to whichever
  source ingested it last. Removing one source therefore removes only what its
  **last** ingest contributed — documented, accepted.
- No source is unreachable: `_source_forms` covers absolute, relative, resolved,
  and URL forms so a delete always finds its targets.

---

## 4. RE-INGESTION DESIGN — IMPLEMENTED (STEP 3)

`IngestionWorkflow._run_knowledge_engine` (`app/pipelines/ingest_workflow.py`):

When source X is re-ingested **successfully**:

1. `remove_by_source(str(document.source))` drops every old vector chunk of X.
2. `remove_by_source` bumps `VectorStore.version`, so the lazy BM25 index in
   `HybridSearch._lexical()` rebuilds on next use (no stale corpus).
3. KG rebuild: on success, `existing.remove_source(X)` then merge + save.
4. Replace via `add_batch` + single `save()` (atomic tmp + os.replace).
5. Manifest/ledger updated by the caller.

**Failure atomicity (CRITICAL contract):** removal is **gated on full embed
success** (`outcome.embedding_succeeded and entries`). If the replacement
source fails to embed/index, **nothing is removed** — the old known-good chunks
+ KG nodes/edges are preserved and the failure is surfaced (`outcome.succeeded
= False`) for retry. Verified by tests.

---

## 5. DELETION DESIGN — IMPLEMENTED (STEP 4)

New CLI command `pam remove <source>` (`app/cli/entry.py`):

- Identifies the source deterministically via `_source_forms`.
- Removes vector chunks (`VectorStore.remove_by_source` per target form, then
  save).
- Removes KG nodes/edges (`KnowledgeGraph.remove_source` — see §7) then saves.
- Removes matching manifest ledger entries (`_manifest_entry_matches`).
- Reports counts: chunks, KG nodes, KG edges, ledger entries removed.
- **Does NOT** delete vault notes (may hold user-written content) and there is
  **no** "remove everything" operation. Explicit source identification required.
- BM25 consistency: version bump → lazy rebuild.

**`KnowledgeGraph.remove_source(source) -> (nodes, edges)`**
(`app/domain/knowledge_graph.py`): removes nodes whose `source` field equals the
target plus all incident edges; returns counts; empty/absent source is a no-op;
unrelated sources untouched.

---

## 6. STATUS SEMANTICS — IMPLEMENTED (STEP 5)

`pam status` rewritten to be truthful. Placeholder note stubs are **no longer
reported as real notes**.

New semantics:
- **Sources indexed** — distinct `source` values in vector store.
- **Indexed chunks** — count of `entries` in vector store (`unavailable` if
  unreadable — never a fabricated 0).
- **Successful ingests / Skipped duplicates / Failed** — from the **durable
  ledger** (manifest), not reset-on-restart runtime counters.
- **Retryable pending** — count of `failed` ledger entries (surfaced for retry).
- **Last ingestion** — most recent `processed`/`skipped_duplicate` timestamp.
- **Real generated notes** — vault notes with a `source` frontmatter.
- **Placeholder notes** — vault notes with `source_type: placeholder`
  (visibility marked, not counted as real).
- **User/other notes** — no source frontmatter and not a placeholder.
- **Ollama / Model / Vault / Logs** — unchanged.

Verified live (read-only) against real state:

```
Sources indexed      24   Vector store
Indexed chunks      195   Vector store
Successful ingests   37   Durable ledger
Placeholder notes   206
Real generated notes 25
Retryable pending     0   Failed entries
Last ingestion  2026-08-27T04:03:17Z
```

These match the frozen baseline exactly (24 sources / 195 chunks / 37
processed / 25 real + 206 placeholder).

---

## 7. SECRET-INGESTION POLICY — IMPLEMENTED (STEP 6)

`DocumentIngestionService._ingest_source` (`app/infrastructure/ingestion/service.py`)
blocks obvious secret-bearing files via `is_secret_bearing()` + `BlockedSourceError`.

Scope (deliberate, documented):
- `.env` and `.env.*`
- Extensions: `.pem .key .ppk .p12 .pfx`
- Basenames: `credentials credential secret secrets passwd shadow htpasswd`
  (+ `.txt` variants)
- **Deliberately NOT blocked:** `.db .sqlite .yaml .json` — these are legitimate
  data sources (validated DB ingest test preserved). Also not blocked: normal
  educational docs, PDFs, DOCX, Markdown, images, audio.

Happens **BEFORE** size check / ingestor selection / any reading → secret
contents never enter memory, **logs**, vectors, or KG. Reason message only
names the file, never its contents. Remote (URL) sources always pass (guard
targets local files).

`is_secret_bearing()` is pure/deterministic (tested twice for determinism).

---

## 8. FAILURE / ATOMICITY BEHAVIOR — VERIFIED (STEP 7)

All modified ingestion paths audited:

| Scenario | Behavior | Atomicity |
|----------|----------|-----------|
| Unsupported file | raises `IngestionError`, ledger records failed | atomic |
| Blocked secret file | `BlockedSourceError`, no read, no chunks, no KG, no partial writes | atomic |
| Embedding failure | `embedding_succeeded=False`, 0 chunks stored, **prior data preserved** | atomic |
| Vector-store failure | exception → `embedding/indexing` flags False, prior data preserved | atomic |
| KG failure | logged, graph step skipped; does not corrupt vector data | atomic per file |
| Duplicate source | ledger dedup (`skipped_duplicate`), no re-write | atomic |
| Re-ingestion failure | old known-good chunks/nodes preserved (gate on embed success) | atomic |
| Retry | re-invocation re-ingests; on success replaces cleanly | atomic |

**Documented limitation (not claimed as fully transactional):** the vector store
and knowledge graph are persisted to **separate files**. A crash between the
vector-store `save()` and the KG `save()` leaves the vector index updated but the
KG stale. This is a cross-file, non-atomic boundary inherent to the current
architecture. Rollback (§15) and the STEP 1 backups recover cleanly. This exact
limitation is documented rather than hidden.

---

## 9. IMPLEMENTATION CHANGES

| File | Change |
|------|--------|
| `app/pipelines/ingest_workflow.py` | `KnowledgeEngineResult`; re-ingest gating; KG rebuild-on-success; engine flags surfaced on result |
| `app/infrastructure/vector_store.py` | `remove_by_source(source) -> int` + version bump → BM25 rebuild |
| `app/domain/knowledge_graph.py` | `remove_source(source) -> (nodes, edges)` |
| `app/cli/entry.py` | `pam remove <source>`; truthful `status()`; helpers `_source_forms`, `_manifest_entry_matches`, `_note_counts`, `_last_ingestion`, `_frontmatter_value`, `_indexed_sources`, `_indexed_chunks`, `_placeholder_style` |
| `app/infrastructure/ingestion/service.py` | `is_secret_bearing()`, `BlockedSourceError`, guard call in `_ingest_source` |
| `tests/unit/test_ingestion_lifecycle.py` | **NEW** — 20 focused 6H tests |
| `tests/unit/test_cli.py` | Updated status-row assertions (6H-required: "Generated notes" → "Real generated notes" semantics) |
| `tests/unit/test_ingest_engine_outcome.py` | Updated partial-embedding assertion (stored 1 → 0, 6H atomicity) |
| `tests/unit/test_ingestion.py` | `test_ingests_env_file` → `test_env_file_preserved_and_rejected_by_secret_guard` |

No changes to retrieval algorithm files (§11).

---

## 10. TESTS — PASS

New focused file `tests/unit/test_ingestion_lifecycle.py` (20 tests) covering
all 15 required scenarios (STEP 8):

1. same-source re-ingest replaces old chunks ✓
2. unrelated source untouched ✓
3. failed replacement preserves old data ✓
4. source deletion removes only selected source ✓
5. deleting nonexistent source is safe ✓
6. BM25 consistency (version bump → rebuild) ✓
7. KG cleanup/rebuild ✓
8. truthful status counts ✓
9. placeholder not counted as real ✓
10. `.env` blocked ✓
11. secret-bearing file blocked ✓
12. blocked file creates no chunks ✓
13. blocked file creates no KG entries ✓
14. retry after legitimate failure works ✓
15. duplicate ingestion stays deduplicated ✓

Plus: partial-embedding stores nothing (atomicity), kg delete safety,
determinism, service-level .env rejection, frontmatter parsing.

All destructive lifecycle tests use **temporary isolated in-memory stores** —
the real corpus is never touched (STEP 10).

---

## 11. REGRESSION RESULTS — PASS

Full unit suite (excluding the known-stale eval file):
- **1558 passed, 1 deselected, 0 failed**
- Coverage: **88.03%** (gate `fail-under=80` satisfied); 6H-touched modules:
  `vector_store.py` 98%, `ingest_workflow.py` 77%, `search.py` 89% (frozen, unmodified).

`tests/unit/test_eval_dataset.py`: **7 pre-existing stale failures** (v2.0
assertions vs frozen v3.0 dataset) — expected, **left unchanged**, not 6H work.

Existing CLI smoke tests pass (`test_cli.py`, including the updated durable-ledger
and note-count tests).

---

## 12. CORPUS SAFETY — VERIFIED (STEP 10)

- **No** real-corpus re-ingestion performed.
- **No** real source deleted.
- All destructive lifecycle tests ran against isolated temporary stores.
- Only live-corpus operations were the read-only `pam status` and config/ownership
  inspections.

---

## 13. RETRIEVAL FREEZE — VERIFIED (STEP 11)

No changes introduced by Phase 6H to: `embeddings.py`, vector-store retrieval
behavior, `search.py` algorithm, `hybrid_search.py`/`bm25.py`, RRF, chunking,
`reranker.py`, HyDE, answerability, or `eval/dataset.json`.

Config verified frozen: `reranker.enabled=false` (L178),
`hyde.enabled=false` (L186), `answerability.enabled=false` (L191),
`qa.timeout_seconds=120`, `min_cosine=0.45`.

---

## 14. KNOWN LIMITATIONS — PARTIAL

1. **Cross-file non-atomicity** — vector store & KG saved separately; a crash
   between saves leaves them inconsistent (§8). Documented; backups/rollback
   cover it. No silent partial writes within a single file.
2. **KG shared-node ownership** — last-writer-wins on same-id concept/entity
   nodes; a shared node can be attributed to the wrong source (§3).
3. **Status "unavailable" vs zero** — vector-store read failures report
   `unavailable` rather than a misleading 0; this is intentional, not a bug.
4. Secret guard is heuristic (name/extension based) — a secret inside a
   normally-named file is out of scope by design.

---

## 15. ROLLBACK PROCEDURE

All Phase 6H changes are **uncommitted** on top of frozen HEAD `9f282b4`. Two
recovery paths:

- **Code:** `git checkout -- <6H files>` (or `git stash`), then re-run tests.
- **Data:** restore the 5 runtime manifests from
  `data/manifests/backups/6h_20260831_132933/` if any live-corpus operation had
  been run (none destructive was run in this phase).

---

## 16. FINAL VERDICT

- **All four scope areas: A (re-ingestion), B (delete), C (status), D (secret
  guard) — IMPLEMENTED / PASS**
- Failure atomicity contract — **VERIFIED**
- Focused 6H tests — **PASS** (20 new)
- Full regression — **1558 passed / 0 failed**, 88% coverage
- Real-corpus safety — **VERIFIED** (read-only only)
- Retrieval freeze — **VERIFIED**
- Known limitations — documented (cross-file atomicity, KG node ownership)

Phase 6H is complete and ready for review. **Nothing committed, pushed, or
released.** No Phase 6I work started.

**STOP — awaiting explicit approval.**
