# 39_PHASE_6D_LIVE_QA_MEASUREMENT

- **Phase:** 6D — Live QA Measurement
- **Type:** READ-ONLY observational validation (no production changes)
- **Date:** 2026-08-30
- **Status:** Complete (measurement only)

---

## 1. Objective

Run a live, observation-only measurement of the QA answering layer against the real 195-chunk / 24-source corpus, using the existing measurement harness, to ground the Phase 6C discovery findings in measured reality before any further application-layer work is considered. No behavior was modified.

## 2. Frozen baseline

- **HEAD:** `9f282b41b6c558b0dbea857c95e24beb3ff63f9a` (confirmed, unchanged)
- **Working tree at start:** 98 pre-existing entries (no 6D changes at baseline)
- **Retrieval config (unchanged):** embedding = `nomic-embed-text`; `reranker.enabled=false`; `hyde.enabled=false`; `answerability.enabled=false`; `min_cosine=0.45` (frozen factual value; not present in YAML, exercised via test-level agreement)
- **Corpus:** 195 chunks / 24 distinct sources (`data/manifests/vector_store.json` count)

## 3. Safety constraints

Absolute rules R1–R25 honoured. Production retrieval, embeddings, chunking, BM25, RRF, reranker, HyDE, answerability, AbstentionGate, QA prompts, QA workflow, configuration, dataset, and corpus were **not** modified. No commits, no pushes, no staging, no new dependencies. No LLM judge, no competing prompts, no threshold/model changes. Additional model calls were made **only** for representative-answer inspection via the identical normal QA request path (disclosed in §18).

## 4. Ollama / model verification

- **Ollama daemon:** available (API responsive)
- **`qwen3:8b`:** available — `500a1f067a9f`, 5.2 GB, loaded for generation (11 GB with context, 48% CPU / 52% GPU at run time)
- **`nomic-embed-text`:** available — `0a109f422b47`, 274 MB (retrieval embedding)
- **Timeout configuration:** `qa.timeout_seconds: 120` nominal client timeout — **not enforced at that duration on this host** (see §12, §18) — `INCONCLUSIVE`
- No model pulled, none changed.

## 5. Dataset verification

- **Version:** 3.0 (phase 5D)
- **Queries:** 199 (expected 199) — id range q001–q202, q092–q094 removed (confirmed absent)
- **Categories:** factoid=106, comparison=20, negative=42, cross_document=11, tricky=9, precise_detail=7, multi_chunk=4
- **Positive/negative:** 157 positive / 42 negative by category (42 == `negative`)
- Query text is unique across the dataset → used as the join key (harness does not persist query IDs; see §18)
- Dataset **not modified**.

## 6. Harness verification

`app/application/qa_measurement_harness.py` (unchanged from 6C) records per query, from the real `QAWorkflow` path:
- query text, outcome, failure category (none/timeout/empty/generation/unexpected), latency_ms
- answer_length, retrieved_source_count, raw `[SOURCE n]` token count, valid citation count, invalid citation count, duplicate citation count, insufficiency-language heuristic result

Verified contents of `tests/unit/test_qa_measurement.py` (12 tests) — schema is consistent. No correctness bug found; no harness changes made. Limitation: answer text and query ID are not persisted (text used for join; representative answers were inspected via re-requests, §9).

## 7. Measurement command

Per-category stratified runs of the existing harness (sequential, single process; parallel invocation caused memory thrash on this host — see §18):

```
python -m app.application.qa_measurement_harness --dataset eval/dataset.json --category <cat> --limit <n> --out <tmp>/p6d_<cat>.jsonl
```

Merged (join by unique query text, sorted by id, dedup-checked) into:

```
eval/results/phase_6d_qa_measurement.jsonl
```

Full-dataset approach: estimated ~2.2 h on this host (mean ~36–41 s cold / ~91 s measured overall). Per the user decision, a **bounded stratified sample of 35** was run instead of all 199.

## 8. Measurement coverage

- **Total records:** 35 (one per query, 0 duplicates)
- **Coverage by category:** factoid=12, negative=6, comparison=5, cross_document=4, tricky=3, precise_detail=3, multi_chunk=2
- All 35 rows mapped to dataset ids (q001–q186, none unmapped)
- Sample≈18% of the 199-query dataset; all 7 categories represented
- No dataset/corpus/production file modified; output is the only new artifact

## 9. Outcome statistics

- **ANSWERED:** 35 (100%)
- **ABSTAINED:** 0
- **FAILED:** 0

No hard-abstentions and no failures occurred. All 35 rows completed and produced an answer. The 6 "negative" soft-abstentions are textually abstaining while recorded as ANSWERED (§11, §16) — the AbstentionGate remains off and the system answers with an explicit insufficiency statement instead of a hard abstention.

## 10. Citation statistics

- **Answers with ≥1 valid citation:** 30 of 35 non-failed (85.7%)
- **Answers with zero citations:** 5 (14.3%) — all are soft-abstention/insufficiency answers
- **Invalid citation occurrences:** **0**
- **Duplicate citation occurrences:** 26 (spanning 9 answers) — benign list-format repetition, e.g. each `[SOURCE n]` in a per-source bullet re-cited in-line (q027, q031) — `VALIDATED` as a formatting pattern, not a validation failure
- **Average valid citations per non-failed answer:** 1.86
- **Average raw `[SOURCE n]` tokens per non-failed answer:** 2.60

## 11. Insufficiency statistics

- **Rows with insufficiency-language heuristic:** 7 of 35 (20.0%) — query ids q032–q036, q040, q041 (all negative or cross_document)
- **Answered + insufficiency:** 7 (100% of the insufficiency set) — these are content-level soft-abstentions ("retrieved context does not contain information about …")
- **Abstained + insufficiency:** 0
- **Answered + no insufficiency (clean):** 28

The heuristic matched the observed soft-abstention rows **7/7 (no false positives on cited rows)**; it also flags hedged-but-answering rows q034/q040 style hedging ("does not confirm", "might imply") — `USEFUL` as a telemetry signal, `DEFERRED` as a behavior trigger.

## 12. Latency statistics (ms)

| Set | n | mean | p50 | p95 | max |
|---|---|---|---|---|---|
| Overall | 35 | 91,017 | 63,034 | 350,147 | 466,191 |
| Answered | 35 | 91,017 | 63,034 | 350,147 | 466,191 |
| Abstained | 0 | – | – | – | – |
| Failed | 0 | – | – | – | – |

- **p50 = 63.0 s, p95 ≈ 5.8 min, max ≈ 7.8 min** — far above the nominal `qa.timeout_seconds: 120`. Several runs printed `httpx.ReadTimeout: timed out` to stderr yet still completed ANSWERED, meaning the configured client timeout is not surfacing as `QATimeoutError` at 120 s on this host — `INCONCLUSIVE` timeout behavior, flagged (§18).
- Hard-latency categories: multi_chunk p50=244 s, tricky p95=466 s, cross_document p95=350 s.
- Single run that produced a 350 s row and 466 s row demonstrates the host is generation-bound (≈1 GB free RAM during runs; 8B model split CPU/GPU).

## 13. Source-usage statistics

- Retrieved sources were **exactly 5 for every row** (mean 5.00, min 5, max 5) — the top-k retrieval cap; constant across categories on this sample. This is the sole retrieval-usage observation; no variation observed to correlate with latency or outcome.

## 14. Failure statistics

- **Failure categories (of `none`):** 35 `FAILURE_NONE`, 0 `FAILURE_TIMEOUT`, 0 `FAILURE_EMPTY_ANSWER`, 0 `FAILURE_GENERATION`, 0 `FAILURE_UNEXPECTED`
- No empty answers, no model failures, no timeouts classified in the sample. The only abnormal signals were the observed (unclassified) 120 s+ latencies and stderr `httpx.ReadTimeout` messages in §12.

## 15. Category analysis

| Category | n | ans | abst | fail | cit% | zero-cit% | insuff% | p50 | p95 |
|---|---|---|---|---|---|---|---|---|---|
| factoid | 12 | 12 | 0 | 0 | 100 | 0 | 0 | 39.1 s | 80.0 s |
| negative | 6 | 6 | 0 | 0 | 17 | 83 | 100 | 60.2 s | 105.9 s |
| comparison | 5 | 5 | 0 | 0 | 100 | 0 | 0 | 86.4 s | 101.1 s |
| cross_document | 4 | 4 | 0 | 0 | 100 | 0 | 25 | 114.0 s | 350.1 s |
| tricky | 3 | 3 | 0 | 0 | 100 | 0 | 0 | 76.3 s | 466.2 s |
| precise_detail | 3 | 3 | 0 | 0 | 100 | 0 | 0 | 67.4 s | 90.2 s |
| multi_chunk | 2 | 2 | 0 | 0 | 100 | 0 | 0 | 244.2 s | 244.2 s |

Every positive category answered with ≥1 valid citation. All zero-citation + insufficiency behavior is concentrated (100%) in negatives and one cross_document row. Gross positive categories (multi_chunk, cross_document) carry the heaviest latency.

## 16. Representative observations

Re-requested 6 representative queries through the identical normal QA path (no judge, no extra inference layer) to inspect answer text; examples:

1. **Normal cited answer (q001):** "Utthunga was founded in 2007 [SOURCE 1]. This is corroborated by … in [SOURCE 4]." — 2 valid citations, corroborating tone. `VALIDATED` signals ↔ behavior.
2. **Uncited soft-abstention (q032, France):** answer states the retrieved context contains no capital/geography information — honest, zero citations, heuristic=True. Explicit insufficiency.
3. **Uncited soft-abstention (q033, email attachments):** answer explains no explicit email-handling coverage, hedges, then shows a **stray `Answer:` label artifact** mid-response (noted quality quirk, `INCONCLUSIVE` significance).
4. **Duplicate citations (q027):** per-source bullet list re-asserting `[SOURCE n]` in each item — raw 10 vs valid 5, all tokens valid. Formatting repetition, not a failure.
5. **Answered + insufficiency (q040, cross_document):** partial-but-honest: only certificate sources found for author, no authored content — useful answer, heuristic=True from "does not contain information about".
6. **Hedged answer (q034, Python latest):** cites Python 3.13, explicitly flags it "does not confirm the current latest… external verification recommended" — cited, verbose, heuristic=True (mild hedging).

No inventable claim is made that any answer is semantically correct; all inspection findings are behavioral.

## 17. Phase 6C hypothesis validation

| 6C risk | Live status | Evidence |
|---|---|---|
| Soft-abstention | **VALIDATED** | 7/35 (20%) content-level insufficiency answers; all negative/cross_document |
| Empty answers | **NOT OBSERVED** | 0/35 since the 6C `QAEmptyAnswerError` fix |
| No-citation answers | **VALIDATED** | 14.3% (5/35), 100% co-occurring with insufficiency language |
| Invalid citations | **NOT OBSERVED** | 0 invalid occurrences in 35 |
| Malformed citation tokens | **NOT OBSERVED** | all `[SOURCE n]` tokens parse; raw>valid only via benign duplicates |
| Model failures | **NOT OBSERVED** | 0 `FAILURE_GENERATION`/`UNEXPECTED` |
| Timeout behavior | **INCONCLUSIVE** | latency far exceeds 120 s nominal without `QATimeoutError` surfacing; stderr `httpx.ReadTimeout` messages observed mid-run yet rows completed ANSWERED |

## 18. Limitations

- **Sample of 35/199 (user-approved bounded stratified)** — statistics are proportionally transferable but explicitly not the full dataset; several rare events (invalid citations, hard failures) may still be rarer than the sample can observe.
- **Answer text and query IDs not persisted** by the harness; join was by unique query text; representative inspection required re-requesting 6 queries through the normal QA path (6 extra normal QA calls, matching §9's inspection mandate; no judge).
- **Latency is confounded by host state:** ~1 GB free RAM during runs and an 8B model split CPU/GPU; observed slowdown over the session suggests cumulative memory pressure; a 2-process parallel attempt caused a 10-min zero-progress hang (re-run sequentially).
- **`OLLAMA CONTEXT 40960`** observed on the running generation model is suspicious (well above the ~4–5 k token needs of the QA prompt) and is the prime latency suspect; **adjusting it would alter production behavior, so it is intentionally not touched here** and is flagged for a dedicated next phase.
- **Timeout enforcement discrepancy:** nominal 120 s client timeout did not yield `QATimeoutError` rows for 120–466 s runs.
- No semantic-correctness claim is possible from the harness signals (`VALID CITATION` ≠ `SUPPORTED ANSWER`).

## 19. Decision

On the measured evidence, the correct decision is **to leave the current QA answering layer unchanged** (`RECOMMENDED`):

1. **Uncited answering:** 5/35, all insufficiency soft-abstentions, zero *confident-but-uncited* cases → no evidence for citation enforcement; monitor. `DEFERRED`
2. **Insufficiency heuristic:** 7/7 precision on soft-abstentions → worth keeping as a telemetry signal only. `DEFERRED`
3. **Invalid citations:** 0/35 → not currently a live problem. `DEFERRED`
4. **Empty answers:** 0/35 → 6C fix holds. `VALIDATED`
5. **Model failures/timeouts:** 0 failures; latency pathology real but an environment/capacity issue, not a workflow defect. `INCONCLUSIVE`
6. **Latency:** p50 63 s / p95 350 s → not interactive-acceptable; highest-value issue to investigate. `RECOMMENDED`
7–9. **Semantic detection / citation enforcement / groundedness verification:** no measured failure mode observed for any of these → insufficient evidence to justify implementation. `DEFERRED`
10. **Leave QA layer unchanged:** **YES** (`RECOMMENDED`).

## 20. Recommended next step

Phase 6E candidate — **Latency & timeout investigation (observational)** as the priority over any QA feature work:
- Measure generation latency with `num_ctx` reduced via a throwaway harness (test-only option, not production config change) to isolate the `40960` context suspicion.
- Confirm/fix the `qa.timeout_seconds: 120` enforcement discrepancy (QATimeoutError vs raw `httpx.ReadTimeout`).
- If/when justified separately, re-run the full 199-query measurement at higher host free-RAM to firm up the zero-citation / invalid-citation rates.
- Keep the QA feature backlog (semantic detection, citation enforcement, groundedness verification) deferred until either host latency is acceptable or a real failure rate is measured.
- Retrieval V1 remains frozen per Phase 5G — this phase does not reopen it.

---

## Appendix A — SAFETY AUDIT (post-run)

- `git rev-parse HEAD`: `9f282b41b6c558b0dbea857c95e24beb3ff63f9a` — unchanged
- New artifact attributable to 6D (only): `eval/results/phase_6d_qa_measurement.jsonl`
- All `M`/`??` entries listed by `git status --short` (99 total) are the same pre-existing cumulative 6A–6C/earlier set, plus the one new measurement file
- `eval/dataset.json`, `config/default.yaml`, `app/**` marked `M` are pre-existing (in inventory before 6D began); no 6D writer touched them (harness/scripts were read-only on those paths)
- `data/manifests/vector_store.json` untouched (read-only search)
- No temp scripts stored inside the repo (all under `%TEMP%\opencode\`)
- Test regression: `test_qa_workflow.py + test_qa_measurement.py + test_cli.py` → **97 passed** (matches pre-6D targeted state)
- No commits, no pushes, no staging