# Phase 5 Final Approval — Hybrid Retrieval (P5-101…P5-105)

**Phase:** Phase 5 — Retrieval Foundation, Hybrid Search, Ranking & Scoring, Query Processing, End-to-End Optimization
**Date:** 2026-08-09
**Audit type:** Independent final engineering approval — every gate re-executed against the live repository (prior per-task reviews re-verified, not trusted).
**Verdict:** **APPROVED**

---

## 1. Scope

Phase 5 delivers a deterministic, offline, hybrid retrieval capability as five additive milestones:

| Task | Deliverable |
|------|-------------|
| P5-101 | `app/infrastructure/bm25.py` — deterministic Okapi-BM25 sparse index (`k1=1.5`, `b=0.75`, pure stdlib) |
| P5-102 | `app/infrastructure/search.py` — reciprocal rank fusion (`_rrf_fuse`, k=60) fusing dense + BM25 |
| P5-103 | `tests/unit/test_scoring.py` — locks the roadmap 4.1 success criterion (keyword-exact beats high-semantic-similarity) |
| P5-104 | `SearchService` facade (`create_default` + `search`) and `pam search` CLI command |
| P5-105 | Optimization — precomputed entry norms, version-keyed BM25 cache, deterministic ordering, exact-match filtering, additive span fields, resilient fallback |

Deliberately deferred (roadmap §4, recorded, not shipped): 4.3 cross-encoder re-ranking, 4.4 query rewriting, 4.6 parent-child retrieval (the `parent_section` slot exists but stays `None`), and the `$in`/range filter syntax of 4.5 (exact-match shipped).

## 2. Verification Checklist (20-point audit)

| # | Item | Status | Evidence (verified live) |
|---|------|--------|--------------------------|
| 1 | Frozen-spec compliance | PASS | `SearchService.search(query, *, top_k=5, filter=None, min_score=0.0) -> list[SearchHit]` matches MEDD §7.6 exactly (`search.py:252`); `SearchHit` (`search.py:18`) is a superset of the frozen shape (adds `source_type`/`chunk_index`/`start_char`/`end_char`/`metadata`). |
| 2 | Acceptance criteria | PASS | Roadmap §4.1/4.2/4.7 DELIVERED, §4.5 PARTIAL, §4.3/4.4/4.6 deferred — all row statuses updated in `05_Development_Roadmap.md` this session; §4.1 success criterion proven by `test_scoring.py`. |
| 3 | Retrieval architecture | PASS | Dense cosine (`VectorStore.search`) + sparse BM25 (`bm25.py`) → RRF k=60 (`_rrf_fuse`) → exact-match filter → min_score → top_k. No new modules beyond the retrieval stack. |
| 4 | Runtime wiring | PASS | `SearchService.create_default(settings)` (`search.py:224`) reads the same `manifest_root/vector_store.json` the ingest pipeline writes and embeds via the configured model (`models.embeddings`, `config.py:200`, pre-existing); live probe through production wiring returned correct ranked hits. |
| 5 | Query processing | PASS | `pam search` (`entry.py:361-410`) validates blank query (exit 1), `--top-k >= 1` (exit 2), `--filter` JSON (exit 1); merges `--source-type` + `--filter` via `_parse_search_filters`; Rich table output; service failure → exit 1. 8 CLI tests cover every path. |
| 6 | Candidate generation | PASS | `HybridSearch.search` (`search.py:148`) fetches `pool_size = max(top_k*5, 50)` per leg; dense leg uses precomputed norms; BM25 leg uses the version-cached index. |
| 7 | Hybrid retrieval | PASS | RRF fuses dense + BM25 candidate sets; a hit present in only one source still ranks via `1/(k+rank)`; verified by scoring tests and live probe. |
| 8 | Scoring | PASS | BM25 (k1=1.5, b=0.75) deterministic `(-score, doc_index)` tie-break; cosine via `dot/(norm_q*norm_d)` matching `_cosine_similarity` semantics (dim mismatch / zero vector → 0.0, kept when `min_score<=0`). |
| 9 | Ranking | PASS | Fusion output sorted by `(-rrf_score, entry_id)`; `VectorStore.search` sorted by `(-score, entry.id)`; final results truncated to `top_k`. |
| 10 | Determinism | PASS | Live probe: repeated queries return identical `(entry_id, score)` sequences; `_rrf_fuse` sorted by `(-score, entry_id)`; BM25 tie-break deterministic; corpus-order independent. |
| 11 | Metadata preservation | PASS | `_to_hit` (`search.py:38`) carries `source`, `source_type`, `chunk_index`, `start_char`, `end_char`, full `metadata`; `parent_section` from `metadata["parent_section_id"]`; verified in unit tests and live probe. |
| 12 | Filtering | PASS | `_matches_filter` (entry field wins, then metadata key) in `VectorStore.search(filters=...)` and `_hit_matches_filter` in `SearchService.search(filter=...)`; live probe returned only matching `source_type`. |
| 13 | Result limits | PASS | `top_k` honored (`<=0` → `[]`); `min_score` applied after fusion; live probe: `top_k=2` → ≤2 hits, `min_score=0.99` → 0 hits. |
| 14 | Empty-query behavior | PASS | Blank/whitespace query → `[]` without calling the embedder (unit test asserts embedder not called); CLI blank → exit 1. |
| 15 | No-result behavior | PASS | Unknown-term query → `[]`; CLI prints "No results found." (exit 0); missing persisted store → `[]`. |
| 16 | Error/fallback behavior | PASS | Embedder failure/`None` → lexical-only (BM25); BM25 build failure → dense-only with cache reset (no poisoning, self-heals); verified by monkeypatch tests AND a live probe patching `BM25Index.__init__` to raise (graceful dense-only + recovery). |
| 17 | Performance behavior | PASS | 20k-corpus steady state: query 223→71 ms (3.1×), dense leg 115→51 ms (2.3×), peak memory 25.4→1.8 MB/query (14×). |
| 18 | Backward compat (Phase 1–4) | PASS | Additive-only; regression — full suite 1384 passed / 0 failed (Phase 4 baseline 1273 + 111); non-retrieval unit run 1282 passed / 0 failed. `SemanticSearch` retained (still used by `_find_cross_document_links`, `ingest_workflow.py:1007`). |
| 19 | Rollback / feature-disabled | PASS | No new config toggles; removing `bm25.py` + RRF/facade additions + CLI command restores pre-Phase-5 behavior; `_load` tolerates missing `start_char`/`end_char` (pre-Phase-5 stores load unchanged); BM25 failure at runtime degrades gracefully (no hard dependency). |
| 20 | Public API compatibility | PASS | `SearchService.search` signature matches MEDD §7.6 verbatim; `SemanticSearch`/`HybridSearch` remain importable (back-compat); `VectorStore.search` gains optional `filters=` kwarg (additive); `VectorEntry` gains optional fields (additive). |

## 3. Implementation Summary

- **P5-101** — `app/infrastructure/bm25.py`: `BM25Index` with tokenization, term-frequency/IDF scoring, `k1=1.5`, `b=0.75`, deterministic `(-score, doc_index)` tie-break.
- **P5-102** — `_rrf_fuse(ranked_lists, k=60)` in `search.py` replaces the old weighted-sum `HybridSearch`; fused dense + BM25.
- **P5-103** — `tests/unit/test_scoring.py`: keyword-exact-over-semantic-similarity, BM25-over-baseline ordering, RRF fusion correctness, metadata preservation.
- **P5-104** — `SearchService` (`create_default` + `search`) + `pam search` CLI with full validation and Rich rendering; `VectorEntry.start_char`/`end_char` (additive, persisted).
- **P5-105** — precomputed `_norms`, `store.version` counter + version-keyed BM25 cache in `HybridSearch._lexical`, deterministic ordering, exact-match `_matches_filter`/`_hit_matches_filter`, graceful dual-leg fallback with cache reset.

## 4. Verification (gates re-run this session)

| Gate | Command | Result |
|------|---------|--------|
| Full unit suite | `python -m pytest -q` | **1384 passed / 0 failed / 59 deselected** |
| Phase 1–4 regression | `python -m pytest -q tests/unit --ignore test_query_pipeline --ignore test_bm25 --ignore test_scoring` | **1282 passed / 0 failed / 1 deselected** |
| Retrieval-specific | `pytest test_query_pipeline.py test_bm25.py test_scoring.py test_query_pipeline_integration.py` | **73 passed / 0 failed** |
| Full integration | `python -m pytest -q -m integration` | **57 passed / 1 skipped** (Tesseract env) / **1 failed** — live-Ollama smoke; re-run in isolation **passes** (known nondeterministic LLM-output flake, no retrieval code) |
| Ruff (Phase 5 src) | `ruff check bm25.py search.py vector_store.py (infra) vector_store.py (domain) entry.py` | **All checks passed** |
| Ruff (Phase 5 tests) | `ruff check` on the 5 Phase 5 test files | **All checks passed** |
| Mypy (Phase 5 core) | `mypy --follow-imports=skip` on the 4 retrieval modules | **Success: no issues found** |
| Coverage (retrieval modules) | `pytest --cov` over the retrieval suite | **bm25.py 100%, app/domain/vector_store.py 100%, search.py 89%, vector_store.py 88%** (misses: unreachable-error branches, cache-hit fast paths) |
| Coverage (repo-wide) | `pytest --cov=app` full suite | **90%** (TOTAL 7236 stmts / 725 miss; floor 80%) — **reached** |
| Live behavior probe | Script against production `create_default` wiring | empty/limit/min_score/no-result/determinism/filter **all pass**; BM25-build-failure → graceful dense-only + recovery **pass** |

## 5. Performance Evidence

Measured in P5-105 on a 20k-entry corpus (steady state, cache warm):

| Metric | Before | After | Gain |
|--------|--------|-------|------|
| End-to-end query latency | 223 ms | **71 ms** | **3.1×** |
| Dense leg (cosine) | 115 ms | **51 ms** | **2.3×** |
| Peak memory per query (tracemalloc) | 25.4 MB | **1.8 MB** | **14×** |

Root causes eliminated: per-query BM25 index rebuild (was ~41% of query cost, identical output each time — now rebuilt only on `store.version` change) and per-query norm recomputation (was ~58% of the dense leg — now precomputed on write).

## 6. Rollback Verification

- **Code:** additive-only — deleting `bm25.py`, the RRF/facade additions in `search.py`, the `VectorStore` optimization, and the `search` CLI command restores the pre-Phase-5 codebase. `VectorStore.search` semantics are identical for pre-Phase-5 persisted stores (spans default `None`).
- **Runtime:** BM25 build/search failure degrades to the surviving leg (no poisoned cache); verified live with a raising-constructor monkeypatch.
- **Data:** `VectorEntry.start_char`/`end_char` are optional; `_load` accepts their absence.
- **Config/Deps:** no new config keys, no new dependencies.

## 7. Changed-File Summary (Phase 5)

- **Created:** `app/infrastructure/bm25.py`; `tests/unit/test_bm25.py`; `tests/unit/test_scoring.py`; `tests/unit/test_query_pipeline.py`; `tests/integration/test_query_pipeline_integration.py`.
- **Modified (retrieval-only):** `app/infrastructure/search.py` (RRF, BM25 cache, `SearchService`); `app/infrastructure/vector_store.py` (norms, version, filters, deterministic order, span round-trip); `app/domain/vector_store.py` (+2 optional fields); `app/cli/entry.py` (search command + `_parse_search_filters`); `tests/unit/test_cli.py` (+8 search CLI tests).
- **No unrelated refactoring:** the diffs of all Phase 5 files are confined to retrieval functionality (verified file-by-file); no Phase 1–4 behavior modified.

## 8. Inspection

- **Temporary files:** none — probe/benchmark scripts were removed after use; no `*.tmp`/`*.bak`/`*.orig`/`*.rej`/bench/probe files in `app/`, `tests/`, `config/`.
- **Generated artifacts:** `data/manifests/*.json` are runtime outputs (integration-run state, incl. pre-existing `knowledge_graph.json`); `.gitignore` whitelists only `.gitkeep` there — pre-existing hygiene note, not a Phase 5 defect.
- **Stale docs:** MEDD §7.6, §2.9, roadmap §4 rows, and implementation-report §14/§15 all carried pre-Phase-5 "naive keyword / no BM25 / no CLI" text — **all corrected this session** (see §9).
- **Obsolete API references:** none — `SemanticSearch` is still a live API used by the ingest workflow; no dangling imports.
- **Accidental dependencies:** none — `pyproject.toml` diff shows only Phase 3/4 additions (`openpyxl`, `intelligence` extra); Phase 5 adds zero packages (BM25 is stdlib).
- **Config changes:** none from Phase 5 — `models.embeddings` (`config.py:200`) and the `embeddings: nomic-embed-text` YAML key predate Phase 5.
- **Secrets:** secret-pattern scan of the Phase 5 diff returned no hits.

## 9. Documentation Synchronization

Per the existing project convention (five deliverables only — no redundant milestone docs created):

- `docs/changelog.md` — added **0.11.0** entry (Phase 5).
- `docs/release_notes/v0.11.0-milestone-5.0.md` — created.
- `docs/01_Current_Implementation_Report.md` — §14 Vector Store and §15 Search rewritten to live state (incl. the still-live `SemanticSearch`).
- `docs/PHASE_5_DOCUMENTATION_SYNCHRONIZATION_REPORT.md` — created (alignment tables + stale-text corrections).
- `docs/MASTER_ENGINEERING_DESIGN_DOCUMENT.md` — version 0.11.0; version-history entry; §2.9 and §7.6 Current Implementation rewritten.
- `docs/05_Development_Roadmap.md` — §4.1/4.2/4.7 DELIVERED, §4.5 PARTIAL, §4.3/4.4/4.6 deferred (matching the MEDD 0.10.0 precedent of row-level status updates).

## 10. Known Non-Blocking Findings

1. **Pre-existing live-Ollama smoke flake** — `smoke_test.py::test_live_ollama_analysis_and_note_generation` failed one integration run and passed in isolation (nondeterministic LLM output); exercises no retrieval code.
2. **Tesseract OCR skip** — environmental, pre-existing.
3. **Full-repo mypy env block** — `numpy` stub syntax under the Python 3.14 interpreter prevents whole-repo runs; scoped runs over the four retrieval modules are clean (pre-existing since M3.1).
4. **Repo-wide ruff baseline** — pre-existing Phase 1–3 findings remain; zero new findings from Phase 5.
5. **Coverage fast-path misses** — `search.py` 89% / `vector_store.py` 88% reflect the BM25 cache-hit and unreachable-error branches, not a correctness gap (all scored/tested paths covered).
6. **Runtime manifests not gitignored** — `data/manifests/*.json` untracked runtime outputs; recommend `.gitignore` entry if manifests should stay out of VCS (pre-existing).
7. **Per-task atomic commits not yet made** — Phase 2–5 work remains uncommitted in the worktree (roadmap §8; consistent with M2.1–M4 convention).
8. **Roadmap phase-label offset** — the roadmap labels retrieval "Phase 4" while engineering tasks are P5-101..105; pre-existing naming offset, not introduced by this phase (roadmap rows reference the P5-xxx IDs).

---

## Verdict

Phase 5 (P5-101…P5-105) delivers the frozen MEDD §7.6 retrieval contract — a `SearchService` facade over hybrid dense + deterministic BM25 retrieval fused with reciprocal rank fusion (k=60), exact-match metadata filtering, a fully validated `pam search` CLI, and a 3.1× latency / 14× memory optimization — as strictly additive, deterministic, offline work with no new dependencies, no config surface, and no Phase 1–4 regressions. Every gate was independently re-executed against the live repository: **1384 unit + 57 integration tests pass (1 env skip; the sole integration failure is the known live-Ollama flake that passes in isolation), 90% repo coverage (retrieval modules 88–100%), zero ruff/mypy findings, fallback and rollback proven live, and all 20 audit points pass.** No blocking or recommended-to-block findings remain.

**Final Verdict: APPROVED**
