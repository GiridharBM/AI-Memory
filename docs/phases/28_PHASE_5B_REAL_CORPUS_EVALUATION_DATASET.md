# Phase 5B — Real Knowledge Base Evaluation Dataset Design

**Status:** PROPOSAL READY FOR APPROVAL — no evaluation run, no corpus change, no commit.
**Date:** 2026-08-27
**Head input:** Phase 5A finding — 18 genuine regressions, 16/18 caused by new-document competition, and 0 of the 14 newly ingested documents had any evaluation queries.

---

## 1. Objective

Design a real-corpus evaluation dataset covering the 14 newly ingested documents, delivered as a **proposal** (`eval/dataset_v3_proposed.json`) so the retrieval system for the first time has ground-truth queries over the content that regressed the metrics in Phase 5A. Nothing here is frozen and nothing runs yet.

## 2. Current corpus state (verified against vector store)

| Item | Value |
|---|---|
| Sources (unique files) | 24 |
| Chunks (total) | 195 |
| Original docs (pre-Phase 5) | 10 (94/101 chunks byte-identical to historical store) |
| New docs (Phase 5 addition) | 14 (101 chunks) |
| Frozen retrieval config | nomic-embed-text, BM25 k1=1.5 / b=0.75, RRF k=60, hybrid pool, min_cosine 0.45, top-k 5 |
| Frozen HEAD | 9f282b41 (do not commit) |

## 3. Gap in the existing dataset (motivation)

`eval/dataset.json` holds 160 queries (q001–q160; 123 positive / 37 negative). Verifying every query's `expected_sources` against the current store showed:

- **Catastrophic coverage gap:** 0 of the 14 new documents appear in any query's expected sources. Metric regressions from Phase 5A were invisible to the eval suite — a correct retrieval change was indistinguishable from interference, and the regression was only caught by manual re-runs.
- 3 orphan queries (q092, q093, q094) reference the removed `pam_smoke_test` doc and can never pass.
- Existing positives target only the 10 legacy docs. The dense, retrievable content (PAM guide — 36 chunks, Web notes — 30, GPU report — 12) had zero coverage.

## 4. New document inventory (all in `data/inbox/`)

| Source (file) | Chunks | Content class |
|---|---|---|
| PAM_V1_LEARNING_GUIDE.pdf | 36 | Dense technical guide (config constants, architecture, RAG/BM25/RRF internals) |
| Web Module 5 notes.pdf | 30 | Course notes (React/VDOM/components/state) |
| GPU_Accelerated_Generative_AI_Testing_Platform_Project_Report.pdf | 12 | Project concept report (workflow, feedback loop, eval strategy) |
| Auto_Testing_Faculty_Explanation.pdf | 7 | RAG pipeline faculty explanation (frozen metrics, abstention) |
| FLAT MODULE 5 NOTES .pdf | 3 | Theory (Turing Machines, transition tables) |
| Docker CheatSheet ApnaCollege.pdf | 2 | Command reference |
| Module 5-Graph Theory.pdf | 4 | Theory (directed graphs, degrees, source/sink) |
| Data Analysis with Python Coursera.pdf | 1 | Certificate |
| python for data science.pdf | 1 | Certificate |
| Introduction to Cloud.pdf | 1 | Certificate |
| Getting Started with DevOps on AWS.pdf | 1 | Certificate |
| AWS CloudFormation.pdf | 1 | Certificate |
| AWS Foundations Getting Started.pdf | 1 | Certificate |
| Docker_Introduction.pdf | 1 | Certificate |
| **Total** | **101** | **4 substantive + 3 theory/reference + 7 certificates** |

## 5. Query generation methodology

Constraints honored:
1. **No model knowledge.** Every query targets a fact that exists verbatim in the source; if the fact could be answered from general knowledge alone it was still anchored to a source-specific value (e.g., k=60, pool_size formula, 7-tuple glyphs).
2. **Verbatim grounding.** Each positive query carries `evidence_fragments` — whitespace-collapsed substrings that must appear in at least one chunk of an expected source. A standalone verifier asserted this against the **current** `vector_store.json` on every query: **0 failures**.
3. **Test retrieval, not generation.** Queries deliberately include exact-token lookups (URL on `cert_python_ds`, `docker ps -a`) and semantically-paraphrased lookups (spaced OCR on the Coursera cert) to exercise both BM25 and vector paths.
4. **Certificates designed as discriminators.** The 4 AWS/CognitiveClass certs share near-identical boilerplate text; queries key on unique dates/courses so a correct match proves source-level discrimination, not just topical overlap.
5. **Multi-chunk questions require synthesis** across separated chunks (PAM 11-stage pipeline, GPU 12-step workflow, state-flow notes) — these fail if retrieval returns only one fragment.
6. **Negatives are near-miss abstention tests** — semantically adjacent to strong-hit docs but genuinely absent from the corpus (RAM usage, Node version, platform cost, SNPSU expansion, orchestration platform). They test the abstention gate under the exact conditions Phase 5A showed fail (high-cosine distractors).

## 6. Proposed distribution (42 queries: 37 positive / 5 negative)

| Direction | Count | Intent |
|---|---|---|
| factoid | 22 | single-source fact retrieval |
| precise_detail | 7 | exact constants/formulas/signatures |
| multi_chunk | 4 | cross-chunk synthesis within one source |
| comparison | 4 | real-vs-virtual DOM, eval configs, hybrid rationale |
| **positive total** | **37** | |
| negative | 5 | abstention/negative-rejection enforcement |
| **total** | **42** | ids q161–q202 (no collision with q001–q160) |

## 7. Source coverage (Step-4 requirement)

**14 / 14 new docs covered** (verified programmatically: every source key non-empty in the positive set).

- PAM guide: q161–q165, q176, q177, q183, q186–q188 (pam_guide is the expected source of **11** queries) — highest because the guide is the most retrieval-dense doc and the #1 interference leader.
- Web notes: q170, q171, q180, q182, q190
- GPU report: q168, q169, q179, q184
- Auto testing: q166–q167, q178, q185
- FLAT: q173, q181, q189
- Graph theory: q172, q175
- Docker cheat sheet: q174
- Certificates (each its own doc): q191–q195, q201, q202

## 8. Negative query methodology

Five negatives, each:
- **Near-hit by construction** — the distractor source produces top candidates under the current threshold (e.g., `q196` "How much RAM..." returns PAM chunks at high cosine; `q199` "SNPSU" returns Web notes).
- **Verified absent** — no evidence fragment, and no supporting text anywhere in any chunk. Manually grepped the store: the terms (RAM requirement, Node.js version, cost estimate, full university name, orchestration platform) do not occur as answer-bearing text.
- **Expected behavior documented** per query as `ABSTAIN` so the post-run report can score negative rejection precisely.

These are deliberately harder than the legacy negatives (which were mostly general-knowledge refusals: "capital of France") — they test the gating decision *in the presence of top-similar documents*, the actual Phase 5A failure profile.

## 9. Proposed schema (v3.0-proposed)

Mirrors `dataset.json` (same keys: id, query, expected_sources, expected_evidence, category, difficulty, ground_truth_reliable, answerability) and adds a machine-checkable field:

```json
{
  "id": "q177",
  "query": "...",
  "expected_sources": ["pam_guide"],
  "expected_evidence": "human-readable answer summary",
  "evidence_fragments": ["verbatim substring in source", "..."],
  "category": "precise_detail",
  "difficulty": "medium",
  "ground_truth_reliable": true,
  "answerability": "yes"
}
```

- `evidence_fragments`: every element is a whitespace-collapsed verbatim substring of at least one chunk of an `expected_sources` doc — this is what makes the dataset self-verifying and diffable against store changes.
- `answerability: no` + empty `expected_sources` + empty `evidence_fragments` marks negatives (consistent with legacy negative detection = empty `expected_sources`).
- Expected-source keys are short mnemonic ids that resolve to the same filename fragments used by `run_eval.SOURCE_KEY_TO_FILENAME`; the 14 new keys are listed in `metadata.source_keys`. Because `run_eval.match_source` falls back to the raw key and substring-matches, `run_eval` runs the proposal **unchanged** once the new keys are merged.

## 10. Full proposed query list (ids, direction, category, expected source)

| ID | Question (abridged) | Category | Source(s) |
|---|---|---|---|
| q161 | RRF constant k | factoid | pam_guide |
| q162 | embedding model + dims | factoid | pam_guide |
| q163 | chunker size/overlap | factoid | pam_guide |
| q164 | default Ollama text model | factoid | pam_guide |
| q165 | kinds/ingestors/processors counts | precise_detail | pam_guide |
| q166 | frozen abstention threshold | factoid | auto_testing |
| q167 | answer-generation LLM | factoid | auto_testing |
| q168 | GPU environments | factoid | gpu_report |
| q169 | initially supported languages | factoid | gpu_report |
| q170 | two React component types | factoid | web_module5 |
| q171 | createRoot in React 18+ | factoid | web_module5 |
| q172 | source and sink definitions | factoid | graph_theory |
| q173 | TM 7-tuple definition | factoid | flat_tm |
| q174 | docker ps -a | factoid | docker_cheatsheet |
| q175 | in/out degree definitions | factoid | graph_theory |
| q176 | 11-stage ingestion pipeline | multi_chunk | pam_guide |
| q177 | 8 chunks / 12k chars context limits | precise_detail | pam_guide |
| q178 | Auto Testing runtime flow | multi_chunk | auto_testing |
| q179 | 12-step GPU workflow | multi_chunk | gpu_report |
| q180 | Color Organizer state flow | multi_chunk | web_module5 |
| q181 | undefined transition-table entry | factoid | flat_tm |
| q182 | Real vs Virtual DOM | comparison | web_module5 |
| q183 | vector + BM25 hybrid rationale | comparison | pam_guide |
| q184 | three eval configurations | comparison | gpu_report |
| q185 | semantic + BM25 + RRF rationale | comparison | auto_testing |
| q186 | RRF worked-example winner | precise_detail | pam_guide |
| q187 | pool_size formula | precise_detail | pam_guide |
| q188 | BM25 k1/b parameters | precise_detail | pam_guide |
| q189 | transition function domain/range | precise_detail | flat_tm |
| q190 | React keys rationale + index key | precise_detail | web_module5 |
| q191 | DevOps on AWS cert (Aug 06) | factoid | cert_devops_aws |
| q192 | CC0101EN = Introduction to Cloud | factoid | cert_intro_cloud |
| q193 | Senior Data Scientist on Coursera cert | factoid | cert_data_analysis |
| q194 | Docker Essentials cert | factoid | cert_docker_intro |
| q195 | Python DS cert verification URL | factoid | cert_python_ds |
| q196 | PAM RAM requirement | negative | — (abstain) |
| q197 | Node.js version for React examples | negative | — (abstain) |
| q198 | GPU platform cost estimate | negative | — (abstain) |
| q199 | full name of SNPSU | negative | — (abstain) |
| q200 | orchestration platform in cheat sheet | negative | — (abstain) |
| q201 | AWS CloudFormation cert (Aug 07) | factoid | cert_cloudformation |
| q202 | AWS Foundations cert (Aug 08) | factoid | cert_aws_foundations |

## 11. Ground-truth evidence guarantees (Step 6 checklist)

- Every `evidence_fragment` verified **verbatim** (whitespace-collapsed) against current store chunks → **0 / 0 fragments missing**.
- Every expected source resolves to a real store file via the same substring rule as `run_eval.match_source`.
- Cross-source query corrections applied during review: q168, q185 narrowed to grounded sources only (`pam_guide` removed as an unverified secondary), so no query passes on a doc that does not contain its answer.
- PDF-griffin cases flagged inline: q171 (`createRoot()function`, `top -level` spacing), q173/q189 (Unicode glyphs Σ Γ' δ q₀ preserved file-exact), q193 (letter-spaced OCR text — an intended hard vector-only probe), q178 (→ glyph).

## 12. Quality audit results (Step 7)

Automatic audit over all 42 queries: id uniqueness, collision with q001–q160, duplicate query text, length bounds, positive/negative consistency (partial cross-check against `dataset.json`).

**Result: 42 PASS / 0 WARNING / 0 REJECT.**

Human-review notes (all PASS with intent):
- The 7 certificate queries are thin by design — discriminating boilerplate docs is an explicit goal; their evidence is 100% grounded.
- `q193` witnesses real OCR degradation in the source; it is kept as a discovered boundary probe (vector must beat letter-spaced garbage).

## 13. Dataset statistics (Step 8 balance analysis)

| Set | total | positive | negative | factoid | precise/multi/comparison |
|---|---|---|---|---|---|
| existing dataset.json | 160 | 123 | 37 | 87 | 36 |
| proposed v3 (new) | 42 | 37 | 5 | 22 | 15 |
| **combined (if adopted)** | **202** | **160** | **42** | **109** | **51** |

- Negative fraction after merge ≈ 20.8% (vs 23.1% today) — still a demanding abstention workload; the 5 new negatives are qualitatively harder (near-miss vs general knowledge).
- Combined coverage: 10 legacy + 14 new = **24/24 sources** with ground truth (3 legacy orphans q092–q094 removed would still resolve; if kept they are permanently EXPIRED and should be dropped when merging).
- Excellent source-level balance: no document is over-sampled beyond its chunk richness.

## 14. Evaluation plan (Step 9 — design only; NOT run)

Three experiments, no production code touched, store loaded read-only:

- **EXPERIMENT A — Full regression gate.** Run the combined 202-query set against the frozen current store (top-k 5, min-cosine 0.45) via `eval/run_eval.py`. Report Hit@1/3/5, MRR, FPR, FNR, abstention rate, positive acceptance, negative rejection, latency p50/p95. This is the single number that future retrieval changes must beat.
- **EXPERIMENT B — New-doc isolation.** Run only the 42 proposed queries. Split report: 37 positives (new-doc Hit@/MRR) and 5 negatives (rejection of near-miss distractors). This measures whether the system can now find the docs that regressed it — the direct Phase 5A closure check.
- **EXPERIMENT C — Interference probe (diagnostic, informational).** For the 37 positive queries, also record **which** sources occupy the top-5 alongside the true source. Share of top-5 slots taken by PAM_V1_LEARNING_GUIDE / GPU report on queries whose true source is another doc quantifies remaining competition and tells us whether the interference is solved or merely measured. No config/corpus change — purely an output-side analysis.

Rollback safety: writes only `eval/results/`; never touches `dataset.json`, ingest, manifests, or the store.

## 15. Risks and limitations

- **Certificates thin:** 7/42 queries draw from ≤1-chunk docs; a correct answer mostly proves the doc was retrieved, not deep reasoning. Accepted as designed (source discrimination was the point).
- **Nomenclature drift:** proposed categories (`precise_detail`, `multi_chunk`) don't match legacy labels (`tricky`, `cross_document`) — a mapping is needed when merging; `run_eval` itself reads categories only for reporting.
- **Unicode/PDF artifacts in evidence** (q171, q173, q189, q193, q178) make the fragments fragile if sources are re-ingested/re-OCRed. Verifier will flag them if the store changes.
- **5 negatives may be too few** for strong FPR confidence. I recommend adding ~5 more near-miss negatives in a later phase once this set is validated.
- **Link to regression closure:** adding queries alone does not fix retrieval; a regression (Experiment A) may still show residual interference — that is an outcome to plan for, not a failure of this dataset.

## 16. Recommendation

1. **Approve** `eval/dataset_v3_proposed.json` as the Phase 5B deliverable (it is a proposal only; merging into `dataset.json` is a separate, later decision — and note the 3 orphan queries q092–q094 should be dropped when merged).
2. Run **Experiment A + B** on the frozen store for the Phase 5 verification gate; use **Experiment C** to decide whether PAM/GPU docs still crowd out true sources.
3. Do **not** change retrieval/config/corpus until the new-doc eval numbers exist — otherwise regressions are once again invisible.

---

*Deliverables: `eval/dataset_v3_proposed.json` (verified: 42 queries, 37 positive grounded verbatim 0/0 failures, 14/14 sources, 5 abstain-hard negatives) + this report. No commits made; HEAD unpushed; `dataset.json` untouched.*