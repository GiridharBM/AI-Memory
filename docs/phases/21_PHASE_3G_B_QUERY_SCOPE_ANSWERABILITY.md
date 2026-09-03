# Phase 3G-B: Query Scope and Answerability Analysis

**Date:** 2026-08-22
**Frozen HEAD:** `9f282b41b6c558b0dbea857c95e24beb3ff63f9a`
**Status:** DISCOVERY ONLY - no code changes, no commits, no pushes
**Phase 3G-A:** Complete, REJECTED (mxbai-embed-large failed acceptance)

---

## Executive Summary

The 30 false positives (FPR=0.811) break into three categories:
1. **PAM/meta/system queries (9):** Ask about PAM itself; pam_smoke_test.txt is a test stub
2. **Hyper-specific detail queries (17):** Topic exists in corpus but specific fact is absent
3. **Out-of-scope queries (4):** Completely unrelated (Bitcoin, FIFA, REST API, SQL vs NoSQL)

**Key finding:** The embedding model cannot distinguish 'about Utthunga' from 'has Utthunga revenue data.' No existing signal (cosine, BM25, source diversity, cosine drop) can reliably separate all 30 FPs from 118 TPs.

**Recommendation:** Direction C - Answerability/evidence gate. A post-retrieval check verifying retrieved text contains the information the query requests, not just that it is topically related.

---

## 1. Answerability Classification (160 queries)

| Category | Count | % | Positive | Negative |
|----------|-------|---|----------|----------|
| A. Clearly answerable | 98 | 61.2% | 98 | 0 |
| B. Clearly not answerable | 37 | 23.1% | 0 | 37 |
| C. Partially answerable | 25 | 15.6% | 25 | 0 |
| D. Ambiguous | 0 | 0.0% | 0 | 0 |

All 37 negatives fall into category B (clearly not answerable). No ambiguous overlap exists. The answerability boundary is clean - the challenge is detecting it computationally.

---

## 2. False Positive Analysis (30 FPs)

### 2.1 Category Breakdown

| Category | Count | IDs |
|----------|-------|-----|
| PAM/meta/system | 9 | q033, q036, q041, q128, q129, q130, q131, q132, q133 |
| Hyper-specific detail | 17 | q034, q035, q118-q127, q134, q157-q160 |
| Out-of-scope | 4 | q114, q115, q135, q137 |

### 2.2 PAM/Meta/System (9)

| ID | Query | Top Source | Cos | Diversity |
|----|-------|-----------|-----|-----------|
| q033 | How does PAM handle email attachments? | pam_smoke_test.txt | 0.558 | 4 |
| q036 | What Docker configuration does PAM use? | pam_smoke_test.txt | 0.543 | 2 |
| q041 | Does KB contain info about mobile app dev? | OpenHands | 0.541 | 3 |
| q128 | How many documents in the KB? | neural_networks | 0.467 | 5 |
| q129 | What version of the KB is loaded? | OpenHands | 0.530 | 3 |
| q130 | When was KB last updated? | Our Organization | 0.479 | 4 |
| q131 | What database for embeddings? | pam_smoke_test.txt | 0.647 | 4 |
| q132 | Max file size PAM can process? | pam_smoke_test.txt | 0.596 | 3 |
| q133 | How does PAM handle multiple languages? | pam_smoke_test.txt | 0.579 | 4 |

**Root cause:** pam_smoke_test.txt is a 1-chunk test stub mentioning 'PAM' and 'local-first search' - enough for high cosine but zero operational data. 6/9 retrieve from it.

### 2.3 Hyper-Specific Detail (17)

| ID | Query | Top Source | Cos | Diversity |
|----|-------|-----------|-----|-----------|
| q034 | Latest version of Python? | LeetCode | 0.491 | 4 |
| q035 | Quantum computing in medicine? | neural_networks | 0.539 | 2 |
| q118 | Utthunga annual revenue? | Our Organization | 0.606 | 1 |
| q119 | Languages OpenHands supports? | OpenHands | 0.697 | 3 |
| q120 | Layers in video NN? | neural_networks | 0.714 | 1 |
| q121 | Exact PCB trace width mm? | PCB Board Design | 0.710 | 1 |
| q122 | Name of sigmamusicart song? | OpenHands | 0.511 | 4 |
| q123 | Exact date Jharkhand protest? | Jharkhand | 0.701 | 1 |
| q124 | Stock price of OpenAI? | GPT-5.6 demo | 0.487 | 3 |
| q125 | IP2312 voltage range? | PCB Board Design | 0.652 | 1 |
| q126 | TiHAN vehicle comm protocols? | TiHAN image | 0.698 | 5 |
| q127 | ML framework Utthunga uses? | Our Organization | 0.602 | 2 |
| q134 | Accuracy of OpenHands code gen? | OpenHands | 0.679 | 3 |
| q157 | Cost of JLCPCB order? | PCB Board Design | 0.604 | 1 |
| q158 | TiHAN webcam model? | TiHAN image | 0.691 | 3 |
| q159 | OpenHands GitHub stars? | OpenHands | 0.616 | 4 |
| q160 | GPT-5.6 display refresh rate? | GPT-5.6 demo | 0.625 | 1 |

**Root cause:** Entity/topic exists in corpus but the specific fact is absent. Utthunga (11 chunks) has no revenue data. OpenHands (6 chunks) has no star count. PCB guide (25 chunks) gives guidance, not exact project specs.

### 2.4 Out-of-Scope (4)

| ID | Query | Top Source | Cos | Diversity |
|----|-------|-----------|-----|-----------|
| q114 | Current price of Bitcoin? | PCB Board | 0.469 | 1 |
| q115 | Who won 2026 FIFA World Cup? | Jharkhand | 0.455 | 2 |
| q135 | Best practices for REST API? | GPT-5.6 | 0.527 | 3 |
| q137 | SQL vs NoSQL databases? | LeetCode | 0.452 | 1 |

### 2.5 Why Embedding Retrieval Finds High-Similarity Chunks

Three mechanisms:
1. **Entity topic matching (17/30):** Query mentions an entity in the corpus. Embedding captures entity-level similarity. System retrieves chunks about that entity. But the chunks do not contain the specific fact requested.
2. **Topical attractor (9/30):** pam_smoke_test.txt acts as a magnet for PAM-related queries. It contains PAM-related keywords but no operational data.
3. **Latent semantic overlap (4/30):** General engineering/tech vocabulary creates accidental similarity.

### 2.6 Common Structural Property

**There is no single computable signal that separates all 30 FPs from the 118 TPs.**

However, the FPs share a structural property: **the retrieved text is ABOUT the entity but does NOT CONTAIN the answer.** This is the answerability concept - it requires checking whether the text content matches the query's information need, not just its topic.

---

## 3. Corpus Topic Profile

### 3.1 Source Distribution

| Document | Chunks | Topic |
|----------|--------|-------|
| PCB Board Design (Beginners) | 25 | Electronics/hardware |
| Neural Networks (3b1b) | 18 | Deep learning education |
| LeetCode article | 13 | Coding interview critique |
| Our Organization (Utthunga) | 11 | Company profile |
| GPT-5.6 demo | 7 | AI model demo transcript |
| DAA Assignment-4 | 7 | Algorithm assignment |
| b.md | 6 | Test artifact |
| OpenHands paper | 6 | AI developer platform |
| Jharkhand protest | 5 | Indian news event |
| TiHAN image | 1 | Autonomous navigation |
| sigmamusicart mp3 | 1 | Song analysis |
| pam_smoke_test.txt | 1 | PAM test stub |

**Concentration:** PCB + neural networks + LeetCode = 55/101 chunks (54.5%).

### 3.2 Topic Boundaries

8 unrelated domains. From a human perspective, boundaries are clear. The embedding model represents them as a continuous semantic space with no hard boundaries. A query about 'Utthunga revenue' lands near 'Utthunga company profile' in embedding space, even though revenue data does not exist.

### 3.3 Available Metadata

Each chunk has: source, source_type, text, embedding (768-dim).
**No topic labels, no entity tags, no answerability markers.** The only metadata is the source filename.

---

## 4. Feature Analysis

### 4.1 Comparison

| Feature | TP (118) | FP (30) | TN (7) | Separation |
|---------|----------|---------|--------|------------|
| Top-1 cosine (median) | 0.662 | 0.587 | 0.418 | Moderate overlap |
| Top-1 cosine (mean) | 0.650 | 0.582 | 0.405 | Moderate overlap |
| Source diversity (median) | 2.0 | 3.0 | 3.0 | Strongest signal |
| BM25 present (%) | 76.4% | 86.7% | 42.9% | Inverted |
| Cosine drop (median) | 0.060 | 0.067 | - | No separation |

### 4.2 Key Findings

**Source diversity is the strongest signal** but imperfect:
- TP median = 2 (concentrated from same source)
- FP median = 3 (scattered across sources)
- Some TPs have diversity=3, some FPs have diversity=1

**BM25 presence is inverted** - FPs have MORE BM25 matches (86.7% vs 76.4%). BM25 confirms topical relevance but not answerability.

**No single feature separates all 30 FPs from 118 TPs.**

---

## 5. Answerability Signal Investigation

### 5.1 Definition

A query is **answerable** if the retrieved text contains information that directly responds to the question. **Unanswerable** if the text is about the same entity/topic but lacks the specific information.

Example:
- 'When was Utthunga founded?' -> Answerable (text says 'founded in 2007')
- 'What is Utthunga annual revenue?' -> Unanswerable (text describes company but has no financial data)

### 5.2 Signal Capability

| Signal | Topic relevance? | Answerability? |
|--------|-----------------|----------------|
| Cosine similarity | YES | NO |
| BM25 | YES | NO |
| Source diversity | Partially | Partially |
| Cosine drop | NO | NO |

**Conclusion:** No existing retrieval-stage signal detects answerability. Answerability is a POST-RETRIEVAL concept - it requires checking whether the retrieved text content matches the query's information need.

### 5.3 Evidence For Answerability

- Clean separation in dataset (all negatives = category B)
- FP patterns are consistent (hyper-specific, PAM/meta)
- Source diversity provides partial pre-filter
- Architecturally compatible with current pipeline

### 5.4 Evidence Against

- No computable feature at retrieval time separates classes
- Some FPs have very high cosine (0.697) - strong topic match
- LLM verification adds latency (~500ms) and cost
- Keyword verification is brittle
- Risk of false negatives on inference-heavy queries

---

## 6. Comparison with Failed Approaches

### 6.1 vs Threshold Tuning (Phase 3E)

Threshold tuning operates at RETRIEVAL time. It raises the cosine bar to reject low-confidence hits. Failed because FP cosine scores (median 0.587) overlap heavily with TP scores (median 0.662). No threshold satisfies FNR<=0.033 AND Hit@5>=0.93.

Answerability operates at POST-RETRIEVAL time. It checks content, not score. Different axis entirely.

### 6.2 vs Embedding Model Swap (Phase 3G-A)

Model swap changes the embedding space geometry. mxbai-embed-large has denser clusters but does not add semantic understanding of 'does this text answer the question.' Same fundamental limitation: embedding similarity is about topic, not answerability.

Answerability is model-agnostic. It works with any embedding model.

### 6.3 vs Cross-Encoder Reranking (Phase 3F)

Cross-encoder re-scores query-document pairs. It improves ranking quality but still operates on topic relevance. It helps when relevant and irrelevant documents are mixed in top-k, but does not help when ALL retrieved documents are topically relevant but unanswerable.

Answerability addresses a different failure mode: topically relevant but factually empty.

### 6.4 vs HyDE (Phase 3E)

HyDE generates hypothetical answers and embeds them. It helps find semantically closer documents but does not verify whether the document actually contains the fact. Same limitation as cross-encoder.

### 6.5 Unique Value Proposition

Answerability is the ONLY approach that directly addresses the root cause: **the system retrieves documents about the right topic but cannot tell if they contain the right fact.** All other approaches optimize different parts of the retrieval pipeline.

---

## 7. Recommendation: Direction C - Answerability Gate

**Architecture:** Post-retrieval verification layer inserted between retrieval and the existing AbstentionGate.

```
Query -> Embed -> Retrieve top-5 -> [Answerability Gate] -> AbstentionGate -> Answer
```

### 7.1 Three-Stage Implementation

**Stage 1: Source diversity pre-filter (fast, zero cost)**
- If diversity of top-5 >= 4: flag as 'scattered' - likely unanswerable
- Catches: q128 (diversity=5), q126 (5), q131 (4), q133 (4), q159 (4), q033 (4), q130 (4)
- NOT a hard reject - passes to Stage 2

**Stage 2: Keyword/evidence check (fast, zero cost)**
- Extract key nouns/entities from query (simple NLP or regex)
- Check if top result text contains those terms
- 'Revenue' not in Utthunga text -> reject
- 'Docker' not in pam_smoke_test.txt -> reject
- 'GitHub stars' not in OpenHands text -> reject
- Catches: most PAM/meta + many hyper-specific FPs

**Stage 3: LLM answerability check (expensive, ~500ms)**
- Only for queries that pass Stage 2 but are still flagged
- Ask: 'Does the following text contain the answer to: [query]?'
- Binary yes/no
- Catches remaining edge cases

### 7.2 Expected Impact

| Metric | Current | Expected |
|--------|---------|----------|
| FPR | 0.811 | 0.4-0.5 |
| FNR | 0.008 | <=0.033 |
| Hit@5 | 0.967 | >=0.93 |
| MRR | 0.934 | >=0.88 |
| Latency | ~200ms | ~250-300ms |

### 7.3 FP Categories Addressed

| Category | Stage 1 | Stage 2 | Stage 3 |
|----------|---------|---------|---------|
| PAM/meta (9) | Partial | Mostly | All |
| Hyper-specific (17) | Partial | Mostly | All |
| Out-of-scope (4) | Most | All | All |

### 7.4 Risks

1. **False negatives from keyword check:** Legitimate queries using different vocabulary than corpus
   - Mitigation: Only reject when keyword overlap is ZERO, not LOW
2. **LLM latency:** Stage 3 adds ~500ms
   - Mitigation: Only triggers for ~20-30% of queries; can be parallelized
3. **Maintenance burden:** Three-stage gate is more complex
   - Mitigation: Each stage is independently testable and toggleable
4. **Corpus dependency:** Keyword check quality depends on corpus vocabulary
   - Mitigation: Use query-term matching, not corpus-term matching

### 7.5 Rollback

- All stages are config-gated (answerability_gate.enabled, keyword_check.enabled, llm_check.enabled)
- Disable all three to return to current behavior
- No production code changes required for discovery phase

---

## 8. Experiment Proposal

### 8.1 Scope

Build answerability gate as separate experiment (like 3G-A). Measure against 160-query dataset.

### 8.2 Steps

1. Build keyword-based answerability checker (no new dependencies)
2. Run against all 160 queries
3. Measure: FPR, FNR, Hit@5, MRR
4. If Stage 2 insufficient, add Stage 3 (LLM) for remainder
5. Final measurement against acceptance criteria

### 8.3 Acceptance Criteria

| Criterion | Threshold |
|-----------|-----------|
| FNR | <=0.033 (max 1 FN) |
| Hit@5 | >=0.93 |
| MRR | >=0.88 |
| FPR | Materially lower than 0.811 (target: <=0.5) |
| Latency | <500ms p95 |

### 8.4 NOT in scope

- Production code changes
- New dependencies
- Corpus modification
- Embedding model changes

---

## 9. Next Steps

Awaiting approval to proceed with experiment. No code changes made.
