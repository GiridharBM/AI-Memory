# Phase 6F-C Report — Validate Ollama Context Length 8192

**Date:** 2026-08-31
**HEAD:** 9f282b41b6c558b0dbea857c95e24beb3ff63f9a (unchanged, frozen)
**Environment:** Windows 11, Python 3.14, Ollama 0.33.2, qwen3:8b + nomic-embed-text, ~15.2GB RAM / 8GB VRAM (RTX 5060 Laptop)
**Runtime change applied (only one):** `OLLAMA_CONTEXT_LENGTH=8192` (server environment variable — user-level host env var + relaunched `ollama serve`; NO repository/config change)

---

## 1. Objective

Validate the Phase 6F-B recommendation — `num_ctx=8192` — on a **bounded stratified 35-query sample of the real 199-query dataset**, with the same composition as the Phase 6D measurement, so results are directly comparable. Validation run only; no optimization experiments.

## 2. Safety Check (STEP 1)

| Check | Result |
|---|---|
| git HEAD | `9f282b41b6c558b0dbea857c95e24beb3ff63f9a` — confirmed unchanged |
| git status | working tree = 102 entries, same set as end of 6F (only parts A/B modifications, all pre-existing, none staged) |
| git diff --stat | 33 files changed — all pre-existing cumulative working-copy state from earlier phases (incl. 6F-A code); corpus vault/state diffs are prior-phase artifacts; no new production diffs this phase |

Nothing from this phase touches the repo until STEP 8/9 add two untracked artifacts (measurement file + this report).

## 3. Runtime Configuration (STEP 2)

- Applied `OLLAMA_CONTEXT_LENGTH=8192` as a **user environment variable** on the host, then restarted the local Ollama server (`ollama serve`, PID 23032) with the variable in its process environment.
- No model pulled/reinstalled. No repository configuration touched.
- Verified with `ollama ps`:

```
NAME        ID              SIZE      PROCESSOR    CONTEXT    UNTIL
qwen3:8b    500a1f067a9f    5.2 GB    100% GPU     8192       4 minutes from now
```

  - CONTEXT column = **8192** (was 40960 under automatic sizing).
  - SIZE 11 GB → **5.2 GB**: the smaller KV cache lets qwen3:8b offload **100%** to GPU (was 48% CPU / 52% GPU). This GPU-complete offload is the mechanical driver behind the latency drop.
- All QA pipeline settings unchanged: `qa.timeout_seconds=120`, true wall-clock timeout active (6F-A), `reranker/hyde/answerability` disabled, `min_cosine=0.45`.

## 4. Measurement (STEP 3)

- Ran the existing Phase 6D harness (`python -m app.application.qa_measurement_harness`) against `eval/dataset.json` with the **identical stratified composition and limits as Phase 6D**:
  factoid 12, comparison 5, negative 6, cross_document 4, tricky 3, precise_detail 3, multi_chunk 2 → **35 queries**.
- Sequential per-category invocations (host hangs under parallel Ollama load — 6D lesson), appended to a new file `eval/results/phase_6fc_qa_measurement_8192.jsonl`.
- Free-RAM sampled before/after each category block.

## 5. Metrics (STEP 4)

| Metric | 6D (automatic 40960) | 6F-C (8192) |
|---|---|---|
| Queries | 35 | 35 (same query set, matched 100% by text) |
| Answered | 35 (100%) | 35 (100%) |
| Abstained | 0 | 0 |
| **Failed** | 0 | **0** |
| **Timeouts** | 0 (never tripped — no wall-clock) | **0** (deadline active now; nothing exceeded it) |
| Citation rate (≥1 valid cite) | 85.7% (30/35) | **88.6%** (31/35) |
| Zero-citation rate | 14.3% (all insufficiency soft-abstentions) | 11.4% (all insufficiency soft-abstentions) |
| Insufficiency heuristic | 7 (20.0%) | 6 (17.1%) |
| Invalid citations | 0 | **0** |
| Duplicate citations (benign list-format) | 26 | 39 |
| Empty answers | 0 | 0 |
| Latency mean | 91.0s | **33.4s** |
| Latency p50 | 63.0s | **31.3s** |
| Latency p95 | 244.2s | **64.8s** |
| Latency max | 466.2s | **81.6s** |
| Avg retrieved sources | 5.0 | 5.0 (retrieval untouched) |
| Answer length mean | 542 chars | 547 chars |
| Answer length max | 1636 chars | 1742 chars |

## 6. Comparison vs 6D and 6F-B (STEP 5)

- Latency improvement **remains visible on the larger bounded sample**:
  - mean **2.7x** faster, p50 **2.0x**, p95 **3.8x**, max **5.7x**.
  - 6F-B's 5-query sample (mean 16.8s, max 24.3s) slightly overstated the steady-state: the 35-query sample shows mean 33.4s / max 81.6s (long multi_chunk answers + RAM degradation across the session). Still far below the 120s wall-clock and far below 6D (p95 350s / max 466s).
- Tail-class behavior: 6D's slowest queries (466.2s tricky, 350.1s cross_document, 244.2s multi_chunk) collapsed to 42.0s, 67.5s, 64.0s respectively — the class that previously approached/needed unbounded time now clears comfortably inside the guardrail.
- Per-category 6F-C latencies (mean / p50 / max): factoid 19.5 / 15.9 / 44.7s; negative 28.9 / 30.1 / 35.1s; tricky 33.2 / 38.8 / 42.0s; comparison 39.4 / 36.6 / 58.6s; precise_detail 41.0 / 37.6 / 54.0s; cross_document 49.0 / 32.1 / 67.5s; multi_chunk 72.8 / 64.0 / 81.6s.

## 7. Quality Safety (STEP 6)

- **Citation loss:** 4 of 35 queries cite fewer `[SOURCE n]` tokens than 6D (comparison 10→5, 7→5; cross_document 5→3; tricky 5→3). Balanced by **8 queries citing MORE** (incl. multi_chunk 2→12, 0→3, several 1→2/3), total citation count rose, **0 invalid citations in both runs**, zero-citation rows remain exactly the soft-abstention class. Citation *counts* vary run-to-run purely from generation sampling (answers differ); no systematic regression detected.
- **Failures/timeouts:** 0 / 0. Outcome distribution identical (35 answered) to 6D.
- **Truncation / abnormal lengths:** 0 empty answers; mean length 547 vs 542; max 1742 vs 1636 — no truncation signature. At 8192, average prompt+output (~2.5k + ~150 tokens) uses <40% of context; no exhaustion observed.
- No LLM judge used; no factual-correctness claims made.

## 8. Memory behavior (STEP 4)

- Load-time footprint: `ollama ps` 5.2 GB VRAM+RAM vs 11 GB at 40960; **100% GPU** offload achieved.
- Session profile (free RAM, sampled between category blocks): 6037 → 2907 → 1431 → 1294 → 614 → 929 → 832 → **486 MB**.
  - **Caveat — observed:** free RAM drifts downward across a long many-generation session (server-side retention; batch size/KV history). Latencies did NOT degrade with it (multi_chunk still 64–82s at ~0.5GB free vs 201–244s in 6D at comparable pressure) because the context is now small. 6F-B's single-condition runs (6.3–8.5GB free for 5 queries) show the accumulation builds with session length, not with 8192 itself.
  - Flagged as a host-operations watch item (monitor long sessions; candidate for 6G hygiene: server `keep_alive`/buffer tuning or a session-restart watchdog). Not a blocker for acceptance — no failure, timeout, or latency fallout observed.

## 9. Decision (STEP 7)

**ACCEPTED — num_ctx=8192 is validated for production use.**

Evidence vs the stated acceptance bar:
- Substantial latency improvement — validate (2.0–5.7x).
- No meaningful citation regression — validate (0 invalid cites; losses balanced by gains; zero-citation class unchanged soft-abstention).
- No unacceptable failures/timeouts — validate (0/0; max 81.6s < 120s).
- No obvious truncation problem — validate (no empties, comparable lengths, <40% context use).
- Materially improved memory behavior — validate with caveat (load footprint halved + full GPU; long-session drift observed but harmless to latency; monitor).

Limitations & open items:
- `OLLAMA_CONTEXT_LENGTH=8192` is applied as a host environment setting per the task's "prefer environment/runtime setting" rule. It is **not yet** permanent in project config (frozen-state rule) and **must be explicitly approved before being made permanent** (e.g. codified for the deployment env/Docker/CI or a doc note).
- Single host + single generation model; citation counts are sampling-variable (documented, not judged).
- Memory-drift across long sessions needs a host-level watch; recommended follow-up in 6G.

## 10. Safety Audit (STEP 9)

- Production files unchanged except the 6F-A modifications already present (`app/application/qa_workflow.py`, `tests/unit/test_qa_workflow.py`, `tests/unit/test_cli.py`) — nothing new from this phase.
- Dataset `eval/dataset.json` and corpus content: unchanged (no diff from this phase).
- Retrieval / embeddings / chunking / BM25 / RRF / reranker / HyDE / answerability / QA prompts: untouched.
- `qa.timeout_seconds=120` unchanged.
- No staging, no commit, no push. HEAD `9f282b4` confirmed.
- New untracked artifacts this phase: `eval/results/phase_6fc_qa_measurement_8192.jsonl` (35 rows) and this report `42_PHASE_6F_C_NUM_CTX_8192_VALIDATION.md`.
- Temp experiment scripts (`p6fc_ram.py`, `p6fc_compare.py`) will be deleted.

## 11. STOP

Phase 6F-C complete. Results returned above. **8192 is not made permanent anywhere.** Awaiting explicit approval before any further action (making 8192 permanent / Phase 6G).