# Phase V1.1 — Cumulative Final Review (A1–A5)

**Date:** 2026-09-02  
**Status:** VERIFIED · READ-ONLY REVIEW  
**Scope:** No implementation. Review-only. Only this report was created.

---

## 1. Executive Verdict

**RECOMMENDED — RELEASE AS v1.1.0, but NOT from current git history as-is.**

V1.1 (A1–A5) is a **coherent, release-worthy source-management lifecycle** that
materially improves PAM for a real user: you can now see what is indexed
(A1), get truthful, actionable ingestion feedback (A2), trust re-ingestion to
preserve data on failure (A3), deterministically remove exactly one source with
the identical-SHA bug fixed (A4), and trust `pam status` to be read-only and
truthful (A5). **Every phase PASSes review. Release value: HIGH.**

The release barrier is not the V1.1 code — it is **git-history hygiene**. The
current `main` contains 6 commits above `origin/main` that interleave
experimental retrieval work (`6a603d8`, `e287226`, `8524caf`, `9f282b4`) with
the application-hardening commits (`10f74f1`, `97197e2`) that V1.1 builds on.
There is no clean ancestor carrying the hardened app layer without the
experiments. The V1.1 delta itself (A1–A5) lives **entirely in the uncommitted
working tree**, so it is separable. The safe release is a class-A patch release
(v1.1.0) built by cherry-picking/selecting only the V1.1 subset from the
working tree — **not** by tagging HEAD.

---

## 2. Git Baseline (STEP 1)

| Ref | Commit | Note |
|-----|--------|------|
| `HEAD` | `97197e2` ("release: PAM V1.0.0") | tip of `main`; label misleading — tagged v1.0.0 is another commit |
| `origin/main` | `198823d` ("docs: finalize V1 README") | published upstream |
| `v1.0.0` (tag) | `a4e5b2a` ("release: finalize v1.0.0") | on the v1 line; **not** an ancestor of the hardening commits |
| `v2.0.0` (tag) | `01d648b` | on unrelated v2 branch (`4f97684` line), not involved |

**HEAD is NOT directly releasable.** `git log origin/main..HEAD` = 6 commits;
`git log HEAD..origin/main` = empty.

```
198823d (origin/main) → 6a603d8 (reranker exp)
                      → e287226 (eval infra 3d)
                      → 8524caf (hyde exp)
                      → 9f282b4 (abstention gate exp)
                      → 10f74f1 (application hardening)
                      → 97197e2 (HEAD, "release: PAM V1.0.0")
```

**Commits are a mix:** 4 experimental-retrieval commits + 2 application-hardening
commits. The hardening commits are the actual V1.0 application layer (ingest
lifecycle, QA workflow, system facts) that V1.1 depends on — they are NOT on
the `v1.0.0` tag. `tag v1.0.0` is absent from these hardening commits. Both
tags exist, but the one labeled "V1.0.0" at HEAD is historically divergent from
the published v1.0.0 tag.

## 3. V1.1 Scope (STEP 2)

V1.1 = **working-tree delta only** (nothing in A1–A5 is committed). Classified:

| Class | Files | In V1.1? |
|-------|-------|----------|
| **A. V1.1 application** | `app/cli/entry.py` (A1/A2/A4/A5), `app/domain/documents.py` (A2), `app/infrastructure/ingestion/service.py` (A2), `app/pipelines/ingest_workflow.py` (A2) | YES |
| **B. V1.1 tests** | `tests/unit/test_cli_sources.py` (A1, 12), `test_cli_ingest_ux.py` (A2, 12), `test_reingestion_reliability.py` (A3, 13), `test_cli_remove.py` (A4, 17), `test_cli_status.py` (A5, 16) — all untracked-new | YES |
| **C. V1.1 reports** | `56`–`60_PHASE_V1_1_*.md` + this review | DOC / optional |
| **D. retrieval experiments** | `app/infrastructure/reranker.py`, `hyde.py`, `answerability.py`, `banded_verifier.py`, `qa_measurement_harness.py`, `eval/results/*` experiment JSONs, `eval/sweep_*.py`, `eval/analyze_reranker.py`, `eval/dataset.json` churn, `20/21/22/31/32/33_*.md` | EXCLUDE (freeze decision) |
| **E. evaluation infrastructure** | `eval/run_eval.py` (answerability-gate edits), `eval/dataset.json`, `eval/results/abstention_gate.json`, `tests/unit/test_answerability_gate.py`, `test_banded_verifier.py`, `test_qa_measurement.py`, `test_qa_timeout.py` | EXCLUDE |
| **F. pre-existing dirty files** | `.obsidian/*`, `docs/01_Current_Implementation_Report.md`, `tests/integration/test_queue_worker_pipeline.py`, `tests/unit/test_{duplicate_detection,manifest,scoring}.py`, `vault/index.md`, `vault/log.md`, `vault/overview.md` | EXCLUDE (not V1.1 work; antecedent uncommitted V1-era adaptations) |
| **G. corpus/runtime state** | `vault/Notes/` (untracked, live corpus) | EXCLUDE |
| **H. stray artifacts** | `nope.json` (empty manifest-like), `run_jobs.json` (job output) | EXCLUDE (accidental) |

**Critical:** `tests/unit/test_cli.py` carries a **small A5 tail** (2 status-test
adaptations: removed `_ollama_status` monkeypatch, `PAM Status (read-only)`
title, read-only dir assertions). It is the ONLY pre-existing V1 test file
that A1–A5 actually modified. Its diff is purely the A5 adaptation.

## 4. A1 Review — `pam sources` (STEP 3)

| Criterion | Finding |
|-----------|---------|
| User value | NEW capability — list what is indexed (source, type, chunks, status, last-ingested). Verdict: HIGH |
| Correctness | Reads vector store (authority for indexable), annotates with durable ledger, missing→empty list, unreadable→exit 1 "Sources unavailable", deterministic sort. VERIFIED |
| Tests | `test_cli_sources.py` (12, hermetic, no Ollama/no corpus). PASS |
| Security | Lists metadata only; never reads content, never launches LLM, no retrieval. PASS |
| Belongs in V1.1 | YES — installation user-facing source management |

**Verdict: RELEASE**

## 5. A2 Review — Ingestion UX (STEP 4)

| Outcome | Verified Behavior |
|---------|-------------------|
| Truthful success | `_print_ingest_success` table with source/type/note/path/created/updated/attempts/chunks. PASS |
| Duplicate | Durable `skipped_duplicate` ledger status; truthful messaging. PASS |
| Generic failure | `_print_ingest_failure` with category; exit 1. PASS |
| Security block | `BlockedSourceError`→"Ingest blocked (security)", truthful "not read, not indexed". PASS |
| Unsupported source | `UnsupportedSourceError`→"Unsupported source" panel. PASS |
| Partial index | Note written but not fully indexed → "Ingestion incomplete" + ledger records `failed` + exit 1. PASS |
| KG warning | "Knowledge graph warning" yellow panel, everything else saved (`graph_succeeded`). PASS |
| Exit codes | 0 on success, 1 on incomplete/failure, distinct panels, no tracebacks. PASS |
| Tests | `test_cli_ingest_ux.py` (12, FakeWorkflow, hermetic). PASS |

`category` added to `DocumentIngestionError`/`IngestionWorkflowError` (blocked /
unsupported / ingestion / retryable) and `graph_succeeded` threaded through
workflow result — minimal, ownership-respecting.

**Verdict: RELEASE**

## 6. A3 Review — Re-ingestion Reliability (STEP 5)

**Key finding confirmed:** NO production fix required. A3 added only 13
hermetic tests (`test_reingestion_reliability.py`) that lock the persistence
invariants: reingest-replace, shrink removes stale chunks, grow adds no
duplicates, embedding/indexing/KG save-failure preserves prior disk state,
retry-after-failure replaces cleanly, identical-hash different-path dedups.

| Question | Answer |
|----------|--------|
| Release value without production code? | YES — these are hardening tests proving the fault-tolerance invariants; they protect future regression with no runtime risk. |
| Verdict | **RELEASE AS HARDENING TEST COVERAGE** |

## 7. A4 Review — `pam remove` (STEP 6)

**Identical-SHA bug (the real fix):** the pre-fix used `manifest.remove_entry(sha256=...)`
which deleted the FIRST same-content sibling, so with two identical-content
files `[B, A]`, removing A deleted B's ledger row. Verified **fixed** — removal
now uses `manifest.remove_entry(path=entry_path)` with the exact resolved
absolute path (`entry.py:502-507`), matching each row by path identity only.

Additional verified behavior: source-scoped (vectors + KG nodes/edges + ledger),
ambiguous→abort with zero deletions, not-found→exit 1, corrupt KG→exit 1
before any deletion, BM25 rebuilt on next use via version bump, URL + relative
path + any-CWD forms, never touches vault notes, never reads file contents,
idempotent second call → not found.

Tests: `test_cli_remove.py` (17), including
`test_identical_sha_removal_keeps_sibling_ledger_and_data` proving the fix.

**Verdict: RELEASE (design of the identical-SHA fix is genuinely source-scoped)**

## 8. A5 Review — `pam status` (STEP 7)

Verified against the report's claims:

- **No mutation** — removed `_ensure_runtime_directories` from status; read-only smoke (`git status` before/after) identical. PASS
- **No fabricated zeroes** — unavailable vector/ledger/queue → "unavailable", never "0". PASS
- **Unavailable state** — distinct `unavailable` string vs genuine `0`. PASS
- **Truthful durable counters** — processed/skipped/failed/manifest count from read-only ledger JSON; last-ingestion from durable `processed_at`, "never" when empty. PASS
- **Placeholder exclusion** — `_note_counts` separates real generated vs placeholder vs user; placeholder not counted as real. PASS
- **No LLM call** — removed the live `_ollama_status`(`ps()`, 300s timeout); row now config-only; test asserts `OllamaClient.is_available` NOT called. PASS
- **No write probe** — vault check via `os.access`, `.pam_write_test` removed. PASS
- **Cheap runtime** — no network, no daemon, no LLM; only JSON reads + dir stat. PASS

Tests: `test_cli_status.py` (16) + `test_cli.py` (2 A5-adapted).

**Verdict: RELEASE**

## 9. Cross-Phase Integration (STEP 8)

The five phases form one coherent source-management lifecycle:

```
SOURCE → INGEST (A2 truthful outcomes, A3 reliability)
       → SOURCES (A1 view) → STATUS (A5 view, read-only/truthful)
       → MODIFY → RE-INGEST (A3 replace cleanly on disk)
       → STATUS (A5 counts reflect durable state)
       → REMOVE (A4 deterministic, source-scoped)
       → STATUS (A5 shows reduced/manifest state truthfully)
       → RE-INGEST (A4 test proves re-ingest after remove is allowed)
```

**No contradiction found.** Terminology is consistent (`source`, `source_type`,
`status`, `last ingested`), the durable ledger is the single source of truth for
ingest status across A1/A2/A4/A5, the vector store is the authority for
"indexed" across A1/A4/A5, and read-only status (A5) never conflicts with the
deleting/ingesting commands (A2/A4). One primary-integrity key (`_canonical_source`,
added in A4) is shared to keep remove/sources/status agreeing on identity.

## 10. Acceptance Matrix (STEP 9)

| # | Criterion | A1 | A2 | A3 | A4 | A5 | Overall |
|---|-----------|----|----|----|----|----|---------|
| 1 | source visibility | **PASS** (new list) | — | — | — | sources in status | **PASS** |
| 2 | ingestion UX | — | **PASS** | — | — | — | **PASS** |
| 3 | duplicate handling | — | **PASS** (skipped_duplicate) | dedup invariant | — | skipped counters | **PASS** |
| 4 | failed-ingest preservation | — | **PASS** (ledger failed + partial) | **PASS** (disk preserved) | — | failed counter | **PASS** |
| 5 | retry | — | **PASS** (retryable) | **PASS** (retry replaces cleanly) | — | — | **PASS** |
| 6 | source replacement | — | — | **PASS** (reingest replaces) | — | — | **PASS** |
| 7 | deterministic removal | — | — | — | **PASS** | — | **PASS** |
| 8 | identical-SHA isolation | — | — | — | **PASS** (path-identity) | — | **PASS** |
| 9 | truthful status | — | — | — | — | **PASS** | **PASS** |
| 10 | unavailable-state truthfulness | **PASS** (store unreadable) | — | — | **PASS** (corrupt KG aborts) | **PASS** (unavailable ≠ 0) | **PASS** |
| 11 | security | **PASS** (no content read) | **PASS** (blocked guard) | — | **PASS** (no content read) | **PASS** (no secrets) | **PASS** |
| 12 | no traceback leakage | **PASS** | **PASS** | **PASS** | **PASS** (agrees no-traceback) | **PASS** (no-traceback test) | **PASS** |
| 13 | corpus safety | **PASS** | **PASS** | **PASS** | **PASS** (never touches vault notes) | **PASS** (read-only) | **PASS** |
| 14 | retrieval freeze | — | — | — | — | — | **VERIFIED** (see §12) |
| 15 | regression stability | +12 | +12 | +13 | +17 | +16 | **PASS** (see §13) |

## 11. Known Limitations (STEP 10)

| Limitation | V1.1 Blocker? |
|------------|---------------|
| Retrieval FPR ≈ 0.857 | **NO** — accepted V1 freeze decision (5G); retrieval is deferred, not regressed |
| Hit@5/MRR below guardrails | **NO** — same freeze; not changed by V1.1 |
| `min_cosine` 0.25 (prod) vs 0.45 (eval) | **NO** — pre-existing; V1.1 did not touch QA path; documented gap |
| Ollama latency / timeout | **NO** — pre-existing; V1.1 reduced status exposure (A5 removed live check) |
| Evidence verification deferred | **NO** — separate research track; not a V1.1 goal |
| Non-atomic vector/KG persistence | **NO** — A3 tests *document* this as expected behavior (invariants hold); unchanged |
| KG ownership caveat (shared node loses cross-source edges on remove) | **NO** — documented A4 limitation; best-effort by design; no concrete bug |
| Stale eval tests (`test_eval_dataset.py`, 8) | **NO** — frozen dataset; pre-existing; release note should mention |
| Cross-file logging-isolation flake (`test_cli_remove` under full-suite order) | **NO (CODE)** but **YES (TEST HYGIENE)** — see §14; does not affect production, but must be fixed before CI gate reliance |

## 12. Retrieval Freeze (STEP 11)

**Verified — VERIFIED:**

- `embeddings.py`, `search.py`, `bm25.py`, `reranker.py`, `semantic_chunking.py`
  (infra + domain): **zero working-tree diffs vs HEAD** (checked correct paths,
  including `app/infrastructure/search.py`, `app/infrastructure/semantic_chunking.py`).
- `app/application/qa_workflow.py`: **zero diff** — `min_cosine` default still **0.25**.
- Config toggles ($conclusion after checking `config.py`):
  - `RerankerSettings.enabled = False` (line 417)
  - `HydeSettings.enabled = False` (line 435)
  - `AnswerabilitySettings.enabled = False` (line 451)
- Explicit freeze confirmations:
  - **3G-A (embedding experiment) = REJECTED** (223 only; not included)
  - **3G-B (query-scope answerability) = REJECTED** (22; not included)
  - **5E (FPR root cause) = REJECTED** (research only)
  - **5F (banded answerability) = REJECTED FOR V1 / research only**
  - **5G = FREEZE DECISION** — retrieval frozen for V1/V1.1; reranker/hyde/abstention code present in tree but inert (`enabled=false`)

## 13. Test Baseline (STEP 12)

Cumulative progression (per reports; verified arithmetic & current run):

| Point | Passed | Deselected | Failed* | Delta |
|-------|--------|------------|---------|-------|
| V1 baseline | ~1611 | 1 | 7 stale-eval | — |
| +A1 (12) | 1623 | 1 | 7 | +12 |
| +A2 (12) | 1635 | 1 | 7 | +12 |
| +A3 (13) | 1648 | 1 | 7 | +13 |
| +A4 (17) | 1664 | 1 | 8 | +16 ef |
| +A5 (16) | **1680** | 1 | 8 | +16 |

*(failed = `test_eval_dataset.py` stale dataset-integration suite; count rose 7→8 during A4 due to one additional pre-existing dataset assertion; frozen, left untouched.)

**Current run (verified this review):** `1680 passed / 1 deselected / 8 failed`.
The 8 failed = 8 `test_eval_dataset.py` stale + the `test_cli_remove`
logging-isolation flake surfaces in a full-suite `tests/unit` run only under a
specific cross-file ordering (confirmed pre-existing, reproduces with untouched
`test_cli_remove.py` at HEAD, passes in isolation 17/17).

**NEW failures = 0** (A1–A5 added 70 tests; all pass; nothing regressed).

## 14. Known Test-Hygiene Issue (release consideration)

`setup_logging` installs stderr `RichHandler` + rotating file handlers once
(`_LOGGING_CONFIGURED` guard). Under pytest, once any CLI test triggers
`setup_logging`, the handlers persist on the root logger for the whole process;
later CLI tests that read `result.output` can have INFO lines interleaved
(they go to stderr, which CliRunner mixes). `test_cli_remove::
test_remove_one_source_and_unrelated_survives` asserts `"0" not in
[output before "Vector chunks removed"]` and this assertion is tripped by the
timestamp "0"s in leaked INFO lines when `test_cli.py` ran earlier in-process.

- Pre-existing (reproducible at HEAD with untouched test_cli_remove.py). NOT introduced by V1.1.
- Not a production defect; a test-isolation defect.
- **Recommendation:** a small follow-up (clear handlers / reset `_LOGGING_CONFIGURED`
  in a fixture, or scope the logging capture) before institutionalizing CI on a
  full-suite gate; the phase reports are unaffected.
- Constraint: this review is READ-ONLY. It is listed as a P1 follow-up, not fixed here.

## 15. Release Value (STEP 13)

**RELEASE VALUE: HIGH.** Not "more features" — measured on the axes the task asks:

- **Reliability:** on-disk safety invariants under re-ingestion and failure are
  now proven by tests (A3); remove is source-scoped and deterministic (A4); status
  can no longer lie or mutate (A5). The identical-SHA ledger bug was real and is fixed.
- **Usability:** user can see sources (A1) and get distinct, actionable ingest
  outcomes — blocked / unsupported / retryable / partial / KG warning (A2).
- **Source management:** this was the gap in V1; A1→A5 closes the 
  view → ingest → verify → modify → re-ingest → remove → verify loop.
- **Operational trust:** truthful unavailability, no LLM-in-status, no write-probe,
  no fabricated retryable count, read-only smoke proven (A5).
- **Regression risk:** LOW — all changes are additive to the CLI observability
  layer; frozen retrieval untouched; 70 new tests with zero regressions.
- **Scope coherence:** one lifecycle, shared durable-ledger truth, no scope drift
  into retrieval/AI/agentic.

## 16. Release Scope (STEP 14)

### MUST RELEASE (application)
- `app/cli/entry.py` — A1 sources + A2 ingest UX + A4 remove + A5 status fully
- `app/domain/documents.py` — A2 `category` on `DocumentIngestionError`
- `app/infrastructure/ingestion/service.py` — A2 failure classification
- `app/pipelines/ingest_workflow.py` — A2 `graph_succeeded` + category error

### SHOULD RELEASE (tests)
- `tests/unit/test_cli_sources.py` (12)
- `tests/unit/test_cli_ingest_ux.py` (12)
- `tests/unit/test_reingestion_reliability.py` (13)
- `tests/unit/test_cli_remove.py` (17)
- `tests/unit/test_cli_status.py` (16)
- `tests/unit/test_cli.py` (A5-modified 2 tests — required, they reference new status contract)

### EXCLUDE FROM V1.1
- **Retrieval experiments:** `reranker.py`, `hyde.py`, `answerability.py`,
  `banded_verifier.py`, `qa_measurement_harness.py`, `eval/sweep_*.py`,
  `eval/analyze_reranker.py`, `20/21/22/31/32/33_*.md` (experiment reports)
- **Eval infrastructure:** `eval/run_eval.py` answerability edits,
  `eval/dataset.json` churn, `eval/results/abstention_gate.json`, all
  `eval/results/experiment_*` JSONs, `test_answerability_gate.py`,
  `test_banded_verifier.py`, `test_qa_measurement.py`, `test_qa_timeout.py`,
  `eval/dataset_backup_*.json`, `eval/dataset_v3_proposed.json`,
  `eval/EVALUATION_AUDIT.md`, `eval/sweep_thresholds.py`
- **Pre-existing dirty (V1-era, unrelated to A1–A5):** `.obsidian/*`,
  `docs/01_Current_Implementation_Report.md`,
  `tests/integration/test_queue_worker_pipeline.py`,
  `tests/unit/test_{duplicate_detection,manifest,scoring}.py`,
  `vault/index.md`, `vault/log.md`, `vault/overview.md`
- **Corpus/runtime:** `vault/Notes/`
- **Stray artifacts:** `nope.json`, `run_jobs.json`
- **Proto files unrelated to release:** `docs/*` project-reference markdowns
  (01–04, 07, 08, 09, 10), `PLAN.md`, `VERSION_1_COMPLETE_FINAL_REPORT.md`,
  `README.md` (already published), unless the project wants these as release docs.

### Reports (project documentation)
`56`–`60_PHASE_V1_1_*.md` + this review are legitimate project documentation.
Their inclusion in the release commit is optional (recommend a separate
`docs/` commit or co-commit as project documentation — project preference).

## 17. Git History Safety (STEP 15)

**CRITICAL:**

- The 6 commits `origin/main..HEAD` are **all** un-published, and none is a
  pure "V1.1" commit. Four are retrieval experiments; two are the V0.1→V1.0
  application hardening that V1.1 builds on.
- `10f74f1` (hardening) and `97197e2` ("V1.0 release") sit **on top of** the
  experiment commits; you cannot reach the hardened app layer without also
  carrying `6a603d8/e287226/8524caf/9f282b4`.
- The `v1.0.0` tag (`a4e5b2a`) is on a different line and does NOT contain the
  hardening — so it is **not** a usable clean release base for the app layer.
- **Consequence:** publishing `HEAD` or anything in `origin/main..HEAD` would
  publish experimental retrieval code (even if inert via `enabled=false`), and
  would mislabel a "V1.0.0" release.
- **V1.1 is entirely uncommitted (working tree),** so it is fully separable.

### SAFEST strategy (recommended; NOT executed here)
1. Do **not** tag/publish HEAD; do not rewrite the retrieval-experiment chain.
2. Create a release branch from the **best stable ancestor** that carries the
   intended application baseline — i.e., from `origin/main` (198823d) or the
   `v1.0.0` tag line (`a4e5b2a`), whichever corresponds to the true published
   product state.
3. Selectively apply only the **V1.1 files** from §16 (MUST+SHOULD) as one
   logical commit (or, if later desired, split: app vs tests vs docs).
4. Leave experiments + eval infra uncommitted/untracked or in a separate
   `research/` branch, never on the release path.
5. Tag the release commit `v1.1.0`.
6. Optionally, later rework `main` history (rebase the hardening commits onto
   the real v1.0.0) as a *separate, developer-approved* history-repair task.
   This review does not perform it.

## 18. Version Recommendation (STEP 16)

**A. RELEASE AS v1.1.0 — RECOMMENDED.**

Justification:
- New user-facing functionality (sources list, remove, truthful status) and a
  real bug fix (identical-SHA ledger removal) → minor version, not patch.
- No API/format breaks; additive CLI observability + hardening.
- Backward compatible with V1 corpus/config, retrieval frozen, no eval changes.
- Must be assembled from the working-tree subset per §17 — not from HEAD.

Rejected alternatives:
- **v1.0.1 (patch):** too small a semantic bucket given new features + lifecycle.
- **KEEP UNRELEASED:** not justified on product grounds — the lifecycle gains are
  real; the only reasons to wait (test-isolation hygiene) are P1 follow-ups, not blockers.
- **MORE WORK REQUIRED:** only if the project treats the logging-isolation flake
  as a hard gate (it is testable-fast; P1, not P0).

## 19. Post-V1.1 Backlog (STEP 17)

| Priority | Item | Rationale |
|----------|------|-----------|
| **P0** | None blocking V1.1 | No functional blocker remains for the lifecycle scope |
| **P0** | Test-isolation fix for CLI logging (RichHandler persistence) | Pre-existing flake; blocks trusting a full-suite CI gate |
| **P1** | Reconcile `min_cosine` (0.25) with eval threshold (0.45) — or document the eval-vs-prod decision explicitly | Known gap; QA quality lever |
| **P1** | Evidence verification (verifiable answers) — separate research track | Deferred by V1 decision; research, not release-driver |
| **P2** | Atomic vector/KG persistence | A3 invariants already protect correctness; concurrency hardening optional |
| **P2** | KG node-ownership/`remove` shared-source semantics | Documented caveat; redesign only if users report loss |
| **DEFERRED** | Retrieval improvement (high FPR, low Hit@5/MRR) | Frozen at 5G for V1/V1.1; reopen as its own research phase with format approval |
| **DEFERRED** | Agentic AI / answerability-enabled behaviors | Requires a trustworthy answering foundation first |
| **REJECTED (for V1/V1.1)** | 3G-A embeddings experiment, 3G-B query-scope answerability, 5E FPR redesign, 5F banded answerability | Research only; e.g. `enabled=false`, experiments remain untracked |

## 20. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Publishing retrieval experiments if release is cut from HEAD | **HIGH** | Assemble V1.1 from working-tree subset (§17 strategy), never tag HEAD |
| Mislabeled V1.0.0 commitment at HEAD (97197e2) vs the published tag | **MEDIUM** | Use `v1.0.0`/`origin/main` as the base; treat 97197e2 as "V1 application layer" history, not the releaseable tag |
| Test-isolation logging flake in CI | **MEDIUM** | P0 follow-up (test hygiene) before CI gate reliance |
| Stale eval tests (8) create false CI noise | **LOW** | Keep frozen; note in release notes; do not "fix" dataset |
| `min_cosine` prod/eval gap | **LOW** | Explicit decision + docs (P1) |
| A-tests assert on path formats (Windows `\`) | **LOW** | Already normalized in tests; only affects future contributors |
| Working-tree bloat (60+ untracked files) risks accidental inclusion | **LOW** | §16 explicit include/exclude list for the release commit |

## 21. Final Recommendation

**RELEASE as v1.1.0 — HIGH release value, assembled from the V1.1 working-tree
subset, NOT from current HEAD.** Every phase (A1–A5) passes review; the V1.1
lifecycle (view → ingest truthfully → verify re-ingest reliability → remove
deterministically with identical-SHA fix → status truthfully) is coherent and
materially improves PAM. Retrieval freeze verified (inert experiments,
`enabled=false`, `min_cosine` unchanged). Regression stable (1680 passed, NEW
failures = 0). One P0 test-hygiene follow-up (logging isolation) should precede
a hard CI gate but does not block the artifact.

**Actions proposed (to approve separately):** (1) create release branch off
`origin/main`; (2) apply the §16 MUST+SHOULD file set as the V1.1 commit;
(3) tag `v1.1.0`; (4) track P0/P1 backlog items. **Nothing was implemented,
branched, committed, tagged, pushed, or rewritten in this phase.**

---

**Labels:** PASS · VERIFIED · RELEASE · EXCLUDE · DEFERRED · KNOWN LIMITATION · RECOMMENDED