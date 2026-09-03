# PAM V1.1.0 — Release Provenance / Dependency Audit (READ-ONLY, Definitive)

- Date: 2026-09-02
- Mode: strictly read-only. No production/test/config code modified; no
  branch/commit/tag/push/stash/reset/clean/rebase/merge/cherry-pick; main
  working tree untouched; only scratch worktrees in a temp dir, removed at end.
- Report file written: `62_PHASE_V1_1_RELEASE_PROVENANCE_AUDIT.md` (this file).

---

## 1. Executive Verdict

**The approved release recipe "origin/main + ONLY the §16 A1–A5 files" is
definitively unimplementable. A coherent, independently reproducible V1.1.0
source tree exists, but it requires:**

1. **a base of the committed HEAD tree `97197e2`** (NOT `origin/main`), and
2. **committing the currently-untracked runtime module
   `app/infrastructure/answerability.py`** (or performing a small import
   decoupling refactor), and
3. **shipping the committed, config-frozen experiment modules** (`reranker.py`,
   `hyde.py`) as inert-with-`enabled=false` code — they cannot be excluded
   without altering the hardening layer that A1–A5 sit on.

The smallest tree that reproduces the reviewed A1–A5 state is:

> **`97197e2` committed tree + `app/infrastructure/answerability.py` + the
> §16 A1–A5 file set (4 app + 6 test files).**

This tree (evaluated as "Candidate C") imports successfully, collects the
full unit suite (1662/1719, 57 deselected, 0 errors), and A1–A5 tests run
**98/99 pass** — the single failure being the known pre-existing P0 logging
flake (`test_cli_remove.py::test_remove_one_source_and_unrelated_survives`),
identical to the reviewed working-tree behavior.

**The release is blocked on a decision, not on missing evidence:** commit the
untracked `answerability.py` (frozen-off) and release from `97197e2`, or
perform the explicit import decoupling refactor and only then assemble. The
§16 recipe sent in the cumulative review (`61`) cannot be executed as written.

---

## 2. Current Git State (verified)

| Ref | SHA | Status |
|---|---|---|
| `origin/main` | `198823d267cb4456b6edf9cc12298a06724ab164` | unchanged |
| `main` (HEAD) | `97197e2876505dec0fdefe5846504ea9d0d5668d` | unchanged |
| `v1.1.0-release` | `198823d267cb4456b6edf9cc12298a06724ab164` | empty branch, still == origin/main |
| `v1.0.0` (annotated tag) | `a4e5b2abb0c60e865da878e291baa04d3535a587` | untouched |
| `v2.0.0` (annotated tag) | `4f9768437edc142487826ccdc2070977fdd05e40` | untouched |
| working tree | dirty (pre-existing V1-era + A1–A5) | untouched by this audit |

`stash@{0}` present and untouched. `git worktree list` = single main.

---

## 3. Commit Provenance Table

All six commits `198823d` → `97197e2`, classified from actual diffs.

| Commit | Message | Files/areas | Purpose | Classification |
|---|---|---|---|---|
| `6a603d8` | feat: add experimental cross-encoder reranking | `app/application/qa_workflow.py` (+154), `app/core/config.py` (+20), `app/infrastructure/reranker.py` (+202 NEW), `app/infrastructure/search.py` (+42), `config/default.yaml` (+8), `eval/analyze_reranker.py`, `eval/run_eval.py`, `eval/sweep_*.py`, `tests/unit/test_reranker.py` (+362) | Cross-encoder re-ranker experiment; **introduces reranker import into production** `qa_workflow.py`/`search.py` | **C** (retrieval experiment) — seeds entanglement |
| `e287226` | feat: expand evaluation infrastructure for phase 3d | `eval/dataset.json` (+1793), `eval/dataset_v1_frozen.json`, `eval/backward_compat_check.py`, `eval/ground_truth_audit.py`, `eval/results/*.json`, `tests/unit/test_eval_dataset.py` (+335) | Eval infrastructure & frozen eval dataset | **D** (evaluation infrastructure) |
| `8524caf` | feat: fix bm25 abstention override and add experimental hyde | `app/application/qa_workflow.py` (+8), `app/core/config.py` (+16), `app/infrastructure/hyde.py` (+65 NEW), `app/infrastructure/search.py` (+31), `config/default.yaml` (+5), `tests/unit/test_hyde.py` (+152), `tests/unit/test_qa_workflow.py`, `tests/unit/test_reranker.py` | HYDE experiment + BM25 abstention fix; **introduces HydE usage in production search.py** (lazy import) | **C** (retrieval experiment) |
| `9f282b4` | feat: evaluate cross-encoder abstention gate | `app/application/qa_workflow.py` (43 lines), `config/default.yaml` (2), `eval/results/phase_3f_sweep.json`, `eval/sweep_3f.py`, `tests/unit/test_reranker.py` | Abstention-gate eval sweep | **C/D** (experiment + eval) |
| `10f74f1` | feat: harden application layer and ingestion lifecycle | 23 files: `app/application/qa_workflow.py` (+348), `app/cli/entry.py` (+430), `app/core/config.py` (+33), `app/core/logging.py`, `app/domain/knowledge_graph.py`, 4 ingestors, `app/infrastructure/ingestion/service.py` (+37), `app/infrastructure/state/manifest.py` (+55 — adds `is_successful_status`, `contains_successful_hash`, `add_failed_file`), `app/infrastructure/vector_store.py` (+16), `app/pipelines/ingest_workflow.py` (+114), `app/prompts/qa.py`, `app/queue/worker.py` (+78), `config/default.yaml`, pyproject/requirements (+docx/pptx/xlsx/rtf deps), tests | **Application hardening + ingestion lifecycle — the layer A1–A5 sit on.** **CRITICAL: in the same commit, the qa_workflow.py change adds `from app.infrastructure.answerability import …` (module-level) while `answerability.py` is never committed.** | **A** (stable app foundation) **MIXED** with C (imports experiments) |
| `97197e2` | release: PAM V1.0.0 | `app/application/qa_workflow.py` (+25), `app/application/system_facts.py` (+302 NEW), `app/cli/entry.py` (+12), `app/infrastructure/state/models.py` (+32), tests (+785) | V1.0.0 release commit; adds system_facts layer. Retains untracked answerability import. | **A** (release commit) — seals entanglement |

**Six-commit range file delta summary (`git diff --name-status 198823d..97197e2`):**
54 files: 24 added (13 eval/experiment, 4 docs, 4 tests, 3 app), 30 modified
(25 app-layer + config + deps, 2 eval, 3 tests).

Key per-file attribution (shared files hardened AND experiment-modified):

| File | Touched by | Entanglement |
|---|---|---|
| `app/application/qa_workflow.py` | 6a603d8, 8524caf, 9f282b4 (experiments) + 10f74f1, 97197e2 (hardening) | **MIXED** — hardening imports answerability (uncond, line 34) + reranker (uncond, line 42) |
| `app/core/config.py` | 6a603d8, 8524caf (experiments) + 10f74f1 (hardening) | MIXED — settings classes only; no import-time dependency |
| `app/infrastructure/search.py` | 6a603d8, 8524caf (experiments) | EXPERIMENT — HyDE use is **lazy import** inside `from_settings` (lines 288–289), NOT import-time → removable |
| `config/default.yaml` | all 4 experiments + 10f74f1 | MIXED — flags only, `enabled=false` |
| `tests/unit/test_cli.py` | 10f74f1 (hardening, +418) + working-tree A5 changes | A1–A5 file sits on hardened CLI contract |

---

## 4. Application Dependency Graph

```
app.cli.entry
  ├─ app.application  ->  app.application.qa_workflow                 [HARDENED]
  │       ├─ app.application.system_facts                            [97197e2, V1 foundation]
  │       ├─ app.core.config                                         [hardened settings]
  │       ├─ app.core.logging
  │       ├─ app.infrastructure.llm
  │       ├─ app.infrastructure.search  (SearchHit, SearchService)
  │       │     ├─ app.domain.vector_store, app.infrastructure.bm25
  │       │     ├─ app.infrastructure.vector_store, app.infrastructure.embeddings
  │       │     └─ app.infrastructure.hyde        [EXPERIMENT — LAZY import, gated enabled=false]
  │       ├─ app.infrastructure.answerability      [EXPERIMENT — UNCOND import, UNTRACKED, gated]
  │       ├─ app.infrastructure.reranker           [EXPERIMENT — UNCOND import, committed, gated]
  │       └─ app.prompts.qa
  ├─ app.core.config / app.core.logging / app.domain.knowledge_graph
  ├─ app.infrastructure.llm / app.infrastructure.search
  ├─ app.infrastructure.state.manifest -> state.hashing, state.models
  ├─ app.infrastructure.vector_store
  ├─ app.pipelines -> app.pipelines.ingest_workflow
  ├─ app.queue / app.watcher
```

### Dependencies absent from origin/main → provenance

| Module | First commit | Git status | Prod imports | Tests import | Runtime-required | Retrieval? | Eval-only? | Foundation? | Required by A1–A5 |
|---|---|---|---|---|---|---|---|---|---|
| `app/infrastructure/answerability.py` | **never committed** | UNTRACKED | YES (qa_workflow.py:34, module-level) | YES (own tests, `test_system_facts.py` docstring refs) | **YES at import time** (uncond); inert at runtime (`enabled=false`) | YES (Phase 3G-B/6C gate) | NO | intention unclear | transitively YES (import forced) |
| `app/infrastructure/reranker.py` | 6a603d8 | COMMITTED | YES (qa_workflow.py:42, module-level) | YES (test_reranker.py) | YES at import time (uncond); inert at runtime (`enabled=false`) | YES | partially | NO | transitively YES |
| `app/infrastructure/hyde.py` | 8524caf | COMMITTED | YES (search.py — **lazy**, inside `from_settings`) | YES (test_hyde.py) | **NO** — lazy import, requires `settings.hyde.enabled` | YES | NO | NO | NO (not at import time) |
| `app/infrastructure/system_facts.py`* | 97197e2 | COMMITTED | YES (qa_workflow.py:33) | YES | YES | NO | NO | YES | YES (production layer) |
| `app/infrastructure/state/manifest.py` newer symbols | 10f74f1 (`is_successful_status`, `contains_successful_hash`, `add_failed_file`) | COMMITTED at HEAD | YES (entry.py:28) | YES | YES | NO | NO | YES | **YES — A1–A5 depend (is_successful_status)** |
| `app/application/qa_workflow.py` newer symbols | 10f74f1/97197e2 (`QAEmptyAnswerError`, `QATimeoutError`, `QAError`, `ObservationTelemetry`, `extract_citations`, …) | COMMITTED at HEAD | YES | YES (test_cli.py:12) | YES | NO (the QA pipeline itself) | NO | YES | **YES — A1–A5 depend (QAEmptyAnswerError/QATimeoutError)** |

\* `system_facts.py` (Phase 6I-B system facts layer) is a genuine V1.0.0 release
component; it reads the same settings flags (`reranker.enabled`,
`hyde.enabled`, `answerability.enabled`) as feature-report strings but imports
nothing from the experiment modules at module level.

---

## 5. Untracked-Module Audit

`git ls-files --others --exclude-standard` (~200 entries). Production-relevant
untracked files:

| File | Purpose | Prod import | Test import | Retrieval | App-layer | Artifact | Safe to exclude? | Evidence |
|---|---|---|---|---|---|---|---|---|
| `app/infrastructure/answerability.py` | Post-retrieval evidence gate | **YES** (uncond, qa_workflow.py:34) | YES | YES | ref'd by system_facts text | NO | **NO — required for import** | `git log --all`=0 committed; import fails without it |
| `app/infrastructure/banded_verifier.py` | Phase 5F banded verifier | NO | YES | YES | NO | NO | YES | no production import |
| `app/application/qa_measurement_harness.py` | Phase 6D latency harness | NO | YES | NO | marginal | NO | YES | no production import |
| `tests/unit/test_answerability_gate.py`, `test_banded_verifier.py`, `test_qa_measurement.py`, `test_qa_timeout.py` | experiment tests | — | — | variably | — | — | YES (not §16) | §16 excludes |
| `tests/unit/test_cli_sources.py`, `test_cli_ingest_ux.py`, `test_reingestion_reliability.py`, `test_cli_remove.py`, `test_cli_status.py`, `test_cli.py` (modified) | **A1–A5 tests (§16 SHOULD)** | — | YES | NO | YES | NO | **NO — required** | §16 SHOULD set |
| `eval/*` untracked results, `sweep_*.py`, dataset backups, `nope.json`, `run_jobs.json` | eval artifacts/strays | NO | — | YES | NO | YES | YES | eval-only |
| `01…61_*.md`, `PLAN.md`, `docs/*`, `VERSION_1_COMPLETE_FINAL_REPORT.md` | documentation | NO | — | — | — | docs | YES (docs) | — |
| `vault/Notes/*` (untracked) + `vault/index.md`,`log.md`,`overview.md` (dirty) | corpus / working index | NO | integration tests only | — | corpus | NO | YES from release commit (not required for import) | corpus |

**Only ONE untracked file is required for the production import path:
`app/infrastructure/answerability.py`** (module-level import in
`qa_workflow.py:34`).

---

## 6. answerability.py Determination

**Classification: 3 — mixed/entangled module: experiment accidentally coupled
into production, requiring an explicit decision (commit-as-inert) or a small
refactor before release.**

Evidence:

- **Contents:** post-retrieval evidence verifier (Phase 3G-B). Docstring:
  "Evaluates whether the retrieved chunks collectively contain enough
  evidence… a second-pass filter that targets topic-adjacent false positives."
  Uses an LLM prompt to emit `SUPPORTED` / `INSUFFICIENT_EVIDENCE`.
- **Git history:** `git log --all -- app/infrastructure/answerability.py` →
  **0 commits** (never committed anywhere). `git ls-files` → untracked.
- **Importers:** production `qa_workflow.py:34` `from
  app.infrastructure.answerability import AnswerabilityGate,
  AnswerabilityResult` — **module-level (column 0), unconditional**. Imported
  indirectly by `app/application/__init__.py:4` and `app/cli/entry.py`.
- **Configuration:** `config/default.yaml:191` `answerability: enabled: false`
  — the gate is **never instantiated** at runtime by default; behavior is
  byte-identical to the frozen Phase 3E baseline (per its own docstring).
- **Does A1–A5 use it directly?** NO — the §16 A1–A5 files do not reference
  `answerability` (grep count 0). They only import `app.cli.entry` /
  `qa_workflow`, transitively pulling the import.
- **Does normal QA import it only because qa_workflow.py has an unconditional
  import?** YES.
- **Does removal alter V1 behavior?** NO, while `enabled=false`. But the
  import statement itself must resolve (either the file ships, or the import
  is made lazy/conditional — a code change).
- **Performs retrieval?** No — consumes `SearchHit`s; it *verifies* evidence.
- **Performs answerability verification?** Yes — LLM-based evidence verdict.
- **Production functionality or experiment infrastructure?** Experiment
  infrastructure (Phase 3G-B/6C) that was wired into production `qa_workflow`
  during the hardening commit without ever being committed.
- **Tests requiring it:** `tests/unit/test_answerability_gate.py` (untracked),
  `test_system_facts.py` (committed, docstring/fixture refs).

Inconclusive sub-point: whether `answerability.py` was intended as a future
production gate (Phase 6C targeted QA hardening used answerability language)
or purely experimental. Its `enabled=false` default and Phase 3G-B origin
support "experiment" labeling; its entanglement origin (hardening commit)
supports "accidental coupling." Either way, **release requires committing it
or decoupling the import.**

---

## 7. Reranker / HYDE Determination

### `app/infrastructure/reranker.py`
- First commit: `6a603d8` (experiment). Committed in HEAD.
- Purpose: cross-encoder re-ranking (`CrossEncoderReranker`).
- Production import: YES, `qa_workflow.py:42` — **module-level, unconditional**.
- Runtime use when flag false: NO (`reranker.enabled=false`,
  `config/default.yaml:178`); constructed only inside
  `if settings.reranker.enabled:` (qa_workflow.py:421).
- Required for basic CLI startup: **YES at import time** (unconditional
  `from app.infrastructure.reranker import CrossEncoderReranker`).
- Required by A1–A5: NO directly; yes transitively via qa_workflow import.
- Retrieval experiment? YES.
- Excludable without changing reviewed V1 behavior? **NO** — requires
  refactoring qa_workflow's import (or stubbing the module). Runtime behavior
  is unaffected when excluded, but the import must be made lazy/optional.

### `app/infrastructure/hyde.py`
- First commit: `8524caf` (experiment). Committed in HEAD.
- Purpose: Hypothetical Document Embedding transform (`HyDETransform`).
- Production import: YES in `search.py`, but **lazy** — imported *inside*
  `SearchService.from_settings` (search.py:288–289) under
  `if getattr(settings, "hyde", None) and settings.hyde.enabled:`. NOT a
  module-level import.
- Runtime use when flag false: NO (`hyde.enabled=false`,
  `config/default.yaml:186`).
- Required for CLI import: **NO** (lazy). Excludable **without** import changes.
- Retrieval experiment? YES.
- Excludable without changing reviewed V1 behavior? **YES** — remove the lazy
  hook; with `enabled=false` behavior is unchanged.

### Configuration verification (working tree & 97197e2, `config/default.yaml`)
```
177 reranker:      enabled: false
185 hyde:          enabled: false
190 answerability: enabled: false
```
`min_cosine` remains **0.25** (hardcoded default `qa_workflow.py:287,385`;
constructor arg `min_cosine: float = 0.25`).

---

## 8. Application-Hardening Foundation Audit

Hardening commits `10f74f1` + `97197e2` per-file classification:

| File | Classification | Required by A1–A5? |
|---|---|---|
| `app/application/qa_workflow.py` | **MIXED** (foundation QA + uncond imports answerability/reranker) | **YES** (QAEmptyAnswerError, QATimeoutError, QAWorkflow) |
| `app/application/system_facts.py` | FOUNDATION | YES (imported by qa_workflow) |
| `app/application/__init__.py` | FOUNDATION | YES |
| `app/cli/entry.py` | FOUNDATION (+A1–A5 delta) | YES |
| `app/core/config.py` | FOUNDATION (incl. experiment settings classes) | YES |
| `app/core/logging.py` | FOUNDATION | YES |
| `app/domain/knowledge_graph.py` | FOUNDATION | YES |
| `app/infrastructure/ingestion/{docx,pptx,spreadsheet,txt}_ingestor.py` | FOUNDATION (hardening) | YES (service.py consumes) |
| `app/infrastructure/ingestion/service.py` | FOUNDATION (+A1–A5 delta) | YES |
| `app/infrastructure/state/manifest.py` | FOUNDATION — adds `is_successful_status` etc. | **YES (entry.py:28,374)** |
| `app/infrastructure/state/models.py` | FOUNDATION | YES |
| `app/infrastructure/vector_store.py` | FOUNDATION (lifecycle hardening; +16, non-retrieval) | YES |
| `app/pipelines/ingest_workflow.py` | FOUNDATION (+A1–A5 delta) | YES |
| `app/prompts/qa.py` | FOUNDATION | YES |
| `app/queue/worker.py` | FOUNDATION | YES |
| `config/default.yaml` | FOUNDATION + experiment flags | YES |
| `pyproject.toml`, `requirements.txt` | FOUNDATION (docx/pptx/xlsx/rtf deps added) | YES |
| `app/infrastructure/reranker.py`, `hyde.py`, `answerability.py` | EXPERIMENT (committed except answerability) | only transitively (imports) |

**Minimal hardening set required by A1–A5 = essentially the full hardening
delta** (17 foundation files above), because A1–A5's four production files
operate across the whole ingestion/CLI/manifest surface. The only "optional"
pieces are the three experiment modules, and two of them (`reranker`,
`answerability`) cannot be dropped without a code change because
`qa_workflow.py` imports them unconditionally.

---

## 9. Retrieval Freeze Audit

Committed-range changes (`198823d` → `97197e2`) on the frozen file list:

| File | Changed in range? | Change type |
|---|---|---|
| `app/infrastructure/embeddings.py` | NO | frozen (identical) |
| `app/infrastructure/bm25.py` | NO | frozen (identical) |
| `app/infrastructure/semantic_chunking.py` | NO | frozen (identical) |
| `app/infrastructure/search.py` | YES | experiment wiring (RRF `rerank_score`, lazy HYDE hook) — working tree == HEAD (0-line diff) |
| `app/infrastructure/reranker.py` | YES (added in range) | experiment module itself; working tree == HEAD |
| `app/infrastructure/vector_store.py` | YES | hardening/lifecycle (+16, save/load path), working tree == HEAD |

Separation:
- **Legitimate application-lifecycle changes:** `vector_store.py` (+16 of the
  hardening), `manifest.py`, ingestors, worker — none alter retrieval ranking.
- **Retrieval-algorithm changes:** only those introduced by the experiments
  themselves (`search.py` rerank/hyde hooks, `reranker.py`); all frozen OFF.

Verified flags: `reranker.enabled=false`, `hyde.enabled=false`,
`answerability.enabled=false`; production `min_cosine=0.25`.

Freeze preserved in **Candidate C** (the recommended tree): frozen retrieval
files in C are byte-identical to the reviewed working tree (0-line diffs).

---

## 10. Candidate A Results

**Tree:** `origin/main` (198823d) + ONLY the 10 §16 files (4 app + 6 tests).
**Method:** scratch detached worktree at 198823d; copied §16 files; imported
with cwd = worktree (correct sys.path resolution).

| Check | Result |
|---|---|
| CLI import | **FAIL** — `entry.py:28`: `ImportError: cannot import name 'is_successful_status' from 'app.infrastructure.state.manifest'` |
| CLI startup | FAIL (unreachable) |
| A1–A5 test collection | **FAIL** — 5 errors: test_cli.py (`QAEmptyAnswerError`), test_cli_sources/ingest_ux/remove/status (`is_successful_status`) |
| Full unit collection | FAIL (blocked by same imports) |
| Retrieval files changed | NO |
| Retrieval experiments included | NO |
| Corpus changed | NO |
| Eval dataset changed | NO |
| Untracked dependencies | none added |
| Missing dependencies | app-hardening layer (`manifest.is_successful_status`, `qa_workflow.QATimeoutError/QAEmptyAnswerError`, system_facts, models ver, etc.) |
| Failure reason | §16 delta is defined over HEAD's hardened layer; origin/main predates the hardening (6 commits) |

---

## 11. Candidate B Results

**Tree:** clean committed `97197e2` tree, no untracked files.
**Method:** scratch detached worktree at 97197e2 (no extra files copied).

| Check | Result |
|---|---|
| CLI import | **FAIL** — `qa_workflow.py:34`: `ModuleNotFoundError: No module named 'app.infrastructure.answerability'` |
| CLI startup | FAIL (unreachable) |
| A1–A5 test collection | N/A — §16 A-tests are not in the committed tree (only `test_cli.py` committed; `test_cli_sources/ingest_ux/reingestion/remove/status` are untracked) |
| Full unit collection | FAIL — 27 errors during collection (answerability missing for all qa_workflow importers) |
| Retrieval files changed | NO |
| Retrieval experiments included | committed: reranker.py, hyde.py present; answerability absent |
| Corpus changed | NO |
| Eval dataset changed | NO (committed eval present but not imported by app tests) |
| Untracked dependencies | `answerability.py` REQUIRED |
| Missing dependencies | `app/infrastructure/answerability.py` |
| Failure reason | the committed "release" commit itself depends on the untracked answerability module |

---

## 12. Candidate C Results

**Tree:** `97197e2` committed tree + **only** `app/infrastructure/answerability.py` + §16 A1–A5 (4 app + 6 tests). No other untracked files.
**Method:** scratch detached worktree at 97197e2; copied answerability + §16.

| Check | Result |
|---|---|
| CLI import | **PASS** |
| CLI startup | PASS (import chain resolves) |
| A1–A5 test collection | **PASS** (99 collected: test_cli + sources + ingest_ux + reingestion + remove + status) |
| Full unit collection | **PASS** — 1662/1719 collected, 57 deselected, 0 errors |
| A1–A5 run | **98 passed / 1 failed** — only known pre-existing P0 flake `test_cli_remove.py::test_remove_one_source_and_unrelated_survives` (logging cross-file isolation), identical to reviewed state |
| Retrieval files changed | NO (byte-identical to reviewed working tree) |
| Retrieval experiments included | YES — reranker.py, hyde.py (committed), answerability.py (untracked→needs commit); all `enabled=false`, freeze preserved |
| Corpus changed | NO |
| Eval dataset changed | NO |
| Untracked dependencies | answerability.py (must be committed or decoupled) |
| Missing dependencies | none |
| Conclusion | **Exactly reproduces the reviewed & tested A1–A5 state** |

---

## 13. Candidate D Results

**Tree:** `origin/main` (198823d) + hardening app files from `97197e2`
(excluding reranker.py / hyde.py / answerability.py) + §16 A1–A5.
**Method:** scratch detached worktree at 198823d; wrote committed hardening
files via `git show 97197e2:...`; added §16 files; imported with cwd =
worktree.

| Check | Result |
|---|---|
| CLI import | **FAIL** — same `qa_workflow.py:34` `ModuleNotFoundError: No module named 'app.infrastructure.answerability'` |
| CLI startup | FAIL |
| A1–A5 test collection | FAIL (blocked by qa_workflow import) |
| Full unit collection | FAIL |
| Retrieval files changed | hardening `search.py`/`vector_store.py` present; experiments excluded |
| Retrieval experiments included | NO (that was the intent) |
| Corpus changed | NO |
| Eval dataset changed | NO |
| Untracked dependencies | answerability.py REQUIRED |
| Missing dependencies | answerability.py (+ reranker.py, needed by qa_workflow:42) |
| Failure reason | **the hardening foundation cannot be separated from the experiment modules it imports — qa_workflow.py (a hardening file) unconditionally imports answerability and reranker.** Adding the two experiment modules makes D import correctly (verified in the first audit pass), proving the separation is impossible without code change |

**Conclusion:** Candidates A, B, D fail; only Candidate C is coherent.

---

## 14. Minimal Coherent Foundation

The smallest independently reproducible tree that reproduces the reviewed
A1–A5 state (evidence: Candidate C):

- **BASE COMMIT:** `97197e2` (release: PAM V1.0.0 — HEAD), the only commit
  whose tree plus one untracked file is importable.
- **FOUNDATION FILES:** the full `97197e2` committed tree (hardening is a
  single indecomposable layer; manifest/qa_workflow/system_facts/models/
  ingestors/queue/config all required).
- **V1.1 FILES (exact §16 set):** `app/cli/entry.py`,
  `app/domain/documents.py`, `app/infrastructure/ingestion/service.py`,
  `app/pipelines/ingest_workflow.py`; `tests/unit/test_cli.py` (A5-modified),
  `test_cli_sources.py`, `test_cli_ingest_ux.py`,
  `test_reingestion_reliability.py`, `test_cli_remove.py`,
  `test_cli_status.py`.
- **EXPERIMENT FILES TO EXCLUDE:** `banded_verifier.py`,
  `qa_measurement_harness.py`, `tests/unit/test_{answerability_gate,
  banded_verifier, qa_measurement, qa_timeout, reranker, hyde}.py`,
  `eval/sweep_*.py`, `eval/analyze_reranker.py`, experiment report docs.
  **NOTE:** committed `reranker.py` and `hyde.py` are present in the base tree
  and cannot be deleted without import-refactor; they remain frozen-off.
- **EVAL FILES TO EXCLUDE:** `eval/` (committed + untracked), datasets
  `eval/dataset*.json`, `eval/results*`, `test_eval_dataset.py` (7 stale tests
  known-mismatch — do not fix).
- **UNTRACKED FILES:** only `app/infrastructure/answerability.py` required;
  commit it. All others excluded.
- **ANSWERABILITY:** commit as-is (inert, `enabled=false`), documented as
  frozen research gate — **or** perform the decoupling refactor below.

---

## 15. Required Exclusions

(Re-stated as an exact list for the release commit.)

INCLUDE (10 files — §16):
```
app/cli/entry.py
app/domain/documents.py
app/infrastructure/ingestion/service.py
app/pipelines/ingest_workflow.py
tests/unit/test_cli.py
tests/unit/test_cli_sources.py
tests/unit/test_cli_ingest_ux.py
tests/unit/test_reingestion_reliability.py
tests/unit/test_cli_remove.py
tests/unit/test_cli_status.py
```
PLUS decision-dependent: `app/infrastructure/answerability.py` (commit, frozen).

EXCLUDE:
- Experiment modules: `app/infrastructure/reranker.py` (committed — cannot
  delete without refactor; ships frozen), `app/infrastructure/hyde.py`
  (ships frozen; safe to prune later), `app/infrastructure/banded_verifier.py`,
  `app/application/qa_measurement_harness.py`
- Experiment/eval tests: `test_reranker.py`, `test_hyde.py`,
  `test_eval_dataset.py`, `test_answerability_gate.py`,
  `test_banded_verifier.py`, `test_qa_measurement.py`, `test_qa_timeout.py`
- Eval: whole `eval/` tree, `eval/dataset*.json`, `eval/results*`
- Pre-existing dirty (V1-era): `.obsidian/*`, `docs/01_…`,
  `tests/integration/test_queue_worker_pipeline.py`,
  `tests/unit/test_{duplicate_detection,manifest,scoring}.py`,
  `vault/index.md`, `vault/log.md`, `vault/overview.md`
- Corpus: `vault/Notes/`
- Strays: `nope.json`, `run_jobs.json`
- Docs (unless desired): `01…61_*.md`, `PLAN.md`,
  `VERSION_1_COMPLETE_FINAL_REPORT.md`, `docs/*`

---

## 16. Required Pre-Release Cleanup

Two viable routes; both are decisions + small steps, **not performed here**:

**Route 1 (no code change): commit the untracked file.**
`git add app/infrastructure/answerability.py` in the release base, commit as
"frozen research gate (enabled=false)". Zero behavior change; import resolves.

**Route 2 (code change, cleanest): decouple the experiment imports.**
In `qa_workflow.py`, convert lines 34 and 42 to lazy/guarded imports:
- `from app.infrastructure.answerability import …` →
  `if settings.answerability.enabled:` local import (inside `from_settings`),
  matching the already-lazy HyDE pattern in `search.py`.
- `from app.infrastructure.reranker import CrossEncoderReranker` → same
  treatment; plus drop `search.py`'s lazy HYDE hook if strict exclusion.
This is a small, low-risk refactor but **must be reviewed and re-tested**
before release. Optionally also add `banded_verifier.py`/`qa_measurement_harness.py`
never-committed cleanup and remove `test_eval_dataset.py` stale tests.

Exact statement: **V1.1.0 release assembly remains blocked until either
(a) `answerability.py` is committed (or otherwise made available in the
release tree), or (b) the `qa_workflow.py` experiment imports are decoupled.**

---

## 17. V1.1.0 Readiness Decision

**Verdict: V1.1.0 may still meaningfully ship, but only after one of the two
steps in §16.** The 98/99 A1–A5 pass (C) is the same result that justified
"RELEASE READY" — the functional readiness conclusion stands. However:

- The version label **remains honest as v1.1.0**: the release still contains
  exactly the reviewed A1–A5 delta over the V1.0.0 line's application layer,
  plus the same frozen-curiosity modules already present at 97197e2. No new
  feature scope has been added; experiments remain `enabled=false`.
- It is **not** honest to claim "v1.1.0 excludes retrieval experiments" while
  committed `reranker.py`/`hyde.py` remain in the tree. The honest framing is:
  "retrieval experiments present in the codebase but disabled and frozen —
  no experiment code enters the A1–A5 delta."
- If experiment-free is a hard requirement, the decoupling refactor (Route 2)
  must precede assembly, meaning V1.1.0 is held until that preparatory change
  is reviewed.

---

## 18. Impact on Cumulative Review

**`61_PHASE_V1_1_CUMULATIVE_FINAL_REVIEW.md` DOES require amendment.**

| Claim in §61 | Reality |
|---|---|
| "RELEASE READY / assemble from `origin/main` + §16 (MUST+SHOULD)" | Unimplementable — imports fail (`is_successful_status`, `QAEmptyAnswerError` absent from origin/main), empirically proven (Candidate A) |
| §16 "EXCLUDE answerability.py" | Contradictory — the release cannot import without it (Candidate B/D) unless a refactor is performed |
| §17 "working-tree subset per §16" | Under-specified — the working-tree subset still requires the untracked answerability file (or a refactor) |
| §12/§14 test results (98/99, 1680/… suite) | Valid — they were measured on the working tree which includes answerability.py on disk |

Amendment needed: replace the base-commit and file-set guidance with the
Candidate-C foundation (base `97197e2`, commit `answerability.py` frozen-off
OR route-2 refactor), resurface the untracked-file dependency as a release
blocker, and document the "experiments frozen on in tree" wording. §61 is not
to be modified in this audit.

---

## 19. Exact Recommended Release Strategy

**ONE recommended path (conservative, no code change):**

1. **Release base:** commit `97197e2` (release: PAM V1.0.0). Create the
   `v1.1.0-release` branch from `97197e2` (currently it is empty at
   `198823d`).
2. **Foundation:** the full `97197e2` committed tree as-is.
3. **Untracked prerequisite:** `git add app/infrastructure/answerability.py`
   first, as a standalone preparatory commit
   (`chore: track frozen answerability gate (enabled=false)`) so the tree is
   importable. Alternative accepted: lazy-import refactor + re-review.
4. **V1.1 files:** exactly the §16 MUST+SHOULD 10-file set, applied as the
   single A1–A5 commit.
5. **Experiment exclusions:** do NOT add any new experiment/eval files.
   `reranker.py`/`hyde.py` remain (they are already in the base); ensure
   `enabled=false` everywhere.
6. **answerability treatment:** committed, frozen-off, documented.
7. **Required cleanup before assembly:** step 3 (or refactor). Nothing else.
8. **Expected verification gates:**
   - `python -c "import app.cli.entry"` → OK
   - A1–A5 collected: 99; run: 98 pass / 1 known P0 flake (recorded, not fixed
     in release)
   - full unit collection: 1662 collected, 57 deselected, 0 errors (excluding
     the deselected stale-eval group)
   - freeze check: `reranker/hyde/answerability enabled=false`, min_cosine 0.25
9. **Final topology:** `v1.1.0-release` = 97197e2 + (answerability commit) +
   (A1–A5 commit). Linear, no merge.
10. **Tag strategy:** tag `v1.1.0` (new annotated tag) ONLY after all gates
    green; leave `v1.0.0`→`a4e5b2a` and `v2.0.0`→`4f97684` untouched; never
    tag `97197e2` itself as v1.1.0.
11. **Push strategy:** push `v1.1.0-release` and the tag only after user
    authorization; `origin/main` untouched until then.

**Conservative wording: "V1.1.0 release assembly remains blocked until
`app/infrastructure/answerability.py` is committed (or the experiment imports
in `qa_workflow.py` are decoupled)."**

---

## 20. Git Safety Verification

| Check | Result |
|---|---|
| `v1.0.0` → `a4e5b2ab…` | ✓ untouched |
| `v2.0.0` → `4f97684…` | ✓ untouched |
| `origin/main` → `198823d…` | ✓ unchanged |
| `main` (HEAD) → `97197e2…` | ✓ unchanged |
| `v1.1.0-release` → `198823d…` | ✓ empty, still == origin/main |
| commits / tags / pushes | ✓ none |
| stash | ✓ `stash@{0}` untouched |
| reset / clean / rebase / merge / cherry-pick | ✓ none |
| main working tree | ✓ unchanged (only the audit report file added/updated) |
| temporary worktrees | ✓ 4 created in temp dir, all removed; `git worktree list` = single main; removal did not affect the main repository |

---

*Evidence-based provenance audit. No recommendation implemented. Next step:
user decision on §16 answerability treatment (commit-as-inert vs refactor).*