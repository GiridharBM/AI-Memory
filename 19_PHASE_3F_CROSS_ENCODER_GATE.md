# 19 — Phase 3F: Cross-Encoder Secondary Abstention Gate

**Date:** 2026-08-22
**Frozen HEAD:** `8524caf56d5b8ed3ac406774fc221073e4357b07`

**Conclusion:** Cross-encoder abstention gate **rejected for production** because every tested threshold exceeded the FNR guardrail (FNR <= 0.033). The cross-encoder has stronger negative/positive discrimination than cosine, but the overlap is too large to safely use as a binary gate.

---

## 1. Objective

Use the existing Phase 3C-B cross-encoder (`ms-marco-MiniLM-L-12-v2`) as a **secondary abstention signal** in an AND gate with the cosine threshold. The cross-encoder must NOT replace RRF ordering.

## 2. Architecture

```
RRF retrieval
  → Top-N candidates
  → Cross-encoder scores candidates
  → Original RRF ordering preserved
  → AbstentionGate:
      cosine >= min_cosine AND rerank_score >= min_rerank_score → accept
      otherwise → abstain
```

When `reranker.enabled=false`, the system preserves Phase 3E behavior exactly (cosine-only gate). BM25 never bypasses either threshold.

## 3. Gate Logic (Implemented)

```python
if top.rerank_score > 0.0:  # reranker-active path
    cosine_ok = top.cosine_score >= self._min_cosine
    rerank_ok = self._min_rerank_score <= 0.0 or top.rerank_score >= self._min_rerank_score
    if cosine_ok and rerank_ok:
        return AbstentionResult(False)
    # else abstain
else:  # reranker-inactive path (Phase 3E behavior)
    # cosine gate only
```

## 4. Files Modified

| File | Change |
|------|--------|
| `app/application/qa_workflow.py` | AND gate logic in `AbstentionGate.evaluate()` |
| `config/default.yaml` | `reranker.min_score: 0.125` (experimental default) |
| `tests/unit/test_reranker.py` | Updated 3 tests encoding old bypass behavior; added 8 Phase 3F AND-gate regression tests |

## 5. Files Created

| File | Purpose |
|------|---------|
| `eval/sweep_3f.py` | Threshold sweep + Experiment 2 + Experiment 3 runner |
| `eval/results/phase_3f_sweep.json` | All experiment results |

## 6. Tests

**1485 passed, 0 failures. Coverage: 88.80%**

8 new AND-gate regression tests:
1. reranker disabled + cosine pass → accept
2. reranker disabled + cosine fail + BM25 positive → abstain
3. reranker enabled + cosine fail + rerank pass → abstain
4. reranker enabled + cosine pass + rerank fail → abstain
5. reranker enabled + cosine pass + rerank pass → accept
6. reranker enabled + cosine fail + rerank fail → abstain
7. reranker failure/unavailable → fallback cosine gate
8. BM25 never bypasses combined gate

3 existing tests updated to reflect new AND-gate behavior (old tests encoded the bypass behavior that Phase 3F removes).

## 7. Threshold Sweep (Experiment 1)

min_cosine=0.45, reranker enabled, 160 queries:

```
     T  Hit@1  Hit@5    MRR    FPR    FNR  Abstain   +Acc   -Rej
 0.050  0.854  0.951  0.896  0.351  0.163    0.275  0.837  0.649
 0.100  0.854  0.951  0.896  0.324  0.195    0.306  0.805  0.676
 0.120  0.854  0.951  0.896  0.324  0.211    0.319  0.789  0.676
 0.125  0.854  0.951  0.896  0.324  0.211    0.319  0.789  0.676
 0.150  0.854  0.951  0.896  0.324  0.252    0.350  0.748  0.676
 0.200  0.854  0.951  0.896  0.270  0.285    0.388  0.715  0.730
```

## 8. Experiment 2: Reranker-Only Lower Bound

min_cosine=0.01 (effectively no cosine gate), min_rerank_score=0.125:

```
Hit@1=0.854, Hit@5=0.951, MRR=0.896
FPR=0.351, FNR=0.203
Abstention rate=0.306
```

Reranker alone rejects 20.3% of true positives. The cross-encoder is too aggressive as a binary gate.

## 9. Experiment 3: Combined Gate

**SKIPPED** — no threshold from Experiment 1 satisfies the acceptance criteria.

## 10. Latency

| Metric | Value |
|--------|-------|
| Avg retrieval latency | ~38ms |
| Avg reranking latency | ~603ms |
| Avg total query time | ~640ms |
| Phase 3E baseline (no reranker) | ~14.6ms |

The reranker adds **~600ms per query** (41× latency increase).

## 11. Comparison with Phase 3E

| Metric | Phase 3E | Best sweep (T=0.20) | Delta |
|--------|----------|---------------------|-------|
| Hit@1 | 0.902 | 0.854 | -4.8pp |
| Hit@5 | 0.967 | 0.951 | -1.6pp |
| MRR | 0.934 | 0.896 | -3.8pp |
| FPR | 0.811 | 0.270 | -54.1pp |
| FNR | 0.008 | 0.285 | +27.7pp |
| Latency | 14.6ms | 640ms | +43× |

The reranker gate **improves FPR** (rejects more negatives) but **catastrophically increases FNR** (rejects 28.5% of true positives). The reranker is a relevance ranker, not an accept/reject gate.

## 12. Whether Reranker-as-Gate Works

**No.** The cross-encoder does not work as a binary abstention gate.

Root cause: the cross-encoder is trained on MS MARCO passage ranking. It assigns low scores to many legitimately relevant documents (cross-document queries, meta queries, tricky queries). A binary threshold that catches negatives also kills ~16-29% of true positives.

## 13. Selected Threshold

**None.** No threshold satisfies the acceptance criteria (FNR <= 0.033, Hit@5 >= 0.93, MRR >= 0.88).

## 14. Acceptance Criteria

| Criterion | Required | Result | Status |
|-----------|----------|--------|--------|
| FNR <= 0.033 | Yes | 0.163 (best at T=0.05) | **FAIL** |
| Hit@5 >= 0.93 | Yes | 0.951 | PASS |
| MRR >= 0.88 | Yes | 0.896 | PASS |

**Overall: FAIL** — FNR constraint not met at any threshold.

## 15. Risks

- **High FNR:** The reranker gate kills legitimate queries at every threshold.
- **41× latency:** 603ms per query vs 14.6ms baseline.
- **No threshold calibration path:** The cross-encoder score space does not separate FPs from true positives well enough for binary gating.

## 16. Rollback Strategy

Revert the 3 modified files to the frozen HEAD (`8524caf`):
- `git checkout 8524caf -- app/application/qa_workflow.py tests/unit/test_reranker.py config/default.yaml`

Or simply set `reranker.enabled=false` (already the default) to disable the gate.

## 17. Recommendation

**Cross-encoder abstention gate rejected for production because every tested threshold exceeded the FNR guardrail.**

**Useful finding:** Cross-encoder scores have stronger negative/positive discrimination than cosine (max negative rerank=0.12, median positive=0.885), but the overlap is too large to safely use as a binary gate. The cross-encoder is a relevance ranker, not an accept/reject classifier.

The AND gate implementation is correct and tested, but the cross-encoder lacks the discrimination power to serve as a binary accept/reject signal without unacceptable false negative rates (16-29% of true positives killed).

**Next steps (for future phases):**
1. **Keep the AND gate implementation** — it is architecturally correct and may become useful with a better gate signal.
2. **Investigate query-type-aware gating** — meta/comparison/cross-document queries may need different handling.
3. **Consider LLM-based abstention** — use the LLM itself to judge whether retrieved context is sufficient before generating.
4. **Consider embedding-level solutions** — fine-tune the embedding model for better negative discrimination (long-term).

**This phase experiment is complete. The cross-encoder gate is NOT recommended for production use.**
