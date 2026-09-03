# Phase 6I-B — System Facts Layer

**Status:** IMPLEMENTED + VERIFIED (STOP honored)
**Baseline commit:** `10f74f1` (retrieval/corpus/dataset frozen, unchanged)
**Report:** Phase 6I-B of the V1 evidential / QA-hardening track.

---

## 1. Objective

Implement a **deterministic System Facts layer** that answers known
PAM/system-meta questions ("ask about the tool") from authoritative application
state and configuration — **without retrieval, without the LLM, without the
network**. Integrate it ahead of QA (router runs before retrieval), prove it
with tests, measure latency, and verify normal questions are unaffected.

This does **not** solve the overall false-positive-rate (FPR) problem; it
removes the F-class "ask about the tool" category from the normal retrieval
path so those questions never reach the evidence verifier. A blocking evidence
verifier remains **REJECTED** for V1 (per 6I-A).

## 2. Current baseline

- HEAD = `10f74f1` "feat: harden application layer and ingestion lifecycle".
- Retrieval files frozen: `embeddings.py`, `search.py`, `bm25.py`,
  `reranker.py`, `semantic_chunking.py`, `hyde.py` — **no diff**.
- `eval/dataset.json` / `tests/unit/test_eval_dataset.py` stale by design
  (7 failed / 24 passed expected) — not touched by this phase.
- Pre-existing dirty/untracked state present before 6I-B and left unchanged.
- Unit baseline: 1558 passed before this phase.
- Locally inferred: qwen3:8b 14–17s for blocking content verification, hence
  that path REJECTED in 6I-A.

## 3. Problem definition

Users ask meta questions about the tool itself:

- "What version of PAM am I running?"
- "How many sources are indexed?" / "How many chunks are indexed?"
- "Is the reranker enabled?"
- "What model answers my questions?"
- "What can PAM ingest?"

Today these fall into the normal RAG path: they retrieve from the corpus, may
return nothing useful, and are a known F-class false-positive source. They have
**deterministic** answers in application state/config, so invoking retrieval +
an LLM on them is wasteful and noisy. (VERIFIED)

## 4. Why retrieval stays frozen

No retrieval file changed in this phase. The System Facts layer sits *in front
of* retrieval in the application layer only. `git diff --stat` on the six
frozen infrastructure files is empty. (VERIFIED)

## 5. Authoritative sources of truth (VERIFIED)

| Fact | Source | Location |
|------|--------|----------|
| App version | `project.version` via `tomllib` | `pyproject.toml` = `1.0.0` |
| App name / env | `settings.app` | `config.py:27-33` |
| QA model | `settings.ollama.model` | `config.py:70` = `qwen3:8b` |
| Embed model | `settings.models.embeddings` | = `nomic-embed-text` |
| QA timeout | `settings.qa.timeout_seconds` | = `120` |
| Feature flags | `reranker/hyde/answerability.enabled` | all `false` |
| Source/chunk counts | `vector_store.json` under `manifest_root` | distinct sources=24, entries=195 |
| Ingestion status | `ManifestManager.list_entries()` | processed/skipped/failed |
| Capabilities | routing kinds + `watcher.supported_extensions` | `processors.py` |

## 6. Design (IMPLEMENTED)

- `app/application/system_facts.py` — new:
  - `Intent` (str-based enum) for the supported intents.
  - `SystemFactsRouter` — deterministic, conservative regex/substring matcher.
  - `SystemFactsService` — collects facts from authoritative state.
  - `SUPPORTED_INGESTION_TYPES`, `OLLAMA_NUM_CTX = 8192` (Phase 6F).
- `app/application/qa_workflow.py`:
  - `QAAnswer.origin` field, default `"retrieval"`.
  - `QAWorkflow` accepts optional `system_facts` service; in `ask()` runs the
    router **before** retrieval; on match returns a system-facts QAAnswer
    (`origin="system"`, `outcome="answered"`, `sources=[]`, no citations).
  - `create_default()` builds `SystemFactsService(settings)`.
- `app/application/__init__.py`: exports the new types.
- `app/cli/entry.py`: `_print_qa_answer` renders system-facts answers in a
  distinct Panel with the explicit "answer from PAM runtime/configuration"
  note and **no citations table**.

## 7. Routing conservatism (VERIFIED)

The router requires a specific signal and deliberately refuses ambiguous
matches so it never hijacks normal knowledge questions:

- "What version ... running?" → VERSION; "what version of X supports Y" → normal.
- "How many sources/documents are indexed?" → SOURCE_COUNT.
- "How many chunks are indexed?" → CHUNK_COUNT.
- "<feature> enabled/disabled/on/off/active" → FEATURE_STATUS.
- "what/which model ..." + model terms → QA_MODEL.
- "what can PAM ingest" / file types / formats → CAPABILITIES.
- "PAM status" / system health → STATUS.

Test-proven bypasses: "What is PAM?", "What did I learn about Docker?",
"When was Utthunga founded?", "How many questions does the DAA assignment
contain?" all fall through to normal QA.

## 8. Determinism & no-retrieval (VERIFIED)

System-facts answers contain no `[SOURCE N]` citations, no `sources`, and no
`citations`; they are computed from state/config only. There is **no LLM, no
vector/BM25 retrieval, and no network** on the matched path. Verified by a test
whose `FakeSearchService` and `FakeOllamaClient` count calls and assert zero.

## 9. No new QA state (VERIFIED)

System-facts answers use the existing `OUTCOME_ANSWERED` with `origin="system"`.
No fourth QA outcome was introduced; tool-meta answers are marked via the new
`origin` discriminator rather than a new state machine.

## 10. Security (VERIFIED)

`SystemFactsService._fact_*` returns only whitelisted fields: version, app
name, environment name, feature-flag booleans, model names, timeouts, counts,
extension counts. A test asserts no secret-like tokens (`secret`, `api_key`,
`token`, `password`) appear in the version answer. No env vars, API keys,
absolute paths, or manifest internals are surfaced.

## 11. Latency (PASS)

Measured 200 resolved system-facts calls (single process):

```
n=200  p50=0.043ms  p95=36.474ms  max=41.389ms
```

- p95 36.5ms **< 50ms** ✅ (the p95 is dominated by first-call/cold-start; the
  steady-state p50 is ~0.04ms).
- Compare qwen3:8b blocking verification at 14–17s (6I-A): a >400x win on the
  tool-meta class.

## 12. Normal QA unaffected (VERIFIED)

- `test_ask_returns_answer...` and the full `test_qa_workflow.py` suite pass
  unchanged (router inert when `system_facts=None` or on non-matching
  questions).
- CLI smoke: `ask "When was Utthunga founded?"` took 92s — retrieval + LLM path
  still executes; the question was NOT hijacked.
- Full unit suite: **1583 passed, 1 deselected** (1558 baseline + 25 new).

## 13. Retrieval / dataset freeze (VERIFIED)

- `git diff --stat` on the six frozen retrieval files: **empty**.
- No change to `eval/dataset.json` made by this phase (its diff is pre-existing
  5D dirty state, untouched).
- No commit, no push performed.

## 14. CLI rendering (VERIFIED)

System-facts answers show in a cyan "System facts" Panel plus the note
"Answer from PAM runtime/configuration (no retrieval, no LLM, no vector
search)." and **no citations table**. Smoke-tested for version, source count,
chunk count, feature status, and QA model — all returned instantly.

## 15. Acceptance guardrails status (PASS)

| Guardrail | Result |
|-----------|--------|
| No LLM / retrieval / network | VERIFIED (0 calls) |
| Normal QA unaffected | VERIFIED (full suite + smoke) |
| No fabricated citations | VERIFIED (empty sources/citations) |
| No secrets exposed | VERIFIED |
| p95 latency < 50ms | PASS (36.5ms) |
| Existing tests healthy | PASS (1583) |
| Retrieval frozen | VERIFIED (no diff) |
| No dataset/corpus changes | VERIFIED |
| Does NOT claim to solve overall FPR | VERIFIED — this phase only removes tool-meta questions |

## 16. Out of scope / DEFERRED

- **Blocking evidence verifier** — REJECTED for V1 (6I-A): p95 < 500ms infeasible
  on CPU for chained content verification.
- **Answerability / reranker / HyDE enablement** — DEFERRED (flags still off).
- **General FPR reduction** — DEFERRED; the System Facts layer deliberately does
  not touch the evidence/verification path.
- **Off-path / observational verifier** — DEFERRED to 6I-C (not started; STOP).

## 17. Risks

- Router false-positive intercepting a genuine knowledge question: mitigated by
  strict phrase requirements + explicit bypass tests, but a novel phrasing could
  still match. Low residual risk; a wrong system-facts answer is deterministic,
  bounded, and correct about state, never fabricated evidence.
- Stale counts if `vector_store.json` is absent/unreadable: handled with
  "unavailable" fallback.
- Router never matches exceptions to the whole class: acceptable — unmatched
  tool-meta questions simply return to normal QA (no regression, only no win).

## 18. Recommendation

Merge this phase as-is. The System Facts layer is small (~300 lines incl.
tests), deterministic, fast, secure, and demonstrably does not disturb the
frozen retrieval/verification path. It closes the F-class tool-meta questions
cheaply. The evidence-verification FPR problem remains open and is a separate,
deferred track (6I-C).

## 19. Decision

**APPROVED for this phase; STOP here.** 6I-B is complete: implementation +
tests + smoke + perf + report all done against frozen baseline `10f74f1`, with
**no commit / no push**. Do **not** proceed to 6I-C.

---

### Labels used
- VERIFIED — proven by test/smoke/diff in this phase.
- IMPLEMENTED — code delivered.
- PASS — acceptance guardrail met numerically.
- DEFERRED — intentionally not done now.
- REJECTED — tried/analyzed and ruled out for V1.
- INCONCLUSIVE — none this phase.
