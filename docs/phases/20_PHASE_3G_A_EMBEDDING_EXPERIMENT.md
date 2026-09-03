# Phase 3G-A: Embedding Model Experiment Report

**Date:** 2026-08-22  
**Status:** COMPLETE — Candidate REJECTED  
**Author:** opencode (big-pickle)

---

## 1. Embedding Models Tested

| Model | Dimensions | Size | Ollama Model |
|-------|-----------|------|--------------|
| nomic-embed-text | 768 | ~270MB | `nomic-embed-text` |
| mxbai-embed-large | 1024 | ~670MB | `mxbai-embed-large` |

---

## 2. Score Distributions (min_cosine=0.45)

### nomic-embed-text (baseline)

| Statistic | Positive (123) | Negative (37) |
|-----------|----------------|---------------|
| Min | 0.4993 | 0.4257 |
| P25 | 0.6167 | 0.5134 |
| Median | 0.6761 | 0.5745 |
| P75 | 0.7239 | 0.6792 |
| Max | 0.8215 | 0.7139 |
| Neg >= 0.45 | — | **36/37** |
| Pos < 0.45 | **0/123** | — |

### mxbai-embed-large (candidate)

| Statistic | Positive (123) | Negative (37) |
|-----------|----------------|---------------|
| Min | 0.4680 | 0.3419 |
| P25 | 0.6261 | 0.5029 |
| Median | 0.6984 | 0.5953 |
| P75 | 0.7487 | 0.6721 |
| Max | 0.8299 | 0.7995 |
| Neg >= 0.45 | — | **33/37** |
| Pos < 0.45 | **0/123** | — |

**Verdict:** mxbai pushes 3 more negatives below 0.45 (33 vs 36) but also raises negative P75 (0.679→0.672) and max (0.714→0.800). Score separation does not materially improve — positives and negatives still heavily overlap.

---

## 3. Retrieval Metrics (min_cosine=0.45, dense vectors only)

| Metric | nomic | mxbai | Delta |
|--------|-------|-------|-------|
| Hit@1 | 0.878 | 0.862 | -0.016 |
| Hit@3 | 0.911 | 0.886 | -0.024 |
| Hit@5 | **0.927** | **0.902** | -0.024 |
| Hit@10 | 0.967 | 0.951 | -0.016 |
| MRR | 0.901 | 0.885 | -0.016 |
| FPR | 0.973 | 0.892 | -0.081 |
| FNR | 0.000 | 0.000 | 0.000 |
| Neg reject | 0.027 | 0.108 | +0.081 |

mxbai **degrades** Hit@1, Hit@5, and MRR across the board. The FPR reduction (0.973→0.892) comes from rejecting 4 negatives below threshold, but at the cost of worse positive retrieval quality.

---

## 4. Threshold Sweep — mxbai-embed-large

| Threshold | Hit@1 | Hit@5 | MRR | FPR | FNR | Pass? |
|-----------|-------|-------|-----|-----|-----|-------|
| 0.30 | 0.862 | 0.902 | 0.885 | 1.000 | 0.000 | No (FPR=1.0) |
| 0.35 | 0.862 | 0.902 | 0.885 | 0.973 | 0.000 | No (FPR=0.973) |
| 0.40 | 0.862 | 0.902 | 0.885 | 0.973 | 0.000 | No (FPR=0.973) |
| 0.45 | 0.862 | 0.902 | 0.885 | 0.892 | 0.000 | No (Hit@5<0.93) |
| **0.50** | 0.846 | **0.878** | 0.865 | **0.757** | **0.033** | **No (Hit@5<0.93)** |
| 0.55 | 0.821 | 0.837 | 0.832 | 0.622 | 0.122 | No (FNR>0.033) |
| 0.60 | 0.780 | 0.789 | 0.786 | 0.432 | 0.187 | No |

**No threshold meets acceptance criteria** (FNR≤0.033, Hit@5≥0.93, MRR≥0.88). At T=0.50 (best FPR), Hit@5=0.878 fails. Above T=0.50, FNR exceeds limit.

---

## 5. Re-Embedding Cost

| Step | nomic | mxbai |
|------|-------|-------|
| Corpus (101 chunks) | 8.8s | 4.4s |
| Queries (160) | 0.8s | 1.4s |
| Retrieval latency/query | 4.3ms | 5.5ms |

mxbai is faster for corpus embedding (likely batched differently) but slower per query. Dimension increase (768→1024) adds ~33% memory per embedding. Re-ingestion of full corpus would cost ~4s per 100 chunks — acceptable but unnecessary given results.

---

## 6. Acceptance Criteria Check

| Criterion | Required | nomic | mxbai | Pass? |
|-----------|----------|-------|-------|-------|
| FNR | ≤ 0.033 | 0.000 | 0.000 | Both pass |
| Hit@5 | ≥ 0.93 | 0.927 | 0.902 | **Both FAIL** |
| MRR | ≥ 0.88 | 0.901 | 0.885 | nomic pass, mxbai marginal |
| FPR improvement | Materially lower | 0.973 | 0.892 | mxbai -0.081 but Hit@5 degrades |

**mxbai-embed-large fails Hit@5 (0.902 < 0.93).** Candidate model rejected.

---

## 7. Raw Scores (Top-10 Negative Queries)

Full negative query scores saved in `eval/results/experiment_3g_a_embedding.json` under `detailed.nomic-embed-text` and `detailed.mxbai-embed-large`.

---

## 8. Regression Tests

```
1485 passed, 57 deselected in 23.97s
```

No regressions. Production config, embeddings pipeline, vector store, and QA workflow are all unchanged.

---

## 9. Production Files Unchanged

```bash
git diff HEAD -- app/infrastructure/embeddings.py app/infrastructure/vector_store.py \
  app/core/config.py app/application/qa_workflow.py config/default.yaml eval/dataset.json
# (no output)
```

---

## 10. 384-dim Chunks (b.md)

Confirmed as test artifact. Garbage content (`Test chunk for dimension validation. Hello from 384-dim.`). Zero eval queries reference b.md. VectorStore returns 0.0 for dimension mismatches. **No impact on any eval metrics.**

---

## 11. Root Cause (from Phase 3G Analysis)

nomic-embed-text 768-dim cannot distinguish relevant from irrelevant queries. 36/37 negatives score cos≥0.45. No existing signal (cosine, BM25, RRF, gap, diversity) can separate FPs from TPs. The hybrid system's BM25 + RRF fusion is the actual mechanism that enables production Hit@5=0.967, not the embedding model alone.

---

## 12. Conclusion and Recommendation

**Do NOT replace nomic-embed-text with mxbai-embed-large.**

mxbai-embed-large degrades retrieval quality (Hit@5 -0.024, MRR -0.016) and fails acceptance criteria at every threshold. The marginal FPR improvement (3 more negatives rejected) does not justify the quality loss.

The embedding model is not the bottleneck. The bottleneck is that dense-vector-only retrieval cannot separate positives from negatives — the hybrid system (BM25 + RRF) is what makes production work.

### Next recommended directions:
1. **Phase 3G-B:** Adaptive threshold per-query (dynamic min_cosine based on score distribution)
2. **Phase 3G-C:** Query expansion / HyDE integration (already prototyped in 3F, needs production tuning)
3. **Phase 4:** Move to other P0 priorities (auto-sync, multi-user, admin dashboard)

---

## 13. Artifact Paths

- **Experiment script:** `C:\Users\girid\AppData\Local\Temp\opencode\exp3ga_part1.py`, `exp3ga_main.py`, `exp3ga_sweep.py`
- **Results JSON:** `eval/results/experiment_3g_a_embedding.json`
- **This report:** `20_PHASE_3G_A_EMBEDDING_EXPERIMENT.md`
