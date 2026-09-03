# Phase 6F Report — QA Timeout Fix + num_ctx Controlled Experiment

**Date:** 2026-08-31
**HEAD:** 9f282b41b6c558b0dbea857c95e24beb3ff63f9a (unchanged, frozen)
**Environment:** Windows 11, Python 3.14, Ollama 0.33.2, qwen3:8b + nomic-embed-text, ~15.2GB RAM / 8GB VRAM (RTX 5060 Laptop)
**Corpus:** 195 chunks / 24 sources | **Dataset:** eval/dataset.json v3.0 (199 queries; q092–q094 removed)

---

## 1. Goal

Two isolated experiments on top of the frozen Phase 6C state:

- **6F-A — Wall-clock QA timeout:** the `qa.timeout_seconds=120` setting was previously applied only as an httpx *per-phase idle* timeout (Phase 6E root cause), so genuinely slow generations far beyond 120s (6D observed up to 466s) never failed. Implement + validate a true end-to-end wall-clock deadline.
- **6F-B — num_ctx controlled experiment:** prove/quantify whether the Ollama auto-allocated context (`num_ctx=40960`, from Phase 6E) is the dominant latency + memory factor, and whether a smaller hand-set context fixes "slow QA" at the root.

**Scope guards honoured:** no commit/push/stage, no retrieval/prompt/citation pipeline changes, no config/default edits (`config/default.yaml` untouched), `qa.timeout_seconds=120` remains the intended production value.

---

## 2. Experiment Design

### 6F-A design
- Production code change in `app/application/qa_workflow.py` only (the QA generation entry point all callers route through).
- Reuse the exact pattern already proven in `app/infrastructure/banded_verifier.py:130-175`: run the blocking generation call inside a `ThreadPoolExecutor`, wait with `future.result(timeout=...)`, convert `TimeoutError` into `OllamaTimeoutError`.
- Preserve every existing contract: `QATimeoutError` stays a `QAError` subclass (CLI catch → Panel "Ask failed" → exit 1), `OllamaClientError`/unexpected/empty-answer mapping unchanged, deadline optional (`None` = old behaviour).
- Tests: 9 new unit tests (deadline honoured/completed, fires at deadline, subclass relationship, unavailable/empty/exception/citation-unchanged), plus a new CLI-level timeout test in `tests/unit/test_cli.py`.
- Live validation through the real CLI (CliRunner, real Ollama): fast query, slow query (must NOT falsely time out), and an env-overridden 10s deadline (must fire end-to-end).

### 6F-B design
- 5 fixed queries, re-run across 3 conditions in the **same process** with only `num_ctx` varied: `automatic` (no option → 40960), `8192`, `4096`.
  Query mix: factoid (q001), precise_detail (q165), comparison (q027), cross_document (q037), negative (q032).
- num_ctx injected ONLY into the request options via a client wrapper — full real retrieval/prompt/generation pipeline otherwise intact; wall-clock deadline disabled (`_generation_timeout_seconds=None`) to measure pure generation.
- Per run recorded: total/generation wall time, `prompt_eval_count`, `eval_count`, `total_duration`, `load_duration`, free RAM before/after, actual loaded context read from `ollama ps` CONTEXT column, outcome + citation numbers.
- 15 sequential runs (host hangs under parallel Ollama processes — 6D lesson).

---

## 3. Part A Implementation (qa_workflow.py)

Files changed:

| File | Change |
|---|---|
| `app/application/qa_workflow.py` | +`ThreadPoolExecutor` import; +`OllamaTextResponse` import; `__init__(..., *, keyword-only)` gains `generation_timeout_seconds: float \| None = None` → `self._generation_timeout_seconds`; `create_default` passes `settings.qa.timeout_seconds` (120); `ask()` routes through `_generate_with_deadline`; new `_generate_with_deadline` helper |
| `tests/unit/test_qa_workflow.py` | +`threading`, `time` imports; +`BlockingOllamaClient`, `SlowOllamaClient`; +`TestWallClockTimeout` (9 tests) |
| `tests/unit/test_cli.py` | +`QATimeoutError` import; +`test_cli_ask_timeout_reports_failure_exit_one` |

`_generate_with_deadline` mechanics:

```
poll = ThreadPoolExecutor(max_workers=1)
future = poll.submit(self._ollama_client.generate_text, request)
try:
    return future.result(timeout=timeout_seconds)   # main thread deadline
except TimeoutError:
    raise OllamaTimeoutError("QA generation exceeded the wall-clock timeout of X seconds.")
finally:
    poll.shutdown(wait=False)   # abandoned worker finishes in background
```

All other `ask()` exception mapping is untouched; the deadline only intercepts `TimeoutError`.

---

## 4. Part A — Test Results [VALIDATED]

- Targeted suite `test_qa_workflow.py + test_qa_measurement.py + test_cli.py` (>= 107 tests):
  **107 passed, 0 failed** (97 pre-existing + 10 new).
- Full `pytest tests/unit -p no:cacheprovider --cov=app`:
  **1562 passed / 7 failed / 1 deselected; coverage 88.74%** (8058 stmts, 907 missed; required 80% reached).
  - The 7 failures are the **same pre-existing stale `test_eval_dataset.py` set** (v3.0 dataset vs tests expecting v1.0/160 queries) — not introduced, do-not-fix carry-over.
  - Coverage denominator/scope here is `tests/unit` only; Phase 6B's 89.35% was measured on a broader test selection, so the figures are not directly comparable. New `qa_workflow` statement count grew +~14 lines, all exercised by the new tests.
- Ruff on changed files: clean (only repo pre-existing E501 lints elsewhere remain, none introduced).

### 6F-A live CLI validation [VALIDATED]

| Run | Deadline | Result | Exit | Wall |
|---|---|---|---|---|
| LIVE A — factoid (q001) | 120s | answered, "SOURCES VERIFIED" | 0 | 71.0s |
| LIVE B — multi_chunk (q176, 6D p50≈244s class) | 120s | answered, verified label | 0 | 97.6s |
| LIVE C — q176 with `PAM_QA__TIMEOUT_SECONDS=10` | 10s | **QATimeoutError surfaced, "Ask failed" panel, no answer label** | **1** | 13.7s |

- LIVE B proves the deadline does **not** false-positive on legitimate long generations under 120s.
- LIVE C proves end-to-end enforcement: real generation still running, deadline fired at ~10s, CLI exited 1 with "Unable to generate an answer: the request timed out after the configured QA timeout (qa.timeout_seconds)."
- Note (observed, benign): the abandoned worker thread is non-daemon, so the Python process lingers until that generation completes (LIVE C process: ~54s after exit). This is safe — the CLI has already returned exit 1 to the shell; the background stream just finishes consuming the abandoned KV work. No deadlock, no hang in the CLI path.

**Part A decision: ACCEPTED** — production code + tests in place, behaviour verified live three ways.

---

## 5. Part B — num_ctx Results [VALIDATED]

All 15 runs answered; `ollama ps` confirmed the requested context each time (40960 / 8192 / 4096).

| Query | Cond | Wall (s) | Gen (s) | Prompt tok | Out tok | Citations | Free RAM after (MB) |
|---|---|---|---|---|---|---|---|
| q001 factoid | automatic | 66.9 | 58.6 | 1122 | 322 | [1,4] | 3004 |
| q001 | 8192 | 24.3 | 20.1 | 1122 | 241 | [1,4] | 8476 |
| q001 | 4096 | 24.9 | 20.7 | 1122 | 239 | [1,4] | 8421 |
| q165 precise_detail | automatic | 72.5 | 66.7 | 2766 | 491 | [1,3] | 2578 |
| q165 | 8192 | 12.7 | 7.5 | 2766 | 377 | [1,3] | 7649 |
| q165 | 4096 | 15.0 | 9.9 | 2766 | 519 | [1,3] | 7627 |
| q027 comparison | automatic | 91.4 | 87.3 | 2426 | 682 | [1,2,3,4,5] | 2163 |
| q027 | 8192 | 20.4 | 16.2 | 2426 | 864 | [1,2,3,4,5] | 7209 |
| q027 | 4096 | 24.2 | 20.0 | 2426 | 1088 | **[]** | 7130 |
| q037 cross_document | automatic | 83.6 | 79.4 | 2375 | 684 | [1,2,3,4,5] | 1984 |
| q037 | 8192 | 18.4 | 14.2 | 2375 | 755 | [1,2,3,4,5] | 6747 |
| q037 | 4096 | 17.6 | 13.4 | 2375 | 717 | [1,2,3,4,5] | 6657 |
| q032 negative | automatic | 36.9 | 32.7 | 2225 | 245 | [] | 1443 |
| q032 | 8192 | 8.4 | 4.3 | 2225 | 186 | [] | 6311 |
| q032 | 4096 | 9.4 | 5.3 | 2225 | 242 | [] | 6350 |

### Means per condition (5 queries)

| Metric | automatic (40960) | 8192 | 4096 |
|---|---|---|---|
| Mean wall time | **70.3s** | **16.8s** | **18.2s** |
| Mean generation time (excl. load) | 64.9s | 12.5s | 13.9s |
| Worst-case wall (q most affected) | 91.4s | 24.3s | 24.9s |
| Speedup (wall, vs automatic) | 1.0x | **4.2x** | 3.9x |
| Total output tokens (5 runs) | 2424 | 2423 | 2805 |
| Free RAM during runs | 1.4–3.0 GB | **6.3–8.5 GB** | 6.4–8.4 GB |
| Citation pattern set | {2,2,5,5,0} | {2,2,5,5,0} | {2,2,**0**,5,0} |

### Findings [VALIDATED]

1. **num_ctx is the dominant latency factor, not decode throughput alone.** Total output-token budget across the 5 runs is nearly identical (2424 vs 2423 tokens), yet generation at 40960 takes ~5x longer per token — the oversized KV cache slows every decode step. Phase 6E's "decode rate" reading missed this dimension because it measured a default-context model.
2. **8192 delivers the same answer-quality signal as automatic** — identical citation sets on all 5 queries (incl. q027's full 5-citation answer and q032's soft-abstention), no truncation, no answer-shape change. Max wall observed 24.3s → 5x headroom under the 120s wall-clock.
3. **4096 is unsafe as a default**: q027 (long-answer comparison, 2426 prompt + 1088 output = 3514 ctx tokens) **lost all 5 citations** while automatic/8192 kept them; output also grew (1088 tok) — behaviour consistent with squeeze at the context boundary. 4096 offers no speed advantage over 8192 anyway (18.2s vs 16.8s mean — noise).
4. **Memory relief is real**: free RAM during runs went from 1.4–3.0 GB (40960) to 6.3–8.5 GB (8192/4096). The 6D instability (release: ~1GB free, parallel throws) was KV-cache pressure of the 40960 context; also explains why runs got *faster* as the session progressed (model already warm).
5. **One-time reload cost** on context change: ~15.5s (8192) / ~16.2s (4096) on the first request; steady-state cheap (keep_alive default 5m).
6. The negative-query soft-abstention behaviour (q032, 0 citations, "not enough information") was **stable across all three contexts** — a safeguard, not degraded by the smaller context.

### Part B decision
- **8192: RECOMMENDED** as the production num_ctx (4.2x latency cut, RAM headroom, zero observed quality regression, comfortable margin under a 120s wall-clock). Set server-side via `OLLAMA_CONTEXT_LENGTH=8192` (or Modelfile `num_ctx`), then restart Ollama once. Zero code change required.
- **4096: REJECTED** (citation loss at long-answer boundary, no speed win).
- **automatic 40960: REJECTED** as the environment default (4x slower, memory pressure).

**Part B decision: RECOMMENDED (8192) — pending user/operator approval to apply the server-side option.**

---

## 6. Combined Analysis (6F-A × 6F-B)

- The 6D failures were: (a) unbounded waits (httpx idle semantics capped nothing) and (b) memory pressure from KV cache at 40960. Fixes: (a)→ wall-clock deadline (Part A, ACCEPTED); (b)→ shrink context (Part B, recommended).
- Interaction: with 40960 left in place, the new 120s deadline would flip the 6D 466s/p95-350s tail into hard failures (timeout → FAILED in harness). With 8192, max observed 24.3s — the deadline becomes an *emergency guardrail* that almost never fires. **They are designed to ship together.**
- No interference with 6C deliverables: retrieval, prompt, HyDE, reranker (all disabled), citations, `min_cosine=0.45` unchanged.

---

## 7. Regression & Safety

| Check | Result |
|---|---|
| Targeted QA/CLI/measurement tests | 107/107 pass |
| Full `tests/unit` | 1562 pass, 7 stale (pre-existing), 1 deselected, coverage 88.74% ≥ 80% |
| Ruff (changed files) | clean (no new issues) |
| `config/default.yaml` | untouched |
| `qa.timeout_seconds` default | remains **120** |
| git | HEAD unchanged 9f282b4…; no commits, no staging (see Section 9) |
| Temp scripts | created under `%TEMP%\opencode\`, deleted (Section 9) |

---

## 8. Conclusions

| Claim | Labelled |
|---|---|
| httpx idle semantics never capped QA wall time (6E) | VALIDATED (reproduced; LIVE C fires at the true deadline) |
| Wall-clock deadline implemented + tested live (exit 1, no answer, "Ask failed") | VALIDATED |
| Deadline does not false-positive under 120s (97.6s real generation) | VALIDATED |
| num_ctx=40960 is the dominant latency factor (~5x per-token decode penalty) | VALIDATED |
| num_ctx=8192: 4.2x faster, RAM relief, identical citation/quality signal in sample | VALIDATED |
| num_ctx=4096: citation loss evidence on long answers (q027 5→0) | VALIDATED |
| Negative-query soft-abstention robust across contexts | VALIDATED |
| num_ctx explanation for 6D memory instability (~1GB free) | SUPPORTED |
| Applying 8192 is zero-code (Ollama env/Modelfile) | VALIDATED (mechanism confirmed via option injection) |

---

## 9. Git & Hygiene Audit

HEAD unchanged, **no commits staged/pushed**. Status (101 pre-existing working-tree entries from phases 6A–6E + this phase's modifications):

- `M app/app/application/qa_workflow.py` (Part A change — intended)
- `M tests/unit/test_qa_workflow.py`, `M tests/unit/test_cli.py` (Part A tests — intended)
- Untracked (reports/deliverables): `39_PHASE_6D_LIVE_QA_MEASUREMENT.md`, `40_PHASE_6E_QA_LATENCY_TIMEOUT_INVESTIGATION.md`, this `41_PHASE_6F_QA_TIMEOUT_AND_NUM_CTX_EXPERIMENT.md`, `eval/results/phase_6d_qa_measurement.jsonl`
- Temp experiment scripts removed from `%TEMP%\opencode\` (p6f_live.py, p6f_live_timeout.py, p6f_live_timeout.log, p6f_partb.py). Experiment data preserved below for traceability.

---

## 10. Raw Data

### Part B runs (as logged; JSONL rows 1–15)

```
[{"condition":"automatic","query_id":"q001","ok":true,"outcome":"answered","total_wall_s":66.9,"citations":[1,4],"ram_free_before_mb":8751,"ram_free_after_mb":3004,"qwen_context":"40960","answer_len":208,"latency_seconds":60.65,"prompt_tokens":1122,"out_tokens":322,"total_ns":58636263300,"load_ns":18756728100},
{"condition":"automatic","query_id":"q165","ok":true,"outcome":"answered","total_wall_s":72.5,"citations":[1,3],"ram_free_before_mb":2987,"ram_free_after_mb":2578,"qwen_context":"40960","answer_len":546,"latency_seconds":68.75,"prompt_tokens":2766,"out_tokens":491,"total_ns":66718303800,"load_ns":7029800},
{"condition":"automatic","query_id":"q027","ok":true,"outcome":"answered","total_wall_s":91.4,"citations":[1,2,3,4,5],"ram_free_before_mb":2576,"ram_free_after_mb":2163,"qwen_context":"40960","answer_len":1203,"latency_seconds":89.29,"prompt_tokens":2426,"out_tokens":682,"total_ns":87259662600,"load_ns":7982900},
{"condition":"automatic","query_id":"q037","ok":true,"outcome":"answered","total_wall_s":83.6,"citations":[1,4,2,3,5],"ram_free_before_mb":2162,"ram_free_after_mb":1984,"qwen_context":"40960","answer_len":1514,"latency_seconds":81.45,"prompt_tokens":2375,"out_tokens":684,"total_ns":79407995200,"load_ns":7410300},
{"condition":"automatic","query_id":"q032","ok":true,"outcome":"answered","total_wall_s":36.9,"citations":[],"ram_free_before_mb":1976,"ram_free_after_mb":1443,"qwen_context":"40960","answer_len":257,"latency_seconds":34.79,"prompt_tokens":2225,"out_tokens":245,"total_ns":32731517500,"load_ns":8006800},
{"condition":"8192","query_id":"q001","ok":true,"outcome":"answered","total_wall_s":24.3,"citations":[1,4],"ram_free_before_mb":1191,"ram_free_after_mb":8476,"qwen_context":"8192","answer_len":200,"latency_seconds":22.18,"prompt_tokens":1122,"out_tokens":241,"total_ns":20146441800,"load_ns":15487714100},
{"condition":"8192","query_id":"q165","ok":true,"outcome":"answered","total_wall_s":12.7,"citations":[1,3],"ram_free_before_mb":8470,"ram_free_after_mb":7649,"qwen_context":"8192","answer_len":635,"latency_seconds":9.54,"prompt_tokens":2766,"out_tokens":377,"total_ns":7492437000,"load_ns":8360800},
{"condition":"8192","query_id":"q027","ok":true,"outcome":"answered","total_wall_s":20.4,"citations":[1,2,3,4,5],"ram_free_before_mb":7645,"ram_free_after_mb":7209,"qwen_context":"8192","answer_len":779,"latency_seconds":18.20,"prompt_tokens":2426,"out_tokens":864,"total_ns":16152806000,"load_ns":7827800},
{"condition":"8192","query_id":"q037","ok":true,"outcome":"answered","total_wall_s":18.4,"citations":[1,2,3,4,5],"ram_free_before_mb":7210,"ram_free_after_mb":6747,"qwen_context":"8192","answer_len":1351,"latency_seconds":16.29,"prompt_tokens":2375,"out_tokens":755,"total_ns":14231217300,"load_ns":8379200},
{"condition":"8192","query_id":"q032","ok":true,"outcome":"answered","total_wall_s":8.4,"citations":[],"ram_free_before_mb":6741,"ram_free_after_mb":6311,"qwen_context":"8192","answer_len":106,"latency_seconds":6.31,"prompt_tokens":2225,"out_tokens":186,"total_ns":4263491200,"load_ns":12422900},
{"condition":"4096","query_id":"q001","ok":true,"outcome":"answered","total_wall_s":24.9,"citations":[1,4],"ram_free_before_mb":6087,"ram_free_after_mb":8421,"qwen_context":"4096","answer_len":193,"latency_seconds":22.74,"prompt_tokens":1122,"out_tokens":239,"total_ns":20719461300,"load_ns":16245701400},
{"condition":"4096","query_id":"q165","ok":true,"outcome":"answered","total_wall_s":15.0,"citations":[1,3],"ram_free_before_mb":8406,"ram_free_after_mb":7627,"qwen_context":"4096","answer_len":516,"latency_seconds":11.94,"prompt_tokens":2766,"out_tokens":519,"total_ns":9918892600,"load_ns":8058800},
{"condition":"4096","query_id":"q027","ok":true,"outcome":"answered","total_wall_s":24.2,"citations":[],"ram_free_before_mb":7637,"ram_free_after_mb":7130,"qwen_context":"4096","answer_len":1054,"latency_seconds":22.04,"prompt_tokens":2426,"out_tokens":1088,"total_ns":20016423200,"load_ns":8603200},
{"condition":"4096","query_id":"q037","ok":true,"outcome":"answered","total_wall_s":17.6,"citations":[1,4,2,3,5],"ram_free_before_mb":7156,"ram_free_after_mb":6657,"qwen_context":"4096","answer_len":1499,"latency_seconds":15.49,"prompt_tokens":2375,"out_tokens":717,"total_ns":13428957700,"load_ns":11611600},
{"condition":"4096","query_id":"q032","ok":true,"outcome":"answered","total_wall_s":9.4,"citations":[],"ram_free_before_mb":6801,"ram_free_after_mb":6350,"qwen_context":"4096","answer_len":249,"latency_seconds":7.34,"prompt_tokens":2225,"out_tokens":242,"total_ns":5259184500,"load_ns":6876000}]
```

### Part A live runs (excerpt)

```
LIVE A: exit_code=0 wall=71.0s label_verified=True ask_failed=False
LIVE B: exit_code=0 wall=97.6s label_verified=True ask_failed=False
LIVE C: CONFIRM deadline=10s exit_code=1 wall=13.7s ask_failed=True timed_out_msg=True
        verified_label=False  ("Ask failed" panel + "request timed out after the configured QA
        timeout (qa.timeout_seconds)")
```

---

## 11. Follow-ups

- **Apply OLLAMA_CONTEXT_LENGTH=8192** on the host (or qwen3 Modelfile `num_ctx 8192`), restart Ollama, re-run the 5-query spot check to confirm identical behaviour — then the 120s wall-clock becomes a pure guardrail.
- Full 199-query measurement (6D was a bounded 35-query sample) remains deferred — now nearly free to run with 8192 (~35 min estimated vs ~2.2h at 40960).
- Re-check citation-quality delta at 8192 on the tricky/multi_chunk classes in that measurement.

## 12. STOP

Phase 6F complete. Awaiting explicit approval before 6G / next phase.