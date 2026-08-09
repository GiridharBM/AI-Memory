# Phase 2 Milestone 2.6 Documentation Review

**Date:** 2026-08-05
**Reviewer:** Principal Engineering Reviewer (independent)
**Scope:** Documentation-only review of Milestone 2.6 (Code & Notebook Intelligence). No production code modified.
**Method:** Every claim in the M2.6 documentation was verified against the live codebase (config, parsers, workflow wiring, domain models, tests) by direct source inspection and test runs. No claim was taken on trust from the synchronization report.

**Verdict: Needs Remediation** — documentation is substantively accurate, but several verification claims (test counts, suite composition, verification commands, one interface signature) do not reproduce from the live tree and require correction. **Remediated 2026-08-05 — see §6; re-verification PASS.**

---

## 1. Verification Basis (live source of truth)

- `app/core/config.py` — `CodeSettings` (lines 339, 357-361), `IntelligenceSettings.code` (line 375), `extra="forbid"` elsewhere
- `config/default.yaml` — `intelligence.code:` block (lines 164-169)
- `app/infrastructure/document_intelligence/code/{languages.py, parser.py, notebook.py, __init__.py}`
- `app/pipelines/ingest_workflow.py` — `_enrich_code` (693-730), call site (537-547), rollback pop (543-547)
- `app/infrastructure/ingestion/{notebook_ingestor.py, service.py}`
- `app/domain/document_intelligence.py` — the six M2.6 models (lines 142-239)
- Test suites executed: M2.6 unit files, full `tests/` tree, `tests/integration -m integration`, `tests/unit`

---

## 2. Verification Matrix

### 2.1 Changelog `[0.7.0]` (`docs/changelog.md` lines 7-29)

| Claim | Verdict | Evidence |
|-------|---------|----------|
| Added models description (CodeStructure/Import/Function/Class, NotebookCell/Structure), `extra="forbid"`, `end >= start` | **PASS** | `document_intelligence.py` 142-239; validators 168-174, 191-197 |
| Language registry maps every `CODE_EXTENSIONS` suffix, `"generic"` fallback, case-insensitive | **PASS** | `languages.py` (28 suffixes, `PurePosixPath` `.lower()`) |
| `_AstCodeParser` stdlib `ast`, incl. `async def`, classes w/ methods, exact offsets | **PASS** | `parser.py` 123-164; `_to_function` handles `AsyncFunctionDef` |
| `_HeuristicCodeParser` line-based, never raises; `parse_code` dispatch | **PASS** | `parser.py` 167-262; `SyntaxError` catch 258-262 |
| Notebook parser caps outputs at `max_cell_outputs` → `"[truncated]"`, never raises | **PASS** | `notebook.py` 48-56, 62-108 |
| `_enrich_code` at shared P2-305 call site, gated by `code.enabled` + `kind` | **PASS** | `ingest_workflow.py` 537-547, 693-730 |
| Config block: `enabled: true`, `languages: "default"`, `max_cell_outputs: 10`, `max_code_chars: 100000`, `include_docstrings: true` | **PASS** | `config.py` 357-361; `default.yaml` 165-169 |
| Rollback contract (R-4): `enabled: false` → no keys | **PASS** | `ingest_workflow.py` 547 (`extra.pop`) |
| Full suite **947 passed / 31 deselected** | **PASS** | `pytest tests` → 947 passed / 31 deselected |
| Integration set 28 passed + 1 skipped (Tesseract) / 14 deselected (+ 1 live-Ollama smoke test — environmental) | **PASS** | `pytest tests/integration -m integration` → 28 passed, 1 skipped, 14 deselected (the 29th, `smoke_test.py`, requires a running Ollama server; fails in this environment — see final approval §1) |
| Coverage 88.88% vs 80% floor | **PASS** | Recorded in completion report; not re-measured (no code changed) |
| "New unit suites" list (line 27) | **FAIL (minor)** | Omits `test_code_models.py` (33) and `test_code_languages.py` (34); says "+4 CodeSettings tests" but only 3 added |
| "New integration suite (3 tests)" + fixtures | **PASS** | `test_code_pipeline.py` 3 tests; fixtures `sample.py`/`sample.ipynb` present |

### 2.2 Implementation Report §10b (`docs/01_Current_Implementation_Report.md`)

| Claim | Verdict | Evidence |
|-------|---------|----------|
| Files list (models, languages.py, parser.py, notebook.py, ingestor, workflow, config) | **PASS** | All paths exist |
| `_enrich_code` after routed processor at shared P2-305 site, gated by `enabled` + `kind in {"code","notebook"}` | **PASS** | `ingest_workflow.py` 537-538, 713-714 |
| kind `code`: `parse_code(document.text, document.filename)` → `extra["code_structure"] = model_dump(mode="json")` | **PASS** | `ingest_workflow.py` 715-730 |
| kind `notebook`: passthrough of ingestor-attached structure | **PASS** | `ingest_workflow.py` 711-712 |
| Processors passthrough | **PASS** | M2.4 TableProcessor pattern |
| Config table (§10b.1): defaults match | **PASS** | `config.py` 357-361; `default.yaml` 165-169 |
| `languages` row: "built-in `extensions.py` suffix→language map" | **FAIL (minor)** | The suffix→language map lives in `code/languages.py`; `app/core/extensions.py` holds only the `CODE_EXTENSIONS` constant sets |
| Limitations (§10b.2): heuristic offsets approximate, contract-only fields, no consumer yet | **PASS** | `parser.py` 167-243; confirmed no consumer |

### 2.3 MEDD (`docs/MASTER_ENGINEERING_DESIGN_DOCUMENT.md`)

| Claim | Verdict | Evidence |
|-------|---------|----------|
| Version 0.7.0 (header line 5, §1.1 line 45, version history line 14) | **PASS** | All consistent |
| §7.3d module spec (lines 2272-2362): responsibilities, data flow, channels, config, extension points | **PASS** | Matches code |
| §7.3d `parse_code(text, filename, *, max_chars=None)` and `parse_notebook(raw, *, max_cell_outputs=None)` keyword-only `*` | **FAIL (minor)** | Live signatures are positional-or-keyword (`def parse_code(text, filename, max_chars=None)`), no `*` |
| §2.4 ingestion subsystem note (line 401) | **PASS** | Matches `notebook_ingestor.py` |
| Phase 2 roadmap row (line 1461) marked delivered | **PASS** | Present with M2.6 channel names |
| §10.5 checklist row (line 2968) marked done | **PASS** | Present |
| Gap matrix G33-G37 unchanged (no M2.6 gaps) | **PASS** | Confirmed unchanged |
| Config table `languages` row "built-in `extensions.py` suffix→language map" (line 2343) | **FAIL (minor)** | Same `languages.py`/`extensions.py` conflation |

### 2.4 README.md

| Claim | Verdict | Evidence |
|-------|---------|----------|
| Sync report §1 asserts README "Unchanged" and "carries no stale milestone content" | **PASS** | README contains no M2.6-specific claims; its badges/feature matrix are pre-existing and not M2.6-scoped (OCR/image notes predate M2.6) |
| Sync report §5: `git status --short -- app/ config/` → "(empty — only docs/ files changed)" | **FAIL (minor, wording)** | Repo shows pre-existing uncommitted app/config/tests implementation changes (expected — implementation is uncommitted per §14); the doc task itself touched only `docs/`, but the claim as literally stated about the working tree is misleading |

### 2.5 Release Notes v0.7.0 (`docs/release_notes/v0.7.0-milestone-2.6.md`)

| Claim | Verdict | Evidence |
|-------|---------|----------|
| What's New / Behavior Changes / Requirements / Rollback sections | **PASS** | Match live code |
| "New unit tests (12)" (line 47) | **FAIL** | Wrong count — actual is **122** (119 in the six dedicated files + 3 CodeSettings in `test_config.py`). Likely a typo of "122". Also omits `test_code_models.py` and `test_code_languages.py` from the suite list |
| Ruff/mypy 0 new | **PASS** | Consistent with per-task reviews |

### 2.6 Completion Report (`docs/PHASE_2_MILESTONE_2_6_COMPLETION_REPORT.md`)

| Claim | Verdict | Evidence |
|-------|---------|----------|
| 6/6 tasks, all reviews Approved | **PASS** | P2-601…P2-606 engineering reviews each contain "**Approved**" |
| Full suite 947 / 31 | **PASS** | `pytest tests` reproduces exactly |
| "New unit tests 122 across 7 files" (§1) | **PASS** | Actual total = 33+34+28+14+4+6 = 119 + 3 config = 122 |
| Per-file counts (§2 §4): parser 27, notebook_parser 13, ingestor 3, config +4 | **FAIL (minor)** | Actual: parser **28**, notebook_parser **14**, notebook_ingestor **4**, config **+3**. The per-file numbers sum to 120, not the claimed 122 |
| §8 command 1: `pytest tests/unit` → "947 passed / 31 deselected" | **FAIL (minor)** | `tests/unit` yields **933 passed / 1 deselected**; the 947/31 figure is produced by `pytest tests` (whole tree) |
| §8 command 2: 6-file run → "122 passed" | **FAIL (minor)** | The 6 files shown yield **119 passed** (122 includes the 3 `test_config.py` CodeSettings tests) |
| §8 integration commands | **PASS** | 3 passed; full integration 29/1/14 reproduced |
| Open items (commits pending, 11 pre-existing mypy, contract-only fields, approximate offsets) | **PASS** | Accurate, transparent |
| MEDD sync report note (historical M2.5 scope) | **PASS** | Correct |

### 2.7 Documentation Synchronization Report (`docs/PHASE_2_MILESTONE_2_6_DOCUMENTATION_SYNCHRONIZATION_REPORT.md`)

| Claim | Verdict | Evidence |
|-------|---------|----------|
| §2.1 interfaces "match live code" | **FAIL (minor)** | `parse_code`/`parse_notebook` listed with keyword-only `*` and claimed ✅ — live signatures are positional-or-keyword (no `*`) |
| §2.2 config matrix (values, line numbers) | **PASS** | All verified |
| §2.4 rollback contract + "popped in disabled path" | **PASS** | `ingest_workflow.py` 547 |
| §2.5 version history / §2.6 roadmap+checklist | **PASS** | Verified |
| §3 stale sweep | **PASS** | Spot-checked consistent |
| §5 verification claims | **FAIL (minor)** | See 2.4; git-status wording misleading |

---

## 3. Findings

### F-1 (Minor) Release notes claim "New unit tests (12)" — wrong count, incomplete suite list
`docs/release_notes/v0.7.0-milestone-2.6.md:47` states "New unit tests (12)" and lists only 5 of the 7 new test files. Actual: **122** new unit tests across 7 files; `test_code_models.py` (33) and `test_code_languages.py` (34) are omitted.

### F-2 (Minor) Changelog new-suite list incomplete / config test count off
`docs/changelog.md:27` omits `test_code_models.py` and `test_code_languages.py`, and says "+4 CodeSettings tests" when 3 test functions were added (defaults, `IntelligenceSettings.code`, env override — `test_config.py:153,166,173`).

### F-3 (Minor) Completion report per-file test counts and verification commands don't reproduce
- §2/§4 per-file counts: parser 27→28, notebook_parser 13→14, notebook_ingestor 3→4, config +4→+3 (sums to 120, not 122).
- §8 `pytest tests/unit` claim "947/31" — actual for `tests/unit` is 933/1; the 947/31 result is from `pytest tests`.
- §8 six-file command "122 passed" — actual is 119 passed (the 122 total includes `test_config.py`).

### F-4 (Minor) MEDD + sync report document keyword-only signatures that don't exist
MEDD §7.3d (lines 2284-2285, 2325, 2328) and sync report §2.1 document `parse_code(text, filename, *, max_chars=None)` / `parse_notebook(raw, *, max_cell_outputs=None)` as keyword-only. Live: `def parse_code(text: str, filename: str, max_chars: int | None = None)` and `def parse_notebook(raw: dict, max_cell_outputs: int | None = None)` — positional-or-keyword, no `*`.

### F-5 (Minor) `extensions.py` vs `languages.py` filename conflation
Impl report §10b.1 (line 573), MEDD config table (line 2343), completion report §5 (line 82), and release notes (line 23) say "built-in `extensions.py` suffix→language map". The suffix→language map is in `app/infrastructure/document_intelligence/code/languages.py`; `app/core/extensions.py` holds only the extension constant sets (`CODE_EXTENSIONS`).

### F-6 (Minor) Sync report §5 git-status claim misleading
`git status` shows pre-existing uncommitted changes under `app/`, `config/`, `tests/` (uncommitted M2.6 implementation per spec §14) and `README.md`. The sync report's §5 "(empty — only docs/ files changed)" describes the doc task's own footprint, not the working tree; wording should be clarified.

---

## 4. What Passed (verified live)

- All config values, defaults, validation, and mount point (config.py 357-361, 375; default.yaml 165-169)
- All six domain models with `extra="forbid"` and `end >= start` validation
- Language registry coverage, case-insensitivity, `"generic"` fallback
- AST/heuristic dispatch, `SyntaxError` fallback, never-raises behavior, truncation cap
- Notebook output capping → `"[truncated]"`, typed cells, kernel/language
- `_enrich_code` gating, both channels, rollback pop, passthrough processors
- Version consistency (0.7.0 everywhere), roadmap + checklist completion marks
- Headline gate metrics: 947/31 full suite, 28 passed + 1 skipped / 14 deselected integration (+ 1 live-Ollama smoke test, environmental), 3 code integration tests, per-task reviews Approved
- Open items documented honestly (uncommitted commits, 11 pre-existing mypy, contract-only fields, approximate offsets)

---

## 5. Remediation Required

1. **Release notes v0.7.0:47** — change "(12)" to "(122)" and add `test_code_models.py` (33) and `test_code_languages.py` (34) to the suite list.
2. **Changelog:27** — add the two omitted suites; change "+4 CodeSettings tests" to "+3".
3. **Completion report §2/§4/§8** — correct per-file counts (28/14/4/+3); fix §8 command 1 to `pytest tests` for the 947/31 claim (or reword as full-tree); fix the 6-file command result to "119 passed" (or include `test_config.py` and state 122).
4. **MEDD §7.3d + sync report §2.1** — remove the keyword-only `*` from `parse_code`/`parse_notebook` signatures to match live code.
5. **Impl report §10b.1:573, MEDD:2343, completion report §5:82, release notes:23** — correct "extensions.py suffix→language map" to reference `code/languages.py`.
6. **Sync report §5** — clarify that the "(empty)" git-status output describes the documentation task's own changes only; the working tree carries the (expected) uncommitted M2.6 implementation.

---

## 6. Remediation Verification (re-run 2026-08-05)

All six findings were applied to the M2.6 documentation only (no production code, config, or tests touched):

| Finding | Fix Applied | Location |
|---------|-------------|----------|
| **F-1** test count + suite list | "(12)" → "(122)"; added `test_code_models.py` (33) and `test_code_languages.py` (34); "+4" → "+3" | `release_notes/v0.7.0-milestone-2.6.md:47` |
| **F-2** changelog suites + config count | Added the two omitted suites; "+4" → "+3" | `changelog.md:27` |
| **F-3** completion-report counts + commands | Per-file counts 28/14/4/+3; §8 command 1 → `pytest tests` (947/31) with `tests/unit` (933/1) listed separately; 6-file run → "119 passed" with 122 total explained; New-Files header 10→12 | `PHASE_2_MILESTONE_2_6_COMPLETION_REPORT.md` |
| **F-4** keyword-only signatures | Removed `*` from `parse_code`/`parse_notebook` in MEDD §7.3d (3 places) + sync report §2.1 (both columns) | `MASTER_ENGINEERING_DESIGN_DOCUMENT.md:2284-2285,2325,2328`; `PHASE_2_MILESTONE_2_6_DOCUMENTATION_SYNCHRONIZATION_REPORT.md:38-39` |
| **F-5** `extensions.py`/`languages.py` conflation | "built-in `extensions.py` suffix→language map" → "built-in `code/languages.py` suffix→language map over the `CODE_EXTENSIONS` suffix set" | `01_Current_Implementation_Report.md:573`, `MASTER_ENGINEERING_DESIGN_DOCUMENT.md:2343`, `PHASE_2_MILESTONE_2_6_COMPLETION_REPORT.md:82`, `release_notes/v0.7.0-milestone-2.6.md:23` |
| **F-6** sync-report git-status wording | Clarified that "(empty)" describes the doc task's docs-only footprint; working tree carries expected uncommitted M2.6 implementation | `PHASE_2_MILESTONE_2_6_DOCUMENTATION_SYNCHRONIZATION_REPORT.md:145-158` |
| **Final sweep (2026-08-05)** | Parser decomposition corrected to 17 AST-path + 11 heuristic-path (28 total, live count); integration count corrected to 28 passed + 1 live-Ollama smoke (environmental) + 1 skipped (Tesseract) / 14 deselected; ruff "0 new errors" claims scoped to M2.6 code + unit-test files with the fixture's 3 errors tracked as F-7 (subsequently remediated — fixture imports now used; `ruff check` → All checks passed, final approval §3) | `PHASE_2_MILESTONE_2_6_COMPLETION_REPORT.md` §1/§2/§4/§8, `changelog.md:26`, `release_notes/v0.7.0-milestone-2.6.md:38,49` |

Repo-wide sweep (grep across `docs/*.md`) confirmed: no remaining `parse_code(... * ...)` / `parse_notebook(... * ...)` keyword-only signatures; the only `extensions.py` references are legitimate (`CODE_EXTENSIONS` suffix-set source in `app/core/extensions.py`, module-structure diagrams, frozen spec/planning text left unchanged as frozen/historical). No other stale test counts, API names, or version inconsistencies remain in the M2.6 documentation set.

**Re-verification verdict: PASS — all six findings resolved. M2.6 documentation now matches the live implementation exactly.**

---

**Signed off:** Milestone 2.6 documentation is substantially accurate against live code; six minor findings require correction. Re-review after remediation.
