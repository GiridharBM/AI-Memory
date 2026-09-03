# Phase 6I-C — End-to-End Application Validation (Final V1 Readiness Audit)

**Status:** READ-ONLY VALIDATION COMPLETE
**Baseline commit:** `10f74f1` (unchanged, no commit/push/stage)
**Verdict:** **CONDITIONAL — READY WITH DOCUMENTED LIMITATIONS**

---

## 1. Objective

Comprehensive read-only validation of the PAM application after Phases 6A–6I-B:
application health, System Facts, normal QA, abstention, citations, failure /
timeout, ingestion lifecycle, secret guard, vector/KG consistency, QA
performance, CLI contract, security/privacy, test suite, and frozen-data
integrity. Bug discovery + classification only; **no new retrieval experiment,
no evidence verifier, no feature enablement, no code changes.**

## 2. Baseline commit

- HEAD = `10f74f1` "feat: harden application layer and ingestion lifecycle" (verified STEP 1, STEP 20).
- Retrieval V1 frozen, corpus = 195 chunks / 24 sources, eval = 199 queries.

## 3. Initial Git state (VERIFIED)

Pre-existing dirty/untracked state present before this phase (from prior
phases) and left **unchanged by 6I-C**. 6I-C modified **zero** tracked files;
its only artifact is this report. See STEP 20 for the exact signal.

## 4. Retrieval freeze verification (VERIFIED)

- `git diff 10f74f1 -- embeddings.py search.py bm25.py reranker.py semantic_chunking.py` → **empty**.
- `reranker.enabled = false`, `hyde.enabled = false`, `answerability.enabled = false` (config.py:417,435,451 defaults) (VERIFIED).
- Production `min_cosine = 0.25` (qa_workflow.py:430); historical eval value `0.45` is a **known inconclusive discrepancy** — documented, NOT changed (CONDITIONAL).
- `app/infrastructure/answerability.py` present, gate inactive by default.

## 5. Application health (VERIFIED)

`pam status` — truthful, no fabricated zeros:
- Sources indexed 24, Indexed chunks 195 (vector store)
- Successful ingests 36, Skipped duplicates 0, Failed 1, Retryable pending 1
- Real generated notes 25, Placeholder notes 206
- Last ingestion 2026-08-27T04:03:17Z

`pam doctor` — exit 0; all OK except `Tesseract binary → WARN (not on PATH)`
(non-blocking dependency note; pytesseract installed). No fabricated values
when state is present; "unavailable" paths fall back deterministically.

## 6. System Facts validation (CONDITIONAL — 1 HIGH bug found, unfixed)

Verified queries (deterministic, ~instant, no LLM/retrieval/BM25/network, no
citation, correct "System facts" label, no secret leakage):
- `What version of PAM am I running?` → `Personal AI Memory v1.0.0 ...` (PASS)
- `How many sources are indexed?` → `24 source(s) indexed` (PASS)
- `How many chunks are indexed?` → `195 chunk(s) indexed` (PASS)
- `Is the reranker enabled?` → `enabled: none ...` (PASS)

**HIGH (genuine bug, unfixed):** `What QA model is PAM using?` (a required
query in this phase) is **NOT intercepted** by the 6I-B System Facts Router —
`SystemFactsRouter.route("What QA model is PAM using?")` returns `None`, so the
query falls through to full retrieval + LLM and hung the CLI for >120s. Root
cause: `_match_qa_model()` requires substring `"what model"` but not `"qa
model"`. The phrase `"What QA model is PAM using?"` therefore bypasses the
router. **Fix deferred** (not authorized; out of read-only scope) — see §19 and
§23. Suggested minimal fix: add a conservative `"qa model"` + tool-signal
(`pam`/`you`/`running`/`using`) match in `_match_qa_model`.

Perf (from 6I-B, unchanged this phase): p50 0.043ms, p95 36.5ms, max 41.4ms —
well under the 50ms target (PASS).

## 7. Normal QA validation (VERIFIED)

`ask "When was Utthunga founded?"` →
- **NOT intercepted** by System Facts (verified via direct router call + live run).
- Retrieval ran; LLM ran; `ANSWERED — SOURCES VERIFIED`; exit 0; 42.5s.
- Citations `[SOURCE 1]` / `[SOURCE 4]` resolved against actual retrieved hits;
  correct sources table; no fabricated citations; no traceback leakage.
- Factual quality intentionally not re-judged (frozen eval governs).

## 8. Abstention validation (VERIFIED — via unit tests)

Abstention behavior, insufficiency-reason preservation, no-LLM-before-abstention,
and correct CLI output covered by `test_qa_workflow.py` abstention cases
(strong/weak/borderline/negative/no-results). No threshold tuning performed.
All 125 focused QA/CLI/timeout/system-facts tests pass.

## 9. Citation validation (VERIFIED — via unit tests)

Contract from 6B/6C confirmed by `test_qa_workflow.py` citation tests:
valid, multiple, duplicate, invalid, malformed, zero citations — invalid
citations flagged and NOT remapped, malformed tokens stay plain text, no
fabricated source, source text unaltered, duplicates handled as designed
(citations deduped + counted). No redesign performed.

## 10. Failure / timeout validation (VERIFIED — via unit tests)

- EMPTY → `QAEmptyAnswerError`/FAILED, exit 1, no empty answer (tested).
- MODEL FAILURE → `QAError`/FAILED, exit 1, no fake answer (tested).
- TIMEOUT → `QATimeoutError`/FAILED, exit 1, no answer presented
  (`test_qa_timeout.py`; generation runs under a wall-clock deadline via
  `_generate_with_deadline`). Normal exceptions do not leak raw tracebacks to
  CLI stdout (live `ask` runs confirmed clean output).

## 11. Ingestion lifecycle validation (VERIFIED — via unit tests)

`test_ingestion_lifecycle.py` / `test_ingest_engine_outcome.py` /
`test_manifest.py` / `test_watcher_filters.py` (40 passed) cover:
- Successful re-ingestion replaces old chunks only **after** successful embedding.
- Failed re-ingestion leaves old good chunks intact.
- Duplicates identified in the durable ledger (skipped_duplicate).
- Source removal removes only the requested source; BM25 lexical index does not
  go stale (Phase 6H hardening).
No real production knowledge source was touched.

## 12. Secret guard validation (VERIFIED)

`is_secret_bearing()` (app/infrastructure/ingestion/service.py) blocks names
`*.pem / *.key / *.ppk / *.p12 / *.pfx`, `.env`/`.env.*`, and name fragments
(credentials/secret/passwd/shadow/htpasswd) **before any reading/processing**.
Direct check (STEP 10 names):
- Blocked: `.env`, `test.pem`, `dummy.key`, `credentials.txt` (all True).
- Allowed: `note.pdf`, `doc.docx`, `a.md`, `b.txt`, `img.png` (all False).
Tests verify blocked files create **no chunks**, **no KG writes**, and secret
values are **not** present in error/log text (e.g. `.env` with `API_KEY=secret123`
→ error contains "blocked" but not "secret123").

## 13. Vector / KG consistency (VERIFIED)

- Vector store: `data/manifests/vector_store.json` loads cleanly; **195 entries /
  24 distinct sources**; **0 entries** missing/undersized embeddings. No corruption.
- Knowledge graph: `data/manifests/knowledge_graph.json` loads; **387 nodes /
  1464 edges**; **0 orphan edges** (every edge source+target resolves); node
  types: 10 note / 87 concept / 87 definition / 114 entity / 89 topic. No orphan
  explosion.
- Documented known limitation: vector store and KG are **separate persistence
  files** with **non-atomic** writes — a mid-write crash can leave them
  inconsistent (pre-existing, **DEFERRED**, not redesigned this phase).
- Minor/DOCUMENTATION note: KG node `source` metadata contains stale path
  `D:\LLM-Wiki\...` from an older checkout; cosmetic persisted metadata, does
  not affect QA (which uses the vector store's source field).

## 14. Ollama / QA performance sanity (CONDITIONAL)

`ollama ps`: `qwen3:8b` loaded, plus `nomic-embed-text`.
- `OLLAMA_CONTEXT_LENGTH=8192` is correctly persisted (User env + registry).
- **BUT** the currently-running Ollama daemon has qwen3:8b loaded at CONTEXT
  **40960** — a stale model-load predating the env var. Per Phase 6F-D, the
  daemon must be reloaded/restarted to honor 8192. This is **host runtime
  status**, not a repo bug; 6F-D already documented restart as required. The
  earlier live QA run therefore executed at 40960 context (warm, 42.5s).
  **CONDITIONAL** — no code change warranted; a host Ollama restart will honor
  8192. QA deadline (120s wall-clock) remains functional via
  `_generate_with_deadline`.

## 15. CLI contract (VERIFIED)

- `status`: clean truthful labels, correct areas/counts.
- `doctor`: exit 0, one WARN (Tesseract), no tracebacks.
- `ask`: clean labels, correct exit codes, distinct System-facts rendering vs
  retrieved answers, no misleading success, no raw tracebacks.
- `ingest file` / `remove`: covered by lifecycle unit tests (not live-run to
  protect the real corpus). Exit-code / error-label behavior asserted in suite.

## 16. Security / privacy (VERIFIED)

- Network surface limited to: localhost Ollama (`http://localhost:11434`),
  explicit `ingest github`, explicit `ingest youtube`. **No other network
  behavior introduced.**
- No secrets in logs; System Facts responses expose only whitelisted values
  (version, env name, flags, model names, counts); secret-guard tests prove
  secret values never reach error/log text; no credentials returned through QA;
  no private filesystem paths surfaced in system-facts responses.

## 17. Test results (PASS)

- Full unit suite (excluding stale eval): **1583 passed, 1 deselected** — matches
  expected 1558 baseline + 25 System Facts tests.
- Focused: 125 passed (QA workflow + timeout + CLI + system facts); 40 passed
  (ingestion lifecycle + engine outcome + manifest + watcher filters); 7 Secret
  Guard cases pass.
- Ruff on recently-touched files: **12 findings, all LOW/DOCUMENTATION**
  (5 E501 line-too-long, 3 F401 unused import — incl. one in
  `test_system_facts.py`; 2 E501 + 2 I001 in `qa_workflow.py`/`entry.py`
  pre-existing structure). Style-only, **no correctness** issues; not fixed
  (read-only scope).
- `tests/unit/test_eval_dataset.py` unchanged; its known **7 stale failures**
  (v2.0 assertions vs frozen v3.0 dataset) remain, as required.

## 18. Frozen dataset / corpus verification (VERIFIED)

- No modification by this phase to `eval/dataset.json`, `eval/run_eval.py`,
  `eval/results/*`, the real corpus, or runtime manifests. The `eval/*` diffs
  shown by git are **pre-existing** working-tree state from earlier phases
  (already present in STEP 1 before 6I-C); 6I-C added zero changes to tracked
  files. Frozen retrieval files remain byte-identical.

## 19. Issue classification

| # | Issue | Severity | Status | Action |
|---|-------|----------|--------|--------|
| 1 | min_cosine 0.25 (prod) vs 0.45 (eval) | LOW/MEDIUM | CONDITIONAL | Documented; not changed; inconclusive discrepancy |
| 2 | Retrieval FPR (~0.857) | HIGH | DEFERRED | Evidence verification deferred to 6I-C+/V1.1 |
| 3 | Hit@5 / MRR below historical guardrails | MEDIUM | DEFERRED | Not addressed; frozen |
| 4 | Ollama hardware latency (qwen3:8b slow on CPU) | MEDIUM | CONDITIONAL | Known; 8192 config set but stale daemon loads 40960 → restart to honor |
| 5 | `pam remove` exact-ingestion-path limitation | LOW | DOCUMENTATION | Known; not a bug, exact-path design |
| 6 | Vector/KG non-atomic persistence | MEDIUM | DEFERRED | Documented; not redesigned in scope |
| 7 | General semantic evidence verification deferred | HIGH | DEFERRED | Explicitly out of 6I-C scope |
| 8 | Stale eval tests (7 fail / 24) | LOW | DOCUMENTATION | Must remain unchanged |
| 9 | **System Facts router misses "What QA model is PAM using?"** | **HIGH** | **OPEN (genuine bug, unfixed)** | Fix not authorized; fell through to LLM, hung >120s. Recommended 1-line fix in `_match_qa_model` |

## 20. Known limitations (unchanged, all documented)

Min_cosine discrepancy; retrieval FPR unsolved; Hit@5/MRR below guardrails;
Ollama hardware latency; evidence verification deferred; `pam remove` exact-path
limit; non-atomic persistence; stale eval tests; plus Host-unless-restarted
num_ctx (40960 currently) — all carried forward, none new regressions introduced.

## 21. Deferred work

- Full general evidence verifier (V1.1 / post-V1).
- FPR reduction, reranker/HyDE/answerability enablement, corpus/dataset change.
- System Facts QA-model router gap fix (see §19 #9) — requires approval.
- Ollama daemon restart to honor `OLLAMA_CONTEXT_LENGTH=8192` (host action).

## 22. Final V1 readiness decision

**CONDITIONAL — READY WITH DOCUMENTED LIMITATIONS.**

- Application layer is **stable**: 1583 unit tests pass, retrieval frozen, secret
  guard effective, ingestion lifecycle hardened, System Facts working, CLI
  contract clean, no security regressions.
- It does **NOT** mean retrieval is perfect, FPR is solved, factual correctness
  is guaranteed, or evidence verification is solved. Those remain **DEFERRED**.
- The single outstanding genuine bug (System Facts missing the QA-model query)
  is **HIGH** but isolated to one tool-meta phrasing that falls back to normal
  QA (correct but slow) — it does not produce wrong evidence and is not a
  retrieval/corruption/security regression. Recommend fixing before final sign-off.

## 23. Recommended next step

1. **Authorize + apply the minimal System Facts router fix** for
   `"What QA model is PAM using?"` (add conservative `"qa model"` match), then
   re-run the 25 system-facts tests + a smoke query. (Highest priority; genuine
   bug within Phase 6 scope.)
2. Restart the local Ollama daemon so qwen3:8b loads at `num_ctx=8192` (host
   action, honors 6F-D config).
3. Clear the LOW lint findings in the System Facts files (optional housekeeping).
4. Proceed to post-V1 / V1.1 work for FPR, evidence verification, and retrieval
   improvements under a separate, authorized phase.

---

### Labels used
PASS / VERIFIED — proven this phase.
CONDITIONAL — correct but requires an action/state (host restart, config) to be fully realized.
DEFERRED — intentionally not done now.
DOCUMENTATION — noted, no code change required.
HIGH/OPEN — genuine unfixed bug, awaiting authorization.
REJECTED / BLOCKED — none this phase.
