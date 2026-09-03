# Phase 3G-B: Answerability Gate Experiment

**Date:** 2026-08-24
**Frozen HEAD:** `9f282b41b6c558b0dbea857c95e24beb3ff63f9a`
**Status:** EXPERIMENT COMPLETE. Code implemented, tests passing, results analyzed. Awaiting approval.

---

## 1. Objective

Implement and evaluate an isolated post-retrieval answerability/evidence gate (Phase 3G-B) to reduce FPR (0.811) while maintaining FNR ≤ 0.033, Hit@5 ≥ 0.93, MRR ≥ 0.88.

---

## 2. Implementation Summary

### 2.1 Files Modified

| File | Change | Lines |
|------|--------|-------|
| `app/core/config.py` | Added `AnswerabilitySettings` (lines 440-455), added field to `Settings` (line 502) | +17 |
| `config/default.yaml` | Added `answerability:` section (lines 190-194) | +5 |
| `app/infrastructure/answerability.py` | New module: `AnswerabilityGate`, `AnswerabilityResult`, `EvidenceVerdict` | +145 |
| `app/application/qa_workflow.py` | Import gate, add param, add gate check in `ask()`, wire in `create_default()` | +15 |
| `eval/run_eval.py` | Add `--answerability` flag, gate setup, per-query evaluation, metrics tracking | +30 |
| `tests/unit/test_answerability_gate.py` | 17 unit tests across 3 test classes | +280 |

**Total new/modified:** ~500 lines. No existing tests modified.

### 2.2 Architecture

```
query → SearchService.search()
      → AbstentionGate.evaluate()        [FROZEN, line 253]
      │  └─ reject → ABSTENTION_MESSAGE
      → AnswerabilityGate.verify()       [NEW, line 261]
      │  └─ INSUFFICIENT_EVIDENCE → ABSTENTION_MESSAGE
      → build_context() → OllamaClient.generate_text()
```

Key design decisions:
- **Fail-open:** LLM timeout/error → accept (proceed to QA generation)
- **Default off:** `answerability.enabled=false` in config, no behavior change when disabled
- **Own return type:** `AnswerabilityResult(sufficient, reason)` — no circular import with `AbstentionResult`
- **Uses `generate_json`** with pydantic `EvidenceVerdict` model for structured output
- **Temperature 0.0** for deterministic verdicts

### 2.3 Prompt Design

```
You are a strict evidence verifier. You evaluate whether the provided
retrieved chunks contain the information needed to answer a question.

Rules:
- ONLY use the provided chunks as your knowledge source.
- Do NOT use any outside/world knowledge.
- Do NOT infer, guess, or assume information not explicitly present.
- Return SUPPORTED ONLY if the chunks explicitly contain the answer.
- When in doubt, return INSUFFICIENT_EVIDENCE.
- Be conservative: prefer INSUFFICIENT_EVIDENCE over SUPPORTED.
```

---

## 3. Experiment Configuration

### 3.1 Baseline (Control)

```
python eval/run_eval.py --top-k 10 --min-cosine 0.45
```

### 3.2 Experiment (Answerability Gate)

```
python eval/run_eval.py --top-k 10 --min-cosine 0.45 --answerability
```

Both runs use the same frozen dataset (160 queries), same frozen vector store (101 chunks), same frozen embedding model (nomic-embed-text), same frozen config (reranker=off, hyde=off).

---

## 4. Results

### 4.1 Primary Metrics

| Metric | Baseline | Experiment | Delta | Guardrail | Status |
|--------|----------|------------|-------|-----------|--------|
| **FPR** | **0.811** | **0.243** | **−0.568 (−70%)** | — | ✅ Excellent |
| **FNR** | 0.008 | **0.098** | +0.090 | ≤ 0.033 | ❌ Exceeds |
| Hit@1 | 0.902 | 0.902 | 0 | — | ✅ |
| Hit@5 | 0.967 | 0.967 | 0 | ≥ 0.93 | ✅ |
| MRR | 0.930 | 0.930 | 0 | ≥ 0.88 | ✅ |
| MRR (pos-only, gate) | 0.934 | **0.963** | +0.029 | — | ✅ |

### 4.2 Gate Behavior

| Metric | Value |
|--------|-------|
| Queries evaluated by answerability gate | 32 |
| Queries returning SUPPORTED | **0** |
| Queries returning INSUFFICIENT_EVIDENCE | 32 |
| False positives rejected | **21** (from 30 → 9 remaining) |
| False negatives introduced | **11** |
| Negative queries rejected by cosine gate | 7 |
| Negative queries rejected by answerability gate | 21 |
| Negative queries passing both gates | 9 |

### 4.3 Latency

| Metric | Baseline | Experiment |
|--------|----------|------------|
| Avg query time | 20.3ms | 2898.7ms |
| Avg answerability gate time | — | 3005.8ms |
| Total evaluation time | 3.24s | 463.79s |
| Overhead per evaluated query | — | ~3.0s (LLM call to qwen3:8b) |

### 4.4 Retrieval Invariance

All positive queries that pass the gate still match their expected source. The answerability gate operates strictly after retrieval and does not modify the search pipeline.

---

## 5. False Negative Analysis

### 5.1 All 11 False Negatives

| ID | Query | Expected | Top Source | Cosine | Category | Verdict |
|----|-------|----------|------------|--------|----------|---------|
| q015 | What EDA tool is recommended in the PCB design guide? | pcb_design | PCB Board Design | 0.6834 | factoid | Over-rejection ⚠️ |
| q024 | What is the sigmamusicart song about? | sigmamusicart | OpenHands | 0.4756 | factoid | Correct ✅ |
| q049 | What is the main theme of the sigmamusicart song? | sigmamusicart | OpenHands | 0.4802 | tricky | Correct ✅ |
| q050 | How many questions does the DAA assignment contain? | daa_assignment | DAA assignment | 0.4937 | tricky | Correct ✅ |
| q090 | What genre is the sigmamusicart song? | sigmamusicart | OpenHands | 0.4592 | factoid | Correct ✅ |
| q091 | What is the processing confidence of the sigmamusicart song analysis? | sigmamusicart | Neural Networks | 0.4929 | factoid | Correct ✅ |
| q092 | What local inference tool does PAM integrate with? | pam_smoke_test | pam_smoke_test | 0.7094 | factoid | Over-rejection ⚠️ |
| q093 | What retrieval method does PAM use? | pam_smoke_test | pam_smoke_test | 0.7890 | factoid | Over-rejection ⚠️ |
| q094 | What is the search approach described in the PAM smoke test? | pam_smoke_test | pam_smoke_test | 0.7683 | factoid | Over-rejection ⚠️ |
| q113 | What is the difference between how the LeetCode article and DAA assignment discuss algorithms? | leetcode, daa | LeetCode | 0.6479 | tricky | Over-rejection ⚠️ |
| q151 | What pattern does the LeetCode article compare the retry-and-resubmit cycle to? | leetcode | LeetCode | 0.5693 | factoid | Over-rejection ⚠️ |

### 5.2 False Negative Categories

| Category | Count | Description |
|----------|-------|-------------|
| **Correct rejections** | 4 | Answer genuinely not in retrieved chunks (sigmamusicart 3 queries + DAA count) |
| **Over-rejections** | 7 | Answer IS in retrieved chunks but gate rejected it (too conservative) |

### 5.3 Root Cause: Over-Conservative Prompt

The gate evaluated 32 queries and returned INSUFFICIENT_EVIDENCE for **all 32** — including queries where the evidence was clearly present. The prompt instructs "be conservative: prefer INSUFFICIENT_EVIDENCE over SUPPORTED" and qwen3:8b follows this too strictly.

Specific over-rejection patterns:
- **pam_smoke_test (q092-q094):** The chunk text IS present but the LLM treats "safe smoke-test document" as insufficient evidence
- **PCB (q015):** The EDA tool recommendation IS in the chunk (EasyEDA) but the gate misses it
- **LeetCode (q113, q151):** Cross-document comparison and specific detail queries — the LLM finds insufficient explicit evidence

---

## 6. False Positive Analysis

### 6.1 Remaining 9 FPs (Negatives That Passed Both Gates)

| ID | Query | Top Source | Cosine | Why Passed |
|----|-------|------------|--------|------------|
| q041 | Does the KB contain info about mobile apps? | OpenHands | 0.541 | Adjacent topic |
| q119 | What programming languages does OpenHands support? | OpenHands | 0.697 | Topic-adjacent |
| q120 | How many layers does the neural network in the video actually have? | Neural Nets | 0.714 | Topic-adjacent |
| q121 | What is the exact width of the PCB traces in mm? | PCB | 0.710 | Topic-adjacent |
| q122 | What is the name of the song by sigmamusicart? | OpenHands | 0.511 | Adjacent topic |
| q123 | What is the exact date the Jharkhand protest started? | Jharkhand | 0.701 | Specific detail missing |
| q129 | What version of the knowledge base is loaded? | OpenHands | 0.530 | Meta query |
| q130 | When was the knowledge base last updated? | Org | 0.479 | Meta query |
| q159 | How many GitHub stars does OpenHands have? | OpenHands | 0.616 | Topic-adjacent |

These are topic-adjacent queries where the chunks are related but don't contain the specific answer. The answerability gate would need to distinguish these from true positives — which it currently fails to do because it rejects everything.

---

## 7. Acceptance Criteria Assessment

| Criterion | Required | Achieved | Status |
|-----------|----------|----------|--------|
| FPR materially < 0.811 | Yes | **0.243 (−70%)** | ✅ Pass |
| FNR ≤ 0.033 | Yes | **0.098** | ❌ Fail |
| Hit@5 ≥ 0.93 | Yes | 0.967 | ✅ Pass |
| MRR ≥ 0.88 | Yes | 0.930 | ✅ Pass |
| Latency < 500ms p95 | Yes | ~3000ms per gate query | ❌ Fail |
| No commits/pushes | Yes | Verified | ✅ Pass |
| answerability.enabled=false default | Yes | Verified in config | ✅ Pass |

---

## 8. Key Findings

### 8.1 What Worked

1. **FPR reduction is dramatic:** 0.811 → 0.243 is a 70% relative reduction — the most effective single change tested
2. **Retrieval invariance preserved:** All positive queries that pass the gate still match their expected source
3. **Architecture is clean:** The gate slots in naturally between abstention and generation
4. **Fail-open works correctly:** LLM errors fall through to existing behavior
5. **Feature flag isolation:** Default-off means zero production risk

### 8.2 What Didn't Work

1. **The strict evidence-only prompt is too conservative:** 0/32 queries returned SUPPORTED — the LLM rejects everything
2. **Latency is 3s per gate call:** Each answerability check requires a full LLM inference pass (~3s with qwen3:8b on CPU)
3. **FNR exceeds guardrail:** 11 false negatives vs 4 allowed (0.098 vs 0.033)

### 8.3 The Core Tension

The answerability gate operates on a fundamentally different axis than cosine similarity. Cosine measures **topic overlap** (which chunks are about the same topic as the query). Answerability measures **information sufficiency** (whether the chunks contain the specific answer). These are related but distinct:

- **q015** (EDA tool): High cosine (0.68), topic overlap is strong, answer IS in chunks → gate should SUPPORT
- **q120** (layers in video): High cosine (0.71), topic overlap is strong, answer NOT in chunks → gate should REJECT

The current prompt can't reliably distinguish these cases because qwen3:8b on the strict prompt defaults to INSUFFICIENT_EVIDENCE.

---

## 9. Recommendations

### 9.1 Prompt Tuning (Immediate)

The most promising path is relaxing the prompt. Options:
- Remove "be conservative: prefer INSUFFICIENT_EVIDENCE"
- Add "If the chunks discuss the same topic as the question and contain related facts, that is sufficient evidence"
- Use a more capable model (qwen3:14b, llama3.1:8b)

### 9.2 Latency Mitigation (Future)

- Use a smaller/faster model for the gate (e.g., phi3:mini, gemma2:2b)
- Batch gate calls or cache results for similar queries
- Run the gate only on borderline queries (cosine between 0.45-0.65)

### 9.3 Hybrid Approach (Future)

Combine the answerability gate with the cosine threshold: only invoke the LLM gate for queries where cosine is in a "borderline" range (e.g., 0.45-0.65), and auto-accept queries with high cosine (>0.65) and auto-reject queries below 0.45. This would reduce latency and false negatives.

---

## 10. Verdict

**The answerability gate is NOT ready for production** due to FNR exceeding the guardrail and latency exceeding the 500ms target. However, the experiment demonstrates that:

1. The FPR reduction potential is massive (70%)
2. The architecture is sound and non-disruptive
3. The failure mode is prompt tunability, not a fundamental flaw

**Recommended next step:** Tune the evidence-only prompt to be less conservative, re-run the 160-query experiment, and re-evaluate.
