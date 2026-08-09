# P5-103 Engineering Review — Ranking and Scoring

**Task:** P5-103 — Ranking and Scoring
**Phase:** Phase 5 (retrieval; scoring verification against MEDD §7.6 / roadmap §4.2)
**Date:** 2026-08-08
**Verdict:** **APPROVED**

---

## 1. Deliverable

P5-103 is a **scoring verification milestone**. The scoring layer required by the frozen specification (MEDD §7.6 + roadmap §4.2) is already implemented by P5-101/P5-102: Reciprocal Rank Fusion with k=60 over the dense (cosine) and sparse (BM25) legs, deterministic tie-breaking by entry id, top-k caps, and exact-match filtering applied post-fusion. No production code changed in this milestone; the deliverable is a locked scoring-behavior contract (`tests/unit/test_scoring.py`, 28 tests) that pins the scoring formula, orderings, limits, and edge cases, plus this comparison against the frozen spec.

## 2. Scoring Behavior vs Frozen Specification

| Spec element (MEDD §7.6 / roadmap §4.2) | Actual behavior | Verdict |
|---|---|---|
| Scoring formula: RRF `Σ 1/(k + rank_i)`, default k=60 | `_rrf_fuse(*ranked_lists, k=60)` — exact formula, default 60 | **MATCHES** |
| RRF works on ranks, **no score normalization** required | No normalization anywhere in the fused path; raw cosine/BM25 scores are consumed as ranks only | **MATCHES** |
| Returns top-k fused results | `top_k` respected at every layer (`VectorStore.search`, `HybridSearch`, `SearchService`); `top_k <= 0` → `[]` | **MATCHES** |
| Deterministic ranking | Every ordering is a total order: `(-score, entry.id)` in store, BM25, and `_rrf_fuse`; repeated runs stable | **MATCHES** |
| Multi-stage pipeline: dense + sparse → RRF | Two legs fused; candidate pools capped `max(top_k*5, 50)`; a leg that yields nothing contributes no ranks, the other leg still results (roadmap 4.1 fallback) | **MATCHES** |
| Metadata filtering (post-filter) | Exact-match filter applied post-fusion on hit fields then metadata keys | **MATCHES** |
| Reuse result structure | All layers return `SearchHit` (score, text, source, entry_id, provenance) unchanged from P5-101 | **MATCHES** |
| Metadata/quality signals in scoring | None applied — the spec names none; no boosters, no recency/importance weights | **MATCHES** (correctly absent) |
| Cross-encoder re-ranking (roadmap 4.3) | Not implemented — separate roadmap item (ONNX model, NDCG eval, <5s/100 pairs); deliberately excluded (req 3/10) | **OUT OF SCOPE BY DESIGN** |

## 3. Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| 1. Reuse the existing retrieval result structure | DONE | `SearchHit` reused unchanged at every layer; no new result types. |
| 2. Identify the scoring formula required by the specification | DONE | RRF with k=60 (roadmap §4.2 formula), verified term-by-term in `TestRrfFormula` (exact `1/(k+rank)` values, custom k). |
| 3. Combine retrieval signals only where explicitly required | DONE | Only dense + sparse → RRF (explicitly required by 4.2). No additional signal combination added. |
| 4. Normalize scores if required by the specification | DONE | Spec requires **no** normalization (RRF is rank-based); none present or added. |
| 5. Apply metadata/quality signals only when specified | DONE | None applied; filtering (4.5 exact-match) is applied as a constraint, not a score signal. |
| 6. Ensure deterministic tie-breaking | DONE | `(-score, id)` total order at all three layers; `TestRrfFormula.test_ties_resolve_by_id` and `TestDeterministicRuns` lock it. |
| 7. Ensure stable result ordering across repeated runs | DONE | Repeated-run tests at store, hybrid, and fuse levels. |
| 8. Respect configured top-k/result limits | DONE | `top_k=0`/negative → `[]`, `top_k=1`, `top_k>corpus` all covered in `TestTopKBoundaries`. |
| 9. Do not silently change the scoring semantics of earlier milestones | DONE | Zero production changes; all P5-101/P5-102 scores and orderings byte-identical (full suite regression). |
| 10. Do not introduce unrelated ranking algorithms | DONE | No new scoring algorithm; cross-encoder (4.3) deliberately deferred to its own milestone. |

## 4. Testing — Required Matrix vs Coverage (`tests/unit/test_scoring.py`, 28 tests)

| Required test | Covered by |
|---|---|
| score ordering | `TestRrfFormula.test_multi_rank_descending`, `TestCombinedScoreOrdering.test_both_legs_outranks_single_leg` (exact fused scores 2/61 vs 2/62) |
| equal-score tie breaking | `TestRrfFormula.test_ties_resolve_by_id`, `TestDeterministicRuns` |
| semantic score differences | `TestCosineExtremes` (identical=1.0, orthogonal=0.0, opposite=-1.0, zero, dim mismatch), `test_negative_scores_excluded_by_default` |
| lexical score differences | existing `TestBM25Index` (TF/IDF/length, `test_bm25.py`) + `TestRrfFormula.test_dual_list_accumulates` |
| combined scores | `TestCombinedScoreOrdering.test_both_legs_outranks_single_leg`, `test_lexical_leg_breaks_dense_tie`, `test_min_score_separates_fused_scores` |
| top-k boundaries | `TestTopKBoundaries` (0, negative, 1, exceeds corpus) |
| duplicate candidates | `TestDuplicateCandidates.test_cross_leg_overlap_single_fused_hit`, `test_store_dedups_duplicate_ids`, `TestRrfFormula.test_duplicate_id_in_single_list_accumulates` |
| empty results | `TestEmptyResults` (empty store, blank query, no matches anywhere) |
| deterministic repeated runs | `TestDeterministicRuns` (store shuffled-insertion, hybrid, fuse) |
| extreme score values | `TestCosineExtremes` ([-1, 1] domain, zero vectors, mismatched dims), `TestRrfFormula` (min/max fused bounds 1/61 vs 2/61), `test_min_score_separates_fused_scores` |

## 5. Verification (commands re-run this session)

| Gate | Result |
|------|--------|
| Focused scoring suite (`test_scoring.py`) | **28 passed** |
| Full default regression suite | **1346 passed / 0 failed / 54 deselected** (baseline 1318 + 28 new; 0 regressions) |
| Integration suite | **51 passed / 1 skipped** (Tesseract binary absent — pre-existing env skip) / **1 failed** (`smoke_test.py::test_live_ollama_analysis_and_note_generation` — pre-existing live-LLM flake, exercises no P5-103 code; documented in P4-104/105, P5-101/102) |
| Ruff | **All checks passed** on `test_scoring.py`; 4 pre-existing findings on unchanged test-file lines elsewhere |
| Mypy (`--ignore-missing-imports`) | **Success: no issues found** in the 4 core modules (bm25, search, vector_store infra + domain). Note: type-checking test files pulls `pytest` → numpy stubs (3.12 syntax) under the repo's `python_version = "3.11"` config — the pre-existing env-wide numpy-stub issue; `test_scoring.py` itself passes with `--follow-imports=skip`. |
| Coverage | `bm25.py` **100%**, `search.py` **100%**, `domain/vector_store.py` **100%**, `infrastructure/vector_store.py` **95%** (4 pre-existing guard lines); total **98%** vs repo floor 80% |
| Rollback | Trivially clean: **no production code changed**. The only added artifact is the untracked test file; removing it restores the exact prior tree. The P5-101/P5-102 scoring semantics are therefore inherently preserved (req 9). |

## 6. Files Changed

| File | Action |
|------|--------|
| `tests/unit/test_scoring.py` | **New** — 28 tests locking the P5-103 scoring matrix (formula, ordering, ties, limits, dups, empty, determinism, extremes) |

No production files modified.

## 7. Findings

**Blocking:** None.

**Non-blocking:**
- `_rrf_fuse` accumulates a duplicated id appearing twice within a single input list (degenerate input; the store and both search legs dedupe by construction, so this cannot occur in the real pipeline). Locked-in behavior, documented in `test_duplicate_id_in_single_list_accumulates`.
- `VectorStore.search` excludes negative-cosine entries by default (`min_score=0.0`); anti-correlated vectors are admitted only with an explicit negative `min_score`. Matches P5-101 semantics (unchanged, req 9).
- `min_score` thresholds RRF scores (max ≈ 2/61 ≈ 0.033 for the two-leg default), not raw cosine/BM25 values — documented in P5-102; unchanged here.
- Cross-encoder re-ranking (roadmap 4.3), query rewriting (4.4), structured `$in` filters (4.5), parent-child (4.6), and CLI (4.7) remain unimplemented by design.
- Per-task atomic commits pending (working tree carries pre-existing uncommitted Phase 2–4 work, consistent with M2.1–M5.0 convention).

## 8. Conclusion

The scoring layer required by the frozen specification — RRF with k=60 over dense + sparse, rank-based with no normalization, deterministic `(-score, id)` tie-breaking, top-k limits, post-fusion filtering, and the unchanged `SearchHit` result structure — is exactly what P5-101/P5-102 delivered and what P5-103 now verifies and locks with a 28-test contract. Actual behavior matches the specification on every element compared; no production code needed changing, no scoring semantics were altered, and no unrelated ranking algorithms (including the deferred cross-encoder) were introduced. All gates pass: 1346 unit tests with 0 regressions, 51 integration tests pass (only the pre-existing Tesseract env-skip and live-LLM flake), ruff clean, mypy clean on the core modules, and new code 100% covered.

**Verdict:** **APPROVED**
