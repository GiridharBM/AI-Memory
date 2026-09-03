# Phase 5A — Real-Corpus Interference Analysis

**Date:** 2026-08-27
**Scope:** Retroactive discovery/analysis (no code changed) of why adding 14 documents to the real knowledge base regressed retrieval metrics — Hit@1 0.902→0.797, MRR 0.930→0.835 — across 160 validation queries.
**Constraints honored:** no production code, embeddings, chunking, retrieval, or thresholds modified; no reranker/HyDE/answerability consumed; no docs deleted or re-ingested; nothing committed or pushed (HEAD unchanged `9f282b41`).

**Legend:** **[O]** = OBSERVED (measured, reproducible), **[I]** = INFERRED (reasoned from observations), **[U]** = UNKNOWN (needs experiment).

---

## 1. Objective

Determine the root cause of the Phase 5 retrieval regression when the corpus grew from 10 sources / 101 chunks to 24 sources / 195 chunks (both PCA-unchanged, byte-identical chunks for the 10 shared sources), and stage which future experiments the evidence actually justifies.

## 2. Current corpus (24 sources / 195 chunks) — [O]

| Source | Chunks | min | median | max | avg |
|---|---|---|---|---|---|
| PAM_V1_LEARNING_GUIDE.pdf | 36 | 265 | 1766 | 2194 | 1626 |
| Web Module 5 notes.pdf | 30 | 36 | 1814 | 2193 | 1622 |
| PCB Board Design…md | 25 | 229 | 782 | 2157 | 835 |
| But what is a neural network…md | 18 | 213 | 1679 | 2168 | 1495 |
| What I Learned From LeetCode.md | 13 | 906 | 1595 | 2159 | 1549 |
| GPU_Accelerated…Project_Report.pdf | 12 | 384 | 1781 | 2136 | 1427 |
| Our Organization.md | 11 | 119 | 693 | 1323 | 670 |
| Meet _GPT-5.6 2.md | 7 | 213 | 590 | 841 | 560 |
| DAA assignment-4.pdf | 7 | 23 | 121 | 1972 | 404 |
| Auto_Testing_Faculty_Explanation.pdf | 7 | 937 | 1673 | 2168 | 1642 |
| OpenHands…pdf | 6 | 42 | 520 | 1965 | 747 |
| Jharkhand…pdf | 5 | 139 | 1813 | 2148 | 1494 |
| Module 5-Graph Theory.pdf | 4 | 71 | 508 | 1993 | 702 |
| FLAT MODULE 5 NOTES.pdf | 3 | 1605 | 1747 | 1986 | 1779 |
| Docker CheatSheet ApnaCollege.pdf | 2 | 1215 | 1567 | 1567 | 1391 |
| 9 single-chunk docs | 1 each | — | — | — | — |

Metadata: only 87/195 chunks carry metadata; the big academic PDFs (PAM guide, Web Module 5, GPU report, Auto_Testing, FLAT, Docker) all carry **empty metadata** — they are indistinguishable to any cross-checks (title, headings, year) at the chunk level.

## 3. Historical corpus (10 sources / 101 chunks) — [O]

Preserved at `data/manifests/backups/20260824_225735/vector_store.json` (101 entries, 12 source names incl. two artifacts `b.md` ×6 and `pam_smoke_test.txt` ×1). **94 of the 101 chunks are common with the current corpus, and those 94 are byte-identical in both text and embeddings (max embedding cosine diff = 0.0)** — verified by re-embedding current text and comparing against the backup store. The 7 non-common chunks are the two removed artifacts.

## 4. The 18 regressions — [O]

Replay (`_phase5a_step1.py`) reproduces historical top-1s exactly, validating the harness. For every regression, expected-source cosine in the new corpus **equals** its old value (identical chunk text) — embeddings did not change. What changed is rank.

| qid | expected src | old rank | new rank | blocker | cos-old | cos-new | bm25-old | bm25-new |
|---|---|---|---|---|---|---|---|---|
| q028 | OpenHands | 1 | 5 | PAM guide | 0.4615 | 0.4615 | — | 9.86 |
| q031 | LeetCode | 2 | 8 | 5×PAM + 1×GPU | — | 0.525 | — | 7.3 |
| q038 | OpenHands | 2 | 3 | GPU report | 0.738 | 0.738 | 7.3 | 7.3 |
| q039 | Neural-new | 1 | 2 | PAM guide | 0.551 | 0.551 | — | 3.1 |
| q040 | DAA | 1 | 2 | AWS | — | 0.501 | — | 11.4 |
| q078 | DAA | 2 | 3 | AWS | — | — | — | — |
| q083 | Neural-new | 1 | 2 | PAM guide | 0.603 | 0.603 | 11.9 | 11.9 |
| q098 | Neural-new | 1 | 3 | PAM guide | — | — | — | — |
| q099 | Jharkhand | 2 | 3 | Jharkhand old chunks (BM25 drift) | — | 0.601 | — | — |
| q102 | Neural-new | 1 | 2 | PAM guide | 0.513 | 0.513 | 7.7 | 7.7 |
| q104 | OpenHands | 1 | 2 | GPU report | 0.665 | 0.665 | 5.4 | 5.4 |
| q106 | OurOrg | 1 | 2 | PAM guide | 0.556 | 0.556 | 4.8 | — |
| q107 | PCB | 1 | 3 | PAM guide | 0.568 | 0.568 | 5.8 | 5.8 |
| q108 | OpenHands | 1 | 2 | GPU report | 0.609 | 0.609 | 8.1 | 8.1 |
| q109 | Neural-new | 1 | 3 | PAM guide | 0.507 | 0.507 | 7.3 | 7.3 |
| q111 | LeetCode | 1 | 2 | PAM guide | 0.462 | 0.462 | 12.0 | — |
| q151 | LeetCode | 1 | 2 | PAM guide | 0.569 | 0.569 | 11.5 | 11.5 |
| q154 | PCB | 1 | 3 | PAM guide | 0.542 | 0.542 | 8.5 | 8.5 |

Classification: **16 of 18** are new-document competition (**A**); **q099** is pure BM25/RRF drift from corpus-stat change with only old chunks above (**B**); **q039** was a chunk-matching artifact — old vs new matched different chunks of the same doc, not a real embedding shift (cosΔ>0.02 senses as artifact) (**C**).

## 5. PAM_V1_LEARNING_GUIDE.pdf analysis — [O]

- 36 chunks, 1626 avg chars, **0/36 carry metadata**, generic-educational lexicon (AI, LLM, RAG, embedding, BM25, RRF, Q&A, engineering guide, learning guide).
- It accounts for **13/18** regressions (q028, q031, q039, q040, q083, q098, q102, q106, q107, q109, q111, q151, q154).
- It is the current top-1 for **27/160** queries overall (17% of all queries).
- Mechanism mix on the 13:
  - **Dense-driven** (PAM cosine ≥ expected cosine): q028, q031, q039, q083, q107, q151, q154 (~7)
  - **BM25-driven** (PAM loses cosine but wins via exact lexical overlap): q102, q106, q109, q111 (~4)
  - Balanced/bit of both: q040, q098 (~2)
  → PAM guide is a **hybrid semantic+lexical attacker**: it genuinely contains the same vocabulary as every other source (it's a technical guide about the very system that ingested all these files), so it has both high embedding overlap and high vocab overlap.

## 6. GPU report analysis — [O]

- 12 chunks, 1427 avg chars, 0/12 metadata.
- **3/18** regressions (q038, q104, q108) + joins q031, q109, q111 as secondary rank-driver.
- Mechanism is **BM25-driven**: in q038/q104 the GPU chunk *loses* the cosine leg (0.682 vs 0.738; 0.582 vs 0.665) but outranks via exact lexical hits (RAG, FastAPI, embedding, Ollama, mutation, open-source) + RRF fusion. q108 wins both legs marginally and is the fusion/balanced case.
- Content is a software-engineering project report full of generic tool names → crowds lexical space of any tool-related query.

## 7. Chunk quality analysis (all 24 sources) — [O]

- Global: 195 chunks, median 1476 chars, avg 1262. Upper tail (2194) is the chunker's character cap; 14 chunks < 400 chars (mostly PDF image-scan spillover / header fragments).
- 3 single-chunk PDFs are trivially small (AWS ×3, 190–218 chars) — ingested but near-useless; they still produced dense top-3 hits on q040/q078 (AWS Foundations started blocking DAA at rank 2 when it should not).
- Chunk counts are highly skewed (PAM 36 → nine doc ×1). Large generic docs dominate rank outcomes.

## 8. Source interference matrix — [O]

| Interfering source | queries hit | pct of 18 |
|---|---|---|
| PAM_V1_LEARNING_GUIDE.pdf | 13 | 72% |
| GPU project report | 6 (3 primary, 3 secondary) | 33% |
| AWS Foundations Getting Started | 2 (q040, q078) | 11% |
| AWS CloudFormation | 2 (q040, q078, joint) | 11% |
| Getting Started with DevOps on AWS | 2 (q040, q078, joint) | 11% |
| Auto_Testing_Faculty_Explanation.pdf | 1 (q109, secondary) | 6% |

No interfering source affects ≥4 of the 18 singlehandedly except PAM guide; interference is **concentrated, not diffuse**.

## 9. Old-vs-new ranking comparison — [O]

- All 94 shared chunks: same text, same embedding, same cosine. Expected-source cosine is **rock-stable** (Δ=0.0000).
- RRF shift therefore comes only from rank changes: RRF `k/(60+rank)` penalizes the expected chunk whenever ≥2 new chunks land above it (RRF drops when any midpoint is overrun; a chunk at rank 1 vs rank 3 loses ~3.3× RRF value). Google-style fusion of a growing corpus thus reorders without any quality degradation of the original chunks — **[O] noise-free, corpus-composition-driven reordering**.
- BM25 scores *did* shift for shared chunks (q099: jharkhand expected 0.601 stayed, but its rank fell because corpus tf/df/avgdl changed; q099 has only old chunks above it) — i.e., BM25 leg is **not order-invariant** to corpus growth ([I] changing df/avgdl reweights all terms).

## 10. New-doc coverage gap — [O]

0 of the 14 new docs have any queries in `eval/dataset.json` (metadata claims 124/36 coverage but actual is 123/37; 3 unreliable retained). All 18 regressions are scored against the ORIGINAL 10 sources — new docs are never tested for hit quality, so we cannot tell if the new top-1s are wrong or merely untracked-right.

## 11. Root-cause determination — [I]

Primary (drives 16/18): **new-document competition (F)**, i.e. legitimate information in the new corpus outranking the expected chunk, amplified by a rank-based fusion leg that penalizes any expected chunk that drops rank. Contributing (drives 16/18 as efficiency): **dataset insufficiency (E)** — the dataset was built against 10 sources and does not constrain the other 14, so it cannot certify the new top-1s; expected-source cosine is unchanged, so this is *not* embedding/chunking/storage decay (D). Secondary ([O] on q099): **BM25 corpus-stat drift (B)** — reranking of already-good chunks via df/avgdl change.

Ranked (+): F (16/18) > E + F combined (17/18) > B (1/18). No evidence for A (decay), C (threshold), or D (embeddings).

## 12. Confidence

- **[O] high:** chunk identity, embedding identity, cosine stability, per-leg mechanism, interference matrix are all measured directly.
- **[I] medium:** the claim that new top-1s are "wrong" is unverifiable without new-doc ground truth (this is the E gap).
- **[U] low:** would new docs be correct top-1s under a properly-scaled dataset? Unknown until Step 10 queries exist and pass; whether the PAM-guide interference is acceptable signal (it is the guide to this very project) is a product judgment.

## 13. Limitations

- The 18 are scored against expected-source hits; the analysis cannot judge the *quality* of new top-1s (no ground truth), so "regression" includes an unknown share of improving retrievals that the frozen dataset cannot see.
- Chunk-identity proof covers shared chunks only; the 7 old artifact chunks (b.md, pam_smoke_test) could not be compared.
- BM25 corpus-stat drift is inferred from the q099 case only, not exhaustively quantified per regression.

## 14. Possible next experiments (justified, no implementation yet)

1. **Expand `eval/dataset.json` with ~35 queries targeting the 14 new docs** (factual, cross-document, comparison, negative, and precise/detail categories; per-source counts as tabled in Step 7) — re-run eval to measure true retrieval quality on the new corpus. *(Highest value; directly converts the UNKNOWN in §12 into OBSERVED.)*
2. **Run eval with top-k 10 (dataset is scored at top-5)** — cheap sensitivity check for fusion overrun.
3. **Record per-leg (cosine-only, bm25-only) metrics** to confirm the split I vs lexical before touching fusion.
4. **Sensitivity run with min_cosine 0.45 unchanged vs 0.50** — only if concern about the AWS single-chunk distractors.

Not justified by current evidence: reranker/hyDE/answerability, chunking change, metadata enrichment, doc removal, threshold changes for the 18.

## 15. Recommended next step

Write the 35 new-doc queries into `eval/dataset.json` (new section, preserving schema + the original 160) and re-run the eval — turning UNKNOWN into OBSERVED before any pipeline change. Awaiting approval.

---

*Truth preamble:* This report only asserts what the frozen replay at QID level shows; per-leg numbers are exact reproductions of `HybridSearch.search` legs with RRF k=60. No production state was modified during this analysis.