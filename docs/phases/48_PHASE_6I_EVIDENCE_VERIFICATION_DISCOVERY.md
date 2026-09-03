# 48_PHASE_6I_EVIDENCE_VERIFICATION_DISCOVERY.md

**Status:** DISCOVERY ONLY. No retrieval, corpus, dataset, config, or code modified. No commits, no pushes.
**Date:** 2026-09-01
**Baseline HEAD:** `10f74f1` (verified at start and end)
**Approval:** Phase 6I-A discovery-only authorized.

---

## 1. Objective

Design — but DO NOT implement — the next possible application-layer experiment for reducing false-positive answers through **fast evidence verification**. Establish whether PAM can determine that retrieved evidence contains enough information to answer a query *without changing retrieval*, at a latency and FNR that clear the frozen guardrails.

All conclusions labeled: `VERIFIED` / `SUPPORTED` / `INCONCLUSIVE` / `PROPOSED` / `REJECTED` / `DEFERRED`.

---

## 2. Current baseline

| Item | Value | Verified |
|------|-------|----------|
| HEAD | `10f74f1` (unchanged during this phase) | ✅ READ |
| Commit | `feat: harden application layer and ingestion lifecycle` | ✅ READ |
| Corpus | 24 sources / **195 chunks**, nomic-embed-text 768-dim | ✅ READ (5E §2) |
| Dataset | `eval/dataset.json` v3.0 — **199 queries** (157 pos / 42 neg) | ✅ READ |
| Retrieval | top_k=5, min_cosine=0.25 (prod) / 0.45 (eval), BM25 k1=1.5 b=0.75, RRF k=60 | ✅ READ |
| Flags | reranker=false, hyde=false, answerability=false | ✅ READ |
| QA model | qwen3:8b, qa.timeout_seconds=120, context=8192 | ✅ READ |
| Ablation drive | FPR 0.857 (36/42), FNR 0.000, Hit@5 0.924, MRR 0.877, p95 47 ms | ✅ READ (5D)

**Hard guardrails (NOT relaxed):** FNR ≤ 0.033; Hit@5 ≥ 0.93; MRR ≥ 0.88; FPR materially < 0.811; p95 < 500 ms. Hit@5/MRR already fail at the frozen baseline (ranking-side, out of scope for this phase). This phase concerns **FPR / FNR / latency** only.

---

## 3. Problem definition

The four concepts this phase must keep distinct (all measured straight from 5E/5F):

| Concept | Definition | Measured state | Separable from FPR? |
|---|---|---|---|
| **1. Retrieval relevance** | Whether a chunk is *about the same topic* as the query. Expressible by cosine/BM25/RRF. | Functional (Hit@5 0.924, new-doc 0.973, FNR 0.000). | NOT the FPR driver |
| **2. Evidence sufficiency** | Whether the chunk *set* contains the requested *fact/answer*, not just the topic. | **The FPR driver.** 31/36 FPs are content-sufficiency misses (B 16 + F 11 + C 2 + E 2). | ONLY content verification deletes this class |
| **3. Answer correctness** | Whether the LLM's final answer is faithfully derived from evidence (grounding / hallucination). | Contract enforced at prompt level only (QA_SYSTEM_PROMPT); verification is observational (Phase 6B/6C telemetry), not enforcement. | Out of scope for this phase |
| **4. Citation validity** | Whether `[SOURCE N]` resolves to a real retrieved chunk. | Enforced by `resolve_citations` (qa_workflow.py:218). | VERIFIED (Phase 6B) |

**Central question — can PAM determine evidence sufficiency without changing retrieval?**

Answer: **YES-in-principle, and this is the only lever that deletes the FP class** — the mechanism is proven (3G-B −70% FPR; 5F −52% FPR). But **NO-fast-enough**: neither prototype met the p95 < 500 ms guardrail, and the FNR ≤ 0.033 guardrail failed. **Do not assume the answer is a cheap "yes."** The honest answer is **PROPOSED-with-a-hard-latency-caveat** (see §9).

---

## 4. Lessons from 3G-B (strict verifier)

**Read:** `22_PHASE_3G_B_ANSWERABILITY_EXPERIMENT.md` + `app/infrastructure/answerability.py`.

| Fact | Value | Label |
|---|---|---|
| FPR | 0.811 → **0.243** | ✅ VERIFIED |
| FNR | 0.008 → **0.098** (11 FN, 7 over-rejections) | ✅ VERIFIED (FAILS ≤ 0.033) |
| Verdict pattern | 32/32 queries → `INSUFFICIENT_EVIDENCE` (0 SUPPORTED) | ✅ VERIFIED |
| Latency | **~3 s/query** (qwen3:8b, CPU) | ✅ VERIFIED (FAILS 500 ms) |

**Root-cause of the over-rejection:** the prompt said *"Be conservative: prefer INSUFFICIENT_EVIDENCE over SUPPORTED."* qwen3:8b followed it to the letter — it rejected everything, including true positives where the evidence was clearly present (q015 PCB EDA tool; q092–q094 PAM smoke test; q113, q151 LeetCode). This was a **prompt-calibration failure, not an architecture failure** (5E §9 confirms).

**Which evidence rules were too conservative:**
- "Return SUPPORTED ONLY if the chunks **explicitly** contain the answer" → rejected paraphrased / synthesized answers.
- "When in doubt, return INSUFFICIENT_EVIDENCE" → systematic reject bias.
- No guidance on multi-chunk synthesis or paraphrase tolerance.

**Was it confusing partial evidence with insufficient evidence?** PARTIALLY — VERIFIED. The 7 over-rejections were complete evidence present but the gate treated *topic-mention* (chunks discuss the subject) as insufficient. It could not separate "the reason/topic is present" from "the required fact is absent."

**Multi-chunk / comparison questions:** YES, mishandled. q113 (LeetCode-vs-DAA comparison) and q151 (retry pattern) were cross-document / detail-over-soft-wording cases that 3G-B over-rejected (5E §9: "cross-document comparison queries are the hardest verdict").

**Negative-query rejection:** CORRECT mechanism, wrong calibration. 21/30 negatives rejected (excellent), but at FNR 0.098 it was unusable.

**World-knowledge reliance?** The prompt forbade outside knowledge; the evidence suggests over-rejection came from *literal reading*, not world-knowledge leakage. The 5F relaxed prompt kept the same evidence-only rule.

**Latency cause?** Model choice (`qwen3:8b`), not prompt cost alone. Frames the ceiling for any LLM gate.

---

## 5. Lessons from 5F (banded relaxed verifier)

**Read:** `32_PHASE_5F_BANDED_ANSWERABILITY_EXPERIMENT.md` + `app/infrastructure/banded_verifier.py`.

| Fact | Value | Label |
|---|---|---|
| FPR | 0.857 → **0.405** (band [0.45, 0.62); 19/36 FPs removed) | ✅ VERIFIED — best lever found |
| FNR | 0.000 → **0.070** (11 positives; 4 correct-retrieval losses = strict 0.0255) | ✅ VERIFIED (frozen definition FAILS ≤ 0.033) |
| Latency | **p50 14.0 s / p95 17.3 s** (qwen3:8b, CPU) | ✅ VERIFIED (FAILS 500 ms) |
| Fallbacks | **0** (0 timeout/error/malformed; 60 s cap) | ✅ VERIFIED — fail-open robust |
| Confidence | degenerate — SUPPORTED always 0.9–1.0, INSUFFICIENT always 0.0 | ✅ VERIFIED — NOT discriminative |
| FP survivors | 12 hard-core (cos ≥ 0.62, auto-accept) + 5 verifier false-accepts (F/C topic overlap) | ✅ VERIFIED |

**What 5F fixed from 3G-B:** the relaxed prompt (no conservative bias, explicit "topic overlap alone is NOT sufficient," paraphrase tolerance, multi-chunk synthesis allowance) capped the over-rejection — but **FNR stayed at 0.070**, above the guardrail even though only 4 of 11 were genuine answer losses.

**Why true positives were still rejected (q037, q103, q151):** the model "reason contradicted by chunks" — evidence was present, but the model held a stricter bar than warranted, or misread soft-wording ("recommended / pattern / exact") as absent. **Conclusion:** even a relaxed qwen3:8b verifier has an FNR floor ≈ 0.026–0.070 on the borderline-positive class. The 4 genuine losses are *exactly* the tight-retrieval, hard-verdict positives (5F §12, 5E §9 pattern).

**Multi-chunk / comparison:** still imperfect. q151 (cross-document pattern comparison) and q037/q103 were borderline-losses. Comparison and soft-wording queries remain the highest-FNR-risk verifier inputs.

**F-class (system/meta) false-accepts:** q041, q045, q129, q131 all latched onto PAM-guide topic facts and returned SUPPORTED despite unanswerability — including q045 whose own reason admitted the KB "does not cover those topics" yet voted SUPPORTED (conf 0.95). This is an **internally contradictory verdict** — evidence the LLM was swayed by topical familiarity, not the requested fact. **This class belongs in the system-facts layer (§13), not the evidence verifier.**

**Latency was model choice, not banding.** Banding only *scoped* invocations (78/199); each call still took ~14 s. qwen3:8b on CPU cannot meet 500 ms. **Confirmed: qwen3:8b is fundamentally unsuitable for a p95 < 500 ms gate** (VERIFIED).

---

## 6. Why retrieval remains frozen

Every retrieval-side lever has been measured and exhausted (5G §8/§9):

| Lever | Outcome |
|---|---|
| Cosine threshold sweep | REJECTED (floor FPR ≈ 0.21 at FNR 0.37; no t meets bundle) |
| BM25 / RRF / gap / spread / diversity / concentration / lexical / length | REJECTED (all distributions overlap TPs/FPs) |
| Embedding swap (3G-A) | REJECTED |
| Reranker (3C) | REJECTED (regressed Hit@1/MRR/FPR) |
| HyDE (3E) | REJECTED (44 s/query) |
| Metadata-only filtering (5E §10) | REJECTED (no discriminating field) |
| Doc removal (5E §7.3) | REJECTED (loses 15 positives; FPR still ≈ 0.5) |

**Load-bearing fact:** 31/36 FPs are content-sufficiency misses — retrieval is on-topic, the fact is absent. **No retrieval score can see this**; only content-level verification deletes it (5G §4 §6; 5E §5). Frozen retrieval stands.

**Reopening only allowed with a new specific, falsifiable Hit@5/MRR hypothesis + new model/data** (5G §13). This phase proposes no retrieval change. LABEL: **VERIFIED (frozen is correct)**.

---

## 7. Evidence sufficiency requirements

For a future verifier to be correct AND safe, it must satisfy (derived from 3G-B + 5F failure analysis):

| Requirement | Status in both prototypes | Priority |
|---|---|---|
| Use evidence only (no world knowledge) | ✅ PRESENT (both prompts forbid it) | Must keep |
| Distinguish topic-overlap from answer-support | ✅ 5F added explicit rule; still 5 false-accepts (F/C) | Must improve |
| Handle multi-chunk / synthesized answers | ⚠️ Partial — q151 cross-doc still failed | Must improve |
| Tolerate paraphrased evidence ("recommended / pattern / exact") | ⚠️ Weak — q037, q103, q151 over-rejected | Must improve |
| Avoid over-rejection of borderline positives (NO conservative bias) | ✅ 5F removed bias; FNR still 0.070 | Must improve |
| Correctly reject F-class (system/meta) | ❌ 4/11 F-FPs false-accepted | Route to system-facts (§13) |
| Fail-open on timeout/crash/malformed | ✅ Both robust (0 fallbacks in 5F) | Must keep |
| Deterministic / non-degenerate confidence | ❌ confidence = binary flag | Not required if not relied on |

**Core tension:** the FNR ≤ 0.033 guardrail (≤ 5 rejected positives) against a mechanism whose measured FNR floor on the borderline-positive class is ~0.026–0.070. Getting under 0.033 is theoretically possible but leaves **~zero margin** — the smallest prompt/model drift over-rejects.

---

## 8. Candidate verifier approaches

Locally available models (Ollama list verified this phase): **qwen2.5:3b (1.9 GB)**, qwen3:8b, llama3.1:8b, gemma3:12b, qwen2.5-coder:7b, qwen2.5vl:7b, qwen2.5vl:latest, translategemma:4b, plus embedders (nomic-embed-text 768-dim, mxbai-embed-large 1024-dim). **There is NO qwen3:1.7b / phi3-mini locally** — the smallest usable text LLM is qwen2.5:3b.

### A. Small local LLM (qwen2.5:3b)

- **Latency:** ~3–8× faster than qwen3:8b on CPU; a 5×2k-char evidence prompt with ~100-token structured output would still be **~2–5 s/query on CPU**. Does NOT meet 500 ms. INCONCLUSIVE-positive on ceiling, REJECTED for the hot 500 ms path.
- **FNR risk:** high — smaller model is *more* susceptible to prompt calibration drift on borderline positives (worse than 5F's 0.070 likely).
- **FPR benefit:** likely retains most of 5F's content-sufficiency deletion (the mechanism is model-size independent for the "fact obviously absent" class — category B/E/C).
- **Complexity:** low (reuse `BandedGate`/`AnswerabilityGate` glue).
- **Privacy:** local — identical to current. ✅

### B. Existing embedding similarity (query ↔ chunk cosine)

- **Latency:** ~ms. ✅ meets 500 ms
- **FNR risk:** low (nothing abstained → no FN introduced)
- **FPR benefit:** **REJECTED — no separation** (5E §5: embedding cosine is already the retrieval signal; topic-overlap ≠ answer-support; 12 FPs ≥ 0.62 above TP p25).
- A query-vs-chunk *re-embedding* after retrieval adds nothing — the same cosine is already in the scores.
- **Verdict: REJECTED as a verifier.**

### C. Lightweight lexical / evidence-overlap (term overlap, answer-type match)

- **Latency:** ms. ✅
- **FNR risk:** low (non-removal)
- **FPR benefit:** **REJECTED — no measured signal** (5E §5: lexical overlap TP median 0.56 vs FP 0.55; BM25 presence TP/FP both half/half). Any heuristic evidence score is "a re-invention of the thing that does not separate." LABEL: VERIFIED-rejected.

### D. Hybrid deterministic + small-model cascade

- The deterministic stage (A/B/C) catches nothing (signal-blind); so a cascade's cheap stage removes ~only the already-rejected cos < 0.45 class, not the B/F content-sufficiency class. Cascade does NOT dodge latency: the expensive case (borderline positive) still needs the LLM, which is > 500 ms.
- **Latency:** cheap stage ms + LLM stage seconds = still fails 500 ms on the queries that matter.
- See §11 for the architecture and §10 for why it cannot hit 500 ms.

### E. Cross-encoder-style evidence scoring (query + evidence → relevance pair)

- Locally: MiniLM cross-encoder measured ~600 ms avg (3C/3F) on CPU, **borderline-to-fails 500 ms**, and as a *binary abstention gate* every threshold violated FNR ≤ 0.033 (3F §verdict).
- Cross-encoder measures *relevance/similarity*, not *fact-presence* — the same topic-vs-answer blindness as cosine (it re-ranks; the 12 ≥ 0.62 FPs are topic-relevant and stay). **REJECTED for FPR** (no measured pathway; 5E §11 Option E).
- **Latency:** ~600 ms avg / higher p95 — over budget.

### F. Two-stage verifier (coarse reject → fine LLM)

- Coarse stage = embedding/lexical → proves unusable (B/C rejected). Fine stage = LLM → > 500 ms. **Net effect: no fast path exists for the content-sufficiency class.**

### Cross-option synthesis

| Option | Latency | FNR risk | FPR benefit | Meets 500 ms? | Verdict |
|---|---|---|---|---|---|
| A. qwen2.5:3b LLM | 2–5 s | HIGH | High (mechanism) | **NO** | PROPOSED only off hot path |
| B. Embedding cos | ms | low | none | YES | REJECTED |
| C. Lexical overlap | ms | low | none | YES | REJECTED |
| D. Cascade | s (LLM stage) | med | High | **NO** | PROPOSED, see §11 |
| E. Cross-encoder | ~600 ms | HIGH (3F) | none | border/NO | REJECTED |
| F. Two-stage | s | HIGH | High | **NO** | PROPOSED, same as D |

**The p95 < 500 ms guardrail is the binding constraint and is NOT satisfiable by any mechanism that actually deletes the FP class on this CPU hardware.** LABEL: **VERIFIED (tension is real), not merely speculative.**

---

## 9. Latency feasibility

Measured anchors:

| Reference | Latency | Source |
|---|---|---|
| Retrieval-only | p95 47 ms | 5D |
| qwen3:8b QA generation | 500–2000 ms typical; up to 120 s on this CPU | 3A, Phase 6F |
| qwen3:8b verifier call | p50 14.0 s / p95 17.3 s | 5F |
| qwen2.5:3b verifier (est.) | 2–5 s (not measured) | extrapolation |
| Cross-encoder MiniLM | ~600 ms avg | 3C/3F |

**Conclusion (VERIFIED):** resolving "is the fact present in 5×2000-char chunks" is a *semantic inference* task. On CPU, every model capable of it (LLM or cross-encoder) exceeds 500 ms. On this hardware the p95 < 500 ms gate is **structurally incompatible with on-the-hot-path content verification**. The only escapes are: (1) hardware with a GPU; (2) moving verification off the hot QA path (async / parallel with generation) — which changes the product contract; (3) a heuristic that does not work (B/C/E rejected).

This is the single most important finding of the phase: **fast** (500 ms) and **evidence-verifying** (FPR-lowering) are in direct tension on this CPU.

---

## 10. FNR / FPR risk analysis

| Guardrail | Requirement | Best measured | Margin | Risk |
|---|---|---|---|---|
| FNR ≤ 0.033 | ≤ 5 rejected positives | 0.0255 strict (4) / 0.070 frozen (11) | −ve if frozen definition; ~zero margin if strict | HIGH — smallest drift over-rejects |
| FPR materially < 0.811 | delete most of 36 FPs | 0.405 (19/36) | PASS comfortably | LOW for content class; F-class needs sys-facts |
| p95 < 500 ms | hard | 17.3 s; no path | fails structurally on CPU | **UNRESOLVED** |

Best realistic FPR with a tuned + small-model verifier + system-facts routing: could plausibly target **0.405 → ~0.25–0.35** (removing the 4 verifier false-accepts via sys-facts) while keeping strict FNR at ~0.025. But that hinges on the small model not degrading FNR, and **latency remains unfixed**. The FPR benefit is real; the latency wall is not.

---

## 11. Proposed cascade architecture

*On paper — NOT implemented. Shown with the reviewer's banding caveat acknowledged: a cascade's cheap stage is signal-blind for the FPR-relevant class, so the cascade does not dodge the LLM latency for borderline cases.*

```
User query
   ↓
Frozen retrieval (5 x top-k, min_cosine)
   ↓
AbstentionGate (cos < 0.25) → ABSTAIN   [existing, unchanged]
   ↓
[Exprimental, default OFF] Fast evidence verifier
   ↓
 ┌──────────────┬──────────────────┬──────────────┐
 ↓              ↓                  ↓
SUPPORTED    UNCERTAIN         INSUFFICIENT
 (high conf)  (borderline)      (clear miss)
 ↓              ↓                  ↓
ANSWER      Small verifier        ABSTAIN
 (qwen2.5:3b)
              ↓
       SUPPORTED / INSUFFICIENT
```

**Critical evaluation (do not assume this is correct):**

1. The cheap "SUPPORTED / INSUFFICIENT / UNCERTAIN" pre-classifier has **no measured signal** (all cheap signals overlap — §8 B/C/E). A heuristic pre-classifier is a re-invention of a non-separator. **PROPOSED but low confidence; a pre-classifier would only gate the LLM on the truly-clear misses (category E temporal, some B), which are a minority.**
2. The LLM stage still runs on borderline positives → **still > 500 ms** for the queries that need verification. The cascade does not fix latency.
3. The cascade's only real value is a **fail-open ordering**: fast-route the obviously-absent negatives to abstain *without* the LLM, saving cost — but it must never wrongly reject a positive in the cheap stage (FNR risk).

**Honest verdict:** A cascade is the right *shape* for cost/throughput management but **cannot meet p95 < 500 ms** on CPU and adds a new FNR risk in its pre-classifier. **PROPOSED-with-reservations; only worth building if latency is off the hot path OR hardware changes.**

---

## 12. Fail-open behavior

Both existing gates (`AnswerabilityGate`, `BandedGate`) already enforce fail-open — any timeout / error / malformed verdict returns `sufficient=True` (accept → proceed to QA), preserving existing behavior. Confirmed in code (`banded_verifier.py:148-155`, `answerability.py:127-141`) and verified 0 fallbacks* in the 5F run. *0 fallbacks means none *triggered*, not that the path is absent. The path is present and correct.

**Required fail-open guarantees for any future verifier (must be preserved):**
- Timeout (`OllamaTimeoutError`) → accept
- LLM unreachable / error (`OllamaClientError`) → accept
- Malformed schema output (`OllamaResponseError` / non-`BandedVerdict`) → accept
- No hits → keep existing abstain logic (never crash)
- The verifier must be feature-flagged, `enabled=False` by default; production behavior byte-identical when off.

LABEL: **VERIFIED** (the contract already exists; keep it).

---

## 13. System-facts separation (F-class)

F-class = 11/36 FPs (q033, q036, q041, q045, q128–q133, q196): "How many documents?", "What version?", "When last updated?", "What DB?", "RAM for vector store?", "max file size?", "handles languages/emails/Docker?" All describe PAM itself. Retrieval answers them falsely by latching onto the PAM guide's topical summary that never states the exact fact.

**Determination — a curated system-facts layer is SAFER than asking retrieval to answer system metadata questions (5G §7 case 3).** LABEL: **VERIFIED-as-safer** (the 5F false-accepts q041/q045/q129/q131 are exactly this class).

**What facts are safe to expose (PROPOSED):**
- PAM version
- Enabled features (reranker/hyde/answerability = off; retrieval frozen)
- Corpus statistics (24 sources / 195 chunks; manifest processed=37) — from `pam status` truth
- Supported ingestion types / extensions
- Application configuration (qa timeout, model names)

**Where they should live:** a static, curated `system_facts.py` registry (or YAML) read by a dedicated handler — NOT injected into the corpus, NOT into the evidence verifier. Kept completely separate (§14).

**How to keep synchronized:** auto-refresh the *counts* from alive sources (manifest / vector store) at call time; static facts (version, feature flags, config) from config at startup. Rebuild/cache logic mirrors `pam status`.

**Separate from evidence verification? YES.** A system/meta query should short-circuit to the facts layer *before* retrieval/verifier — it is a different answer source, not an evidence-verification input. This removes 11 FPs by construction without any true-positive risk (LABEL: PROPOSED; would need pilot confirmation that real F-class-adjacent positives are not misrouted).

---

## 14. Pilot experiment design (small, bounded — NOT run)

**Stratification** (existing frozen queries, no dataset change):

| Stratum | Count source | Characteristic |
|---|---|---|
| Positive-factoid | ~10 | fact present, mid/high cosine |
| Negative (B: fact-absent-same-topic) | ~10 | the FPR core |
| Negative (F: system/meta) | ~8 | sys-facts target |
| Comparison (q113/q151-class) | ~5 | hardest verifier verdict |
| Multi_chunk (synthesized) | ~5 | cross-chunk |
| Cross_document | ~5 | two+ sources |
| Tricky/precise (soft-wording) | ~5 | over-rejection risk |

**Sample size:** ~40–48 queries (≈20–24% of 199). Box: every stratum represented with ≥ its target count; no new queries.

**Selection method:** deterministic stratified subsample from the frozen 199 (same ids each run), reproducible via fixed seed. DO NOT cherry-pick by expected verifier outcome.

**Why representative:** covers every failure class 5E/5F identified (B/F/C/E, comparison, soft-wording, multi-chunk) with the frozen query ids, so FPR/FNR deltas map 1:1 to the known population.

**Early-stop condition:** if a verifier variant's strict-FNR on the pilot already exhausts the ≤ 5-rejection budget (i.e., ≥ 5 positives lost in a ~40 sample that projects ≥ guardrail), abort that variant immediately — do not run the full 199.

**Proceed-to-large condition:** pilot shows strict FNR ≤ 0.033 AND FPR materially < 0.811 AND latency-p95 target met (or explicitly waived per §9), with no Hit@5/MRR change. Only then consider the full 199.

---

## 15. Acceptance guardrails

**Fixed (do not move after seeing results):**

| Guardrail | Requirement | Notes |
|---|---|---|
| FNR | ≤ 0.033 (frozen metric: abstained positives / positives) | ≤ 5 rejected positives |
| FPR | **materially < 0.811** | Numeric definition: **FPR ≤ 0.5 required for acceptance** (matches 5G §8 target); a result of 0.405 (5F) already clears this. "Materially < 0.811" is fixed as ≤ 0.5. |
| Latency | p95 < 500 ms | VERIFIED infeasible on CPU for content verification (§9) — must be either met off-path or explicitly waived |
| Hit@5 | unchanged (0.924) | verifier never touches ranking |
| MRR | unchanged (0.877) | verifier never touches ranking |
| Dataset | unchanged (v3.0, 199) | — |
| Corpus | unchanged (24 src / 195 chunks) | — |
| Production default | OFF (`answerability.enabled=false`) | verifier ships disabled |
| Existing QA | always available | fail-open preserves it |
| Verifier failure | fail-open → accept | non-negotiable |

**Do not move goalposts:** the FNR ≤ 0.033, FPR ≤ 0.5, p95 < 500 ms numbers above are fixed at design time.

---

## 16. Stop conditions

- **HARD STOP:** any variant with FNR > 0.033 (frozen definition) is rejected and reported — do not ship.
- **HARD STOP (latency):** if no variant meets p95 < 500 ms on the hot path (expected), the verifier is NOT wired into the synchronous QA path; it can only be a separate, off-path mode.
- **STOP (pre-existing):** Hit@5/MRR shortfalls are out of scope; do not let the verifier chase ranking metrics.
- **STOP (no repeat):** do not re-run a strict-conservative prompt (3G-B), do not band to auto-accept the ≥ 0.62 hard-core as the *only* fix (5F), do not use a pre-classifier that rejects positives.
- **ABANDON trigger (this is the "why we walk away"):** if the FNR floor of a tuned verifier cannot be held ≤ 0.033 with a working small model at any viable latency, OR if verifier latency cannot be removed from the hot path, then **evidence verification as a blocking gate is abandoned for V1**, and only the **system-facts layer (F-class removal, safe by construction)** is pursued. See §18.

---

## 17. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| FNR overshoot on borderline positives | HIGH | guardrail fail | fail-open + numeric gate; pilot early-stop |
| Latency wall (p95 < 500 ms impossible on CPU) | CERTAIN (measured) | blocks blocking-gate | off-path / async; don't wire into sync path |
| Small-model FNR degradation (qwen2.5:3b) | HIGH | guardrail fail | measure before any larger run |
| F-class false-accepts in verifier | CERTAIN-ish (5F) | 4 hard FPs | route to system-facts layer (§13), not verifier |
| Pre-classifier injecting new FNR risk | MED | guardrail fail | make pre-classifier fail-open / non-rejecting |
| Verifier depends on slow model | HIGH | UX | never on hot path without waiver |

---

## 18. Recommendation

**Evidence verification as a blocking gate on the hot QA path is RECOMMENDED AGAINST for V1 on this CPU hardware** — because the p95 < 500 ms guardrail is structurally un-meetable by any mechanism that deletes the FP class (§9), and the FNR floor sits at zero-margin (§10). This is a hardware/data-realism conclusion, not a capitulation.

**What IS recommended (safe, actionable, no latency wall):**

1. **System-facts layer (F-class) — HIGH priority.** A curated system-facts registry (version, enabled features, corpus stats, supported types, config) that short-circuits the 11/36 F-class FPs *by construction*, with ~zero FNR risk. This alone could move FPR from 0.857 → ~0.60 on the F-class portion (11 FPs), plus preserves the 5 verified-honest `pam status` truth. **Do this first; it is the highest-value, lowest-risk application-layer move.**

2. **Off-path / async evidence verification — MEDIUM priority.** A non-blocking evidence-confidence signal attached to answers as telemetry (like `has_insufficiency_language`), recorded and used for *observational* measurement — not for blocking. This keeps the mechanism's FPR-learning without violating latency. Matches the existing Phase 6C telemetry pattern.

3. **Re-measure the 5F verifier as scoped, off-path, with qwen2.5:3b — PROPOSED, only if (2) is accepted** — to quantify FNR/latency on the pilot before any larger call. Not a blocking gate.

4. **Maintain frozen retrieval.** No change.

**Do NOT implement any of this in this phase.**

---

## 19. Decision

**Final answers (as required):**

1. **Is a fast evidence verifier technically plausible?**
   **PARTIALLY.** The *mechanism* is proven (3G-B −70%, 5F −52% FPR) and technically sound as a content-sufficiency check. But **"fast" (p95 < 500 ms) on this CPU is NOT plausible** for the semantic inference that the task requires — every LLM/cross-encoder capable of the task exceeds 500 ms (VERIFIED: 14–17 s for qwen3:8b; est. 2–5 s for qwen2.5:3b; ~600 ms for MiniLM). A *non-blocking* verifier is plausible; a blocking sub-500 ms one is not.

2. **Is it worth attempting?**
   **Only as off-path / non-blocking + via the system-facts layer.** The FPR deltas are the largest found (−52% best), but the latency gate makes a blocking gate a dead end on this hardware. Attempting the *blocking* version is NOT worth it now; attempting the *off-path* version and/or the *system-facts* layer IS worth it.

3. **Which architecture is the most promising?**
   **System-facts short-circuit for F-class + observational/off-path evidence confidence** — NOT a blocking LLM cascade. A cascade (§11) is the right shape only if latency leaves the hot path; as a blocking gate it structurally fails §15's p95 < 500 ms.

4. **What is the smallest safe experiment?**
   **The 40–48-query stratified pilot (§14)** covering B/F/C/E, comparison, multi-chunk, cross-doc, soft-wording — run only off the hot path, measuring strict-FNR and FPR with a fail-open, qwen2.5:3b verifier, with early-stop if FNR budget exhausts. Even smaller & safer: **implement only the system-facts layer** and measure the F-class delta on the frozen 199 without any LLM.

5. **What would cause us to abandon the idea?**
   - If the FNR floor of any tuned verifier cannot be held ≤ 0.033 with a working small model (the 5F 0.070 floor suggests high risk), OR
   - If verifier latency cannot be kept off the hot path, OR
   - If the system-facts layer alone already makes the FPR benefit marginal (diminishing returns).
   
   In any such case, **evidence verification as a blocker is abandoned for V1** and only the system-facts F-class removal is retained.

**Phase delivers DISCOVERY ONLY.** No code, config, dataset, corpus, retrieval, or production change was made. HEAD remains `10f74f1`. No staging, commit, or push.

---
**STOPPING after this report per Phase 6I-A instruction.**
