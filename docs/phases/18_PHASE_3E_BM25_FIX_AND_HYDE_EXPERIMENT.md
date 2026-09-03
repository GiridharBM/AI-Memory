# Phase 3E — BM25 Override Fix + HyDE Experiment

**Date:** 2026-08-22
**Status:** VALIDATED (BM25 fix) / EXPERIMENTAL (HyDE)

---

## A. BM25 Override Fix — VALIDATED

### Problem

The `AbstentionGate` in `qa_workflow.py` had a logic bug at line 109:

```python
# OLD (buggy):
if top.cosine_score < self._min_cosine and top.bm25_score == 0.0:
```

This allowed any negative query with `bm25_score > 0` to bypass the cosine
threshold, producing false positives. Two specific negatives were affected:
q117 (sourdough bread) and q139 (photosynthesis).

### Fix

```python
# NEW (corrected):
if top.cosine_score < self._min_cosine:
```

Cosine below threshold → ABSTAIN, regardless of BM25 score. BM25 remains
a retrieval signal but must NOT override the cosine abstention gate.

### Results (160-query evaluation)

| Metric | Phase 3D | Phase 3E | Delta |
|--------|----------|----------|-------|
| Hit@1 | 0.902 | 0.902 | 0.000 |
| Hit@5 | 0.967 | 0.967 | 0.000 |
| MRR (pos-only) | 0.934 | 0.934 | 0.000 |
| FPR | 0.865 | 0.811 | **-5.4pp** |
| FNR | 0.008 | 0.008 | 0.000 |
| Neg rejection | 13.5% | 18.9% | +5.4pp |
| Pos acceptance | 99.2% | 99.2% | 0.000 |
| Avg latency | 18.9ms | 14.6ms | -4.3ms |

### Verified Abstentions

- **q117** (sourdough bread): cos=0.3973 → ABSTAINED (previously accepted via BM25 override)
- **q139** (photosynthesis): cos=0.4278 → ABSTAINED (previously accepted via BM25 override)

### Positive Regression Check

Zero positive queries were incorrectly rejected. All 86 positive queries that
passed before the fix still pass after it.

### Conclusion

BM25 override fix is **VALIDATED**. Modest FPR improvement with no measured
positive regression.

---

## B. HyDE Experiment — EXPERIMENTAL / INCONCLUSIVE

### Implementation

Optional HyDE (Hypothetical Document Embedding) transform implemented behind
`hyde.enabled: false` toggle.

- `app/infrastructure/hyde.py` — 65-line transform module
- `app/core/config.py` — HydeSettings (enabled, max_length, timeout_seconds)
- `app/infrastructure/search.py` — SearchService accepts optional HyDE transform
- `config/default.yaml` — `hyde.enabled: false` by default
- `tests/unit/test_hyde.py` — 15 unit tests (all pass)

When enabled, HyDE generates a hypothetical answer paragraph via the LLM,
embeds that instead of the original query, while BM25 still receives the
original query text. Falls back to original query embedding on any failure.

### Sample Evaluation (10 queries)

| Metric | Value |
|--------|-------|
| HyDE generation time | ~34s/query (qwen3:8b) |
| Total HyDE+search latency | ~44s/query |
| Estimated 160-query eval time | ~117 minutes |
| Sample fallbacks | 0/10 |

### Key Findings from Sample

- HyDE improved cosine for some positives (q042: 0.769→0.806)
- Thematically adjacent false positives persist (q118: 0.611, q130: 0.497)
- ~3,000x latency increase over baseline (14.6ms → 44,036ms)

### What Was NOT Completed

- Full 160-query HyDE evaluation
- Threshold sweep
- Full failure-mode testing at scale

### Conclusion

HyDE is **NOT proven to improve retrieval**. Full validation was not completed
due to ~44s/query latency. HyDE remains experimental and must NOT be enabled
by default.

---

## C. Test Results

| Metric | Value |
|--------|-------|
| Total tests | 1477 passed, 0 failed, 57 deselected |
| Coverage | >= 88% |

### Test Changes

- `tests/unit/test_qa_workflow.py`: 7 new gate regression tests + 1 renamed
- `tests/unit/test_hyde.py`: 15 new HyDE tests (transform + SearchService integration)
- `tests/unit/test_reranker.py`: 1 test updated (renamed + assertion corrected)

The reranker test update reflects the corrected BM25 gate behavior. The test
now asserts `cosine < threshold + BM25 > 0 → ABSTAIN` instead of the old
incorrect expectation of acceptance.

---

## D. Frozen Components (Unchanged)

- `app/infrastructure/reranker.py` — Phase 3C-B reranker implementation
- `eval/dataset.json` — Phase 3D 160-query dataset
- `eval/dataset_v1_frozen.json` — Phase 3B 50-query dataset
- `eval/results/abstention_gate_phase3b_frozen.json` — Phase 3B frozen results
- Embedding model, chunking, BM25 indexing, RRF algorithm — all unchanged

---

## E. Configuration

```yaml
reranker:
  enabled: false

hyde:
  enabled: false
  max_length: 500
  timeout_seconds: 30.0
```

---

## F. Recommended Next Phase

The remaining FPR problem (0.811) is caused by 30/37 negatives having
cosine scores ≥ 0.45 due to structural embedding overlap between unrelated
queries and knowledge base content. This is a fundamentally different problem
than the BM25 override bug.

Options for reducing FPR further:
- Higher-dimension embeddings (e.g., 1536 vs 768)
- Fine-tuned embedding model for this domain
- Query-aware threshold calibration
- Metadata-based filtering
