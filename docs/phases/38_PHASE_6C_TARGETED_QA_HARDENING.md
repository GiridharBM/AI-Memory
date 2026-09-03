# 38_PHASE_6C_TARGETED_QA_HARDENING.md

Phase 6C — Targeted QA hardening + measurement harness
Status: IMPLEMENTED & TESTED (no commit, no push)
Frozen baseline: commit `9f282b4` — unchanged. Retrieval, dataset, corpus untouched.

---

## 1. Objective — VALIDATED

Implement the three targeted QA hardening fixes approved from the Phase 6C
discovery (report 37) and the §15 measurement harness, while keeping retrieval,
the evaluation dataset, the real corpus, and all experimental gates frozen.
Explicitly out of scope (per approval): semantic abstention detection,
citation-enforcement gating, answer/source semantic-overlap validation,
reranker/HyDE/answerability activation, and any retrieval change.

## 2. Discovery findings — VALIDATED (recap of report 37)

- Soft-abstention prose becomes ANSWERED with `.outcome == "answered"`, no
  clear label, full source list shown (transparent but mislabeled).
- Citation validity (syntax/range/presence/dedup) is verifiable locally;
  support/groundedness is not.
- Three-state contract (ANSWERED/ABSTAINED/FAILED) is sufficient.
- One residual ambiguity: an **empty/whitespace model response** was treated
  as ANSWERED success (empty green panel, exit 0).
- Unexpected non-Ollama exceptions could escape `ask()` unwrapped.
- No local test/data corpus exists to validate a semantic abstention detector
  → deferred pending live measurement.

## 3. Empty-answer fix — IMPLEMENTED

`app/application/qa_workflow.py`:

- New `QAEmptyAnswerError(QAError)` (in the existing error taxonomy; distinct
  from `QATimeoutError` and from plain `QAError`). It is FAILED-style — never
  an ABSTAINED `QAAnswer`, never a new outcome state.
- After generation, `if not response.response.strip(): raise
  QAEmptyAnswerError(...)`. Covers `""`, `"   "`, `"\n\t "`, `" \r\n "`.
- The check lives **after** the try/except so it is never re-wrapped by the
  generic handler, and the question/`finally`-latency plumbing is intact.
- CLI already catches `QAError` → red "Ask failed" panel, exit 1, no empty
  green panel. Traceback stays on stderr (6B logging boundary unchanged).

Verified by tests and smoke C.

## 4. Exception-handling fix — IMPLEMENTED

`app/application/qa_workflow.py` — the `generate_text` call now has a third
handler:

```python
except Exception as exc:   # after OllamaTimeoutError, then OllamaClientError
    logger.warning("QA generation raised an unexpected error.", exc_info=True)
    raise QAError("Unable to generate an answer: the model produced an
                   unexpected error.") from exc
```

- `QATimeoutError` → wrapped to `QATimeoutError` (preserved, first handler).
- `OllamaClientError` (unavailable/connection) → wrapped to `QAError`
  (preserved, second handler; verified non-QATimeoutError).
- Any other provider/model exception (e.g. `OllamaResponseError`, httpx,
  raw `RuntimeError`) → `QAError`, so callers always receive the documented
  failure hierarchy and no raw traceback reaches the normal CLI path.

## 5. No-citation presentation — IMPLEMENTED

`app/cli/entry.py` `_print_qa_answer` (ANSWERED path):

- citations present → `ANSWERED — SOURCES VERIFIED` label above the cited
  "Sources" table.
- citations empty (+ retrieved sources exist) → `ANSWERED — NO CITATIONS
  PROVIDED` (yellow) above the full retrieved-sources fallback table.
- The answer text is never altered; no citations are fabricated; no new QA
  state. Uncited answers are still accepted (never rejected).

Smoke B/A and unit CLI tests verify the two labels are mutually exclusive.

## 6. Measurement harness — IMPLEMENTED (measurement-only)

New module `app/application/qa_measurement_harness.py`:

- `record_row(query, result, failure, latency_s)` → one observational JSONL
  dict: query, outcome, failure_category, answer_length, retrieved_source_count,
  citation_count (total `[SOURCE N]` tokens via `extract_citations`),
  valid/invalid/duplicate citation counts, `has_insufficiency_language`
  heuristic flag, latency_ms.
- `has_insufficiency_language` is **observational only** — it labels telemetry;
  it can never change ANSWERED/ABSTAINED/FAILED (tested at module and workflow
  level with an obviously-insufficient answer still ending `answered`).
- `_classify(exc)` maps `QATimeoutError/QAEmptyAnswerError/QAError/other` →
  `timeout/empty_answer/generation_error/unexpected`.
- `main(argv)` CLI: `python -m app.application.qa_measurement_harness
  [--dataset eval/dataset.json] [--limit N] [--category C]
  [--out eval/results/qa_measurement.jsonl]`. Appends JSONL rows (safe resume),
  runs each query through `QAWorkflow.create_default(load_settings())`, times
  each `ask`, records failure categories if the model is unreachable, prints a
  terminal summary. Reads only — it never writes the dataset or the corpus.

No LLM judge, no additional model call, no production-path dependency: the
harness imports the workflow, never the reverse.

## 7. Tests — IMPLEMENTED (+26 over baseline)

`tests/unit/test_qa_workflow.py` (+11):
- Empty/whitespace (`""`, `"   "`, `"\n\t "`, `" \r\n "`) → `QAEmptyAnswerError`.
- `QAEmptyAnswerError` is `QAError` subclass; distinguishable from
  `QATimeoutError`; whitespace answer is not an ABSTAINED answer.
- Normal answer stays ANSWERED with `latency_seconds` + `telemetry` recorded.
- Unexpected model exception (`RuntimeError`) → wrapped `QAError`;
  `OllamaTimeoutError` → `QATimeoutError`; `OllamaClientError` → unavailable
  `QAError` (all preserved).
- Insufficiency heuristic flags obvious phrasing and is measurement-only
  (outcome remains answered).

`tests/unit/test_cli.py` (+3):
- Uncited answer labeled `ANSWERED — NO CITATIONS PROVIDED` (and not verified).
- Cited answer labeled `ANSWERED — SOURCES VERIFIED` (and not no-citations).
- Empty answer through the CLI → exit 1, "Ask failed", "empty response".

`tests/unit/test_qa_measurement.py` (+12, new file):
- `record_row` statistics incl. latency and citation counts; abstention row;
  insufficiency detection never changes outcome; failure-row recording;
  `_classify` mapping; `main()` end-to-end writes JSONL; failure rows recorded
  when the model raises.

Existing tests untouched; all 6B/6A QA protections (valid/invalid citations,
duplicates, verbatim text, no renumbering) still pass.

## 8. CLI verification — VALIDATED

In-process smoke (Temp `p6c_smoke.py`, result stdout/stderr checked, all PASS):

| case | observed | exit |
|------|----------|------|
| A cited answer | `ANSWERED — SOURCES VERIFIED` + cited Sources table | 0 |
| B uncited answer | `ANSWERED — NO CITATIONS PROVIDED` + full Sources table | 0 |
| C empty answer | red "Ask failed" + "empty response" pane, no empty green panel | 1 |
| D model/ollama failure | red "Ask failed" + clean message | 1 |
| E retrieval abstention | yellow "Insufficient evidence" + reason, no LLM | 0 |
| F invalid citation | `ANSWERED — NO CITATIONS PROVIDED` + yellow "Invalid citations" warning | 0 |

No run leaked a raw traceback to stdout. No retrieval threshold was altered.

## 9. Retrieval regression — VALIDATED

- No modifications to `SearchService`, `VectorStore`, `EmbeddingService`, BM25,
  RRF, chunking, reranker, HyDE, answerability modules or `eval/dataset.json`
  in this phase (git audit §18; only 6C files changed).
- `config/default.yaml`: `reranker.enabled=false`, `hyde.enabled=false`,
  `answerability.enabled=false` — reconfirmed.
- Abstention path behavior (empty hits / below-threshold → ABSTAINED, LLM not
  invoked) unchanged and re-covered by existing tests; `_abstention_answer`
  helper preserves the exact same contract and adds telemetry only.

## 10. Performance impact — VALIDATED

- Empty-answer guard: O(1) `strip()` on an already-present string.
- Exception wrap: zero cost except on failure.
- Telemetry: constant-time counts + one regex scan of the answer (sub-µs–µs
  scale); `latency_seconds` is a single `perf_counter` read.
- No extra model call, no extra I/O, no network. Latency test asserts the
  recorded `latency_seconds >= 0` and equals the measured generation time.

## 11. Known limitations — VALIDATED

- The insufficiency-language heuristic is intentionally naive (regex over a
  fixed phrase set). Negation ("the sources don't say X, so the answer is not
  determinable"), mixed answers, and novel phrasings are only partially covered.
  It is telemetry only, so a miss is harmless; a false positive merely labels
  a row.
- Citation/support relationship remains unverifiable locally (as in 6B/37).
- The harness requires a live Ollama + indexed store; failure rows are
  recorded if the model is down, so an offline run still yields usable rows.
- `test_cli.py:722` has a pre-existing E501 (line too long) not introduced by
  this phase.

## 12. Deferred semantic detection — DEFERRED

Keyword/pattern soft-abstention **acting on** the outcome remains rejected for
now. Approved scope only permits *measuring* it (harness flag). A real detector
requires the measurement corpus: run the harness (report 37 §15) to collect N
live answers, then decide.

## 13. Deferred groundedness validation — DEFERRED

Answer-to-source overlap scoring and LLM-as-judge remain unimplemented
(loop-checked into the freeze list). The disabled `answerability` gate /
banded verifier remain the candidates if a future phase re-opens this.

## 14. Deferred citation enforcement — DEFERRED

No hard requirement that every answer cite; no retry-on-no-citation. Uncited
answers stay accepted and are now honestly labeled, matching approval scope.

## 15. Acceptance criteria — MET

- empty/whitespace output → FAILED (`QAEmptyAnswerError`), CLI exit 1,
  no empty green panel ✓
- ANSWERED-without-citations renders honest label + full sources ✓
- QA tests from 6A/6B remain green; final suite 1575p/7f(identical stale set)/57d ✓
- harness produces JSONL + summary; detection never changes outcomes ✓
- retrieval/dataset/corpus/HEAD `9f282b4` untouched; no commits ✓

## 16. Rollback plan — VALIDATED (none needed)

All changes are additive guards/labels/telemetry in `qa_workflow.py` +
`entry.py` + one new module + tests. Rollback = remove the empty-answer guard,
the third `except` handler, the CLI labels, and delete
`qa_measurement_harness.py`/`test_qa_measurement.py`; 6A/6B behavior is
restored exactly (no schema/config/data migration).

## 17. Next phase — PROPOSED

Use the harness to collect a live measurement corpus (e.g.
`python -m app.application.qa_measurement_harness --limit 60`), then analyze:
- real no-citation / soft-abstention rates and phrasing variance,
- empty-answer frequency,
- latency distribution.

Only after that: decide whether a semantic abstention detector is justified.
Suggested next phase: **6D — QA Live Measurement Analysis** (run harness,
summarize, decide). Requires no retrieval changes and no gate activation.

---

### Appendix — test suite delta

| metric | baseline (pre-6C) | final (6C) |
|--------|-------------------|------------|
| passed | 1549 | 1575 |
| failed | 7 (stale `test_eval_dataset.py`) | 7 (identical set) |
| deselected | 57 | 57 |
| coverage | 89.23% (7083/7938) | 89.35% (7187/8044) |
| statements | 7938 | 8044 |
| new tests | — | +26 |

### Appendix — git audit (complete)

Changed/new files for Phase 6C:
- `app/application/qa_workflow.py` (M — cumulative with 6A/6B working tree)
- `app/cli/entry.py` (M — cumulative with 6A/6B)
- `tests/unit/test_qa_workflow.py` (M — cumulative with 6B)
- `tests/unit/test_cli.py` (M — cumulative with 6B)
- `app/application/qa_measurement_harness.py` (new)
- `tests/unit/test_qa_measurement.py` (new)
- `38_PHASE_6C_TARGETED_QA_HARDENING.md` (new)

All other working-tree entries (`git status --short`) are PRE-EXISTING /
UNRELATED cumulative state from phases before 6C (33 already-modified tracked
files; untracked phase reports/artifacts/`vault/Notes/`). Verified:
- no retrieval/vector/embedding/BM25/RRF/chunking/reranker/HyDE/answerability
  modification,
- no `eval/dataset.json` or corpus change from this phase,
- no experimental gate activated,
- no temporary scripts left in the repository (6C smoke lives outside the repo
  in the Temp opencode directory; `scripts/` contains only `.gitkeep`),
- HEAD `9f282b4`, no commits, no pushes, no staging.