# 46_PHASE_5E_FINAL_AUDIT.md

## 1. Objective

Audit the completed Phase 5E (FPR Root-Cause and Signal Analysis), Phase 5F (Banded Answerability Verifier Experiment), and Phase 5G (V1 Retrieval Journey Decision) to verify that:

- Phase 5E findings are substantiated by the evaluation artifacts.
- Phase 5F actually evaluated the recommended mechanism.
- Phase 5G formally froze retrieval V1.
- No reimplementation of Phase 5E/5F/5G is required.

This is a **read-only verification** — no code changes, no commits, no pushes.

---

## 2. Current Git State

| Item | Value |
|------|-------|
| HEAD | `9f282b41b6c558b0dbea857c95e24beb3ff63f9a` |
| Branch | `main` |
| Working tree | 38 modified files (cumulative 6A–6H + pre-existing), 40+ untracked (reports, eval artifacts, vault) |
| Staged | 23 files (Phase 6A–6H cumulative application commit prepared separately) |
| Retrieval files | `embeddings.py`, `search.py`, `bm25.py`, `reranker.py`, `semantic_chunking.py` — **no diff vs HEAD** |
| `eval/dataset.json` | Modified on disk (pre-existing, v3.0 frozen) — **not a Phase 5E/5F/5G change** |
| `eval/results/` | Contains `phase_5d_frozen_baseline.json`, `phase_5f_experiment_a.json`, `phase_5f_experiment_b.json` — read-only experiment outputs |
| `app/infrastructure/banded_verifier.py` | Exists (Phase 5F isolated module, default `enabled=False`) |
| `tests/unit/test_banded_verifier.py` | 13 tests — **all pass** |

**Git Safety:** Verified — no Phase 5E/5F/5G reimplementation staged or committed.

---

## 3. Phase 5E Evidence — VERIFIED

### 3.1 36 FPs Profiled — VERIFIED
Report 31 §4.1 lists all 36 accepted negatives (q033–q200 excluding 6 correctly rejected). Count confirmed: **36 FPs**.

### 3.2 31/36 FPs = Content-Sufficiency Misses — VERIFIED
Report 31 §6 table: Category B (16) + F (11) + C (2) + E (2) = **31**. Category A (5 accepted) are the only ones caught by cosine < 0.45.

### 3.3 Retrieval Signals Did Not Provide Safe Separator — VERIFIED
Report 31 §5: 13 candidate signals measured (cosine, BM25, RRF, gap, spread, diversity, concentration, lexical overlap, chunk length, query length, retrieved count, BM25 presence, source type). **Only cosine showed partial separation**; all others have TP/FP distributions overlapping to near-identity. Report 31 §11: Options B (heuristic evidence score), C (metadata filtering), E (cross-encoder) all **REJECTED** for lack of measured separation.

### 3.4 Cosine Threshold Tuning Could Not Satisfy All Guardrails — VERIFIED
Report 31 §8 sweep (0.45 → 0.65): No threshold meets FNR ≤ 0.033, Hit@5 ≥ 0.93, MRR ≥ 0.88, FPR materially < 0.811 simultaneously. Best FNR-compliant (t=0.49) leaves FPR 0.762 (marginal). Floor FPR ≈ 0.21 at FNR ≈ 0.37 (t=0.65). **REJECTED** in §11/§17.

### 3.5 PAM Learning Guide / GPU Report Interference Understood — VERIFIED
Report 31 §7: PAM guide is top-1 for 14 FPs (39%) AND 11 TPs, and demotes 10 other TPs. GPU report: 1 FP, 3 TP demotions. Both docs are legitimate (Phase 5C validated). **Doc removal rejected** — would still leave FPR ≈ 0.50 and lose 15 legit positives (§7.3).

### 3.6 Answerability Proposed as Different-Axis Mechanism — VERIFIED
Report 31 §9 (retrospective on 3G-B): FPR 0.857 → 0.243 (−70%) on older corpus; FNR 0.098. Mapped to frozen 199: B+F+C+E = 31/36 FPs are verifier targets. §11 Option D: expected FPR −0.85 → ≤ 0.15 plausible. **RECOMMENDED for Phase 5F** as scoped, re-calibrated, evaluation-only prototype.

---

## 4. FP Taxonomy — VERIFIED

| Cat | Name | Count | FP | Rejected | Mechanism |
|-----|------|-------|-----|----------|-----------|
| A | Out of corpus scope | 11 | 5 | 6 | cos < 0.45 (caught) |
| B | Correct topic, fact absent | 16 | **16** | 0 | Content-sufficiency |
| C | Related topic, wrong doc | 2 | **2** | 0 | Content-sufficiency |
| E | Temporal/current absent | 2 | **2** | 0 | Content-sufficiency |
| F | Meta/system (PAM/KB) | 11 | **11** | 0 | Content-sufficiency |
| **Total** | | **42** | **36** | **6** | |

**VERIFIED:** 31/36 FPs (B+F+C+E) are content-sufficiency misses. All 6 correctly rejected are Category A. Category B+F = 27/36 (75%).

---

## 5. Signal-Separation Findings — VERIFIED

| Signal | TP p25/med/p90 | FP p25/med/p90 | Separable? |
|--------|----------------|----------------|------------|
| top cosine | 0.610 / 0.676 / 0.761 | 0.549 / 0.598 / 0.699 | **Partial** — 12 FPs ≥ 0.62 (above TP p25) |
| top BM25 | 0.0 / 0.0 / 6.80 | 0.0 / 0.0 / 5.27 | **REJECTED** |
| top RRF | .0320 / .0325 / .0328 | .0308 / .0323 / .0328 | **REJECTED** (saturated) |
| cos gap | 0.010 / 0.033 / 0.102 | −0.004 / 0.026 / 0.076 | **REJECTED** (weak) |
| cos std top-5 | 0.024 / 0.042 / 0.092 | 0.024 / 0.035 / 0.080 | **REJECTED** |
| source diversity | 1 / 2 / 4 | 1 / 2 / 4 | **REJECTED** (identical) |
| top-source concentration | 2 / 4 / 5 | 2 / 4 / 5 | **REJECTED** (identical) |
| lexical overlap | 0.43 / 0.56 / 0.82 | 0.38 / 0.55 / 0.71 | **REJECTED** |
| chunk length | 693 / 1268 / 1980 | 1062 / 1585 / 1980 | **REJECTED** (FP longer — wrong direction) |

**VERIFIED:** Only cosine carries partial separation; 12 FPs ≥ 0.62 are score-indistinguishable from TPs. All other 12 signals **REJECTED** as standalone or combinational separators.

---

## 6. Threshold Findings — VERIFIED

| t | Hit@1 | Hit@5 | MRR | FPR | FNR | Verdict |
|---|-------|-------|-----|-----|-----|---------|
| 0.45 | 0.841 | 0.924 | 0.877 | 0.857 | 0.000 | Baseline |
| 0.49 | 0.828 | 0.911 | 0.865 | 0.762 | **0.032** | FNR-compliant but FPR 0.762 (fail) |
| 0.51 | 0.815 | 0.892 | 0.850 | 0.738 | 0.051 | FNR fails |
| 0.65 | 0.612 | 0.631 | 0.621 | 0.214 | 0.369 | FNR explodes |

**VERIFIED:** No threshold satisfies all guardrails. FNR-compliant region (t ≤ 0.49) leaves FPR ≥ 0.76. Floor FPR ≈ 0.21 at FNR ≈ 0.37.

---

## 7. Phase 5F Verification — VERIFIED

### 7.1 Banded Answerability Actually Evaluated — VERIFIED
- Module: `app/infrastructure/banded_verifier.py` (isolated, feature-flagged, `enabled=False` default)
- Tests: `tests/unit/test_banded_verifier.py` — **13 tests PASS**
- Experiment A (control): 199/199 queries identical to Phase 5D baseline — **VERIFIED**
- Experiment B: 78 verifier invocations on union band [0.45, 0.64) — **completed**

### 7.2 FPR Improved Substantially — VERIFIED
- Headline band [0.45, 0.62): FPR **0.857 → 0.405** (45-point drop, 19/36 FPs rejected)
- FPs removed: 19 (all Categories A, B, C, E, some F)
- Survivors: 12 hard-core ≥ 0.62 (auto-accept outside band) + 5 verifier false-accepts (F/C)

### 7.3 FNR Exceeded Guardrail — VERIFIED
- Headline band: FNR **0.000 → 0.070** (11 positives abstained)
- Guardrail ≤ 0.033 — **VIOLATED** (0.070 > 0.033)
- 4 correct-retrieval positives lost (q037, q050, q103, q151)

### 7.4 Latency Exceeded Guardrail — VERIFIED
- Verifier p95: **17.3 s** (guardrail ≤ 500 ms — **violated by ~34×**)
- CPU qwen3:8b cannot serve in real time

### 7.5 Rejected as Production Candidate — VERIFIED
Report 32 §16: **RESULT: REJECTED** (FNR fail, latency fail, Hit@5/MRR pre-existing fail, no band closes gap). Labeled **CANDIDATE FOR FURTHER VALIDATION** — mechanism signal strong (45-pt FPR drop, 0 fallbacks).

---

## 8. Phase 5G Verification — VERIFIED

### 8.1 Retrieval V1 Formally Frozen — VERIFIED
Report 33 §11: Decision **C — Freeze retrieval V1; move to application layer.**
- No variant of "continue retrieval optimization" or "one justified experiment" survives §8/§9.
- Strict rule: zero candidates pass (relaxed prompt re-sweep, reranker, query classifier, hybrid, corpus expansion all fail).

### 8.2 No Additional Retrieval Optimization Without New Evidence — VERIFIED
Report 33 §13: Reopening conditions require:
- New embedding/ranking model with specific falsifiable hypothesis for Hit@5/MRR (not FPR)
- New evidence source/negative class
- V1.1 answering-layer verdict that still cannot meet bundle

### 8.3 All-Guardrails-Green Remains V1.1 Criterion — VERIFIED
Report 33 §10: V1 completion ≠ all-guardrails-green. Guardrails **untouched and re-stated as V1.1 acceptance gate**, NOT renegotiated. V1 retrieval is "finished" — frozen, measured, decision-recorded.

---

## 9. Guardrail Comparison — VERIFIED

| Guardrail | Frozen Baseline | 5F Best (band [0.45,0.62)) | Status |
|-----------|-----------------|----------------------------|--------|
| FPR < 0.811 (materially) | 0.857 ❌ | 0.405 ✅ | **5F PASS** |
| FNR ≤ 0.033 | 0.000 ✅ | 0.070 ❌ | **5F FAIL** |
| Hit@5 ≥ 0.93 | 0.924 ❌ | 0.924 ❌ | **Pre-existing FAIL** (retrieval-side) |
| MRR ≥ 0.88 | 0.877 ❌ | 0.877 ❌ | **Pre-existing FAIL** (retrieval-side) |
| Latency p95 < 500 ms | 47 ms ✅ | 17.3 s ❌ | **5F FAIL** |

**VERIFIED:** 5F mechanism reduces FPR but cannot satisfy the bundle. Two guardrails (Hit@5, MRR) are already red at frozen baseline — retrieval-side, untouched by verifier.

---

## 10. Retrieval Freeze Status — VERIFIED

| Component | Status |
|-----------|--------|
| `app/infrastructure/embeddings.py` | **NO DIFF** (frozen) |
| `app/infrastructure/search.py` | **NO DIFF** (frozen) |
| `app/infrastructure/bm25.py` | **NO DIFF** (frozen) |
| `app/infrastructure/reranker.py` | **NO DIFF** (frozen) |
| `app/infrastructure/semantic_chunking.py` | **NO DIFF** (frozen) |
| `app/infrastructure/vector_store.py` | **6H CHANGE ONLY** (`remove_by_source` — application-layer, not retrieval algorithm) |
| `eval/dataset.json` | Pre-existing v3.0 — **untouched by 5E/5F/5G** |
| `config/default.yaml` | `reranker/hyde/answerability` all `false` — **frozen** |

**VERIFIED:** Core retrieval algorithm files unchanged. Only `vector_store.py` has a Phase 6H application-layer addition (`remove_by_source`), which is source-scoped deletion, not retrieval behavior.

---

## 11. Open Issues — DOCUMENTED

| Issue | Status | Notes |
|-------|--------|-------|
| Production min_cosine = 0.25 vs frozen eval 0.45 | **INCONCLUSIVE** | Production `AbstentionGate` default is 0.25 (hardcoded in `qa_workflow.py:430`); 0.45 is evaluation harness value. Not a Phase 5E issue — documented in Phase 6H audit. |
| Hit@5 / MRR below guardrail at frozen baseline | **DEFERRED** | Retrieval-side gap (12 misses, 13 wrong-rank). Phase 5G §4: "ranking quality" is contributing but secondary. Requires new specific hypothesis + new model/data to reopen. |
| Verifier FNR/latency for answering layer | **DEFERRED** | Phase 5F mechanism is CANDIDATE FOR FURTHER VALIDATION. Hand-carried to application layer (Phase 6+) with fail-open, scoped bands, small models, numeric FNR gate. |
| Corpus cert-sibling discrimination (q193) | **DEFERRED** | Doc-quality backlog, not retrieval. |

---

## 12. Final Decision

### Does Phase 5E Need to Be Repeated?

**NO — Phase 5E is complete.**

**Evidence:**
1. **Phase 5E** performed exhaustive root-cause analysis: profiled all 36 FPs, taxonomized 6 categories, measured 13 retrieval signals, swept cosine thresholds 0.45→0.65, analyzed doc interference, and retrospectively evaluated 3G-B answerability.
2. **Phase 5F** implemented and evaluated the **exact mechanism recommended by Phase 5E** (Option D: banded, re-calibrated answerability verifier) against the frozen 199-query dataset.
3. **Phase 5F results** confirmed the mechanism is the strongest FPR lever found (−45 pts) but **cannot satisfy the guardrail bundle** (FNR 0.070 > 0.033, latency 17.3 s > 500 ms, no band closes the gap).
4. **Phase 5G** formally reviewed the complete journey, applied a strict experiment-justification rule, and **decided: C — Freeze retrieval V1; move to application layer.**
5. **No retrieval-side experiment remains justified** under the strict rule (§9 of Phase 5G). The failure mode is an answering-layer content-sufficiency problem (31/36 FPs), not a retrieval ranking problem.

**Phase 5E does not need to be repeated.** Its findings are confirmed, its recommended mechanism was tested in Phase 5F, and Phase 5G formally closed the retrieval V1 chapter.

---

## Appendix: Verification Commands Run

```bash
# Config flags
python -c "from app.core.config import load_settings; s=load_settings(); print(s.reranker.enabled, s.hyde.enabled, s.answerability.enabled, s.qa.timeout_seconds)"
# → False False False 120

# Frozen retrieval diffs
git diff HEAD -- app/infrastructure/embeddings.py app/infrastructure/search.py app/infrastructure/bm25.py app/infrastructure/reranker.py app/infrastructure/semantic_chunking.py
# → only vector_store.py has 6H change (remove_by_source)

# Phase 5F artifacts exist
ls eval/results/phase_5f_experiment_a.json eval/results/phase_5f_experiment_b.json app/infrastructure/banded_verifier.py tests/unit/test_banded_verifier.py
# → all present

# Banded verifier tests
pytest tests/unit/test_banded_verifier.py -q
# → 13 passed

# Full unit suite (excl. stale eval)
pytest tests/unit -p no:cacheprovider --ignore=tests/unit/test_eval_dataset.py -q
# → 1558 passed, 1 deselected

# Eval dataset stale failures (unchanged)
pytest tests/unit/test_eval_dataset.py -q
# → 7 failed, 24 passed (v2.0 assertions vs frozen v3.0)
```

---

**AUDIT COMPLETE — NO ACTION REQUIRED.**

Phase 5E is verified complete. Phase 5F evaluated its recommendation. Phase 5G formally froze retrieval V1. The application layer (Phases 6A–6H) now carries the addressable value (answering-layer evidence verification, citation UX, system-facts handling, narrow ranking gap).

**STOP — no further verification needed.**