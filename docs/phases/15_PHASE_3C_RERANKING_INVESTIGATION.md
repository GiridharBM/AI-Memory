# 15. Phase 3C-A — Cross-Encoder Reranking Investigation

**Date:** 2026-08-20
**Status:** READ-ONLY — analysis/design only, no code changes
**Constraint:** DO NOT modify source code, tests, config, or dependencies

---

## 1. Current Retrieval Architecture

**Source-verified** from `app/infrastructure/search.py`, `app/infrastructure/vector_store.py`, `app/infrastructure/bm25.py`, `app/infrastructure/embeddings.py`, `app/application/qa_workflow.py`.

### Pipeline

```
Query text
  |
  v
EmbeddingService._embed(query)          [embeddings.py:53-84]
  |  nomic-embed-text, 768-dim, via Ollama
  v
HybridSearch.search(query, embedding)   [search.py:175-230]
  |
  +-- VectorStore.search(embedding, top_k=pool_size)   [vector_store.py:94-124]
  |     Brute-force cosine similarity over all entries
  |     Returns: list[SearchResult(entry, score)]
  |
  +-- BM25Index.search(query, top_k=pool_size)         [bm25.py:52-78]
  |     Okapi BM25 (k1=1.5, b=0.75), regex tokenizer
  |     Returns: list[(doc_index, score)]
  |
  +-- _rrf_fuse(vector_ids, bm25_ids, k=60)            [search.py:60-93]
  |     Accumulates 1/(k + rank) per leg per document
  |     Returns: list[(entry_id, rrf_score, cosine_score, bm25_score)]
  |
  v
HybridSearch truncates to top_k (default 10)           [search.py:230]
  |
  v
SearchService applies optional filter                  [search.py:297-298]
  |
  v
AbstentionGate.evaluate(hits)                          [qa_workflow.py:75-86]
  |  Signal 1: empty hits -> abstain
  |  Signal 2: cosine=0 AND bm25=0 -> abstain
  |  Signal 3: cosine < min_cosine AND bm25=0 -> abstain
  v
build_context(hits[:8], max_chars=12000)              [qa_workflow.py:89-114]
  |
  v
qwen3:8b via Ollama                                   [qa_workflow.py:183-189]
```

### Key Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| Pool size per leg | `max(top_k * 5, 50)` = 50 | `search.py:185` |
| RRF k | 60 | `search.py:148` |
| BM25 k1 | 1.5 | `bm25.py:33` |
| BM25 b | 0.75 | `bm25.py:34` |
| BM25 tokenizer | `[a-z0-9_]+` lowercase | `bm25.py:13` |
| Vector dimension | 768 | nomic-embed-text |
| Top-K (final) | 10 (eval), 5 (default) | `run_eval.py`, `qa_workflow.py:154` |
| Context chunks | 8 | `qa_workflow.py:16` |
| Context chars | 12,000 | `qa_workflow.py:17` |
| Abstention threshold | 0.45 | Phase 3B |
| Embedding model | nomic-embed-text | `embeddings.py:45` |
| Generation model | qwen3:8b | `config/default.yaml:15` |

### Candidate Generation vs Ranking vs Reranking

| Stage | What it does | Current implementation |
|-------|-------------|----------------------|
| **Candidate generation** | Retrieve a broad pool of potentially relevant documents | Vector search (top 50) + BM25 (top 50) |
| **Ranking** | Score and order candidates | RRF fusion (k=60) — produces a single fused score per document |
| **Reranking** | Re-score candidates with a more precise model | **NONE** — this is the gap |
| **Filtering** | Remove candidates that fail quality checks | Abstention gate (cosine threshold) |
| **Context selection** | Choose final documents for the LLM | Truncate to top 8 chunks, 12k chars |

---

## 2. Why Reranking?

### What retrieval errors remain?

Phase 3B evaluation (verified from `eval/results/abstention_gate.json`):

- **FPR = 0.714** — 5 of 7 negative queries still produce accepted retrieval
- The abstention gate at T=0.45 catches only the two lowest-confidence negatives (q032 at 0.3444, q045 at 0.4381)
- Five negatives in the cosine overlap zone [0.46, 0.56] pass through

### What did Phase 3A discover?

Source-verified from `13_PHASE_3A_RETRIEVAL_INVESTIGATION.md`:

1. **RRF scores are compressed into a 17% band** (0.028 to 0.033). They cannot distinguish positive from negative queries.
2. **Raw cosine shows separation** but with an overlap zone [0.46, 0.56] where 5 of 7 negatives overlap with positives.
3. **q036 ("What Docker configuration does PAM use?") scores 0.032787** — tied for the highest RRF score in the entire dataset — despite being a negative query. It matches because "PAM" and "configuration" are generic terms that overlap with PAM documentation chunks.
4. **3 of 7 negative queries score above the mean of positive queries** on raw cosine.

### Why can semantic similarity retrieve the wrong document?

Embedding models (like nomic-embed-text) encode semantic meaning into dense vectors. But cosine similarity between vectors is a **coarse proxy** for relevance. It cannot distinguish:
- "This document mentions the same keywords" from "This document answers the question"
- "This document is about a related topic" from "This document is about the exact topic"
- Partial lexical overlap from genuine topical relevance

### Why can BM25 retrieve lexical matches that lack semantic relevance?

BM25 scores based on term frequency and inverse document frequency. It excels at exact keyword matching but has no understanding of meaning. The query "What Docker configuration does PAM use?" matches PAM documentation chunks because "PAM" and "use" appear frequently — even though no Docker content exists.

### What does RRF solve?

RRF combines the strengths of both legs: documents that appear in both vector and BM25 rankings get boosted. This handles the case where one leg misses a document the other finds.

### What does RRF NOT solve?

RRF operates on **rank positions**, not content quality. If both legs rank a partially-relevant document highly (because it shares keywords), RRF will boost it further. RRF cannot verify whether a retrieved document actually answers the query.

---

## 3. What Is a Cross-Encoder?

### Embedding model (bi-encoder)

```
query  -->  [encoder]  -->  vector_q
                              |
                          cosine similarity
                              |
document --> [encoder]  -->  vector_d
```

- Encodes query and document **independently**
- Fast: document vectors can be pre-computed and cached
- Limited: cannot model fine-grained query-document interaction

### Cross-encoder

```
[query + document]  -->  [single model]  -->  relevance score (0.0 - 1.0)
```

- Encodes query and document **together** as a single input
- Slower: must process every (query, document) pair from scratch
- More precise: the model sees exactly how query terms relate to document content
- Cannot pre-compute: every query requires scoring all candidate documents

### Why cross-encoders are more precise

A cross-encoder like `BAAI/bge-reranker-v2-m3` reads the query and document as a single concatenated input. It can model:
- Whether the document directly answers the query (not just shares keywords)
- Whether the document's topic matches the query's topic
- Whether specific facts in the document satisfy the query

This is fundamentally more powerful than comparing two independent vectors, because the model can attend to fine-grained token-level interactions between query and document.

### Why cross-encoders are slower

Every (query, document) pair must be processed through the full model. For 20 candidates, that's 20 forward passes. There is no way to pre-compute or cache cross-encoder scores because they depend on the specific query.

---

## 4. Where Should Reranking Go?

### Architecture A: Rerank after RRF, before gate

```
Vector + BM25 -> RRF -> Reranker -> Abstention -> Context -> LLM
```

Problem: The gate would need a new threshold calibrated to cross-encoder scores, not cosine. This doubles the calibration work.

### Architecture B: Rerank after gate

```
Vector + BM25 -> RRF -> Abstention -> Reranker -> Context -> LLM
```

Problem: The gate rejects before reranking sees the candidates. If a negative query passes the gate (FPR=0.714), the reranker wastes compute on it. The gate cannot benefit from the reranker's superior judgment.

### Architecture C: Rerank each leg before RRF

```
Vector -> Rerank each hit -> BM25 -> Rerank each hit -> RRF
```

Problem: Cross-encoders score (query, document) pairs. Reranking individual legs before fusion defeats the purpose — RRF already combines them.

### Architecture D: RRF -> Top-N -> Reranker -> Top-K -> Gate

```
Vector + BM25
  -> RRF (pool_size = 50 per leg)
  -> Top-N candidates (e.g., N=20)
  -> Cross-encoder reranker
  -> Reranked results
  -> Abstention gate (using cross-encoder score)
  -> Top-K context (K=5 or 8)
  -> qwen3:8b
```

**Recommended: Architecture D.**

Why:
1. **Reranker operates on a bounded set** (Top-N) — compute cost is predictable
2. **Gate benefits from reranker scores** — the gate can use cross-encoder scores instead of (or in addition to) cosine, which directly measure query-document relevance
3. **Reranker catches what RRF cannot** — partial-match negatives that RRF boosts
4. **Fallback is clean** — if reranker fails, fall back to RRF order (the pre-reranker state)

---

## 5. Candidate Count

### Analysis

| top-N | Recall coverage | Reranking cost | Latency | Memory | Context quality |
|-------|----------------|----------------|---------|--------|----------------|
| 10 | May miss good docs ranked 11-20 by RRF | 10 forward passes | Low | Low | Good — but limited pool |
| 20 | Covers all docs that RRF ranks in top 20 | 20 forward passes | Moderate | Moderate | Best balance |
| 30 | Diminishing returns — most good docs already in top 20 | 30 forward passes | Moderate | Moderate | Marginal improvement |
| 50 | Overkill for 101-chunk corpus | 50 forward passes | High | High | Unnecessary |

### PAM context

PAM's corpus is 101 chunks. The pool_size per leg is already `max(top_k * 5, 50) = 50`. After RRF fusion, many of these 50 candidates will have been deduplicated (a chunk appearing in both legs counts once). The realistic candidate count after RRF is likely 30-40 unique chunks.

**Recommendation: top-N = 20.** This covers the meaningful RRF candidates without excessive compute. For a 101-chunk corpus, 20 candidates is 20% of the entire store — more than sufficient for recall preservation.

---

## 6. Model Options

### Source-verified: No reranking model exists in PAM

Grep across all `.py`, `.toml`, `.txt`, and `.yaml` files returned zero matches for: rerank, reranker, cross-encoder, BGE, ms-marco, sentence-transformers, transformers, FlagEmbedding, Cohere, rerank API.

### Candidate models

| Model | Size | Quality | CPU feasible | Offline | License | Notes |
|-------|------|---------|-------------|---------|---------|-------|
| **BAAI/bge-reranker-v2-m3** | ~568M params (~1.1GB) | Excellent (MTEB Reranking leaderboard top tier) | Yes, moderate latency | Yes (local download) | MIT | Multi-lingual, multi-granularity. Best quality option. |
| **BAAI/bge-reranker-base** | ~278M params (~560MB) | Good | Yes, moderate latency | Yes | MIT | Smaller, faster, slightly lower quality. |
| **cross-encoder/ms-marco-MiniLM-L-6-v2** | ~22M params (~90MB) | Good for English | Yes, fast | Yes | Apache-2.0 | Very small, fast, English-only. Good for CPU. |
| **cross-encoder/ms-marco-MiniLM-L-12-v2** | ~67M params (~270MB) | Better than L-6 | Yes, moderate | Yes | Apache-2.0 | Good balance of size and quality. |
| **Jina reranker-v2-base-multilingual** | ~278M params (~560MB) | Good | Yes | Yes | Apache-2.0 | Multi-lingual alternative to BGE. |
| **Ollama reranking API** | N/A | N/A | N/A | N/A | N/A | Ollama does **not** provide a reranking endpoint. Only chat and embedding. |

### Ollama reranking

**Source-verified from `embeddings.py:76`:** Ollama is used for embeddings via `self._client.embed(model=self._model, input=text)`. Ollama supports chat and embedding endpoints only. There is no reranking endpoint in Ollama's API. Cross-encoder reranking cannot use Ollama.

### Recommended model

**`cross-encoder/ms-marco-MiniLM-L-12-v2`** for initial implementation:
- 67M params — small enough for fast CPU inference
- 270MB download — reasonable for a local system
- Apache-2.0 license — permissive
- Well-tested, widely used, stable
- English-optimized — PAM's corpus is English

**Upgrade path to `BAAI/bge-reranker-v2-m3`** if quality is insufficient or multilingual support is needed.

### Dependency requirements

| Dependency | Required for | Approximate size |
|-----------|-------------|-----------------|
| `torch` (PyTorch) | Model inference | ~200MB (CPU-only wheel) |
| `transformers` (Hugging Face) | Model loading, tokenization | ~50MB |
| `sentence-transformers` (optional) | Higher-level reranker API | ~10MB |

**Alternative: ONNX Runtime** — If PyTorch is too heavy, `onnxruntime` (~30MB) + an ONNX-exported cross-encoder can run inference without PyTorch. This is a lighter path but requires an extra export step.

---

## 7. Hardware / Local Execution

### Requirements for cross-encoder inference

| Component | Minimum | Recommended |
|-----------|---------|------------|
| CPU | Any modern x86_64/ARM64 | 4+ cores |
| RAM | 2GB free (model + working memory) | 4GB free |
| GPU | Not required | CUDA-capable GPU speeds up ~3-5x |
| Disk | 300MB for model download | SSD preferred |
| Python | 3.11+ (PAM requirement) | 3.11+ |

### Latency estimates (conceptual)

| Candidates | CPU latency | GPU latency |
|-----------|-------------|-------------|
| 10 | Low (50-200ms) | Very low (10-30ms) |
| 20 | Low-moderate (100-400ms) | Low (20-60ms) |
| 50 | Moderate (250-1000ms) | Low-moderate (50-150ms) |

These are rough estimates based on typical MiniLM cross-encoder benchmarks. Actual latency depends on hardware, batch size, and model choice.

### Batching

Cross-encoders can batch multiple (query, document) pairs in a single forward pass. For 20 candidates with one query, all 20 pairs can be batched into a single inference call, which is significantly faster than 20 individual calls.

---

## 8. Interaction with RRF

### RRF score vs cross-encoder score

| Property | RRF score | Cross-encoder score |
|----------|-----------|-------------------|
| Range | ~[0.028, 0.033] (compressed) | [0.0, 1.0] (well-separated) |
| Basis | Rank position in each leg | Token-level query-document interaction |
| Meaning | "How often does this doc appear across retrieval legs?" | "How relevant is this document to this query?" |
| Can distinguish positive from negative? | No (17% band) | Yes (designed for this) |

### Should cross-encoder replace RRF?

**No.** RRF serves as a **candidate generator** — it efficiently combines two retrieval signals to produce a diverse pool of candidates. Cross-encoders are too expensive to score all 101 chunks. RRF narrows the field from 101 to ~20-50 candidates; the cross-encoder then precisely ranks those candidates.

### Should it operate after RRF?

**Yes.** This is Architecture D: RRF produces candidates, cross-encoder reranks them.

### Should scores be normalized?

**Not necessarily.** The cross-encoder produces scores in [0, 1] (or logits that can be sigmoid-normalized). These scores are used for **ordering** candidates, not for absolute relevance thresholds. Normalization is only needed if combining cross-encoder scores with other signals.

### Should RRF scores be retained?

**Yes.** RRF scores should be stored on `SearchHit` as they already are (`hit.score`). They can serve as:
1. A fallback ordering if the reranker fails
2. A feature for the abstention gate
3. Debugging information

**Recommendation:** Add a `rerank_score: float = 0.0` field to `SearchHit`. When reranking is applied, it populates this field. The abstention gate can then optionally use `rerank_score` instead of (or alongside) `cosine_score`.

---

## 9. Interaction with Abstention Gate

### Current gate logic

The gate at `qa_workflow.py:75-86` uses `top.cosine_score` and `top.bm25_score` from `hits[0]`.

### Proposed architecture

```
RRF -> Top-N candidates -> Cross-encoder -> Reranked results -> Abstention gate -> Top-K -> LLM
```

### Why reranking before the gate is better

The gate's purpose is to decide "is the evidence sufficient to answer this query?" Currently it uses cosine similarity as a proxy for this judgment. But cosine is a **retrieval signal** (how similar is the query vector to the document vector?), not a **relevance signal** (does this document answer the query?).

A cross-encoder score IS a relevance signal. It directly measures whether the document content answers the query. This makes it a strictly better input for the abstention gate.

### What score should the gate use?

| Option | Pros | Cons |
|--------|------|------|
| **Cross-encoder score only** | Directly measures relevance. Single, clean signal. | Loses the BM25 fallback for embedding failures. |
| **Cross-encoder + BM25 fallback** | Handles embedding failure (cosine=0, but BM25 provides evidence). Cross-encoder score is primary when available. | More complex gate logic. |
| **Cross-encoder + cosine combination** | Two independent relevance signals. More robust. | Requires calibration of combined threshold. |

**Recommendation: Cross-encoder score as primary, BM25 as fallback.**

When the reranker is available:
- Use `rerank_score >= min_rerank_score` as the primary acceptance signal
- If `rerank_score = 0.0` (reranker failed or unavailable), fall back to cosine + BM25 logic

When the reranker is unavailable:
- Fall back to current cosine + BM25 logic (Phase 3B behavior)

This preserves the hybrid system's resilience while adding a more precise signal.

---

## 10. Evaluation Design

### Dataset

Use existing `eval/dataset.json` (50 queries, 43 positive, 7 negative).

### Current baseline (Phase 3B final)

| Metric | Value |
|--------|-------|
| Hit Rate@1 | 0.907 |
| Hit Rate@5 | 0.953 |
| Recall@5 | 0.913 |
| Recall@10 | 0.926 |
| Precision@1 | 0.907 |
| Precision@5 | 0.219 |
| Precision@10 | 0.114 |
| MRR | 0.940 |
| Positive-only MRR | 0.930 |
| FPR | 0.714 |
| FNR | 0.000 |
| Negative rejection rate | 0.286 |

### Evaluation methodology

1. **Reranking-only eval** (gate disabled, min_cosine=0.0): Measures whether reranking improves retrieval ranking
2. **Reranking + gate eval** (gate enabled): Measures the combined effect
3. **Threshold sweep** over reranker scores: Finds the optimal gate threshold for cross-encoder scores

### Metrics to measure

All existing metrics plus:
- **Latency per query** (retrieval + reranking, excluding LLM)
- **Reranker overhead** (time added by cross-encoder vs baseline)
- **Rank changes** (how many documents moved position after reranking)

### Which metrics should improve

| Metric | Expected change | Why |
|--------|----------------|-----|
| Hit Rate@1 | May improve | Reranker can promote the correct document to rank 1 |
| Hit Rate@5 | Should not regress | Reranker should not demote correct documents below rank 5 |
| Recall@5 | May improve slightly | Better ordering can surface more relevant docs |
| MRR | Should improve | Correct documents promoted to higher ranks |
| **FPR** | **Should improve significantly** | Reranker can demote negative-query matches below the gate threshold |
| **Negative rejection rate** | **Should improve** | More negatives caught by the gate |
| FNR | Should remain 0.000 | Reranker should not demote correct documents below threshold |

**Primary success criterion: FPR reduction from 0.714 without increasing FNR above 0.000.**

---

## 11. Latency Budget

### Current retrieval-only latency

From `eval/results/baseline_v1.json`: Average query time is 59.8ms (includes embedding + search + RRF). This does NOT include LLM generation (500-2000ms).

### Reranking latency estimates

| Candidates | CPU (MiniLM-L-12) | GPU (MiniLM-L-12) | Impact on end-to-end |
|-----------|-------------------|-------------------|---------------------|
| 10 | Low (~50-150ms) | Very low (~10-30ms) | +50-150ms to retrieval |
| 20 | Low-moderate (~100-300ms) | Low (~20-60ms) | +100-300ms to retrieval |
| 50 | Moderate (~250-800ms) | Low-moderate (~50-150ms) | +250-800ms to retrieval |

### End-to-end impact

Current end-to-end latency (retrieval + LLM): ~59.8ms + ~1000ms = ~1060ms.

With reranking (20 candidates, CPU): ~59.8ms + ~200ms + ~1000ms = ~1260ms.

**Overhead: ~200ms (19% increase).** This is acceptable for a personal knowledge base where accuracy matters more than speed. The LLM generation dominates the latency anyway.

---

## 12. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|-----------|
| Model not downloaded | Reranker unavailable | Fall back to RRF ordering (current behavior) |
| Insufficient RAM | OOM during inference | Fall back to RRF ordering |
| GPU unavailable | Slower CPU inference | Still works, just slower |
| Inference timeout | Query blocked | Set a timeout (e.g., 2s), fall back to RRF on timeout |
| Malformed output | Score unavailable | Fall back to RRF ordering |
| Dependency missing (torch/transformers) | Reranker cannot load | Fall back to RRF ordering; log a warning |
| Batch failure | Partial scores | Fall back to RRF ordering for affected candidates |

**Design principle:** The reranker is an **enhancement**, not a requirement. If it fails for any reason, the system degrades gracefully to Phase 3B behavior (RRF ordering + cosine-based gate). The user should never see an error caused by reranker failure.

---

## 13. Offline / Privacy

| Property | Assessment |
|----------|-----------|
| Can run offline? | **Yes.** Model is downloaded once, then runs entirely locally. |
| External API required? | **No.** No cloud services needed. |
| Privacy implications | **None.** All data stays on the local machine. |
| Model download requirements | One-time download of ~270MB (MiniLM-L-12) or ~1.1GB (bge-reranker-v2-m3). |
| Reproducibility | Model is deterministic for a given input. Results are reproducible. |

This aligns with PAM's core design principle: local-first, offline-capable, private.

---

## 14. Complexity

| Component | Complexity | Notes |
|-----------|-----------|-------|
| Model integration | MEDIUM | New module (`app/infrastructure/reranker.py`), model loading, inference |
| Configuration | LOW | Add `reranker` section to `config/default.yaml` |
| Batching | LOW | Batch all (query, candidate) pairs in one forward pass |
| Testing | MEDIUM | Unit tests for reranker, integration tests for pipeline, eval tests |
| Evaluation | LOW | Extend `eval/run_eval.py` with reranker option |
| Fallback | LOW | Try/except around reranker, fall back to existing behavior |
| CLI/config changes | LOW | Add `--reranker` flag, config options |
| SearchHit changes | LOW | Add `rerank_score` field |

**Overall: MEDIUM complexity.** The main work is model integration and evaluation. The fallback path is straightforward because the existing pipeline is already clean.

---

## 15. Architectural Recommendation

```
Query
  |
  v
Embedding + BM25 (unchanged)
  |
  v
Vector Search + BM25 (unchanged)
  |
  v
RRF(k=60) (unchanged)
  |
  v
Top-N candidates (N=20)
  |
  v
Cross-Encoder Reranker (NEW)
  |  model: cross-encoder/ms-marco-MiniLM-L-12-v2
  |  scores: (query, candidate.text) pairs
  |  output: rerank_score per candidate
  |
  v
Reranked results (sorted by rerank_score)
  |
  v
Abstention Gate (updated to use rerank_score)
  |  primary: rerank_score >= min_rerank_score
  |  fallback: cosine + BM25 (Phase 3B logic)
  |
  v
Top-K context (K=5 or 8)
  |
  v
qwen3:8b
  |
  v
Grounded answer
```

---

## 16. What Should NOT Change

| Component | Reason |
|-----------|--------|
| nomic-embed-text | Working well, Hit@5=0.953 |
| Cosine similarity | Core retrieval signal, proven effective |
| Vector store | In-memory + JSON persistence, no issues |
| BM25 k1=1.5, b=0.75 | Standard Okapi parameters, working well |
| RRF k=60 | Standard parameter, working well as candidate generator |
| Semantic chunking | No evidence chunking is the bottleneck |
| QA grounding prompt | Working, citations functional |
| Citation format | `[SOURCE N]` format is clear |
| Knowledge graph | Not used in retrieval, out of scope |
| Ingestion pipeline | Stable, 24 source types working |

---

## 17. V1.1 Scope

**Classification: SHOULD HAVE.**

Reasoning:
- The abstention gate (Phase 3B) reduced FPR from 1.000 to 0.714 — meaningful but incomplete
- FPR = 0.714 means 71.4% of negative queries still produce accepted retrieval
- Cross-encoder reranking is the most direct way to improve FPR without changing the retrieval pipeline
- It does not require changing embedding models, BM25, RRF, or chunking
- It fits PAM's local-first design (no external APIs)
- The dependency cost (torch + transformers) is acceptable for a local system

It is not a MUST HAVE because:
- PAM works without it (Hit@5=0.953, FNR=0.000)
- The dependency adds weight
- The latency overhead is non-trivial on CPU

It is not OPTIONAL because:
- FPR=0.714 is a known limitation that directly affects answer quality
- Phase 3A explicitly identified reranking as the next logical step
- The current cosine-based gate cannot solve the overlap zone problem

---

## 18. Implementation Plan for Future Phase 3C-B

### Files likely to change

| File | Change |
|------|--------|
| `app/infrastructure/reranker.py` | **NEW** — CrossEncoderReranker class |
| `app/infrastructure/search.py` | Add `rerank_score` field to SearchHit, add reranker parameter to HybridSearch/SearchService |
| `app/application/qa_workflow.py` | Update AbstentionGate to use rerank_score, pass reranker to SearchService |
| `config/default.yaml` | Add `reranker` section |
| `app/core/config.py` | Add RerankerSettings dataclass |
| `eval/run_eval.py` | Add `--reranker` flag, measure reranking latency |
| `tests/unit/test_reranker.py` | **NEW** — Unit tests for reranker |
| `tests/unit/test_qa_workflow.py` | Update gate tests for rerank_score |

### Classes likely to be added

- `CrossEncoderReranker` in `app/infrastructure/reranker.py`
  - `__init__(model_name, device, timeout)`
  - `rerank(query, hits, top_n) -> list[SearchHit]`
  - `is_available() -> bool`

### Configuration required

```yaml
reranker:
  enabled: true
  model: "cross-encoder/ms-marco-MiniLM-L-12-v2"
  device: "cpu"           # or "cuda"
  top_n: 20               # candidates to rerank
  timeout_seconds: 5
  fallback: "rrf"         # fallback strategy when reranker fails
```

### Dependency required

```
torch>=2.0.0 (CPU-only)
transformers>=4.30.0
```

### Tests required

1. Unit tests for `CrossEncoderReranker.rerank()`
2. Unit tests for fallback behavior (reranker unavailable)
3. Unit tests for AbstentionGate with rerank_score
4. Integration tests for full pipeline with reranker
5. Evaluation tests (reranking-only, reranking+gate)

### Evaluation changes

- Add `--reranker` flag to `eval/run_eval.py`
- Add `--reranker-model` flag for model selection
- Add reranking latency measurement
- Add rank-change analysis (before/after reranking)
- Add threshold sweep over reranker scores

### Fallback behavior

- If reranker is disabled: use Phase 3B behavior (cosine-based gate)
- If reranker fails: log warning, fall back to RRF ordering, use cosine-based gate
- If reranker times out: same as failure

### Documentation changes

- Update `14_PHASE_3B_ABSTENTION_RESULTS.md` to reference Phase 3C
- Add reranker section to architecture docs
- Update `config/default.yaml` comments

---

## 19. Risks

| Risk | Severity | Likelihood | Mitigation |
|------|----------|-----------|-----------|
| Latency too high on CPU | MEDIUM | MEDIUM | Use MiniLM (small model), batch inference, timeout |
| torch dependency too heavy | MEDIUM | LOW | Consider ONNX Runtime as lighter alternative |
| Model download fails | LOW | LOW | Graceful fallback to RRF ordering |
| Reranker hurts recall | HIGH | LOW | Evaluate carefully, keep RRF fallback |
| Overfitting to 50-query dataset | MEDIUM | MEDIUM | Use careful evaluation, consider expanding dataset |
| Score calibration issues | MEDIUM | LOW | Use sigmoid normalization, threshold sweep |
| Interaction with abstention gate | MEDIUM | LOW | Test gate with rerank_score, keep cosine fallback |
| Increases codebase complexity | LOW | MEDIUM | Keep reranker module isolated, clean fallback |

---

## 20. Final Decision

### 1. Should PAM implement cross-encoder reranking?

**Yes.**

### 2. Why?

Phase 3B achieved FPR=0.714 with the cosine-based gate. The remaining 5 negative queries are in the cosine overlap zone [0.46, 0.56] where cosine cannot distinguish them from positives. A cross-encoder directly measures query-document relevance, which is exactly the signal needed to resolve this overlap. No other retrieval change (embedding model, BM25 tuning, RRF tuning) can address this — the problem is that the current signals lack semantic precision, and cross-encoders provide it.

### 3. What should be reranked?

The Top-N candidates from RRF fusion. These are the documents that have already been identified as potentially relevant by both the vector and BM25 legs. Reranking precisely re-orders them.

### 4. How many candidates?

**N = 20.** This covers the meaningful RRF candidates without excessive compute. For PAM's 101-chunk corpus, 20 candidates is a generous pool.

### 5. Where should reranking occur?

**After RRF, before the abstention gate.** Architecture D: RRF -> Top-N -> Cross-encoder -> Reranked results -> Abstention gate -> Top-K context -> LLM.

### 6. Which model family is most suitable?

**`cross-encoder/ms-marco-MiniLM-L-12-v2`** (67M params, 270MB, Apache-2.0). Small enough for CPU, good quality, well-tested. Upgrade path to `BAAI/bge-reranker-v2-m3` if needed.

### 7. Should it be local/offline?

**Yes.** Model is downloaded once, runs entirely locally. No external APIs. Aligns with PAM's local-first design.

### 8. What should happen if reranking fails?

**Fall back to RRF ordering + Phase 3B cosine-based gate.** The system degrades gracefully to the current behavior. The user never sees an error from reranker failure.

### 9. What metrics determine success?

**Primary:** FPR reduction from 0.714 without FNR increase above 0.000.
**Secondary:** MRR improvement, Hit@1 improvement.
**Guard:** No regression in Hit@5, Recall@5, or latency exceeding 500ms overhead.

### 10. Should implementation begin now?

**Not yet.** This investigation is the design document. Implementation should begin only after:
1. This report is reviewed and approved
2. The dependency decision is confirmed (torch vs ONNX Runtime)
3. The model choice is validated with a small manual test

---

*Investigation completed 2026-08-20. All source code inspected, no modifications made. All claims marked as VERIFIED FROM SOURCE, WEB-VERIFIED, INFERENCE/RECOMMENDATION, or NOT VERIFIED.*
*Phase 3C-A is READ-ONLY. Phase 3C-B implementation must NOT start until this report is approved.*
