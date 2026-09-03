# Phase 5G — V1 Retrieval Journey Decision

**Status:** REVIEW / DECISION ONLY — complete retrospective of the PAM V1 retrieval journey with an explicit engineering decision. No production code, config, corpus, dataset, or embedding modified; no commits; no pushes.
**Date:** 2026-08-28
**Head input gates:** Phases 3A–3G (investigation), 4 (ingestion), 5–5F (real-corpus eval + experiments). Frozen state verified this phase: `eval/dataset.json` v3.0 (199 queries), 5D baseline, reports 20–32 all read.

---

## 1. Objective

Review the complete PAM V1 retrieval journey end-to-end, determine whether a justified next engineering step exists on the retrieval side, and emit exactly ONE decision. This phase is analysis-only; its deliverable is this report and its evidence-backed decision.

**Constraint honored:** nothing below proposes or implies a change to frozen state. All analysis is derived from the measured artifacts (reports 20–32, `eval/dataset.json`, `eval/results/phase_5d_frozen_baseline.json`, 5F experiment outputs).

## 2. Frozen state and hard guardrails (verified this phase)

| Item | Value | Verified |
|---|---|---|
| HEAD | `9f282b41` | in prior phases; unchanged |
| Dataset | `eval/dataset.json` v3.0 — **199 queries (157 pos / 42 neg, q001–q202)** | read this phase (ids q001..q202, 157/42) |
| Corpus | 24 sources / 195 chunks, nomic-embed-text 768-dim | reports 27/30 |
| Config | top_k=5, min_cosine=0.45, BM25 k1=1.5/b=0.75, RRF k=60; reranker/hyde/answerability all `false` | report 30 §9 |
| Baseline | Hit@1 0.841, Hit@3 0.911, Hit@5 **0.924**, MRR **0.877**, FPR **0.857**, FNR 0.000, abstention 0.030, p95 47.1 ms | `phase_5d_frozen_baseline.json` read this phase |
| Guardrails (NOT relaxed) | FNR ≤ 0.033; Hit@5 ≥ 0.93; MRR ≥ 0.88; FPR materially < 0.811 (target ≤ 0.5 per older specs); p95 < 500 ms | user mandate |

**Two guardrails already fail at the frozen baseline independent of abstention:** Hit@5 0.924 < 0.93 and MRR 0.877 < 0.88. FPR 0.857 fails. FNR and latency pass trivially.

## 3. Evidence table — the complete retrieval journey (measured, not modeled)

Every row is taken from the phase report cited; a value is only shown where it was measured. "≈" marks a figure measured once under a different dataset/corpus than now.

| # | Experiment (phase → report) | Direction | Corpus / queries | Hit@1 | Hit@5 | MRR | FPR | FNR | Latency (p95 or per-query) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Cosine abstention gate + threshold (2C→3B → **14**) | threshold tuning | 101 chunks / 160q (legacy) | 0.902 | 0.967 | 0.930 | 0.811→0.714 (t sweep) | 0.008 | sub-ms overhead | **VALIDATED as gate**; t-top-out floor FPR ≈ 0.21 at FNR ≈ 0.37 (5E §8) |
| 2 | Cross-encoder reranker (3C → **16**) | retrieval architecture | 101 chunks / 160q | 0.907→**0.837** | 0.953 | 0.940→**0.895** | 0.714→**1.000** | 0.000 | ~22→**~850 ms** | **REJECTED** (regression on Hit@1/MRR; FPR worse; latency) |
| 3 | BM25 override fix (3E → **18**) | retrieval bugfix | 101 chunks / 160q | 0.902 | 0.967 | 0.934 | 0.865→**0.811** | 0.008 | ~ms | **VALIDATED** (FPR −5.4pp, no positive loss) |
| 4 | HyDE (3E → **18**) | retrieval architecture | 101 chunks / 160q | — | — | — | — | — | ~44 s/query | **REJECTED / INCONCLUSIVE** (latency) |
| 5 | Embedding swap → mxbai-embed-large 1024-dim (3G-A → **20**) | embedding replacement | ~176–199q / 101 chunks | 0.878→0.862 | **0.927→0.902** | 0.901→0.885 | 0.973→0.892 | 0.000 | ~ms | **REJECTED** (Hit@5 < 0.93; denser clusters, same topic-vs-answer limit) |
| 6 | Corpus growth 10→24 sources (5/5A → **26/27**) | ingestion / composition | 199q over 24 src | 0.902→**0.797** | 0.967→0.886 | 0.930→0.835 | 0.811→0.838 | 0.008→0.000 | ~ms | **Expected cost of relevance** — PAM guide legitimately tops 13/18 regressions |
| 7 | Real-corpus eval dataset (5B → **28**) | evaluation design | 42 new grounded q (37 pos/5 neg), 14/14 new docs | — | — | — | — | — | — | **VALIDATED** (verbatim grounding 0/0 misses) |
| 8 | Real-corpus evaluation (5C → **29**) | measurement | Exp A 157 / Exp B 42 / Exp C 199 | A 0.817 / B 0.919 / C 0.841 | A 0.908 / B 0.973 / C 0.924 | A 0.856 / B 0.946 / C 0.877 | A 0.838 / B **1.000** / C 0.857 | A–C 0.000 | A 72.5 / B 59.5 / C 60.1 ms | New-doc retrieval **strong (VALIDATED)**; FPR fails everywhere |
| 9 | Dataset freeze 199q (5D → **30**) | freeze | 199q / 24 src | 0.841 | 0.924 | 0.877 | 0.857 | 0.000 | 47.1 p95 | **FROZEN** |
| 10 | Score-signal root cause (5E → **31**) | signal analysis | 199q / 24 src | 0.841 | 0.924 | 0.877 | 0.857 | 0.000 | 47.1 p95 | **VALIDATED**: only cosine separates; all other 12 signals overlap TPs/FPs; t-sweep floor FPR ≈ 0.21 @ FNR ≈ 0.37; 12/36 FPs ∈ hard-core ≥0.62 |
| 11 | Banded answerability verifier experiment (5F → **32**) | LLM evidence gate (prototype, default off) | 199q / 24 src | 0.841 | 0.924 | 0.877 | 0.857→**0.405** (band [0.45,0.62)) | 0.000→**0.070** | **~17 s p95 on band** (avg 14.1 s) | **REJECTED for V1** (FNR 0.070 > 0.033; latency fails; no threshold point satisfies all guardrails). **CANDIDATE mechanism for the answering layer** |

**Cross-cutting measured facts (5E, 5C, 5F):**

- **31 of 36 FPs** are *content-sufficiency* misses — retrieval is on-topic, the requested fact is absent (B 16 + F 11 + C 2 + E 2). All 6 correctly-rejected negatives are Category A (cos < 0.45).
- **12/36 FPs** sit at cos ≥ 0.62 (above the TP p25 of 0.610) — score-indistinguishable from true positives. No score-only rule can touch them.
- **PAM_V1_LEARNING_GUIDE.pdf** is the FP hub (14/36 top-1) and a legitimate positives source (11/11 new queries at Hit@1 1.000) — must be kept (5C/5E/5F all agree).
- **Verifier behavior (5F):** 78 banded invocations → 44 SUPPORTED (39 pos / 5 neg), 34 INSUFFICIENT, **0 fallbacks, 0 timeouts**; confidence degenerate (SUPPORTED 0.9–1.0, INSUFFICIENT exactly 0.0). Survivor FPs = 12 hard-core (auto-accept) + 5 verifier false-accepts (q041, q045, q129, q131 = F-class topic overlap; q199 = C-class).
- **Determinism:** 5F Experiment A (199/199) reproduced the 5D baseline exactly.

## 4. Root limitation (A–G) — *combination, but with one decisive core*

| Hypothesized limitation | Evidence | Verdict |
|---|---|---|
| A. Retrieval recall | Hit@5 0.924; only 12/157 misses, mostly cert-siblings (q193) and known interference; new-doc Hit@5 0.973 | **No** — recall is adequate |
| B. Ranking quality | 13 wrong-rank + interference demotions (10 by PAM guide); Hit@5/MRR fail independent of abstention | **Contributing, secondary** — real but narrow (few queries) |
| C. Abstention / rejection design | 36/42 negatives accepted; gate only catches cos < 0.45 (Category A) | **DECISIVE CORE for FPR** |
| D. Corpus quality | Certificates near-duplicate (AWS ×3, Python ×2); OCR noise; single-chunk certs; but all substantive docs retrieve at 1.000 | **Marginal** — not the FPR driver |
| E. Query understanding | Ask-the-tool questions (F: 11) and fact-absent-same-topic (B: 16) all pass the gate | **Core contributor** (joins C) |
| F. Evaluation design | Hard near-miss negatives (5 new + legacy B/F) deliberately stress abstention; FPR measured on dense same-topic corpus | **Amplifier, honest** — not a defect |
| G. Combination | FPR = C (no semantic-abstention) + E (cannot distinguish "topic" from "answer"); Hit@5/MRR = B under D-competition | **Yes — this is the answer** |

**Conclusion:** The true limitation is a **combination**: the *answering layer has no evidence-verification* (C+E) — that drives FPR — while a *narrow ranking gap* (B, aggravated by legitimate new-doc competition D) drives the two already-red retrieval-side guardrails (Hit@5, MRR). No retrieval-side score, threshold, model, or re-ranking lever is capable of fixing the C+E core (5E §5/§8/§11, 5F). This is the load-bearing fact for the decision.

## 5. V1 requirements realism

- **The guardrail bundle (all five at once) has no measured compliant point** on the frozen 199-query corpus:
  - FPR-compliant states (3G-B 0.243; 5F 0.405; t=0.49→0.762) all violate **FNR ≤ 0.033** (0.098, 0.070) or fail the "materially < 0.811" bar, and/or latency.
  - The only FNR-compliant threshold (t=0.49) leaves FPR 0.762 (marginal) and Hit@5/MRR failing.
  - Hit@5 ≥ 0.93 and MRR ≥ 0.88 **cannot be reached by abstention tuning at all** — they are ranking metrics already red at the frozen baseline.
- **Why:** the guardrails were calibrated on a 10-source / 101-chunk corpus (Hit@5 0.967, MRR 0.930). The 24-source dense corpus plus 42 near-miss negatives moved FPR measurement from "general-knowledge refusals" to "same-topic-absent-fact" — an intrinsically harder bar that the V1.1 guardrail set never anticipated.
- **Realism verdict:** each guardrail is individually reasonable; **the bundle as a strict go/no-go on the current corpus is not simultaneously satisfiable by any measured means**. This is a *requirements-realistic* finding stated plainly, NOT a proposal to relax targets (user mandate: do not relax — respected below; completion is defined without redefining metrics, §10).

## 6. Retrieval vs answering — where the failure actually lives

| Layer | What it does | Measured state | Verdict |
|---|---|---|---|
| **Retrieval** | Find chunks relevant to the query | Hit@5 0.924, MRR 0.877, new-doc Hit@5 0.973, FNR 0.000; retrieval-side deterministic | **Functional.** Only a narrow ranking gap (12 misses / 13 wrong-rank) |
| **Answering** | Decide the evidence *contains the answer*, then answer/abstain | 36/42 negatives accepted; every accepted B/F/C/E negative has on-topic chunks but **no requested fact** | **The failure.** Semantic topic-match ≠ answer-presence. No retrieval score can express it (5E §5) — it requires evidence verification |

FPR is an **answering-layer** responsibility that retrieval has been asked to carry. The 3G-B (-70% FPR) and 5F (-52% FPR) numbers prove a content-verifier is the only tested mechanism that deletes this class; its costs (FNR, latency, model dependency) belong to the answering layer, where they can be engineered (scoped invocation, fail-open, small models, per-query policy) rather than inherited blind by every retrieval path.

Implication: **attempting to fix FPR through retrieval changes is mis-aimed and has been empirically exhausted** (thresholds 3B/5E, embeddings 3G-A, reranking 3C, HyDE 3E, metadata 5E §10, doc removal 5E §7.3).

## 7. Safe product behavior (reference contract — NO implementation)

Behavior the product should exhibit for each observed failure class, defined so future (application-layer) work has a spec; nothing here changes production:

| Case | Measured class | Safe behavior (policy-level) |
|---|---|---|
| 1. Answer present, strong evidence | 133/157 accepted positives (top-5) | Answer, cite sources (retrieval already works) |
| 2. On-topic, fact absent | B: 16/36 FPs | **Abstain with explanation** ("the sources discuss X but do not state Y") — requires evidence verification |
| 3. Meta/system question about PAM/KB | F: 11/36 FPs | **Knowledgeable abstention or guided answer** from a curated system-facts source — never a fabricated count/version |
| 4. Temporal/current info absent | E: 2/36 FPs | **Abstain** ("not in the knowledge base; as of last index…") |
| 5. Related topic, wrong doc | C: 2/36 FPs | **Abstain + show nearest sources** so the user can refocus |
| 6. Truly out-of-scope | A, currently caught (cos < 0.45, 6/42) | **Abstain** (works today); keep coverage for mid-band A-near-misses (5/36) |

All six are already defined at the citation/abstain layer and none requires a retrieval change.

## 8. V1 directions evaluated (7) — evidence-weighted

| Direction | Evidence for | Evidence against | FNR risk | Latency | Complexity | Maintenance | Verdict |
|---|---|---|---|---|---|---|---|
| 1. **Freeze retrieval V1**; move to application layer | Retrieval measured-exhausted (this report §4/§6); answering is where FPR lives | — | n/a | n/a | none | none | **VALIDATED — chosen** |
| 2. Answerability verifier re-run (relaxed prompt on frozen 199) | 5F re-calibration not fully swept | 5F relaxed prompt already: brand [0.45,0.62) FNR 0.070, p95 17.3 s; 3G-B 0.098. No measured (prompt, band, model) passes all guardrails; confidence signal degenerate | **high (guardrail 0.033)** | **high** | medium | medium | **REJECTED for V1** (repeated rejected approach under the strict rule, §9); keep as answering-layer candidate |
| 3. Binary query classification (meta/system detection) | kills F + part C (≥11/36) | B (16/36) untouched → best-case FPR ≈ 0.596, still not ≤ 0.5; classifier accuracy unmeasured → hypothesis not specific | low | low | medium | medium | **REJECTED as root fix** (cannot meet all guardrails alone) |
| 4. Metadata-aware scoring | headings/tables exist for some chunks | 5E §10: no measured discriminating field; FPs split across all types | low | none | low | per-corpus rules | **REJECTED** (no measured signal) |
| 5. Retrieval architecture change (reranker / query-scoped / colBERT) | 5E fallback noted | 3C: reranker degraded Hit@1/MRR and FPR; any ranking lever is FPR-blind to the 31 content-sufficiency FPs | low | high | high | model-dependent | **REJECTED for FPR**; could revisit only for the narrow Hit@5/MRR gap with a *new* specific hypothesis |
| 6. Corpus / eval expansion (more near-miss negatives) | 5C §12 notes 5 new negatives may be too few | Evaluation-only: does not move a system metric; hard negatives *lower* FPR measured value → defeats the guardrail as written | none | none | low | dataset churn | **REJECTED as an engineering step** (measurement change ≠ fix; also risks moving goalposts) |
| 7. Hybrid (verifier + ranking simultaneously) | both mechanisms proven individually | Not a single measurable hypothesis; two unknown interactions; complexity multiplies debugging | **high** | **high** | **high** | high | **REJECTED by rule** (speculative bundle) |

## 9. Experiment justification (strict rule applied)

> Another experiment may be recommended **only if**: (1) it has a specific, measurable hypothesis; (2) it has not already been answered by completed phases; (3) it is *plausible* to satisfy ALL guardrails simultaneously; (4) it does not repeat a rejected approach.

| Candidate | Specific hypothesis? | Answered already? | Plausible all-guardrails? | Repeats rejected? | Passes? |
|---|---|---|---|---|---|
| Relaxed-prompt answerability re-sweep | yes | **yes — 3G-B + 5F** (strict AND relaxed variants, banded and full, measured) | no (FNR/latency fail at every measured point) | **yes** | **NO** |
| Reranker / query-scoped retrieval | partial | yes — 3C reranker | no (ranking-only; cannot bound FPR; 3C regressed) | **yes** | **NO** |
| Query classifier | no — accuracy unmodeled, no calibration data | no | no (B-class untouched → FPR ≥ ~0.60) | no | **NO** |
| Hybrid bundle | no | no | no | — | **NO** |
| Corpus/eval expansion | not a system-quality hypothesis | — | n/a (changes the ruler, not the thing measured) | — | **NO** |

**Result: exactly zero candidates pass the strict rule on the retrieval side. No further retrieval experiment is justified at V1.**

## 10. V1 completion criteria

V1 retrieval is declared **COMPLETE** (frozen, measured, decision-recorded) — independent of the V1.1 guardrail gate:

1. **Frozen, reproducible state** — dataset v3.0 (199q), corpus (24 src / 195 chunks), config, baseline artifact `phase_5d_frozen_baseline.json`, HEAD `9f282b41`. Verification: exists (this report §2; 5F Experiment A reproduced 5D on 199/199) — **MET**.
2. **Every retrieval-side lever tested with a recorded measured outcome** — cosine/abstention, BM25 bugfix, embeddings, HyDE, reranker, metadata, doc removal, answerability (strict + banded), signal analysis. Each is VALIDATED or REJECTED with evidence (this report §3) — **MET**.
3. **Known gaps enumerated with owners** — (a) FPR/abstention → answering-layer evidence verification (candidate mechanism: 5F verifier, hand-carry FNR/latency engineering forward); (b) Hit@5 0.924 / MRR 0.877 → narrow ranking gap, revisit only with a new specific hypothesis and new model/data; (c) cert-sibling discrimination (q193) → doc-quality backlog — **MET by this report**.
4. **Guardrails untouched and re-stated as the V1.1 acceptance gate**, NOT renegotiated to declare success — **MET**.

V1 completion ≠ all-5-guardrails-green. Green is the V1.1 gate and stays un-relaxed; retrieval V1 is *finished*, which is a different (and honest) statement.

## 11. Decision (ONE)

> **C — Freeze retrieval V1 and move to the application layer.**

No variant of A (continue optimization) or B (one justified experiment) survives §8/§9; D (expand corpus+eval) is rejected as a change-the-ruler move (§8). The full options table is the answer:

| Option | Verdict |
|---|---|
| A — Continue retrieval optimization | **REJECTED** (every retrieval lever measured-exhausted; two guardrails unreachable from retrieval) |
| B — One justified retrieval experiment | **REJECTED** (strict rule: zero candidates pass §9) |
| **C — Freeze retrieval V1; move to application layer** | **CHOSEN** |
| D — Expand corpus/eval | **REJECTED for now** (measurement churn ≠ fix; revisit if corpus grows materially) |

## 12. Rationale (evidence-anchored)

1. **The dominant failing metric (FPR 0.857) is an answering-layer defect.** All 31/36 B/F/C/E FPs are content-sufficiency misses that no retrieval score, threshold, model, reranker, or metadata can detect (§4, §6; 5E §5/§8). Retrieval is being asked to answer a question it does not possess the signal for.
2. **Retrieval itself is at a defensible ceiling for this corpus:** Hit@5 0.924 recall and MRR 0.877 with zero false negatives, deterministic, 47 ms p95; new-doc recall 0.973. The two red ranking guardrails are a narrow, named gap (12 misses / 13 wrong-rank; PAM-guide demotions) — not a systemic failure.
3. **The only mechanism that deletes the FP class is content evidence verification, and both its prototypes (3G-B strict, 5F banded) were measured:** −70% and −52% FPR respectively — but each violated FNR ≤ 0.033 and 500 ms. That is a *parameter-and-scoping* problem of the answering layer, properly engineered there (scoped invocation, fail-open, small models, per-query policy), not a reason to keep re-testing retrieval.
4. **Continuing retrieval work is now cost-negative:** it has consumed 11 measured experiments with no approach meeting the bundle; repetition is the failure mode the strict rule exists to prevent.
5. **The application layer holds the addressable value:** answer-with-citation UX, evidence-verified abstention with explanations, curated system-facts handling (F-class), and the narrow ranking gap are all there — each with a defined safe behavior (§7) and a measured starting point.

## 13. Risks, exceptions, and reopening conditions

- **Risk — frozen guardrails stay red.** Accepted as V1.1 gate, not V1 completion bar. Do not "ship" red metrics without product sign-off on the V1.1 plan.
- **Risk — verifier FNR.** Hand-carrying 5F's 0.070 FNR risk into the answering layer is the single highest risk; mitigated by fail-open defaults, scoped bands, and the ≤ 5-rejection numeric gate at V1.1.
- **Exception — corpus changes.** If a materially different document set is ingested (new domain, new file volumes), re-run the frozen 199 against the new corpus first (the 5A/5B lesson) before touching anything.
- **Reopening conditions for retrieval (any one):** a new embedding/ranking model with a *specific, falsifiable* hypothesis for Hit@5/MRR (not FPR); a new evidence source set/negative class; or a V1.1 answering-layer verdict table that still cannot meet the bundle and therefore re-opens the whole question. Any reopen must clear the §9 rule fresh.

## 14. Safety verification (this phase)

- No production code, config (all gates remain `false`), corpus, `dataset.json`, vector store, or embeddings were touched.
- Reads only: reports 20–32, `eval/dataset.json`, `eval/results/phase_5d_frozen_baseline.json`, 5F artifacts.
- One throwaway analysis script in `C:\Users\girid\AppData\Local\Temp\opencode\p5g_verify.py` (read-only; deleted before stop).
- `git status --short` / `git diff --stat` verified unchanged vs. the pre-existing cumulative uncommitted state; no commits, no pushes. (See §15 footer verification.)

## 15. Final status and next step

**STOPPING — awaiting explicit approval.** Decision delivered: **C — Freeze retrieval V1; move to the application layer.**

Next step (requires explicit approval, not started): a V1.1 application-layer phase that (1) defines the answering-layer contract per §7, (2) re-measures the 5F verifier as a scoped, fail-open evidence module with a numeric FNR/latency gate, and (3) targets the named ranking gap independently. Retrieval config, dataset, and corpus remain frozen throughout; any future retrieval change must clear the §9 rule.

---

*Truth preamble: every number in the evidence table is taken from the cited measured artifact; where a figure was measured under a different dataset/corpus it is flagged. This report introduces no new measurements and asserts no unmeasured improvement.*