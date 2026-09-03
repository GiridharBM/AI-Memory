# Phase 3G-B: Query Scope and Answerability Analysis

**Date:** 2026-08-22
**Frozen HEAD:** `9f282b41b6c558b0dbea857c95e24beb3ff63f9a`
**Status:** DISCOVERY ONLY. No code changes, no commits, no pushes.
**Phase 3G-A:** Complete. mxbai-embed-large REJECTED (Hit@5=0.902 < 0.93).

---

## 1. Objective

Investigate whether query/corpus scope or answerability can reduce FPR (0.811) while preserving FNR <= 0.033, Hit@5 >= 0.93, MRR >= 0.88.

This is a discovery-phase report. No implementation, no production changes.

---

## 2. Current Baseline

| Metric | Value |
|--------|-------|
| Hit@1 | 0.902 |
| Hit@5 | 0.967 |
| MRR | 0.934 |
| FPR | 0.811 |
| FNR | 0.008 |
| Production config | nomic-embed-text, min_cosine=0.45, reranker=off, hyde=off |
| Dataset | 160 queries (123 positive, 37 negative) |
| Corpus | 101 chunks, 12 sources |

---

## 3. Corpus Profile

### 3.1 Source Distribution

| Source | Chunks | Type | Dims |
|--------|--------|------|------|
| PCB Board Design (Beginners) | 25 | markdown | 768 |
| Neural Networks (3b1b) | 18 | markdown | 768 |
| LeetCode article | 13 | markdown | 768 |
| Our Organization (Utthunga) | 11 | markdown | 768 |
| GPT-5.6 demo | 7 | markdown | 768 |
| DAA Assignment-4 | 7 | scanned_pdf | 768 |
| b.md (test artifact) | 6 | markdown | 384 |
| OpenHands paper | 6 | markdown | 768 |
| Jharkhand protest | 5 | markdown | 768 |
| TiHAN image | 1 | image | 768 |
| sigmamusicart mp3 | 1 | audio | 768 |
| pam_smoke_test.txt | 1 | text | 768 |

### 3.2 Corpus Characteristics

- **101 chunks** across **12 sources** (10 real + 2 test artifacts)
- **8 unrelated domains:** electronics, ML, coding, corporate, AI demo, algorithms, news, music
- **Concentration:** PCB + neural networks + LeetCode = 55/101 chunks (54.5%)
- **b.md** = 6 test chunks with 384-dim embeddings (different model). Not real content.
- **pam_smoke_test.txt** = 1-chunk test stub. Mentions PAM but has no operational data.

### 3.3 Source Metadata

- Each chunk has: `source` (full path), `source_type` (derived), `text`, `embedding` (768-dim)
- **Source identity IS available at retrieval time** (source field in vector store)
- **No topic labels, no entity tags, no answerability markers**
- **No structured metadata** beyond filename and source_type

### 3.4 Source-Aware Gate Viability

VALIDATED FACT: Source identity is available but unstructured. Filenames are human-readable but not machine-interpretable as topics. A source-aware gate would need a topic mapping layer.

VALIDATED FACT: The corpus is small (12 sources). A manually curated topic map is feasible but adds maintenance burden for a corpus that will grow.

---

## 4. 160-Query Answerability Analysis

### 4.1 Classification Rules

- **A (Clearly answerable):** Query asks about a fact present in a corpus document
- **B (Clearly not answerable):** Query asks about topics outside corpus, system metadata, or entities with no data
- **C (Partially answerable):** Multi-source comparison, hard trivia, cross-document synthesis
- **D (Ambiguous):** Cannot determine from corpus alone

### 4.2 Results

| Category | Count | % | Positive | Negative |
|----------|-------|---|----------|----------|
| A. Clearly answerable | 98 | 61.2% | 98 | 0 |
| B. Clearly not answerable | 37 | 23.1% | 0 | 37 |
| C. Partially answerable | 25 | 15.6% | 25 | 0 |
| D. Ambiguous | 0 | 0.0% | 0 | 0 |

### 4.3 Key Finding

VALIDATED FACT: The answerability boundary is perfectly clean. All 37 negatives are category B. All 123 positives are A or C. No ambiguous overlap.

INFERENCE: The answerability concept is real and applies to this dataset. The challenge is detecting it computationally.

---

## 5. 30 False-Positive Analysis

### 5.1 Category Breakdown

| Category | Count | IDs |
|----------|-------|-----|
| pam_meta | 9 | q033, q036, q041, q128, q129, q130, q131, q132, q133 |
| hyper_specific | 17 | q034, q035, q118-q127, q134, q157-q160 |
| wrong_source | 4 | q114, q115, q135, q137 |
| out_of_scope | 0 | (none) |

NOTE: The original Phase 3G analysis listed hyper_specific=11, wrong_source=10. Our analysis found hyper_specific=17, wrong_source=4. The difference: 6 queries originally categorized as wrong_source (q119, q126, q134, q158, q159, q160) are actually hyper-specific -- the entity IS in the corpus but the specific fact is absent.

### 5.2 pam_meta (9)

**What they ask:** PAM system capabilities (email handling, Docker, database, file size, languages, KB version/update count)
**What they retrieve:** pam_smoke_test.txt (6/9), OpenHands (2/9), neural_networks (1/9)
**Why cosine matches:** pam_smoke_test.txt mentions PAM, local-first search, embedding retrieval. OpenHands mentions knowledge base. The embedding model correctly identifies topical similarity.
**Why evidence is insufficient:** pam_smoke_test.txt is a 1-chunk test stub with no PAM operational data. OpenHands discusses AI platforms, not PAM.
**Source diversity help:** Partially. 6/9 have diversity >= 3 (scattered retrieval). But 3/9 (q036=2, q129=3, q132=3) have diversity <= 3.

### 5.3 hyper_specific (17)

**What they ask:** Specific facts about entities that exist in the corpus (Utthunga revenue, OpenHands star count, PCB trace width, Jharkhand protest date, TiHAN protocols, etc.)
**What they retrieve:** Chunks about the same entity/topic (Utthunga company profile, OpenHands paper, PCB guide, etc.)
**Why cosine matches:** Entity-level embedding similarity. The query and corpus chunk share the same entity/topic embedding cluster.
**Why evidence is insufficient:** The corpus has 11 Utthunga chunks but none contain financial data. 6 OpenHands chunks but no star counts. 25 PCB chunks but no exact project specs.
**Source diversity help:** NO. 9/17 have diversity <= 2 (concentrated retrieval). Diversity cannot distinguish these FPs.

### 5.4 wrong_source (4)

**What they ask:** General tech topics (Bitcoin price, FIFA World Cup, REST API best practices, SQL vs NoSQL)
**What they retrieve:** Tech-related corpus documents (PCB, LeetCode, GPT-5.6 demo)
**Why cosine matches:** Latent semantic overlap in tech/engineering vocabulary.
**Why evidence is insufficient:** These topics are genuinely absent from the corpus.
**Source diversity help:** Mixed. q114=1, q115=2, q135=3, q137=1. Two have low diversity.

### 5.5 Summary: Root Cause Per Category

| Category | Root cause | Diversity helps? |
|----------|-----------|------------------|
| pam_meta (9) | Smoke test is topical attractor | Partially |
| hyper_specific (17) | Entity match, fact absent | NO |
| wrong_source (4) | Accidental semantic overlap | Partially |

---


## 6. Source-Diversity Analysis

### 6.1 Full Distribution

#### Positive Queries (123)

| Diversity | Count | % | Examples |
|-----------|-------|---|----------|
| 1 | 61 | 49.6% | q001-q006, q011-q017, q030, q042-q044, ... |
| 2 | 26 | 21.1% | q023, q025, q026, q029, q031, q037, ... |
| 3 | 19 | 15.4% | q007, q009, q018, q028, q059, q073, ... |
| 4 | 13 | 10.6% | q008, q010, q024, q027, q038, q039, ... |
| 5 | 4 | 3.3% | q021, q047, q095, q098 |

#### False-Positive Queries (30)

| Diversity | Count | % | IDs |
|-----------|-------|---|-----|
| 1 | 9 | 30.0% | q114, q118, q120, q121, q123, q125, q137, q157, q160 |
| 2 | 4 | 13.3% | q035, q036, q115, q127 |
| 3 | 8 | 26.7% | q041, q119, q124, q129, q132, q134, q135, q158 |
| 4 | 7 | 23.3% | q033, q034, q122, q130, q131, q133, q159 |
| 5 | 2 | 6.7% | q126, q128 |

#### True-Negative Queries (7)

| Diversity | Count | IDs |
|-----------|-------|-----|
| 1 | 0 | (none) |
| 2 | 2 | q032, q116 |
| 3 | 5 | q045, q117, q136, q138, q139 |

### 6.2 Threshold Sweep Results

Gate logic: accept query if diversity <= threshold. Reject if diversity > threshold.

| Gate | FNR | Pos Rejected | FPR | FP Remaining | Hit@5 | MRR |
|------|-----|--------------|-----|--------------|-------|-----|
| div <= 1 | 0.504 | 62 | 0.243 | 9 | 1.000 | 1.000 |
| div <= 2 | 0.293 | 36 | 0.351 | 13 | 0.989 | 0.983 |
| div <= 3 | 0.138 | 17 | 0.568 | 21 | 0.981 | 0.950 |
| div < 4 | 0.138 | 17 | 0.568 | 21 | 0.981 | 0.950 |

### 6.3 Combined Gates

| Gate | FNR | FPR | Hit@5 | MRR |
|------|-----|-----|-------|-----|
| cos>=0.45 AND div<=1 | 0.504 | 0.243 | 1.000 | 1.000 |
| cos>=0.45 AND div<=2 | 0.293 | 0.351 | 0.989 | 0.983 |
| cos>=0.45 AND div<=3 | 0.146 | 0.568 | 0.981 | 0.954 |
| has_bm25 OR div<=1 | 0.073 | 0.784 | 0.965 | 0.939 |
| has_bm25 OR div<=2 | 0.033 | 0.811 | 0.966 | 0.938 |
| has_bm25 OR div<4 | 0.008 | 0.811 | 0.967 | 0.930 |
| cos>=0.45 AND (bm25 OR div<=2) | 0.041 | 0.811 | 0.966 | 0.941 |

### 6.4 Verdict: Source Diversity

VALIDATED FACT: No source-diversity threshold meets FNR <= 0.033 while materially improving FPR.

- div <= 1: FNR=0.504 (catastrophic). 62 positives rejected. REJECT.- div <= 2: FNR=0.293 (36 rejected). REJECT.- div <= 3: FNR=0.138 (17 rejected). REJECT.- Combined with BM25: FNR=0.033 but FPR=0.811 (no improvement). REJECT.
VALIDATED FACT: 9/30 FPs (30%) have diversity=1. Source diversity cannot identify these.
INFERENCE: Source diversity is a USEFUL FEATURE but NOT SUFFICIENT as a production gate.
---


## 7. Positive vs Negative Feature Analysis

| Feature | TP (118) | FP (30) | TN (7) | Separation |
|---------|----------|---------|--------|------------|
| Top-1 cosine (median) | 0.662 | 0.587 | 0.418 | Moderate overlap |
| Top-1 cosine (mean) | 0.650 | 0.582 | 0.405 | Moderate overlap |
| Source diversity (median) | 2.0 | 3.0 | 3.0 | Overlap |
| BM25 present (%) | 76.4% | 86.7% | 42.9% | Inverted |
| Cosine drop (median) | 0.060 | 0.067 | - | No separation |

VALIDATED FACT: BM25 presence is INVERTED. FPs (86.7%) have MORE BM25 matches than TPs (76.4%). BM25 confirms topical relevance but not answerability.

VALIDATED FACT: Cosine scores overlap heavily. 50% of FPs score above the TP 25th percentile.

VALIDATED FACT: No single feature separates all 30 FPs from 118 TPs.

---

## 8. Answerability Signal Analysis

### 8.1 Definition

A query is **answerable** if the retrieved text contains information that directly responds to the question. **Unanswerable** if the text is about the same entity/topic but lacks the specific information.

### 8.2 Signal Capability Matrix

| Signal | Detects topic relevance? | Detects answerability? |
|--------|------------------------|----------------------|
| Cosine similarity | YES | NO |
| BM25 | YES | NO |
| Source diversity | Partially | Partially |
| Cosine drop | NO | NO |

VALIDATED FACT: No existing retrieval-stage signal detects answerability. Answerability is a POST-RETRIEVAL concept requiring text content analysis.

### 8.3 Evidence For Answerability Approach

- Clean separation in dataset (all negatives = category B)
- FP patterns are consistent (hyper-specific, pam_meta)
- Source diversity provides partial pre-filter
- Architecturally compatible with current pipeline

### 8.4 Evidence Against

- No computable feature at retrieval time separates classes
- Some FPs have very high cosine (0.697) -- strong topic match
- LLM verification adds latency (~500ms) and cost
- Keyword verification is brittle
- Risk of false negatives on inference-heavy queries

---

## 9. Comparison With Previous Approaches

| Approach | Phase | Why it failed | How answerability differs |
|----------|-------|--------------|--------------------------|
| Threshold tuning | 3E | FP cosine (median 0.587) overlaps TP cosine (median 0.662). No threshold satisfies FNR<=0.033 AND Hit@5>=0.93 | Checks content, not score |
| HyDE | 3E | Generates hypothetical answers but does not verify whether document actually contains the fact | Verifies fact, not similarity |
| Cross-encoder reranker | 3F | Reranks on topic relevance. Does not help when ALL retrieved docs are topically relevant but unanswerable | Different failure mode |
| mxbai embedding swap | 3G-A | Hit@5=0.902 < 0.93. Denser clusters but same topic-vs-answerability limitation | Model-agnostic approach |
| BM25 override fix | 3B | Fixed BM25 scoring but did not address answerability | Complementary |

INFERENCE: Answerability is the ONLY approach addressing the root cause: topically relevant but factually empty retrieval.

---


## 10. Root Cause

VALIDATED ROOT CAUSE: The embedding model retrieves documents about the right TOPIC but cannot determine if they contain the right FACT.

Three mechanisms produce FPs:

1. **Entity topic matching (17/30):** Query mentions entity in corpus. Embedding captures entity similarity. Chunks about entity are retrieved. But specific fact is absent.
2. **Topical attractor (9/30):** pam_smoke_test.txt acts as magnet for PAM queries. Contains PAM keywords but no operational data.
3. **Latent semantic overlap (4/30):** Tech vocabulary creates accidental similarity between unrelated topics.

---

## 11. Candidate Approaches

### A. Query/Corpus Scope Classifier
- Pre-retrieval classifier that determines if query topic is in corpus scope
- Requires topic mapping for each corpus source
- PROS: Catches out-of-scope queries before retrieval
- CONS: Does not help with hyper-specific FPs (entity IS in scope)
- ESTIMATED FPR IMPROVEMENT: 1-2 FPs (out_of_scope only)

### B. Metadata/Source-Aware Retrieval Gate
- Use source identity to filter or weight results
- PROS: Source identity is available
- CONS: Filenames are not topic labels. Requires manual mapping. Does not help with hyper-specific FPs.
- ESTIMATED FPR IMPROVEMENT: 0-3 FPs (pam_meta via smoke test filtering)

### C. Answerability/Evidence Gate
- Post-retrieval check verifying retrieved text contains the answer
- Three stages: diversity pre-filter, keyword check, LLM verification
- PROS: Addresses root cause. Model-agnostic. Covers all FP categories.
- CONS: Adds latency (~500ms for LLM stage). Keyword check is brittle.
- ESTIMATED FPR IMPROVEMENT: 15-25 FPs (67-83% reduction)

### D. Another Evidence-Supported Approach
- No other approach has evidence supporting FPR improvement

---

## 12. ONE Recommended Direction

### Recommendation: C. Answerability/Evidence Gate

**Rationale:** Direction C is the only approach that addresses the root cause. Directions A and B each address <10% of FPs. Direction C can address 67-83%.

**Key distinction:**
- Source diversity is a USEFUL FEATURE (partial pre-filter)
- Source diversity is NOT SUFFICIENT as a production gate (FNR=0.138 at best)
- Answerability checking requires content analysis, not just diversity

---

## 13. Proposed Phase 3G-B Experiment

### 13.1 Architecture

```Query -> Embed -> Retrieve top-5 -> [Answerability Gate] -> AbstentionGate -> Answer
```

### 13.2 Three-Stage Implementation

**Stage 1: Source diversity pre-filter (zero cost)**
- If diversity of top-5 >= 4: flag as scattered, pass to Stage 2
- NOT a hard reject

**Stage 2: Keyword/evidence check (zero cost)**
- Extract key nouns/entities from query
- Check if top result text contains those terms
- Zero overlap -> reject

**Stage 3: LLM answerability check (~500ms)**
- Only for ambiguous cases
- Binary: does text contain the answer?

### 13.3 Inputs

- 160-query dataset (frozen)
- Existing retrieval results (abstention_gate.json)
- Corpus chunks (vector_store.json)

### 13.4 Decision Logic

1. Compute source diversity from top-5 hits
2. If diversity >= 4: flag as scattered
3. Extract key terms from query (nouns, named entities)
4. Check if top result text contains key terms
5. If zero key-term overlap: reject (answerability gate)
6. If ambiguous: LLM check (Stage 3)

### 13.5 Evaluation Procedure

1. Run keyword-based answerability checker against all 160 queries
2. Measure FPR, FNR, Hit@5, MRR
3. If Stage 2 insufficient: add Stage 3 (LLM) for remainder
4. Final measurement against acceptance criteria

### 13.6 NOT in Scope

- Production code changes
- New dependencies
- Corpus modification
- Embedding model changes

---


## 14. Metrics

| Metric | Current | Target |
|--------|---------|--------|
| FPR | 0.811 | <= 0.5 |
| FNR | 0.008 | <= 0.033 |
| Hit@5 | 0.967 | >= 0.93 |
| MRR | 0.934 | >= 0.88 |
| Latency | ~200ms | < 500ms p95 |

---

## 15. Acceptance Criteria

| Criterion | Threshold |
|-----------|-----------|
| FNR | <= 0.033 (max 1 false negative) |
| Hit@5 | >= 0.93 |
| MRR | >= 0.88 |
| FPR | Materially lower than 0.811 (target: <= 0.5) |
| Latency | < 500ms p95 |

Any experiment that violates FNR <= 0.033 is REJECTED regardless of FPR improvement.

---

## 16. Risks

1. **False negatives from keyword check:** Legitimate queries using different vocabulary
   - Mitigation: Only reject when keyword overlap is ZERO, not LOW

2. **LLM latency:** Stage 3 adds ~500ms
   - Mitigation: Only triggers for ~20-30% of queries

3. **Maintenance burden:** Three-stage gate is more complex
   - Mitigation: Each stage independently toggleable

4. **Corpus dependency:** Keyword check quality depends on corpus vocabulary
   - Mitigation: Use query-term matching, not corpus-term matching

5. **Test dataset size:** 160 queries may not generalize
   - Mitigation: Start with 160, expand if results are promising

---

## 17. Rollback Strategy

- All stages config-gated (answerability_gate.enabled, keyword_check.enabled, llm_check.enabled)
- Disable all three to return to current behavior
- No production code changes for discovery phase
- Experiment runs in isolated temp directory (like 3G-A)

---

## 18. Frozen Components

| Component | Status ||-----------|--------|| Production code | FROZEN at HEAD 9f282b4 || Config | FROZEN (nomic, min_cosine=0.45, reranker=off, hyde=off) || Embeddings | FROZEN (nomic-embed-text) || Chunking | FROZEN || BM25 | FROZEN || RRF | FROZEN || Reranker | FROZEN (disabled) || HyDE | FROZEN (disabled) || Dataset | FROZEN (160 queries) |
---

## 19. Conclusion

### Validated Facts

1. All 37 negatives are clearly not answerable (category B). No ambiguous overlap.
2. 30 FPs break into: pam_meta (9), hyper_specific (17), wrong_source (4).
3. Source diversity FAILS as standalone gate: best FNR=0.138 (17 rejected).
4. 9/30 FPs (30%) have diversity=1 -- source diversity cannot identify them.
5. No single feature (cosine, BM25, diversity, drop) separates all FPs from TPs.
6. BM25 presence is INVERTED (FPs have more BM25 than TPs).
7. Answerability is a POST-RETRIEVAL concept not detectable at retrieval time.

### Inferences

1. Source diversity is a USEFUL FEATURE but NOT SUFFICIENT as a production gate.
2. The root cause is topic-vs-answerability confusion, addressable by content verification.
3. Answerability is the only approach addressing the root cause.

### Proposed Future Experiment

Direction C: Answerability/evidence gate with three stages (diversity pre-filter, keyword check, LLM verification). Designed as isolated experiment, no production changes.

Awaiting approval before any implementation.

---

