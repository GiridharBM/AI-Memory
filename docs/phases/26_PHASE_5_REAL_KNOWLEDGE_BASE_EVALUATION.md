# Phase 5 — Real Knowledge Base Evaluation

**Date:** 2026-08-27
**Status:** COMPLETE
**Frozen HEAD:** `9f282b41b6c558b0dbea857c95e24beb3ff63f9a`
**Scope:** Evaluation ONLY. No production code/config changed. No new dataset created. No reranker/HyDE/answerability enabled. No tuning.

---

## 1. Executive Summary

The existing frozen 160-query evaluation dataset (`eval/dataset.json` v2.0) was classified, validated, and run against the current 24-source / 195-chunk real corpus with the frozen production configuration (`nomic-embed-text`, `min_cosine=0.45`, reranker/hyde/answerability disabled).

**Result: retrieval quality regressed on the original 10 sources after the 14 new documents were ingested.**

| Metric | Historical (12 doc / 101 chunks, 2026-08-21) | Current (24 doc / 195 chunks, 2026-08-27) | Δ |
|--------|:---:|:---:|:---:|
| Hit@1 | 0.902 | **0.797** | −0.105 |
| Hit@3 | 0.959 | **0.870** | −0.089 |
| Hit@5 | 0.967 | **0.886** | −0.081 |
| MRR | 0.930 | **0.835** | −0.095 |
| FPR (neg accept) | 0.811 | **0.838** | +0.027 |
| FNR (pos abstain) | 0.008 | **0.000** | −0.008 |
| Abstention rate | 0.050 | **0.037** | −0.013 |
| Avg query time | 21.7 ms | **32.5 ms** | +10.8 ms |

Of the 21 positive-query regressions, **3 are expected** (q092–q094 reference the removed `pam_smoke_test` artifact) and **18 are genuine corpus-scale interference**. Excluding the pam_smoke_test queries, Hit@1 is still down from 0.900 → 0.817 (−0.083), Hit@5 0.967 → 0.908 (−0.059), MRR 0.960 → 0.943 (−0.017).

**Primary interference source:** `PAM_V1_LEARNING_GUIDE.pdf` (36 chunks) displaces the correct source's top-1 for 11 of the 18 genuine regressions; `GPU_Accelerated_Generative_AI_Testing_Platform_Project_Report.pdf` accounts for 3 more.

**Dataset coverage limitation (explicit):** none of the 14 new documents are represented in the eval dataset, so this evaluation measures **retrieval stability of the original 10 sources under corpus growth** — it does NOT measure how well the new documents are retrieved.

---

## 2. Dataset Classification — Step 2

`eval/dataset.json` v2.0: **160 queries** (metadata claims 124 positive / 36 negative; actual = **123 positive / 37 negative**).

| Class | Count | Query IDs |
|-------|:---:|---|
| **A — answerable against current corpus** | 157 | All except q092–q094 |
| **B — NOT answerable (source removed from corpus)** | 3 | q092, q093, q094 (expect `pam_smoke_test`, removed Phase 4 cleanup) |
| **C — ambiguous** | 0 | — |

Source-key distribution of positive queries:

| Key | Queries | In corpus? |
|-----|:---:|:---:|
| pcb_design | 27 | ✓ |
| daa_assignment | 24 | ✓ |
| utthunga | 22 | ✓ |
| neural_networks | 20 | ✓ |
| openhands | 19 | ✓ |
| leetcode | 17 | ✓ |
| gpt56_demo | 14 | ✓ |
| jharkhand_protest | 8 | ✓ |
| sigmamusicart | 7 | ✓ |
| tihan | 6 | ✓ |
| pam_smoke_test | 3 | ✗ (removed artifact) |
| b_md | 0 (referenced by metadata only) | ✗ (removed artifact) |

Categories: factoid 87, negative 37, comparison 16, cross_document 11, tricky 9.
Difficulty: easy 56, medium 64, hard 40.
Unreliable ground truth: 3 (q033, q036, q050 — all flagged with notes in the dataset).

## 3. Dataset Suitability — Step 3

**The dataset is suitable for a partial regression evaluation, not a full real-corpus evaluation.**

- 157/160 queries (98.1%) are valid against the current corpus; only q092–q094 are unanswerable, all due to the intentionally-removed `pam_smoke_test.txt`.
- **Coverage gap:** queries reference only the 10 original sources (+ removed `pam_smoke_test`). **0 of 14 new documents** (AWS ×3, Docker ×2, FLAT, Graph Theory, PAM guide, Web notes, Data Analysis, python data science, Auto_Testing, GPU report, DevOps) have any evaluation queries.
- Per prior instruction: **no new dataset was created** and `eval/dataset.json` was **not modified**.
- Verdict: run the existing evaluation to (a) confirm the historical baseline still holds after corpus growth, and (b) detect interference. Results above show it does not hold.

## 4. Baseline Configuration Verification (Unmodified) — Step 4

| Parameter | Value | Source |
|-----------|-------|--------|
| Embedding model | `nomic-embed-text` (768-dim) | `config/default.yaml` → `models.embeddings` |
| min_cosine | 0.45 | eval gate (`AbstentionGate`), matches frozen production threshold |
| reranker.enabled | false | `config/default.yaml` line 178 |
| hyde.enabled | false | line 186 |
| answerability.enabled | false | line 191 |
| top_k | 5 (matches historical baseline runs) | CLI arg |
| Vector store | 195 chunks, 24 sources, all 768-dim | `data/manifests/vector_store.json` |
| Search path | `SearchService.create_default(settings)` (HybridSearch RRF + BM25) — untouched | `app/infrastructure/search.py` |

## 5. Evaluation Run — Step 5

Command: `python eval/run_eval.py --top-k 5 --min-cosine 0.45` (Ollama up, `nomic-embed-text` OK, 768-dim). Full per-query output saved to `eval/results/abstention_gate.json` (historical copies preserved in `eval/results_backup_20260827/`).

| Metric | Value |
|--------|:---:|
| Hit@1 / @3 / @5 / @10 | 0.797 / 0.870 / 0.886 / 0.886 |
| MRR | 0.835 |
| Precision@1 / @3 / @5 | 0.797 / 0.295 / 0.187 |
| Recall@1 / @3 / @5 | 0.748 / 0.795 / 0.818 |
| FPR | 0.838 (31/37 negatives accepted) |
| FNR | 0.000 (0/123 positives abstained) |
| Abstention rate | 0.037 (6/160) |
| Pos acceptance | 1.000 |
| Avg query time | 32.5 ms |

Per-category hit@5: factoid 0.920, comparison 0.875, tricky 0.889, cross_document 0.636, negative 0.000 (correct behavior).

## 6. Per-Query Analysis — Step 6

Transitions vs historical (`experiment_1_bm25_fix.json`):

| Transition | Count |
|-----------|:---:|
| TOP1 → TOP1 (stable) | 96 |
| rank dropped (still hit) | 11 |
| HIT → MISS | 10 |
| MISS → MISS | 4 |
| rank improved (LOWER → TOP1) | 2 |
| HIT → HIT (other) | 0 |
| MISS → HIT | 0 |

**The 10 HIT→MISS queries:** q031, q040, q078, q092, q093, q094, q098, q106, q109, q111.
**The 3 pam_smoke_test queries (q092–q094) are expected losses** — the source was intentionally removed and these queries are no longer answerable.

**Genuine regressions (18):** q028, q031, q038, q039, q040, q078, q083, q098, q099, q102, q104, q106, q107, q108, q109, q111, q151, q154.

Interference by new document (top-1 displacing the correct source):

| New document | Genuine regressions blocked |
|---|:---:|
| PAM_V1_LEARNING_GUIDE.pdf | 11 |
| GPU_Accelerated_Generative_AI_Testing_Platform_Project_Report.pdf | 3 |
| AWS Foundations Getting Started.pdf | 1 |
| (non-new backgrounds) | 3 |

`PAM_V1_LEARNING_GUIDE.pdf` is the top-1 source for **27 of 160 queries** overall — the strongest corpus-scale signal. It is the largest new document (36 chunks, 58,552 chars) with broad, elastic language that matches general/topic queries (learning, education, documents, knowledge base, tools) and crowds out the original specialized sources.

## 7. New Knowledge Base Coverage in Dataset — Step 7

**None of the 14 new files are referenced by any of the 160 queries.**

| New source | Chunks | Queries in dataset |
|---|:---:|:---:|
| PAM_V1_LEARNING_GUIDE.pdf | 36 | 0 |
| Web Module 5 notes.pdf | 30 | 0 |
| GPU_Accelerated_Generative_AI_Testing_Platform_Project_Report.pdf | 12 | 0 |
| Auto_Testing_Faculty_Explanation.pdf | 7 | 0 |
| Module 5-Graph Theory.pdf | 4 | 0 |
| FLAT MODULE 5 NOTES .pdf | 3 | 0 |
| Docker CheatSheet ApnaCollege.pdf | 2 | 0 |
| Docker_Introduction.pdf | 1 | 0 |
| AWS CloudFormation.pdf | 1 | 0 |
| AWS Foundations Getting Started.pdf | 1 | 0 |
| Data Analysis with Python Coursera.pdf | 1 | 0 |
| Getting Started with DevOps on AWS.pdf | 1 | 0 |
| Introduction to Cloud.pdf | 1 | 0 |
| python for data science.pdf | 1 | 0 |

**Conclusion:** the current dataset cannot answer "does the system retrieve the new knowledge correctly?". That requires new per-source queries (not created per instructions).

## 8. Historical Comparison — Step 8

Comparable runs both used `--top-k 5 --min-cosine 0.45`, identical dataset:

| Metric | exp0/exp1 baseline (101 chunks) | Current (195 chunks) | Δ |
|--------|:---:|:---:|:---:|
| Hit@1 | 0.902 | 0.797 | −0.105 |
| MRR | 0.930 | 0.835 | −0.095 |
| FPR | 0.811 | 0.838 | +0.027 |
| FNR | 0.008 | 0.000 | −0.008 |
| Avg time | 21.7 ms | 32.5 ms | +10.8 ms |

Excluding pam_smoke_test queries (both sides, n=120): Hist Hit@1=0.900, Hit@5=0.967, MRR=0.960 vs Cur Hit@1=0.817, Hit@5=0.908, MRR=0.943.

**Interpretation with caution — confound:** the corpus doubled (101→195 chunks) while the dataset stayed fixed. Covariate shift is expected; the dataset was designed for the 12-doc corpus. The direction (worse) and mechanism (documented interference by 3 specific new docs) are trustworthy; the magnitude is only descriptive of this dataset, not a general claim.

## 9. Corpus-Scale Observation — Step 9

- 195 chunks / 24 distinct sources / all embeddings 768-dim.
- **108 chunks lack metadata** (PDF-sourced; expected), 87 have it.
- Chunk distribution is heavily skewed: top 5 documents = 36+30+25+18+13 = 122 chunks (~63% of store).
- Latency rose ~50% (21.7 → 32.5 ms) with linear-in-store embedding comparisons; acceptable at this scale (~195 × 768 dim).
- The store grew 101 → 195 via 14 new files; original 10 sources retained their chunks and source strings (all dataset `SOURCE_KEY_TO_FILENAME` fragments confirmed present in the store).

## 10. Stale Manifest Status — Step 10

`data/manifests/processed_files.json` has **37 entries**; **13 are stale** (no chunks in the vector store) — identical set identified in Phase 4, still awaiting cleanup approval, **not removed**:

| Stale entry (inbox name) | Generated note |
|---|---|
| Meet _GPT-5.6.md | meet-gpt-5-6.md |
| DevOps Terms A to Z Glossary.md | DevOps_Terms_A_to_Z_Glossary.md |
| test.md | Machine_Learning.md |
| ai-basics.md | Artificial Intelligence Basics.md |
| AI_News_&_Artificial_Intelligence.md | AI_News_and_Artificial_Intelligence.md |
| test-functional.md | Python Decorators.md |
| python.md | Python-Programming.md |
| Chinese open-weight models…Washington… | Chinese Open-Weight Models… |
| 20_AI_Concepts_Explained_in_40_Minutes.md | 20_AI_Concepts… |
| AI_Concepts.md | Artificial Intelligence Concepts.md |
| buildfastwithai.txt | Gemini_3_6_Flash_Review… |
| image.png | Introduction to Machine Learning.md |
| images (1).jpg | How-Artificial-Intelligence-Works.md |

Recorded only; **no modification performed**.

---

## 11. Evaluation Design Recommendations (for the NEXT phase — design only, not executed)

Required future work to measure the real knowledge base properly — none performed in this phase:

1. **Extension dataset (new queries):** ~2 queries × 14 new sources covering factoid/cross-document on the new content (done in a future phase's Step 6 as originally scoped).
2. **Dataset correctness:** fix the metadata positive/negative count (124/36 vs actual 123/37) and remove/replace the 3 pam_smoke_test queries.
3. **Interference mitigation candidates (evaluation only, not enabled):** the PAM guide crowds other sources on general queries — chunk budget reduction for oversized docs, or per-source caps are the obvious levers, but any decision requires the extension dataset first.

---

## 12. Artifacts

| Artifact | Path |
|---|---|
| Current full results (160 queries) | `eval/results/abstention_gate.json` |
| Historical copies (pre-run backup) | `eval/results_backup_20260827/` |
| Dataset backup (unmodified) | `eval/dataset_backup_20260827.json` |
| Frozen dataset | `eval/dataset.json` (v2.0, untouched) |
| Historical baseline (used as comparator) | `eval/results/experiment_1_bm25_fix.json` |
| Phase 4 ingestion report | `25_PHASE_4_REAL_KNOWLEDGE_BASE_INGESTION_RESULTS.md` |

## 13. Constraints Honored

- Production retrieval code, embeddings, chunking, BM25, RRF, cosine threshold: **untouched**.
- Reranker, HyDE, answerability: **not enabled**.
- No parameter tuning, no new dataset, no `eval/dataset.json` modification.
- No stale-manifest deletion, no forbidden artifacts ingested.
- No commits/pushes made.
- STOP after this report; no optimization phase started.