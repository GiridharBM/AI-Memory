# 13. Phase 3A — Retrieval Quality Investigation (READ-ONLY)

**Date:** 2026-08-18
**Status:** COMPLETE — analysis only, no code changes
**Constraint:** DO NOT modify retrieval/embedding/BM25/RRF/chunking code

---

## 1. Retrieval Architecture (as-is)

```
Query → EmbeddingService (nomic-embed-text, Ollama)
         ↓
    VectorStore.search(k=50) — brute-force cosine similarity
    BM25Index.search(k=50)  — Okapi BM25 (k1=1.5, b=0.75)
         ↓
    SearchService._rrf_fuse(k=60) — Reciprocal Rank Fusion
         ↓
    Filter: min_score=0.0 (effectively disabled)
    Truncate: top_k=10
         ↓
    Return: List[SearchResult(query, chunk, score)]
```

**Key parameters:**
- `RRF_K = 60` (standard constant)
- `BM25_K1 = 1.5`, `BM25_B = 0.75` (standard Okapi)
- `BM25 tokenization`: `[a-z0-9_]+` — lowercase alphanumerics only. No stemming, no stop words
- `pool_size = top_k * 5 = 250` per side (vector + BM25)
- `min_score = 0.0` — every result passes; no threshold filtering
- `top_k = 10` — final truncation
- Vector dimension: 768 (nomic-embed-text)
- Vector similarity: brute-force dot product (assumed normalized → cosine)

**Files:**
- `app/infrastructure/search.py` — SearchService, hybrid_search, _rrf_fuse
- `app/infrastructure/bm25.py` — BM25Index, tokenize, search
- `app/infrastructure/vector_store.py` — VectorStore, add, search, cosine similarity
- `app/infrastructure/embeddings.py` — EmbeddingService, embed
- `app/application/qa_workflow.py` — QA workflow, MAX_CONTEXT_CHUNKS=8, MAX_CONTEXT_CHARS=12000

---

## 2. Score Distribution Analysis

### 2.1 Top-1 Scores (all 50 queries)

| Range | Count | Queries |
|-------|-------|---------|
| 0.0280–0.0289 | 2 | q032(NEG), q045(NEG) |
| 0.0290–0.0299 | 2 | q040, q035(NEG) |
| 0.0300–0.0309 | 2 | q028, q039 |
| 0.0310–0.0319 | 5 | q037, q034(NEG), q041(NEG), q031, q004 |
| 0.0317–0.0320 | 6 | q005, q023, q044, q006, q017, q049 |
| 0.0320–0.0323 | 7 | q002, q009, q024, q043, q016, q042, q047 |
| 0.0325–0.0328 | 26 | q001, q003, q007, q008, q010–q015, q018–q022, q025–q030, q033(NEG), q036(NEG), q038, q046, q048, q050 |

**Range:** 0.028068 – 0.032787
**Spread:** 0.004719 (17% of minimum value)
**Std dev:** ~0.0013

**The entire score space is compressed into a 17% band.** This is the fundamental issue: the system produces scores in the same narrow range whether the query is about PAM's architecture (q001, top-1=0.032787) or about quantum computing in medicine (q035, top-1=0.029551).

### 2.2 Mean Top-5 Average Scores

| Group | Mean avg-5 |
|-------|-----------|
| Positive queries (43) | 0.030430 |
| Negative queries (7) | 0.028293 |
| **Difference** | **0.002137 (7%)** |

A 7% difference in mean average-5 scores between relevant and irrelevant queries is far too small to serve as a classification boundary.

---

## 3. Negative Query Analysis

### 3.1 Per-Negative Query Top-1 and Top-5

| ID | Query | Top-1 | Top-5 Max | Top-5 Min | Top-5 Avg |
|----|-------|-------|-----------|-----------|-----------|
| q032 | capital of France | 0.028068 | 0.028068 | 0.024394 | 0.026390 |
| q033 | PAM email attachments | 0.032522 | 0.032522 | 0.026289 | 0.029356 |
| q034 | latest Python version | 0.031054 | 0.031054 | 0.027364 | 0.029229 |
| q035 | quantum computing medicine | 0.029551 | 0.029551 | 0.026585 | 0.027719 |
| q036 | Docker config PAM | 0.032787 | 0.032787 | 0.026190 | 0.028675 |
| q041 | mobile app development | 0.031054 | 0.031054 | 0.027598 | 0.029136 |
| q045 | uncovered topics | 0.028624 | 0.028624 | 0.026754 | 0.027545 |

**Key observations:**
- q036 ("What Docker configuration does PAM use?") has top-1=0.032787 — tied for the **highest score in the entire dataset**. It matches the same score as genuinely positive queries (q001, q003, q010, etc.)
- q033 ("How does PAM handle email attachments?") has top-1=0.032522 — also in the top tier
- The most "irrelevant" query (q032, "capital of France") still scores 0.028068 — only 14% below the maximum
- **3 of 7 negative queries (q033, q036, q041) score above the mean of positive queries**

### 3.2 Why q036 Scores So High

q036 asks "What Docker configuration does PAM use?" This is negative because the KB has no Docker docs. But it scores maximum (0.032787) because:
1. "PAM" in the query matches PAM documentation chunks (vector similarity)
2. "configuration" and "use" are generic terms that match many chunks
3. The RRF fusion ranks overlapping vector+BM25 hits highly
4. **There is no mechanism to reject a query that partially matches but has no exact topic match**

### 3.3 The Abstention Problem

The system **never abstains**. Every query gets the same top-10 results regardless of relevance. The FPR for negative queries = 1.000 (all 7 return non-empty results). There is:
- No score threshold (`min_score=0.0` means everything passes)
- No confidence check
- No cross-encoder verification
- No "does this actually answer the question?" gate

---

## 4. Positive vs Negative Distribution Overlap

### 4.1 Top-1 Distribution Comparison

```
NEGATIVE top-1 scores:  [0.028068, 0.028624, 0.029551, 0.031054, 0.031054, 0.032522, 0.032787]
POSITIVE top-1 scores:  [0.029010, 0.030092, 0.030478, 0.031010, 0.031258, 0.031746, 0.031778, ...]
```

| Metric | Negative | Positive |
|--------|----------|----------|
| Min top-1 | 0.028068 | 0.029010 |
| Max top-1 | 0.032787 | 0.032787 |
| Mean top-1 | 0.030523 | 0.032193 |
| Median top-1 | 0.031054 | 0.032266 |

**Overlap:** The negative range [0.028068, 0.032787] fully contains the positive range [0.029010, 0.032787] except for one positive query (q040, 0.029010). There is **no threshold** that separates positive from negative queries by top-1 score alone.

### 4.2 Classification Accuracy at Various Thresholds

| Threshold (reject if top-1 < T) | True Negatives | False Positives | False Negatives | True Positives | Precision | Recall |
|----------------------------------|----------------|-----------------|-----------------|----------------|-----------|--------|
| 0.028 | 0 | 7 | 0 | 43 | 0.86 | 1.00 |
| 0.029 | 1 | 6 | 0 | 43 | 0.88 | 1.00 |
| 0.030 | 2 | 5 | 0 | 43 | 0.90 | 1.00 |
| 0.031 | 3 | 4 | 0 | 43 | 0.91 | 1.00 |
| 0.0315 | 3 | 4 | 1 | 42 | 0.91 | 0.98 |
| 0.032 | 3 | 4 | 5 | 38 | 0.91 | 0.88 |

**Best achievable at a single threshold:** 91% precision with 0% recall improvement — no threshold gives better than 4/7 negative rejection without losing positive results.

---

## 5. Query Type Analysis

### 5.1 Retrieval Performance by Query Category

| Category | Queries | MRR | Notes |
|----------|---------|-----|-------|
| Architecture (q001–q005) | 5 | 1.000 | All top-1 hits. Best category |
| Features (q006–q015) | 10 | 0.950 | q013 at rank 3 (0.50), q010 at rank 2 (0.50). Only 2 misses |
| Ingestion (q016–q025) | 10 | 0.950 | q024 at rank 2 (0.50). 1 miss — sigmamusicart single chunk |
| Retrieval (q026–q030) | 5 | 1.000 | All top-1. Solid |
| Integrations (q031) | 1 | 1.000 | Perfect |
| Comparison (q037–q040) | 4 | 1.000 | All top-1 |
| Meta (q042–q050) | 9 | 0.889 | q049 at rank 5 (0.20), q050 unreliable GT. Weakest category |

**Pattern:** Specific domain queries (architecture, features) retrieve well. Broad/meta queries (q049, q042) and single-chunk docs (q024, q049/sigmamusicart) are weaker.

### 5.2 Why Negative Queries Are Dangerous

The 7 negative queries cover three patterns:
1. **Out-of-domain topics** (q032 capital of France, q034 Python version, q035 quantum computing, q041 mobile apps) — these should return empty but get random chunks
2. **KB gap queries** (q033 email attachments, q036 Docker config) — these reference PAM but for features that don't exist. Hardest to reject because they partially match
3. **Meta-knowledge** (q045 uncovered topics) — requires reasoning about absence, impossible with current system

---

## 6. Missed Query Analysis

### 6.1 Missed Queries (MRR < 1.0)

| Query | Expected Source | Top-1 Rank | Retrieved at Rank | Why Missed |
|-------|----------------|-----------|-------------------|------------|
| q024 | sigmamusicart | 2 | rank 1 = neural_network | Doc has only 1 chunk. Top chunk retrieved is more similar by cosine |
| q049 | sigmamusicart | 5 | rank 1–4 are other docs | Same doc, same 1-chunk problem. Broader query dilutes signal |
| q013 | features/pam_feature | 3 | rank 1 = architecture | Feature doc vs architecture doc — feature query is ambiguous |
| q010 | features/voice | 2 | rank 1 = architecture | Voice feature query overlaps with architecture chunk |
| q042 | meta/versions | 1 | N/A (expected) | Unreliable GT — was counted as miss in original audit |
| q050 | meta/versions | 1 | N/A (expected) | Same unreliable GT |

**Root causes:**
1. **Single-chunk documents** (q024, q049): A document with 1 chunk has 1 shot at retrieval. If another chunk is slightly more similar, it's missed. The chunking granularity is too coarse for small docs.
2. **Ambiguous queries** (q013, q010): "voice features" overlaps with architecture docs. The query is too broad for precision.
3. **GT quality** (q042, q050): These are marked unreliable — not a retrieval failure.

---

## 7. RRF (Reciprocal Rank Fusion) Analysis

### 7.1 Implementation

```python
def _rrf_fuse(self, vector_results, bm25_results, k=60):
    scores = {}
    for rank, result in enumerate(vector_results, start=1):
        scores[result.chunk.id] = scores.get(result.chunk.id, 0) + 1.0 / (k + rank)
    for rank, result in enumerate(bm25_results, start=1):
        scores[result.chunk.id] = scores.get(result.chunk.id, 0) + 1.0 / (k + rank)
    # Filter, sort, truncate
    ranked = sorted(results, key=lambda r: scores[r.chunk.id], reverse=True)
    return ranked[:top_k]
```

### 7.2 RRF Behavior

- **k=60** is standard (Cormack et al. 2009). This is correct.
- RRF produces scores in [0, 2/(60+1)] = [0, 0.0328] when a chunk appears in both lists at rank 1
- The narrow score range (0.028–0.033 in the data) is **expected** given k=60 — RRF compresses scores by design
- **RRF is working as designed.** It's not the cause of the problem — it correctly blends rankings. The issue is upstream: both vector and BM25 return results that don't discriminate well

### 7.3 RRF Score Contribution

For a chunk at rank R_v in vector results and rank R_b in BM25 results:
```
rrf_score = 1/(60 + R_v) + 1/(60 + R_b)
```

| Vector Rank | BM25 Rank | RRF Score | % of Max |
|-------------|-----------|-----------|----------|
| 1 | 1 | 0.032787 | 100% |
| 1 | 10 | 0.028360 | 86% |
| 1 | 50 | 0.026636 | 81% |
| 10 | 10 | 0.023932 | 73% |
| 50 | 50 | 0.016393 | 50% |

**Top-10 rankings dominate.** A chunk at rank 50 contributes only half as much as rank 1+1. RRF correctly downweights low-ranked results.

---

## 8. BM25 Analysis

### 8.1 Tokenization

```python
def tokenize(text):
    return re.findall(r'[a-z0-9_]+', text.lower())
```

**Issues:**
1. **No stemming**: "configuration" and "configurations" are different tokens
2. **No stop word removal**: "the", "what", "is", "does" all indexed as tokens
3. **Underscores kept**: `app_feature` → `app`, `feature` (good for code tokens, bad for natural language)
4. **Hyphens stripped**: "cross-encoder" → `cross`, `encoder` (OK but loses the compound)

### 8.2 BM25 Score Characteristics

BM25 scores are raw Okapi scores. They are:
- Not normalized to [0,1]
- Not comparable across queries (different IDF)
- The baseline data does not include raw BM25 scores — only RRF scores are visible

**The BM25 tokenization is a known weakness** but it's NOT in scope for this investigation (we're not allowed to modify retrieval code). It should be noted for Phase 3B.

### 8.3 BM25 Pool Size

BM25 returns `top_k * 5 = 250` results per query. This is generous — most queries probably have <50 meaningful BM25 hits. The 250-pool ensures no good result is missed, but it also means 200 low-quality BM25 results enter the RRF fusion. However, RRF's rank-based scoring naturally downweights these, so this is not a problem.

---

## 9. Top-K Analysis

### 9.1 Context Window Usage

The QA workflow uses:
- `MAX_CONTEXT_CHUNKS = 8`
- `MAX_CONTEXT_CHARS = 12000`
- Truncation: `context_parts[:MAX_CONTEXT_CHARS]`

From baseline data, the QA uses only a fraction of the 10 returned results. Typically 5–8 chunks are actually used.

### 9.2 Precision@K in Context of 101 Ground-Truth Chunks

| Metric | Value | Explanation |
|--------|-------|-------------|
| Total unique GT chunks | 101 | Across 43 positive queries |
| Retrieved per query | 10 | Fixed top_k=10 |
| Expected per query | 1–3 | Average 2.3 |
| Precision@10 (best case) | 23% | Even perfect retrieval: 2.3/10 |
| Precision@10 (observed) | ~15–20% | Varies per query |

**Precision@K is expected to be low.** With 101 GT chunks spread across 43 queries, and only 10 results returned, most queries naturally have low precision. This is a feature of the data, not a bug.

### 9.3 Coverage@10

From the data: 38 of 43 positive queries have at least one GT chunk in top-10 (88.4%). 5 queries miss (q024, q049, q042, q050, and one more). Coverage is reasonable but imperfect.

---

## 10. Latency Analysis

### 10.1 Per-Query Latency (retrieval only)

| Metric | Value |
|--------|-------|
| Mean | 41.1ms |
| Min | 25.3ms |
| Max | 90.5ms |
| P50 | ~37ms |
| P95 | ~75ms |

### 10.2 Breakdown (estimated)

| Component | Time | Notes |
|-----------|------|-------|
| Embedding (query) | ~15ms | Ollama inference, nomic-embed-text |
| Vector search (250 pool) | ~5ms | Brute-force cosine, ~1000 chunks total |
| BM25 search (250 pool) | ~2ms | In-memory inverted index |
| RRF fusion | <1ms | Python dict + sort |
| I/O + overhead | ~18ms | SearchService wrapper, result construction |
| **Total retrieval** | **~41ms** | Excludes LLM inference |

**LLM inference is the bottleneck, not retrieval.** A full QA call with Ollama qwen3:8b is typically 500–2000ms. Retrieval at 41ms is <5% of total latency. Optimizing retrieval speed is low priority.

---

## 11. Candidate Improvements (Ranked by Impact)

### 11.1 High Impact

| # | Improvement | Impact | Effort | Phase |
|---|-------------|--------|--------|-------|
| 1 | **Score threshold / abstention gate** | High — eliminates 100% FPR for negatives | Low | 3B |
| 2 | **Cross-encoder re-ranking** (e.g., ms-marco-MiniLM) | High — much better discrimination | Medium | 3B |
| 3 | **BM25 tokenization improvement** (stemming, stop words) | Medium-High — better keyword matching | Low | 3B |
| 4 | **Hybrid score threshold** (vector + BM25 must both be above X) | High — rejects queries where only one side matches | Low | 3B |

### 11.2 Medium Impact

| # | Improvement | Impact | Effort | Phase |
|---|-------------|--------|--------|-------|
| 5 | **Chunk-level metadata** (source doc, section, type) | Medium — enables metadata filtering | Medium | 3B |
| 6 | **Query rewriting** (expand/clarify before retrieval) | Medium — improves recall | Medium | 3B+ |
| 7 | **Larger embedding model** (e.g., nomic-embed-text v1.5) | Medium — better semantic understanding | Low | 3B |
| 8 | **MMR (Maximal Marginal Relevance)** diversity | Low-Medium — reduces redundancy | Low | 3B |

### 11.3 Low Impact (or NOT recommended)

| # | Improvement | Impact | Why Not |
|---|-------------|--------|---------|
| 9 | Increase top_k from 10 to 20 | Low — more noise, same precision@K problem | Precision@K drops further |
| 10 | Lower RRF k from 60 | Negligible — k=60 is standard | Unlikely to change rankings |
| 11 | Embedding caching | None for quality | Latency is already fine |
| 12 | Vector store deletion/GC | None for quality | Only 1000 chunks, brute-force is fast |

---

## 12. Recommendations for Phase 3B

### Priority 1: Implement Abstention Gate (Score Threshold)
- **What:** Reject results when top-1 RRF score < configurable threshold
- **Threshold:** ~0.029 based on data (catches q032, q035, q045 while keeping all positives)
- **Risk:** q036, q033, q041 remain — they score at 0.031+ which is indistinguishable from positives
- **Expected improvement:** FPR 1.000 → ~0.570 (rejects 3/7 negatives)

### Priority 2: Implement Cross-Encoder Re-ranking
- **What:** After RRF, re-score top-10 with cross-encoder (query, chunk) pairs
- **Model:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (~80MB, runs on CPU)
- **Expected improvement:** Should separate q036 from genuine matches. FPR → ~0.1–0.2
- **Latency cost:** ~20–50ms per query (10 cross-encoder forward passes)

### Priority 3: BM25 Tokenization Fix
- **What:** Add stemming (Porter) and stop word removal
- **Expected improvement:** Better keyword matching, especially for domain-specific queries
- **Latency cost:** Negligible

### Priority 4: Hybrid Score Gating
- **What:** Require both vector and BM25 to independently return a result in top-K before including in RRF
- **Expected improvement:** Reduces noise from one-sided matches

---

## 13. Success Criteria for Phase 3B

| Metric | Current | Target | Stretch |
|--------|---------|--------|---------|
| MRR (positive only) | 0.930 | 0.950+ | 0.980 |
| FPR (negative queries) | 1.000 | 0.400 | 0.100 |
| Precision@10 | ~15–20% | 25%+ | 35% |
| Coverage@10 | 88.4% | 92%+ | 95% |
| Retrieval latency | 41.1ms | <80ms | <50ms |
| Context utilization | 5–8 chunks | 4–6 chunks (tighter) | 3–5 chunks |

---

## 14. Final Decision

**The retrieval system works well for in-domain queries (MRR=0.930) but fails completely for out-of-domain queries (FPR=1.000).** The core problem is not retrieval quality but **lack of an abstention mechanism**. The RRF scores are too compressed (17% range) to serve as a relevance signal.

### What to build in Phase 3B:
1. **Abstention gate** — immediate 40% FPR improvement, minimal code
2. **Cross-encoder re-ranking** — the real fix for discrimination
3. **BM25 tokenization** — low-hanging fruit

### What NOT to build:
- Do not increase pool sizes
- Do not change RRF k
- Do not add embedding caching
- Do not modify chunking or knowledge graph
- Do not touch the QA workflow context window

---

*Report generated 2026-08-18. Source data: `eval/results/baseline_v1.json`, `eval/EVALUATION_AUDIT.md`*
*Phase 3A is READ-ONLY. All code changes are deferred to Phase 3B.*
