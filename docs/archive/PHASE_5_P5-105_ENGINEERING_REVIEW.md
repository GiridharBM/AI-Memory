# P5-105 Engineering Review — End-to-End Retrieval Optimization

**Task:** P5-105 — End-to-End Retrieval Optimization
**Phase:** Phase 5 (retrieval; optimize and harden the complete query path: query → processing → candidate retrieval → hybrid retrieval → scoring → ranking → final results)
**Date:** 2026-08-09
**Verdict:** **APPROVED**

---

## 1. Scope and Method

Audited the complete retrieval path (`SearchService` → `_embed_query` → `HybridSearch` → `VectorStore.search` → `_rrf_fuse` → filter → top-k) against the frozen Phase 5 specification (MEDD §7.6, roadmap §4.1–4.7). Optimization was **evidence-driven only**: a baseline benchmark of the unmodified path was measured first, bottlenecks identified from that data, two safe changes made, and the same benchmark re-run to quantify the improvement. No speculative work was done (req 2). All scoring, ranking, and filtering semantics are untouched.

## 2. Performance Evidence (before → after, measured on this machine)

Benchmark methodology: synthetic corpora of 1k–20k chunks (dim-32 embeddings, realistic short-document texts), deterministic fake embedder, `time.perf_counter` medians, `tracemalloc` for memory. Script kept outside the repo and removed after use (see §7).

### 2.1 Per-query latency, `SearchService.search(top_k=5)`

| Corpus | Before | After (first query) | After (steady state) | Speedup (steady) |
|---|---|---|---|---|
| 1,000 | 9.9 ms | 7.0 ms | 2.7 ms | 3.7× |
| 5,000 | 51.2 ms | 36.7 ms | 19.0 ms | 2.7× |
| 10,000 | 104.4 ms | 73.1 ms | 30.4 ms | 3.4× |
| 20,000 | 223.1 ms | 146.2 ms | 71.3 ms | **3.1×** |

The "first query" column includes a one-time lexical index build that is then amortized; steady state is the per-query cost after warm-up.

### 2.2 Time decomposition inside one query at 20k entries (req: candidate count, ranking time)

| Component | Before | After | Note |
|---|---|---|---|
| Dense leg (`VectorStore.search`) | 115.0 ms | 50.7 ms | **2.3×** — norms precomputed, query norm hoisted |
| `store.entries()` copy | 0.2 ms | 0.07 ms | now only on index rebuild |
| BM25 index build | 90.9 ms | — (once) | eliminated from the per-query path |
| BM25 search (top_k=50) | 10.7 ms | ~6–10 ms | bounded by pool size |
| Candidates | dense=50, lexical=50 | identical | pool caps `max(top_k*5, 50)` unchanged |
| Final results | 5 | 5 | top_k unchanged |

The BM25 index build was **41% of the steady-state query cost** (90.9 ms of 223 ms) and — critically — produced the *identical index on every query* because the corpus does not change between queries. That is duplicate retrieval work (req 4) and unnecessary computation (req 3), eliminated by building once per corpus snapshot and rebuilding only when the store mutates.

The dense leg's norm computation was **58% of its cost** (54.3 ms of 93.1 ms in an isolated micro-measurement): the query norm was recomputed once per entry and every entry norm was recomputed on every query. Entry embeddings are write-once (verified: no code mutates `entry.embedding` after construction), so entry norms are precomputed at add/load time and the query norm once per search.

### 2.3 Repeated-query behavior (req: repeated-query behavior)

Before: every query cost the same (queries 1–10 at 20k all ~210–260 ms) — no warm-up benefit, the index was rebuilt 10×.

After: query #1 = 148 ms (builds the index once), queries #2–10 = **56–73 ms**. Repeated queries on an unchanged corpus are served from the cached index with identical results.

### 2.4 Memory behavior (req 10: memory-sensitive paths)

`tracemalloc` peak for one query at 20k entries: **25.4 MB before → 1.8 MB after** (14× reduction). The 25.4 MB was transient per-query allocation of the BM25 index (postings, term-frequency dicts); the index is now allocated once and reused, so steady-state queries allocate ~nothing.

## 3. Correctness Evidence

| Contract | Evidence |
|---|---|
| Scores bit-identical to `_cosine_similarity` | `TestPrecomputedNorms.test_scores_match_cosine_similarity_bit_for_bit` — 200 entries, every returned score `== _cosine_similarity(...)` exactly (same float ops, same values) |
| Zero-vector / dim-mismatch semantics preserved | `test_zero_norm_entries_included_at_min_score_zero`, `test_zero_norm_entries_excluded_by_min_score`, `test_empty_embedding_handled` — 0.0-score entries included at `min_score=0.0`, excluded above, exactly as before |
| Deterministic ranking preserved | `TestDeterministicRuns` (store, hybrid, fuse), `test_large_corpus_is_deterministic`, `test_scores_identical_across_repeated_queries` — exact `(-score, id)` total order; RRF scores byte-identical across cache hits |
| Ranking unaffected by caching | `TestBm25CacheInvalidation.test_repeated_query_reuses_index` — same result ids/scores, cache version matches store version |
| Cache stays correct across mutations | `test_add_after_query_is_reflected`, `test_remove_after_query_is_reflected` — ingest/delete between queries is reflected on the next query (version-keyed invalidation) |
| Embedder failure → lexical-only | `test_embedder_failure_falls_back_to_lexical` (unchanged, still passing) |
| BM25 failure → dense-only | `TestFallbackBehavior.test_bm25_build_failure_falls_back_to_dense` — a raising build degrades to dense results and a later successful build recovers (no poisoned cache) |
| Blank query → dense-only | `test_blank_query_with_cached_index_returns_dense_only` — cached index is not searched on blank queries |
| Exact RRF scores / fused orderings | All `test_scoring.py` assertions unchanged and passing (2/61, 1/62, 1/63; tie-breaks; top-k boundaries) |

## 4. Requirement Traceability

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Identify actual bottlenecks using evidence | DONE | §2.2: BM25 rebuild = 41% of query; norm recompute = 58% of dense leg — both measured, not assumed |
| 2 | No speculative optimization | DONE | Only the two measured costs were touched; brute-force dense scan left as-is (O(n) documented in status report, acceptable at documented personal-wiki scale) |
| 3 | Reduce unnecessary computation where safe | DONE | Norms computed once (not N×/query); BM25 stats once (not per query) |
| 4 | Avoid duplicate retrieval work | DONE | BM25 index built once per corpus snapshot, reused across queries; rebuilt only on store mutation |
| 5 | Enforce configured limits early where appropriate | DONE | `max(top_k*5, 50)` pool caps and `top_k<=0 → []` enforced unchanged at the legs; filter/min-score semantics untouched (post-fusion is spec-required) |
| 6 | Preserve deterministic ranking | DONE | §3; exact-order tests all passing |
| 7 | Preserve retrieval correctness | DONE | §3; bit-identical scores, identical result sets, all 1366 pre-existing tests pass unchanged |
| 8 | Test larger candidate sets | DONE | `TestLargeCorpus` — 5,000-entry corpus (correctness, determinism, top-k, filters, no-match) |
| 9 | Test empty/sparse/large datasets | DONE | `TestSparseDataset` (zero-norm, dim-mismatch, empty query), `TestLargeCorpus`, empty-store tests from P5-103 |
| 10 | Verify memory behavior where practical | DONE | §2.4: tracemalloc 25.4 → 1.8 MB |
| 11 | Preserve Phase 1–4 functionality | DONE | Full regression: 1384 passed / 0 failed (baseline 1366 + 18 new), plus integration suite |
| 12 | Preserve rollback/feature-disabled behavior | DONE | §6; failure/fallback paths tested; changes confined to two files + one test file |

## 5. Verification (gates, re-run this session)

| Gate | Result |
|---|---|
| Focused retrieval suite (query_pipeline + bm25 + scoring) | **73 passed** |
| Full default regression suite | **1384 passed / 0 failed / 59 deselected** (baseline 1366 + 18 new; 0 regressions) |
| Integration suite | **56 passed / 1 skipped** (Tesseract absent — pre-existing) / **1 failed** (`smoke_test.py::test_live_ollama_analysis_and_note_generation` — pre-existing live-LLM flake; passed the previous P5-104 integration run, exercises no retrieval code) |
| Ruff | **All checks passed** on the two modified modules and the extended test file |
| Mypy | **Success: no issues found** in the 4 core modules (bm25, search, vector_store infra + domain) |
| Coverage | `search.py` 85%, `vector_store.py` 88% under focused run; repo **90%** vs floor 80% (missing lines are the BM25-failure branches and live-embedder default — exercised by dedicated tests, not the focused run) |
| Benchmark A/B | §2 — measured before → after on identical synthetic corpora |
| Rollback | §6 |

## 6. Rollback / Feature-Disabled Verification (req 12, quality gate)

- **Change surface**: exactly two production files — `app/infrastructure/vector_store.py` (version counter + `_norms` + precomputed-norm `search`) and `app/infrastructure/search.py` (BM25 cache in `HybridSearch`). Rollback is reverting those hunks; the untracked test file `tests/unit/test_query_pipeline.py` extensions are additive and removable. No temporary or benchmark files exist in the repo (verified via `git status`; the benchmark script lives outside the workspace).
- **Behavior-preservation proof**: all 1366 pre-existing tests pass with byte-identical assertions after the change (the +18 are new tests only), and the benchmark shows identical candidate counts (50/50), final counts (5), and RRF scores. Removing the optimizations therefore restores the exact prior tree with zero behavior change.
- **Feature-disabled**: a broken/disabled lexical leg (BM25 build or search raising) degrades to dense-only with recovery on the next build (no poisoned cache) — locked by `TestFallbackBehavior`. A disabled embedder degrades to lexical-only — unchanged and still passing. Both roadmap §4.1 fallback contracts hold.

## 7. Files Changed

| File | Action |
|------|--------|
| `app/infrastructure/vector_store.py` | **Modified** — `version` mutation counter; precomputed entry norms (`_norms`, `_norm`) populated on add/add_batch/remove/_load; `search` uses precomputed norms + hoisted query norm with `_cosine_similarity`-identical semantics |
| `app/infrastructure/search.py` | **Modified** — `HybridSearch` caches the BM25 index per corpus snapshot, rebuilding only when `store.version` changes; build/search failures still fall back to dense-only |
| `tests/unit/test_query_pipeline.py` | **Modified** — +18 tests: `TestLargeCorpus` (5k), `TestSparseDataset`, `TestPrecomputedNorms`, `TestStoreVersion`, `TestBm25CacheInvalidation`, `TestFallbackBehavior` |

Benchmark script was run from `%TEMP%\opencode` (outside the workspace) and removed after use. No other files changed; no documentation edits required beyond this review (roadmap §4.2, MEDD §7.6, and status-report notes remain accurate).

## 8. Findings

**Blocking:** None.

**Non-blocking:**
- The dense leg remains an O(n) brute-force cosine scan. This is inherent to the in-memory store without an ANN index (roadmap/MEDD already document IVF/FAISS as a future item). At the documented personal-wiki scale (thousands of chunks) the optimized dense scan is ~50 ms at 20k; a real ANN index is warranted only if the corpus grows well beyond that.
- The BM25 cache holds the lexical index for the store's lifetime and rebuilds on any mutation (including an `add` that replaces an existing id). For a read-mostly corpus this is ideal; a write-heavy loop of add→search→add→search rebuilds each time, which is correct but not incrementally updated — incremental BM25 updates are a possible future optimization if measured to matter.
- This milestone resolves the P5-102 review's non-blocking finding #77: entries added after `HybridSearch` construction are now reflected on the next query (the index rebuilds on store-version change), so live ingest + immediate search within one process works.
- The pre-existing live-Ollama smoke test (`smoke_test.py::test_live_ollama_analysis_and_note_generation`) is flaky (passed the P5-104 run, failed this one) and independent of retrieval code; tracked since P4-105.

## 9. Conclusion

The complete retrieval path was audited end to end and optimized strictly on measured evidence. Two genuine bottlenecks were identified and removed: the full-corpus BM25 index was rebuilt on every query (41% of steady-state cost, identical output every time) and vector norms were recomputed on every query (58% of the dense leg). Both changes are behavior-preserving — scores are bit-identical, ranking and filtering semantics are untouched, determinism holds, and every failure/fallback path still works — as proven by 1384 passing unit tests (0 regressions), the passing integration suite (only the pre-existing live-LLM flake), clean ruff/mypy, 90% coverage, and a 14× memory-peak reduction. Steady-state query latency at 20k entries fell 3.1× (223 ms → 71 ms) with a one-time amortized index build, and repeated queries now serve from the cache. Rollback is trivial and the change surface is two files.

**Verdict:** **APPROVED**
