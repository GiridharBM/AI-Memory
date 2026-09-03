# Phase 5E — FPR / Abstention Root-Cause and Signal Analysis

**Status:** DISCOVERY COMPLETE. Analysis only — no production code, config, corpus, or dataset modified. No commits.
**Date:** 2026-08-27
**Approval:** Phase 5E (discovery-only) authorized.

---

## 1. Objective

Root-cause the false-positive problem (FPR 0.857, 36/42 negatives accepted) on the frozen 199-query real-corpus dataset, measure every available cancelation signal against the actual TP/FP populations, evaluate whether any lightweight separator can satisfy the acceptance criteria without production changes, and recommend exactly one evidence-supported next direction.

**Constraint honored:** all experiments were offline. The only writes were to `C:\Users\girid\AppData\Local\Temp\opencode\` (analysis scripts + capture); no production file was modified.

## 2. Frozen baseline (reference)

| Metric | Value |
|---|---|
| Hit@1 | 0.841 (132/157) |
| Hit@5 | 0.924 (145/157) |
| MRR | 0.877 |
| FPR | 0.857 (36/42) |
| FNR | 0.000 |
| Abstention rate | 0.030 (6/199) |
| Positive acceptance | 1.000 |
| Negative rejection | 0.143 (6/42) |
| Latency p50 / p95 | 37.4 / 47.1 ms |

Configuration unchanged: top_k=5, min_cosine=0.45, BM25 k1=1.5 b=0.75, RRF k=60, no reranker/HyDE/answerability.

## 3. Dataset composition

| Set | Count |
|---|---|
| Total queries | 199 |
| Positive (rank-verified) | 157 |
| Negative (abstention-supervised) | 42 (37 legacy + 5 new q196–q200) |
| Corpus | 24 sources / 195 chunks, nomic-embed-text 768-dim |

All numbers below come from a fresh full run of the 199 queries (13.8 s) capturing per-hit cosine/BM25/RRF, chunk text, source type, and heading metadata. This capture is byte-identical in correctness to the frozen baseline (deterministic retrieval).

## 4. FP inventory (36 accepted negatives)

### 4.1 Full table (all rows)

| ID | Query (trimmed) | Cat | cos | bm25 | rrf | gap | div | conc | top-1 source |
|---|---|---|---|---|---|---|---|---|---|
| q033 | How does PAM handle email attachments? | F | 0.579 | 0.0 | .0305 | .034 | 1 | 5 | PAM_V1_LEARNING_GUIDE.pdf |
| q034 | What is the latest version of Python? | E | 0.549 | 0.0 | .0325 | .007 | 3 | 3 | PAM_V1_LEARNING_GUIDE.pdf |
| q035 | quantum computing applications in medicine | A | 0.539 | 0.0 | .0293 | .050 | 4 | 2 | neural network chapter |
| q036 | What Docker configuration does PAM use? | F | 0.555 | 0.0 | .0318 | −.043 | 2 | 3 | PAM_V1_LEARNING_GUIDE.pdf |
| q041 | KB contain information about mobile apps? | F | 0.559 | 0.0 | .0320 | .026 | 3 | 3 | PAM_V1_LEARNING_GUIDE.pdf |
| q045 | What topics are NOT covered in the KB? | F | 0.506 | 0.0 | .0320 | −.011 | 1 | 5 | PAM_V1_LEARNING_GUIDE.pdf |
| q114 | current price of Bitcoin? | A | 0.469 | 2.84 | .0320 | .037 | 1 | 5 | PCB Board Design.md |
| q115 | Who won the 2026 FIFA World Cup? | E | 0.485 | 0.0 | .0308 | −.004 | 4 | 1 | AWS Foundations.pdf |
| q118 | Utthunga's annual revenue? | B | 0.606 | 6.08 | .0320 | −.007 | 1 | 5 | Our Organization.md |
| q119 | programming languages OpenHands supports? | B | 0.697 | 3.53 | .0323 | .143 | 4 | 2 | OpenHands arXiv.md |
| q120 | layers in the NN video actually have? | B | 0.714 | 0.0 | .0311 | .064 | 1 | 5 | neural network chapter |
| q121 | exact trace width in mm (PCB)? | B | 0.710 | 5.27 | .0328 | .001 | 1 | 5 | PCB Board Design.md |
| q122 | name of the sigmamusicart song? | C | 0.511 | 4.09 | .0325 | .035 | 5 | 1 | OpenHands arXiv.md |
| q123 | exact date Jharkhand protest started? | B | 0.701 | 0.0 | .0325 | .047 | 1 | 5 | Jharkhand protest.md |
| q124 | stock price of OpenAI? | A | 0.487 | 3.35 | .0323 | .052 | 3 | 3 | GPT-5.6.md |
| q125 | IP2312 chip operating voltage range? | B | 0.652 | 0.0 | .0323 | −.046 | 1 | 5 | PCB Board Design.md |
| q126 | TiHAN vehicle communication protocols? | B | 0.699 | 2.46 | .0328 | .189 | 4 | 1 | WhatsApp Image.jpeg |
| q127 | Utthunga ML framework for projects? | B | 0.685 | 10.96 | .0311 | .065 | 2 | 4 | Our Organization.md |
| q128 | How many documents in the KB? | F | 0.598 | 0.0 | .0323 | .044 | 2 | 4 | PAM_V1_LEARNING_GUIDE.pdf |
| q129 | version of the KB currently loaded? | F | 0.558 | 0.0 | .0320 | .014 | 2 | 4 | PAM_V1_LEARNING_GUIDE.pdf |
| q130 | When was the KB last updated? | F | 0.553 | 0.0 | .0328 | .024 | 1 | 5 | PAM_V1_LEARNING_GUIDE.pdf |
| q131 | DB for storing embeddings? | F | 0.589 | 0.0 | .0323 | .041 | 1 | 5 | PAM_V1_LEARNING_GUIDE.pdf |
| q132 | max file size PAM can process? | F | 0.637 | 0.0 | .0323 | .041 | 1 | 5 | PAM_V1_LEARNING_GUIDE.pdf |
| q133 | How does PAM handle multiple languages? | F | 0.546 | 0.0 | .0315 | −.040 | 1 | 5 | PAM_V1_LEARNING_GUIDE.pdf |
| q134 | accuracy rate of OpenHands codegen? | B | 0.679 | 4.61 | .0325 | .075 | 2 | 1 | OpenHands arXiv.md |
| q135 | best practices for REST API design? | A | 0.527 | 4.61 | .0305 | .022 | 4 | 1 | GPT-5.6.md |
| q137 | difference between SQL and NoSQL? | A | 0.455 | 0.0 | .0267 | −.003 | 3 | 3 | PAM_V1_LEARNING_GUIDE.pdf |
| q157 | cost of a JLCPCB fabrication order? | B | 0.604 | 0.0 | .0318 | −.021 | 1 | 5 | PCB Board Design.md |
| q158 | specific webcam model TiHAN uses? | B | 0.691 | 4.90 | .0328 | .178 | 5 | 1 | WhatsApp Image.jpeg |
| q159 | GitHub stars of OpenHands repo? | B | 0.616 | 4.87 | .0323 | .056 | 3 | 1 | OpenHands arXiv.md |
| q160 | refresh rate of GPT-5.6 demo display? | B | 0.625 | 9.36 | .0328 | .002 | 1 | 5 | GPT-5.6.md |
| q196 | RAM required for PAM vector store? | F | 0.623 | 0.0 | .0323 | .076 | 1 | 5 | PAM_V1_LEARNING_GUIDE.pdf |
| q197 | Node.js version for React examples? | B | 0.610 | 0.0 | .0320 | .005 | 1 | 5 | Web Module 5 notes.pdf |
| q198 | total cost of the GPU test platform? | B | 0.599 | 0.0 | .0323 | −.038 | 1 | 5 | GPU_Accelerated...Project_Report.pdf |
| q199 | full name of institution "SNPSU"? | C | 0.552 | 0.0 | .0323 | .041 | 3 | 3 | PAM_V1_LEARNING_GUIDE.pdf |
| q200 | orchestration platform Docker CheatSheet? | B | 0.587 | 0.0 | .0325 | −.012 | 2 | 2 | Docker CheatSheet.pdf |

(diff = source diversity, conc = # of top-5 hits from top-1 source. The 6 correctly-rejected negatives — q032, q116, q117, q136, q138, q139 — all sit at cos < 0.45 and are all Category A.)

### 4.2 Cosine-band structure (the decisive structural fact)

| Band | TP | FP | FP share | Note |
|---|---|---|---|---|
| < 0.45 | 0 | 0 | — | gate already rejects at 0.45 |
| [0.45, 0.51) | 8 | 5 | 14% | cheap band — a threshold lift kills these |
| [0.51, 0.62) | 34 | 19 | 53% | borderline band — 24 FPs live here |
| ≥ 0.62 | 115 | **12** | 33% | **hard core** — cos-indistinguishable from TPs |

33% of FPs (12) score ≥ 0.62 — **above the 25th percentile of TRUE positives (0.610)**. No score-only rule can remove them without butchering recall.

### 4.3 Structural cross-tabs

| Facet | FP count | Comment |
|---|---|---|
| PAM_V1_LEARNING_GUIDE.pdf top-1 | **14 / 36** | single biggest FP generator |
| bm25 = 0.0 on top-1 | 23 / 36 | most FPs are pure semantic matches |
| bm25 > 0 on top-1 | 13 / 36 | lexical hits don't imply answer presence |
| lexical overlap < 0.5 | 22 / 36 | unusable: TP median overlap is only 0.56 |

## 5. TP / FP feature distributions

Measured over 157 accepted positives vs 36 FPs. (Both sets fully accepted at 0.45.)

| Feature | TP p25 / median / p90 | FP p25 / median / p90 | Separable? |
|---|---|---|---|
| top cosine | 0.610 / 0.676 / 0.761 | 0.549 / 0.598 / 0.699 | Partial — heavy overlap, 12 FPs ≥ 0.62 |
| top bm25 | 0.0 / 0.0 / 6.80 | 0.0 / 0.0 / 5.27 | **No** (idle medians equal) |
| top rrf | .0320 / .0325 / .0328 | .0308 / .0323 / .0328 | **No** — degenerate, RRF saturates |
| cos gap (top1−top2) | 0.010 / 0.033 / 0.102 | −0.004 / 0.026 / 0.076 | Weak; FP max 0.189, TP max 0.382 |
| cos std (top-5) | 0.024 / 0.042 / 0.092 | 0.024 / 0.035 / 0.080 | **No** |
| source diversity | 1 / 2 / 4 | 1 / 2 / 4 | **No** (identical) |
| top-source concentration | 2 / 4 / 5 | 2 / 4 / 5 | **No** (identical) |
| lexical overlap top-1 | 0.43 / 0.56 / 0.82 | 0.38 / 0.55 / 0.71 | **No** |
| query length | 8 / 10 / 15 | 7 / 9 / 15 | **No** (insignificant) |
| chunk length top-1 | 693 / 1268 / 1980 | 1062 / 1585 / 1980 | **No** (FP slightly longer — wrong direction) |
| retrieved count | 5 / 5 / 5 | 5 / 5 / 5 | Constant — no signal |
| bm25 presence (any hit) | 0 / 1 / 1 | 0 / 1 / 1 | **No** (both half/half) |

**Verdict:** Of 13 candidate signals, only **cosine** carries any measurable separation, and it is insufficient alone (band table in §4.2). BM25, RRF, gap, spread, diversity, concentration, lexical overlap, lengths, and counts are all **REJECTED** as standalone or combinational separators — their TP and FP distributions overlap to the point of near-identity. This rejects hypotheses (2), (3), (5)–(8) of the prompt's candidate list.

## 6. Negative-query taxonomy (all 42, evidence from actual top chunks)

| Cat | Name | Count | Accepted (FP) | Rejected | Top-1 evidence pattern |
|---|---|---|---|---|---|
| A | completely out of corpus scope | 11 | 5 | 6 | q032, q035, q114, q116, q117, q124, q135, q136, q137, q138, q139 |
| B | correct topic, requested fact absent | 16 | 16 | 0 | q118–q121, q123, q125–q127, q134, q157–q160, q197, q198, q200 |
| C | related topic, wrong document pulled | 2 | 2 | 0 | q122, q199 |
| D | hyper-specific info absent (non-attribute) | 0 | 0 | 0 | (folded into B/C on this corpus) |
| E | temporal / current info absent | 2 | 2 | 0 | q034, q115 |
| F | metadata / system question about PAM/KB | 11 | 11 | 0 | q033, q036, q041, q045, q128–q133, q196 |
| G | ambiguous query | 0 | 0 | 0 | none detected |
| H | other | 0 | 0 | 0 | none |

Notes:
- **All 6 correctly-rejected negatives are Category A** (fully off-topic, unrelated docs, cos < 0.45). The cosine gate only ever catches "nothing to do with anything" — it cannot catch topic-adjacency.
- **Every B/F/E/C negative in the corpus gets accepted** — every negative that *mentions the right subject* clears the gate regardless of cos. B + F alone = 27 of 36 FPs (75%).
- Category B is the 3G-B "topic adjacent, fact missing" class; F is the "asks about the tool that the tool's own guide describes" class — both require **content-level verification** (does the retrieved chunk actually contain the requested fact?), which no retrieval score can express.

**Measurable retrieval signature per category:**
| Category | Retrieval signature | Exists? |
|---|---|---|
| A (low) | cos < 0.45 | Measured, already caught |
| A (mid) | cos 0.45–0.55 | Measured — catchable by threshold lift 0.51–0.53 |
| B, F, C, E | none — cos ranges over the full accepted band, no score feature differs from TP | **None measurable** |

## 7. New-document interference analysis

Focused on the PAM guide and GPU report (validated legitimate in Phase 5C — retained).

### 7.1 PAM_V1_LEARNING_GUIDE.pdf

| Role | Count |
|---|---|
| top-1 for a true positive (rank 1) | 11 |
| top-1 for a **false positive** | **14** (39% of all FPs) |
| top-1 for a positive whose expected source is different (demoted to rank 2–5) | **10** |
| Total queries it tops | 35 / 199 (17.6%) |

The 10 demotions are exactly the known hard regressions: q028 (rank 5), q038, q039 (rank 5), q083, q102, q104, q107, q108, q151, q154 (most rank 2). The same doc both generates the largest FP block **and** suppresses 10 true-positive ranks — it is a genuine interference hub, not a measurement artifact.

Why: the guide is a long, self-referential summary of PAM that itself cites PAM's views on neural networks, LeetCode, PCB, GPT-5.6, etc. Any query about *the tool*, *the knowledge base*, *files*, *documents*, or *the neural-net/leetcode topics* embeds strongly toward it. Phase 5C's verdict stands: the doc is legitimate (11 real answers) — **delete/exclude is REJECTED**.

### 7.2 GPU_Accelerated...Project_Report.pdf

| Role | Count |
|---|---|
| top-1 for true positive | 4 |
| top-1 for FP | 1 |
| top-1 demoting a different-expected positive | 3 (q038, q104, q108 — all rank 2) |

Minor relative to PAM but the same signature: a long technical report about a capable AI/GPU platform that out-ranks answers for questions about *platforms/tech stacks*. Its FP contribution is small; its regression contribution is 3 of the 18.

### 7.3 Effect on FPR

| Setting | FPR |
|---|---|
| Whole corpus (current) | 0.857 |
| FPs attributable to PAM guide (14) | +0.333 of that |
| FPs attributable to GPU report (1) | +0.024 |

Even if both docs were removed, FPR would be ≈ 0.50 — the other 21 FPs are spread across 12 legacy + new docs. **Doc removal cannot fix FPR**; it would also destroy 15 real positives. REJECTED.

## 8. Cosine threshold sweep (0.45 → 0.65, offline)

| t | Hit@1 | Hit@5 | MRR | FPR | FNR | abst | pos_acc | neg_rej |
|---|---|---|---|---|---|---|---|---|
| 0.45 | 0.841 | 0.924 | 0.877 | 0.857 | 0.000 | 0.030 | 1.000 | 0.143 |
| 0.47 | 0.834 | 0.917 | 0.871 | 0.809 | 0.013 | 0.050 | 0.987 | 0.191 |
| 0.49 | 0.828 | 0.911 | 0.865 | 0.762 | 0.032 | 0.075 | 0.968 | 0.238 |
| 0.51 | 0.815 | 0.892 | 0.850 | 0.738 | 0.051 | 0.096 | 0.949 | 0.262 |
| 0.53 | 0.809 | 0.885 | 0.843 | 0.691 | 0.057 | 0.111 | 0.943 | 0.309 |
| 0.55 | 0.809 | 0.879 | 0.840 | 0.619 | 0.096 | 0.156 | 0.904 | 0.381 |
| 0.57 | 0.790 | 0.847 | 0.819 | 0.500 | 0.134 | 0.211 | 0.866 | 0.500 |
| 0.59 | 0.764 | 0.802 | 0.783 | 0.429 | 0.191 | 0.271 | 0.809 | 0.571 |
| 0.61 | 0.720 | 0.745 | 0.733 | 0.309 | 0.248 | 0.342 | 0.752 | 0.691 |
| 0.63 | 0.669 | 0.688 | 0.678 | 0.238 | 0.306 | 0.402 | 0.694 | 0.762 |
| 0.65 | 0.612 | 0.631 | 0.621 | 0.214 | 0.369 | 0.457 | 0.631 | 0.786 |

**Verdict — REJECTED:** No single cosine threshold satisfies the acceptance criteria.
- The only t that keeps FNR ≤ 0.033 is t = 0.49 (FNR 0.032), and there it fixes **nothing**: FPR 0.762 (not materially < 0.811), Hit@5 0.911 (fail), MRR 0.865 (fail).
- Every FNR-compliant move leaves the B/F/E/C FPs in place (they sit at 0.51–0.71).
- The floor of threshold-only reduction is FPR ≈ **0.21 at FNR ≈ 0.37** (t=0.65, still 9 FPs > 0.65), because 12 FPs are score-identical to ordinary true positives.

Combination tests (cos + BM25 presence; cos + concentration ≥ 2 OR BM25): **both REJECTED**. Requiring any BM25 hit kills 71 of 157 positives (FNR 0.45); the "evidence-ish" concentration rule changes FPR not at all (FPs also cluster on one source).

## 9. Answerability retrospective (Phase 3G-B against today's corpus)

3G-B result (then: 160-query dataset, 101-chunk corpo): FPR **0.243**, FNR **0.098**, ~3 s per gated query. It rejected 21 FPs and introduced 11 false negatives (4 legitimately-unanswerable + 7 over-rejections). Prompt root cause: "be conservative: prefer INSUFFICIENT_EVIDENCE" → the gate returned INSUFFICIENT_EVIDENCE for **all 32** queries it evaluated.

Mapping to the frozen 199-query corpus:

**Which FPs would answerability attack (evidence from §4, §6):**
Category B + F + C + E = 31 of 36 FPs. In every one, the top chunk is about the right topic but does **not** contain the requested fact (e.g., q119 OpenHands abstract without a language list; q128 PAM page-limit sampler without a document count; q131 vector_store.json description with no explicit "database" statement). These are precisely the cases the verifier was built for — the mechanism is sound and the FPR headroom is on the order of **−0.85 → ≤ 0.15** if the verifier reaches ~90% precision on them.

**Which TPs were wrongly rejected in 3G-B, and would the pattern recur?**
The 7 over-rejections: q015 (PCB EDA tool — evidence present, gate mistrusted), q113 (LeetCode-vs-DAA comparison), q151 (LeetCode retry pattern), q092-94 (removed from dataset). On today's corpus the recurring risky profiles are:
- **cross-document comparison** queries (q113-class): explicit-answer matching across 2 sources is the hardest verdict,
- **specific detail with soft wording** ("recommended", "pattern", "exact"), where evidence is present but phrased differently than the question,
- scanned-PDF/OCR/image/docs (q121-class PCB, q126-class TiHAN image): text is noisy, so "explicit evidence" looks thin even when the fact is there.

**Could a less conservative criterion fix the trade-off?** The 3G-B failure was prompt-calibration, not architecture. A relaxed, "grounded topic + one corroborating sentence" criterion could plausibly keep the B/C/F rejections while passing the evidence-bearing TPs. **This is exactly what must be measured** — the FNR-guardrail (5 relaxations max) makes it an empirical question, not a spec assumption.

**Latency:** 3 s/query with qwen3:8b on CPU. Fundamentally unsuitable **if applied to all 199 queries**. Boundable only by scoping (§14). Not a blocker for a prototype; is a blocker for blind production enablement.

## 10. Metadata / evidence-options analysis (existing fields only)

Available per hit today (no new metadata allowed):

| Field | Present | Value for a light relevance/evidence rule |
|---|---|---|
| source filename / path | ✓ | Duplicates cosine source identity; no FP-discriminative use found |
| source_type | ✓ (pdf/markdown/scanned_pdf/image/audio) | FPs are split across all types (PDF 15, md 14, image 2…); no type is a separator. **No rule** |
| heading / heading_path / parent_heading | ✓ (markdown/pdf) | FP chunks carry no synthetic heading signal (ranges overlap TPs). **No rule** |
| page number | ✗ | Not stored |
| document title | ✗ | Not stored as a field (filename only) |
| chunk_index / start_char / end_char | ✓ | Position carries no relevance signal; only useful for parent-window expansion (NOT a divisive signal) |
| structure_type (table/blockquote/definition_list) | ✓ (partial) | Too sparse; tables would need a row-answer check. Marginal |
| ingestion provenance | ✗ | Not stored per chunk beyond source_type |

**Verdict — INCONCLUSIVE-to-REJECTED as a primary lever:** existing metadata supports *context assembly* (heading-aware citation rendering, table-structure hints) but provides **no measured discriminating signal** for FP removal. A metadata-only filter would need to encode per-source rules ("this doc type can't answer PAM questions") — which contradicts Phase 5C's legitimacy finding. Metadata can only *enhance* an evidence step, not replace it.

## 11. Candidate comparison

| Option | Expected FPR effect | Expected FNR risk | Latency | Impl. complexity | Corpus dependence | Explainability | Rollback |
|---|---|---|---|---|---|---|---|
| A. Higher cosine threshold | 0.857→0.76 best case at FNR-safe t | breaks at t≥0.51 (§8) | none | none | blind to 33% of FPs (≥0.62) | perfect | instant |
| B. Lightweight deterministic evidence score (heuristic term/co-occurrence) | none measured — all score signals overlap (§5) | replaces heuristic failure with new heuristic | none | low | per-corpus hand-tuning | good | instant |
| C. Metadata-aware filtering | none measured (§10) | low if non-removal | none | low | high — per-doc rules | good | instant |
| D. Improved answerability verifier (evidence-verify, tuned prompt, scoped) | **−0.85→≤0.15 plausible, based on 3G-B 0.243 and B/F/C coverage (31/36)** | 3G-B hit 0.098 → must be re-measured with relaxed criterion; guardrail is tight (≤5 rejections) | ~0.3–3 s **only on gated band** | medium (re-tune threshold, band, prompt; no new infra) | moderate — verifier is content-native, generalizes | best — returns the verdict text | one flag |
| E. Cross-encoder soft ranking | **weak/none for FPR** — it re-ranks relevance; the 12 ≥0.62 FPs are *relevant* topics and would remain in top-5 (FPR counts acceptance, not rank) | low | high (~per-query model call) | high | high (model/data) | poor (opaque score) | one flag |
| F. Query classification (e.g., detect "meta/system/out-of-scope" questions) | partial — kills F + some C (13/36) but not B (16/36) | low | low | medium (classifier accuracy is the wildcard) | medium | good | instant |
| G. No change / accept behavior | none | none | none | none | none | — | — |

Evidence basis: A §8, B §5/§6, C §10, D §9, E §5 (12 FPs are topic-relevant → presumed re-ranking keeps them; no measured counter-evidence), F §6 (16 B-FPs wouldn't be caught by scope-detection).

## 12. Acceptance-criteria analysis

| Criterion | Required | Current | Best measured compliant state |
|---|---|---|---|
| FNR ≤ 0.033 | ≤ 5 rejections | 0.000 ✅ | only t ≤ 0.49 (rejects 5) — which fails everything else |
| Hit@5 ≥ 0.93 | ≥ 147/157 | 0.924 ❌ | 0.924 (can't raise without better ranking) |
| MRR ≥ 0.88 | — | 0.877 ❌ | 0.877 |
| FPR materially < 0.811 | well below | 0.857 ❌ | 0.49 threshold → 0.762 (marginal) |
| p95 < 500 ms | — | 47 ms ✅ | must be preserved by any gate scoping |

Also note: baseline Hit@5 0.924 / MRR 0.877 miss their guardrails *regardless of abstention* — those are ranking holes (12 retrieval misses + 13 wrong-rank, unresolved since 5C). Fixing FPR alone will not green these.

## 13. Risks

1. **FNR overshoot (highest risk).** The verifier traded FPR 0.857→0.243 at the cost of FNR 0.098. Guardrail allows exactly 5 rejected positives. A less conservative verifier reduces but doesn't eliminate this risk; it must be measured on the frozen 199, not assumed.
2. **Latency regression.** 3s/query on every query breaks the 500ms p95. Scoping to the borderline band (~24/36 FPs live in [0.51,0.62)) caps exposure; auto-accept ≥0.62 would leave 33% of FPs untouched, so banding detail determines the trade.
3. **PR review of the frozen dataset.** Hit@5/MRR shortfalls are ranking problems; a pool that chases only FPR may "pass" the abstention part while the headline ranking guardrails stay red.
4. **No score-only shortcut.** Every non-content signal measured overlaps (this report) — any heuristic "evidence score" (Option B) is a re-invention of the thing that doesn't separate.
5. **Prompt brittleness.** qwen3:8b over-rejects on a strict prompt. Any verifier must default to accept on parse/error (fail-open) to keep FNR safe.

## 14. ONE recommended direction

**Validated/rejected summary first:**

- VALIDATED: cosine is the only score signal with separation, and it tops out at FPR ≥ 0.21 before FNR explodes; 12 FPs (>0.62) are score-indistinguishable from TPs. Category B/F/C/E negatives (33/36 FPs) are *content-sufficiency* misses, not relevance-misses — no retrieval score can see them. PAM guide is the FP hub (14) and a positives-demoter (10), legitimately, and must be kept.
- REJECTED: threshold sweep (all t), BM25 presence, RRF/gap/spread/diversity/concentration/lexical/length features, metadata-only filtering, cross-encoder soft-ranking (no FPR pathway), doc removal.
- INCONCLUSIVE: answerability's FNR+latency trade on the *frozen 199-query corpus* (3G-B measured on a different, smaller corpus).

**Recommendation — Option D, as a scoped, re-calibrated, evaluation-only prototype for Phase 5F:**

> **Phase 5F — "Banded answerability verifier" experiment.** Implement the *existing* AnswerabilityGate glue (no new production paths) but evaluate a re-tuned, less-conservative evidence criterion and a banded invocation rule against the frozen 199-query dataset:
> - Gate band: only queries whose top-1 cosine ∈ [0.45, 0.62) get an LLM verdict; auto-accept ≥ 0.62 (protects throughput), auto-reject < 0.45 (already the gate). *Measured effect:* 24 of 36 FPs live in the band vs 42 of 157 TPs — best FP/TP exposure ratio.
> - Re-calibration : 2–3 relaxed prompt variants ("grounded topic + corroborating sentence = SUPPORTED", firm "no invented facts"), measured for FNR ≤ 0.033 with **fail-open default (parse error/timeout → accept)**.
> - Latency instrumentation: per-band p50/p95; if the band is still too slow, drop to a tiny model (phi3-mini/gemma2:2b) measured on a 50-query bisect before the full 199.
> - Hard stop: any variant exceeding FNR 0.033 is rejected and reported; the deliverable is a measured trade table (criterion × band × model), NOT a production change.

**Rationale (evidence-anchored, not intuition):** it is the only option with a *measured* precedent for −70% FPR, it attacks exactly the 33/36 FPs that nothing else can touch, it is the only candidate whose failure mode (FNR/latency) is tunable rather than fundamental (§7 of the 3G-B report already localized the root cause to prompt conservatism), and its FNR hole is precisely quantifiable against the frozen suite.

**Fallback (explicitly sequenced, not simultaneous):** if banded-verifier variants all blow past FNR 0.033 at viable latency, then Option E (cross-encoder soft ranking) becomes the next discovery target — but with the caveat that E must be measured for *FPR* reduction, not just ranking gain, and is expected to help Hit@5/MRR before it helps FPR.

## 15. Proposed next experiment (Phase 5F sketch)

| Step | Action |
|---|---|
| 1 | Instrument: reuse frozen `phase_5d_frozen_baseline.json` + this report's capture for labels (zero re-runs needed for metrics) |
| 2 | Build the experiment in a sandbox module under `eval/` (flag-gated, default off) |
| 3 | Prompt variants: (a) current strict, (b) grounded-topic+corroboration, (c) cite-the-sentence-or-reject |
| 4 | Banded invocation [0.45, 0.62) vs full-scan (both rendered) |
| 5 | Metrics per variant: FPR, FNR, Hit@5, MRR, abstention, band p95; FP/TP verdict detail |
| 6 | Acceptance: exists a (criterion, band, model) with FNR ≤ 0.033 AND FPR < 0.5 AND p95 < 500 ms, with all other guardrails not regressed |
| 7 | Produce `32_PHASE_5F_...md` + artifact JSON; no production wiring without fresh approval |

## 16. Rollback strategy

- Any Phase 5F prototype ships behind its own `answerability.*` config block, **default disabled** (the 3G-B pattern already exists; `answering.enabled=false` unchanged today).
- No retrieval/config/corpus/dataset mutation → rollback = flag off (same story as 3G-B §7: "answerability.enabled=false default" verified, zero production risk).
- Dataset is frozen at 199 queries; any future leg can be re-verified against `phase_5d_frozen_baseline.json`.
- Threshold experiments leave the runtime `min_cosine=0.45` untouched (sweeps were in-memory on captured cosines).

## 17. Final decision

**STOPPING now (per Phase 5E STOP condition).**

One direction selected for Phase 5F approval: **Option D — banded, re-calibrated answerability verifier experiment, evaluation-only.** No production code, config, dataset, corpus, or embedding change was made in this phase; no commits or pushes.

| Direction | Status |
|---|---|
| Cosine threshold lift (any t) — standalone | **REJECTED** (no t meets all criteria; floor FPR 0.21 at FNR 0.37) |
| BM25 / RRF / gap / spread / diversity / concentration / lexical / length features | **REJECTED** (distributions overlap TPs/FPs) |
| Doc removal / exclusion (PAM, GPU) | **REJECTED** (would lose 15 legit positives; FPR would still be ≈0.5) |
| Metadata-only filtering | **REJECTED** (no discriminating fields exist) |
| Cross-encoder soft ranking | **INCONCLUSIVE/PROPOSED fallback** (no measured FPR pathway; revisit if verifier fails) |
| Query classification (scope/meta detection) | **REJECTED as the one direction** (goes 13/36 at best; B-class untouched) |
| No-change / accept | **REJECTED** (FPR 0.857 fails the criterion outright) |
| **Banded answerability verifier (Option D)** | **VALIDATED + PROPOSED for Phase 5F prototype** |