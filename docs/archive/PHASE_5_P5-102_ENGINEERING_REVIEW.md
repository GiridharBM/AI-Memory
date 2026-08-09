# P5-102 Engineering Review — BM25 Lexical Retrieval + RRF Hybrid Fusion

**Task:** P5-102 — BM25 Lexical Retrieval + RRF Hybrid Fusion
**Phase:** Phase 5 (roadmap §4.1 BM25, §4.2 RRF; hybrid retrieval)
**Date:** 2026-08-08
**Verdict:** **APPROVED**

---

## 1. Deliverable

A deterministic hybrid retrieval layer per MEDD §7.6 and roadmap §4.1/§4.2/§4.5: a dependency-free BM25 lexical index fused with the existing dense (embedding) search via Reciprocal Rank Fusion (RRF, k=60), with safe fallbacks when either leg is unavailable:

| Artifact | Purpose | Reuses |
|----------|---------|--------|
| `BM25Index` (`app/infrastructure/bm25.py`) | Okapi BM25 index: k1=1.5, b=0.75, lowercase `[a-z0-9_]+` tokenizer, inverted postings, deterministic `search(query, top_k)` returning `(doc_index, score)` sorted `(-score, doc_index)` | Nothing new — pure stdlib (`re`, `math`, `collections`), per MEDD §7.6 "rank_bm25 or custom BM25 implementation" |
| `VectorStore.entries()` | Insertion-order accessor seeding the BM25 corpus | Existing internal `_entries` |
| `_rrf_fuse(*ranked_lists, k=60)` | Reciprocal Rank Fusion: `sum(1/(k + rank))` over ranked id lists, sorted `(-score, id)` | Roadmap §4.2 (k=60) |
| `HybridSearch` (rewritten) | Dense + lexical legs, RRF fusion, pool cap `max(top_k*5, 50)`, min_score on RRF scores, top_k<=0 → `[]` | Existing store/search, new `BM25Index`, `_rrf_fuse` |
| `SearchService` (now hybrid) | Facade `search(query, *, top_k, filter, min_score)`; `_embed_query()` swallows embedder failures → `None` (lexical-only fallback); exact-match filter applied post-fusion | Existing facade, rewritten `HybridSearch` |

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| 4.1 BM25 lexical retrieval (supersedes keyword overlap) | DONE | `BM25Index` with k1=1.5, b=0.75, per-doc TF/IDF, length normalization, deterministic ranking. The old `sum(1 for w in query_words if w in text)` overlap is fully replaced inside `HybridSearch`. |
| 4.1 Lexical fallback when embedding unavailable | DONE | `SearchService._embed_query()` returns `None` on embedder exception or disabled service → `HybridSearch` runs lexical-only. Same for empty/`None` dense results. |
| 4.2 RRF fusion with k=60 | DONE | `_rrf_fuse` implements `1/(k + rank)`, k=60 per roadmap; verified `test_fuses_semantic_and_lexical`, `test_min_score_filters_rrf_scores`. |
| 4.2 Deterministic fusion | DONE | Both legs return deterministic orders; `_rrf_fuse` sorts `(-score, id)` — total order. `test_deterministic_ties`, `test_overlapping_results_deduped` (dedup by entry id, no double counting). |
| 4.5 Metadata filter applies to fused results | DONE | Exact-match `filter` applied post-fusion on both legs; a document matching only the dense leg is still excluded when it fails the filter (`test_filter_applies_to_both_legs`); malformed filter values are safely no-ops (`test_malformed_metadata_filter_is_safe`). |
| BM25 failure safety | DONE | A raising `BM25Index.search` degrades to dense-only (`test_bm25_failure_falls_back_to_dense` via monkeypatch), never propagates. |
| No new dependencies | DONE | Custom BM25 on stdlib per MEDD §7.6 option; no `rank_bm25`, no numpy change. |
| No scope creep | DONE | No cross-encoder (4.3), query rewriting (4.4), `$in` filter syntax (4.5), parent-child (4.6), or CLI (4.7). |

## 3. Backward Compatibility

- `SearchService` and `HybridSearch` keep their exact public signatures; callers see the same `SearchHit[]` shape and the same `top_k`/`filter`/`min_score` semantics (now fused, not dense-only).
- `VectorStore` gains only the additive `entries()` accessor; public `search`/`get`/`save`/`load` unchanged.
- Persisted `vector_store.json` files are untouched by this milestone (no schema change).
- `min_score` now thresholds RRF scores (in `1/(k+rank)` units) rather than raw cosine similarity — the facade semantics are "minimum fused score", consistent across both legs.
- Blank queries fall back to dense-only (lexical leg skipped on empty tokens), preserving P5-101 behavior for blank input.

## 4. Testing

**18 new tests** in `tests/unit/test_bm25.py` (`TestTokenize` ×3; `TestBM25Index` ×15): empty corpus, blank query, no matches, term relevance, TF weighting, IDF for rare terms, length normalization (equal TF, shorter doc wins), multi-term scoring, top_k, determinism, all-tokenizer edge cases (mixed case, punctuation, underscore).

**TestHybridSearch rewritten 2 → 13** in `tests/unit/test_knowledge_engine.py`: fusion of both legs, deterministic ties, semantic-only when no lexical match, lexical-only when embedding raises/empty, dedup of overlapping results, no-results-when-both-empty, result limit, blank query → dense-only, 200-document candidate pool, BM25 failure → dense fallback, min_score on RRF scores, provenance preserved on fused hits.

**TestSearchService updated** (`embed_failure`/`embed_disabled` now assert lexical fallback; added `lexical_match_outranks_pure_semantic` per roadmap 4.1, `filter_applies_to_both_legs`, `malformed_metadata_filter_is_safe`).

## 5. Verification (commands re-run this session)

| Gate | Result |
|------|--------|
| Focused suite (`test_bm25.py` + search tests) | **55 passed** |
| Full default regression suite | **1318 passed / 0 failed / 54 deselected** (baseline 1289 + 29 new; 0 regressions) |
| Integration suite | **51 passed / 1 skipped** (Tesseract binary absent — pre-existing env skip) / **1 failed** (`smoke_test.py::test_live_ollama_analysis_and_note_generation` — pre-existing live-LLM flake, exercises no P5-102 code; documented in P4-104/105 and P5-101) |
| Ruff (changed app files) | **All checks passed** — 0 findings on `bm25.py`, `search.py`, `vector_store.py`, `test_bm25.py`; the 4 findings on unchanged test-file lines are pre-existing baseline debt |
| Mypy (`--ignore-missing-imports`) | **Success: no issues found** in the 4 modules (bm25, search, vector_store infra + domain) |
| Coverage | `bm25.py` **100%**, `search.py` **100%**, `domain/vector_store.py` **100%**, `infrastructure/vector_store.py` **95%** (4 pre-existing guard/warning lines); total **98%** vs repo floor 80% |

## 6. Files Changed

| File | Action |
|------|--------|
| `app/infrastructure/bm25.py` | **New** — `BM25Index` (k1=1.5, b=0.75, postings, deterministic `search`) |
| `app/infrastructure/search.py` | **Updated** — `_rrf_fuse` (k=60), rewritten `HybridSearch` (RRF fusion + fallbacks), `SearchService` hybrid with `_embed_query` |
| `app/infrastructure/vector_store.py` | **Updated** — additive `entries()` accessor |
| `tests/unit/test_bm25.py` | **New** — 18 tests |
| `tests/unit/test_knowledge_engine.py` | **Updated** — TestHybridSearch 2→13, TestSearchService updated |

## 7. Findings

**Blocking:** None.

**Non-blocking:**
- The BM25 corpus is seeded from `VectorStore.entries()` at `HybridSearch` construction time; entries added after construction are not in the lexical index until the hybrid is rebuilt. Rebuilding on every search is the upgrade path if live ingest + immediate search within one process matters.
- Tokenizer is lowercase `[a-z0-9_]+` with no stemming or stopword list — adequate for note-scale corpora; a `rank_bm25` drop-in or stemmer is the roadmap-4.x upgrade.
- `min_score` operates on RRF units (`1/(k+rank)`, ~0.016 per fused hit), so absolute thresholds are small; callers migrating from P5-101 cosine thresholds must rescale.
- Query rewriting (4.4), cross-encoder reranking (4.3), `$in`/range filter syntax (4.5), parent-child context (4.6), and CLI (4.7) remain unimplemented by design.
- Per-task atomic commits pending (working tree uncommitted, consistent with M2.1–M5.0 convention).

## 8. Conclusion

P5-102 replaces the keyword-overlap lexical leg with a dependency-free, deterministic BM25 index and fuses it with the P5-101 dense search via RRF (k=60), exactly per roadmap §4.1/§4.2, with strict fallbacks: embedder failure/disabled → lexical-only, BM25 failure → dense-only, both empty → `[]`. Determinism is preserved end-to-end (each leg ordered, fusion tie-broken by id), filters apply post-fusion to both legs, and no dependency or schema changes were introduced. All gates pass: 1318 unit tests with 0 regressions, 51 integration tests pass (only the pre-existing Tesseract env-skip and live-LLM flake), ruff clean on all changed files, mypy clean on all 4 modules, and new code 100% covered (store 95% on 4 pre-existing guard lines).

**Verdict:** **APPROVED**
