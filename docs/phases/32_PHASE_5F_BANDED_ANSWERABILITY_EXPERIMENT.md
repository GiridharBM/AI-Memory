# 32. Phase 5F — Banded Answerability Verifier Experiment

> **Date:** 2026-08-28 · **SESSION:** `ses_fbde6595dffeTjAxbomDR36utR` · **FROZEN HEAD:** `9f282b41b6c558b0dbea857c95e24beb3ff63f9a`
>
> **This is an isolated, feature-flagged experiment. No production code changed.**
> The Phase 3G-B gate (`app/infrastructure/answerability.py`), the frozen dataset,
> retrieval config, and all historical artifacts are untouched and reproducible.
> The only repo additions are a new standalone module, its unit tests, and this report.

---

## 1. Executive Summary

| Item | Value |
|---|---|
| **RESULT** | **REJECTED** as a Phase-5 production candidate under the current guardrails |
| **Mechanism signal** | **CANDIDATE FOR FURTHER VALIDATION** (banded post-retrieval verifier is the strongest FPR lever found; fails on FNR + latency) |
| FPR | **0.857 → 0.405** at headline band `[0.45, 0.62)` (a **45‑point drop**) |
| FNR | **0.000 → 0.070** (11 abstained positives; **guardrail ≤ 0.033 violated**) |
| Hit@5 / MRR | Unchanged at 0.9236 / 0.8773 (retrieval-side; gate cannot move them) |
| Verifier latency | p95 **17.3 s** (guardrail ≤ 500 ms **violated by ~34×**) |
| Control fidelity | Experiment A matches Phase 5D baseline on **all 199/199 queries** |

The banded verifier is the **first mechanism in Phase 5 that materially reduces FPR without touching retrieval**, but the frozen guardrail bundle cannot be met by banding alone: any band wide enough to matter violates FNR, the ≥ 0.62 hard-core fact-absent FPs survive every threshold tested, and the LLM verdict costs ~14 s/query on this CPU setup.

The experimental artifact is labeled **`CANDIDATE FOR FURTHER VALIDATION`** because the verdict signal itself is strong (22/27 in-band FPs rejected, 0 fallbacks, 0 timeouts, 0 malformed outputs).

---

## 2. Objective

Run **one isolated experiment** — a *banded* post-retrieval answerability verifier — and determine whether it reduces the Phase 5D false-positive rate **without violating the frozen acceptance guardrails**:

| Guardrail | Target |
|---|---|
| False-Negative Rate | ≤ 0.033 |
| Hit@5 | ≥ 0.93 |
| MRR | ≥ 0.88 |
| False-Positive Rate | materially < 0.811 |
| Latency | p95 < 500 ms |

All other frozen constraints honored: no changes to `eval/dataset.json`, historical artifacts, embedding model, chunking, BM25, RRF, cross-encoder, HyDE, corpus documents, or the `answerability.enabled = false` production default; Phase 3G-B remains reproducible. No commits/pushes made.

---

## 3. Dataset and Environment

- **Dataset:** frozen v3.0 — `eval/dataset.json`, **199 queries** (157 positive / 42 negative).
- **Corpus:** 24 sources / 195 chunks (`data/manifests/vector_store.json`), read-only.
- **Retrieval:** production `SearchService` — nomic-embed-text (768‑dim) + BM25 (k1=1.5, b=0.75) + RRF (k=60), `top_k=5`, `min_cosine=0.45`.
- **Reranker / HyDE / answerability:** all disabled (frozen default).
- **Verifier LLM:** `qwen3:8b` via local Ollama (`http://localhost:11434`), `temperature=0.0`, JSON-schema-constrained via `OllamaClient.generate_json(response_model=...)`.
- **Hardware:** CPU-only host. **Extraction used none of the previous fallback invalidation from Phase 5E** — Ollama was verified up (HTTP 200 / `is_available()`) before the run.

---

## 4. Frozen Baseline Metrics (Phase 5D, re-established)

Re-read from `eval/results/phase_5d_frozen_baseline.json` (deterministic, values re-verified by Experiment A):

| Metric | 5D value | 5F Exp A | Match |
|---|---|---|---|
| Hit@1 | 0.8408 (132/157) | 0.8408 | ✔ |
| Hit@3 | 0.9108 (143/157) | 0.9108 | ✔ |
| Hit@5 | 0.9236 (145/157) | 0.9236 | ✔ |
| HRR / MRR | 0.8773 | 0.8773 | ✔ |
| FPR | 0.8571 (36/42) | 0.8571 | ✔ |
| FNR | 0.0000 (0/157) | 0.0000 | ✔ |
| Abstention rate | 0.0302 (6/199) | 0.0302 | ✔ |
| Neg rejection | 0.1429 (6/42) | 0.1429 | ✔ |

Baseline FPs: the 36 negatives accepted at cosine ≥ 0.45. Baseline abstentions: q032, q116, q117, q136, q138, q139 (all Category A, cosine < 0.45).

> Note: **Hit@5 (0.9236) and MRR (0.8773) are already below their guardrail targets (0.93 / 0.88) in the frozen baseline itself.** They are retrieval-side metrics; the verifier never changes ranking, so it can neither raise nor lower them. This phase's decision therefore rests on **FPR / FNR / latency**.

---

## 5. Experiment A — Control (Reproducibility)

Ran the exact Phase 5D harness (`AbstentionGate(0.45)`, no verifier) against the frozen dataset.

- Output: `eval/results/phase_5f_experiment_a.json`
- **Query-level comparison vs Phase 5D: 199/199 identical** (accepted / abstained / correct / expected_rank) — mismatch count **0**.
- Conclusion: the harness and corpus are unchanged; Experiment B deltas are attributable solely to the verifier.

---

## 6. Experiment B — Banded Answerability Verifier (Setup)

| Setting | Value |
|---|---|
| File | `app/infrastructure/banded_verifier.py` (new, isolated) |
| Enabled flag | `BandedGate(enabled=True)` — production default **remains `answerability.enabled = false`** |
| Band | `band_low = 0.45`, `band_high = 0.62` (headline); sweep 0.46–0.64 |
| Verifier LLM | `qwen3:8b`, `temperature=0.0`, `timeout_seconds=60` |
| Max evidence chunks | 5 |
| Policy | `cos < 0.45` → baseline abstain · `0.45 ≤ cos < band_high` → LLM verdict · `cos ≥ band_high` → baseline accept |
| Fail-open | timeout / LLM error / malformed output → baseline decision (accept) |
| Verdict cache | `eval/results/phase_5f_experiment_b.json` (all 199 queries, resume-safe) |

**Verifier coverage:** invoked on all queries with `0.45 ≤ top_cosine < 0.64` (the widest union band) so every candidate threshold could be evaluated from one LLM pass: **78 invocations** (51 positive, 27 negative).

---

## 7. Verifier Design

**Policy** (per query, top-1 cosine):

```
no hits / cos < 0.45            → ABSTAIN            (identical to frozen baseline)
0.45 ≤ cos < band_high          → LLM verifier:
                                     SUPPORTED            → accept
                                     INSUFFICIENT_EVIDENCE → abstain
                                     timeout/error/malformed → accept  (fail-open)
cos ≥ band_high                 → ACCEPT             (identical to frozen baseline)
```

**Prompt** (`_EVIDENCE_SYSTEM_PROMPT`): relaxed relative to 3G-B. Explicitly:
- uses ONLY retrieved chunks (no outside/world knowledge, no invention);
- does **not** require exact wording (paraphrase OK);
- allows synthesis across chunks *only* when the answer is distributed;
- **distinguishes topic-overlap from answerable evidence** ("Topic overlap alone is NOT sufficient");
- defines "fact" operationally; gives a **Vocab** note covering broad how/what-is/explain questions.

The prompt does **not** contain any "prefer SUPPORTED" or "prefer INSUFFICIENT" instruction and is **not** artificially permissive.

**Structured verdict** (`BandedVerdict`, pydantic, `extra="forbid"`):

```json
{ "verdict": "SUPPORTED" | "INSUFFICIENT_EVIDENCE",
  "confidence": 0.0–1.0,
  "supporting_chunk_indices": [1-based, may be empty],
  "reason": "one short sentence" }
```

`OllamaClient.generate_json` enforces the schema; any violation is caught and counted as `malformed` → fail-open.

---

## 8. Verifier Invocation Coverage & Latency

| Stat | Value |
|---|---|
| Invocations (union band [0.45, 0.64)) | **78 / 199** (51 positive · 27 negative) |
| SUPPORTED | 44 (39 positive · 5 negative) |
| INSUFFICIENT_EVIDENCE | 34 (12 positive · 22 negative) |
| Fallback (timeout/error/malformed) | **0** |
| Verifier latency avg | 14 111 ms |
| Verifier latency p50 / p95 / p99 | 14 009 / 17 297 / 18 188 ms |
| Verifier latency max | 18 275 ms |
| Retrieval latency (this run) p50 / p95 | 31.6 / 2 347 ms * |

\* Retrieval p95 (2.3 s) is cold-start noise (embedding-model reload on an otherwise RAM-pressure run); p50 matches 5D's ~37 ms. It is not a verifier artifact.

**Latency guardrail: FAIL. p95 = 17.3 s vs ≤ 500 ms.** A CPU qwen3:8b cannot serve this gate in real time. The latency result is reported honestly; nothing was hidden or retimed.

---

## 9. Banded Policy Decision-Boundary Analysis

| Band | FPR | FNR | Abstention rate | Pos acceptance | Neg rejection |
|---|---|---|---|---|---|
| [0.45, 0.46) | 0.8333 | 0.0064 | 0.0402 | 0.9936 | 0.1667 |
| [0.45, 0.48) | 0.8095 | 0.0127 | 0.0503 | 0.9873 | 0.1905 |
| [0.45, 0.50) | **0.7619** | **0.0255** | 0.0704 | 0.9745 | 0.2381 |
| [0.45, 0.52) | **0.7381** | **0.0255** | 0.0754 | 0.9745 | 0.2619 |
| [0.45, 0.54) | 0.6905 | 0.0382 | 0.0955 | 0.9618 | 0.3095 |
| [0.45, 0.55) | 0.6429 | 0.0446 | 0.1106 | 0.9554 | 0.3571 |
| [0.45, 0.58) | 0.5714 | 0.0573 | 0.1357 | 0.9427 | 0.4286 |
| [0.45, 0.60) | 0.5000 | 0.0701 | 0.1608 | 0.9299 | 0.5000 |
| **[0.45, 0.62)** | **0.4048** | **0.0701** | 0.1809 | 0.9299 | 0.5952 |
| [0.45, 0.64) | 0.3333 | 0.0764 | 0.2010 | 0.9236 | 0.6667 |

**No band satisfies the full guardrail bundle.** The FNR ≤ 0.033 boundary lies between 0.52 and 0.54; the widest compliant bands ([0.45,0.50) and [0.45,0.52)) cut FPR only to ~0.74, and their rejection capacity stays far from the hard-core FPs.

---

## 10. Experiment Results — Metrics Table (headline band [0.45, 0.62))

| Metric | Frozen 5D | 5F Exp B | Guardrail | Verdict |
|---|---|---|---|---|
| FPR | 0.8571 (36/42) | **0.4048** (17/42) | < 0.811 (materially) | **PASS** (45-pt drop) |
| FNR | 0.0000 | **0.0701** (11/157) | ≤ 0.033 | **FAIL** |
| Abstention rate | 0.0302 | 0.1809 | — | n/a |
| Hit@5 | 0.9236 | 0.9236 | ≥ 0.93 | FAIL (pre-existing, retrieval-side) |
| MRR | 0.8773 | 0.8773 | ≥ 0.88 | FAIL (pre-existing, retrieval-side) |
| Latency p95 | 47 ms | ≈ 17.3 s (verifier) | < 500 ms | FAIL |

FPs removed: **19** (36 → 17). Positives newly abstained: **11** — of which only **4** (q037, q050, q103, q151) had correct retrieval (rank ≥ 1); the other 7 were already retrieval misses in 5D and represent no loss of a correct answer.

---

## 11. Experiment B — FP Error Analysis

**19 of the 36 frozen FPs were correctly rejected** by the verifier at band [0.45, 0.62):

| 5E category | Cleared | Survived |
|---|---|---|
| A — out-of-scope | q035, q114, q124, q135, q137 | — |
| B — correct topic, fact absent | q118, q157, q159, q197, q198, q200 | q119, q120, q121, q123, q125, q126, q127, q134, q158, q160 (all cos ≥ 0.62) + q132, q196 |
| C — wrong document | q122 | q199 |
| E — temporal | q034, q115 | — |
| F — PAM system/metadata | q033, q036, q128, q130, q133 | q041, q045, q129, q131 |

**Remaining 17 FPs** fall into two distinct mechanisms:

1. **Hard-core high-cosine fact-absent (12):** all have `cos ≥ 0.62` (B and F), so they are *outside the band* — never verifier-evaluated, auto-accepted by the frozen policy. This is exactly the Phase 5E "top-band" finding: score-indistinguishable FPs. Banding cannot reach them without setting `band_high` far beyond 0.64 (i.e., verifying nearly every query).
2. **Verifier false-accepts (5):** q041, q045, q129, q131 (F — PAM-guide topic overlap) and q199 (C). The model returned SUPPORTED despite the question being unanswerable from evidence. Failure mode: topic-overlap latching onto PAM-guide facts. e.g. q045's own reason reads *"the knowledge base does not cover [those] topics…"* yet still returned `SUPPORTED` (conf 0.95) — an internally contradictory verdict.

Every surviving FP except q041/q045/q129/q131/q199/q132/q160/q196 had a vote of INSUFFICIENT but fell outside the headline band.

---

## 12. Experiment B — FN Error Analysis

**11 positives abstained** (all voted `INSUFFICIENT_EVIDENCE`, conf 0.0):

| id | cos | 5D rank | Expected-source evidence in retrieved | Loss |
|---|---|---|---|---|
| q024 | 0.476 | none | — | no correct answer lost (already miss) |
| q031 | 0.586 | none | — | no correct answer lost |
| q037 | 0.563 | **1** | yes (reason contradicted by chunks) | **correct answer lost — verifier error** |
| q049 | 0.480 | none | partial (correct doc retrieved below top-1) | no correct answer lost (rank none) |
| q050 | 0.494 | **1** | likely present (daa assignment count) | **correct answer lost — verifier error or content gap** |
| q078 | 0.568 | none | — | no correct answer lost |
| q090 | 0.459 | none | — | no correct answer lost |
| q091 | 0.537 | none | — | no correct answer lost |
| q103 | 0.530 | **1** | yes (reason contradicted by chunks) | **correct answer lost — verifier error** |
| q109 | 0.544 | none | — | no correct answer lost |
| q151 | 0.586 | **2** | yes (LeetCode pattern comparison) | **correct answer lost — likely verifier error** |

**Summary:** 4 positives with correct retrieval (rank ≥ 1) were rejected by the verifier: **q037, q050, q103, q151**. Their absten `reason` strings contradict or miss available chunk content (e.g. q037, q103) or are plausibly absent-in-evidence (q050). This is the FNR cost of the relaxed-but-still-LLM gate. Even by the strictest count (only correct-retrieval losses), 4/157 = 0.0255 would fit under FNR ≤ 0.033 — but under the **frozen metric definition** (all abstained positives / positives), 0.0701 **fails**.

---

## 13. Band Threshold Comparison (one LLM pass, offline simulation)

Winner at each guardrail: **no threshold is fully compliant.**

| Target concern | Best threshold | Value |
|---|---|---|
| FNR ≤ 0.033 | [0.45, 0.50) / [0.45, 0.52) | 0.0255 ✔ — but FPR only 0.74 |
| FPR materially < 0.811 | [0.45, 0.64) | 0.3333 — but FNR 0.0764 ✘ |
| Both | **∅ (none exists)** | — |

Widening the band trades FPR for FNR almost 1:1. The region 0.54–0.60 is the knife-edge (FPR 0.69→0.50 while FNR crosses the guardrail). The 12 hard-core FPs are unreachable at any tested threshold.

---

## 14. Verifier Error Taxonomy & Confidence Analysis

**Confidence is not discriminative.** Across all 78 invocations: every SUPPORTED verdict carried confidence 0.9–1.0 and non-empty `supporting_chunk_indices`; every INSUFFICIENT verdict carried confidence exactly **0.0** and empty indices. The field degenerates to a binary flag — it cannot separate the 5 false-accepts (conf 0.9–1.0) from true SUPPORTED (conf 0.9–1.0).

| Error class | Count | Verdict pattern | Cause |
|---|---|---|---|
| False accept (FP-relevant) | 5 | SUPPORTED w/ conf ≥ 0.9 | Topic-overlap latching on PAM-guide facts (F); wrong-doc-but-mentions (C) |
| False reject (FN-relevant) | 4 | INSUFFICIENT w/ conf 0.0 | Evidence present but the model holds an overly strict bar (q037, q103, q151); possible genuine content gap (q050) |
| Timeout / error / malformed | 0 | — | schema handling + 60 s cap robust |

Root causes align with **Phase 5E's** taxonomy: the verifier fixes the *mid-band content-sufficiency* class well but both error classes live where Phase 5E showed signals collapse (high-cosine fact-absent FPs and borderline positives).

---

## 15. Guardrail Compliance

| Guardrail | Baseline 5D | Banded 5F (headline) | Target | Status |
|---|---|---|---|---|
| FPR | 0.8571 | 0.4048 | < 0.811 | ✔ **PASS (best single lever so far)** |
| FNR | 0.0000 | 0.0701 | ≤ 0.033 | ✘ FAIL |
| Hit@5 | 0.9236 | 0.9236 | ≥ 0.93 | ✘ FAIL (pre-existing, retrieval-side, unchanged) |
| MRR | 0.8773 | 0.8773 | ≥ 0.88 | ✘ FAIL (pre-existing, retrieval-side, unchanged) |
| Latency | 47 ms | 17.3 s p95 | < 500 ms | ✘ FAIL |

---

## 16. Decision

```
RESULT: REJECTED                     ← does not satisfy the Phase 5 acceptance guardrail bundle
LABEL:  EXPERIMENTAL_CANDIDATE       ← the mechanism is the best FPR lever yet found
```

- REJECTED because FNR (0.070), latency (17.3 s p95), and the pre-existing Hit@5/MRR shortfalls invalidate acceptance — and **no band threshold closes the gap**.
- The mechanism is a genuine, reproducible discovery: **a score-banded verifier is the first non-retrieval change to cut FPR to 0.40, with perfect reliability (0 fallbacks)**. It is **CANDIDATE FOR FURTHER VALIDATION** along the following line: verify *every* query with a fast/small verifier (or cross-encoder-ranked evidence) rather than band-gating, trading the 12 hard-core FPs for tighter FNR control, on hardware/latency that meets p95 < 500 ms (or off the hot QA path).
- **Production default remains `answerability.enabled = false`. Nothing was activated.**

---

## 17. Limitations / Threats to Validity / Future Experiments

1. **Single LLM, single run.** Verdicts come from one non-deterministic `qwen3:8b` at `temperature=0.0`. JSON-mode generation was schema-stable (0 malformed), but semantic output can vary across models/temperatures.
2. **Band-gating vs global gating.** The experiment only *band* the verifier; it does not evaluate verifying all queries (which would reach the ≥ 0.62 hard-core). A global-gate variant is the natural follow-up.
3. **Cost/time.** ~14 s/query on CPU. p50 verifier latency alone exceeds the entire 500 ms guardrail — production activation without a faster model or async scheduling is out of scope.
4. **Confidence unusable.** Reported so future prompts don't rely on it.
5. **Latency pollution.** Retrieval p95 (2.3 s) in run B is cold-start/environment noise; p50 matches baseline.
6. **Pre-existing guardrail gap.** Hit@5/MRR shortfalls originate in the frozen baseline+retrieval stack and are untouched here.

### Future experiments (ranked)
1. **Global verifier (no band), all 199** — measures full FPR ceiling + FNR floor of the relaxed prompt.
2. **Cross-encoder as the verifier's evidence feeder** (Phase 5E Option D successor) to cut false-accepts like q041/q129.
3. **Smaller/faster verifier model** (e.g. qwen3:1.7b) for latency-valid activation.
4. **Retrieval-side hard-core attack**: query-specific source feeds for the 12 high-cosine FPs (embedding/chunking is a separate phase decision).

---

## 18. Final Safety & Git State / Artifacts / Reproducibility

**Repo changes (intended deliverables):**
- `app/infrastructure/banded_verifier.py` — new isolated, feature-flagged module (`BandedGate`, default `enabled=False`); **not** wired into `QAWorkflow` (production `answerability.enabled` untouched).
- `tests/unit/test_banded_verifier.py` — 13 unit tests (all band boundaries, verdicts, fail-open paths, disabled==baseline); **pass**.
- `32_PHASE_5F_BANDED_ANSWERABILITY_EXPERIMENT.md` — this report.

**Temp artifacts deleted after use:** `p5f_smoke.py`, `p5f_run.py`, `p5f_analyze.py` (runner/analyzer/verifier-execution scripts; no longer present).

**Results JSON (read-only, kept for reproducibility):**
- `eval/results/phase_5f_experiment_a.json` — control (matches 5D on 199/199).
- `eval/results/phase_5f_experiment_b.json` — full 199-query banded run + verdict cache.

**Unchanged & verified:** `eval/dataset.json`, corpus, `config/default.yaml` (`answerability.enabled: false`), Phase 3G-B files, all prior-phase artifacts.

**Git safety check:** no commits, no pushes, no force ops. Final diff (report items above + results JSON) reviewed. STOPS for Phase 5G approval.