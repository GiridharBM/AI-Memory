# Milestone 3.1 — P3-105 Implementation Report

**Task:** P3-105 — Config + plumbing
**Status:** DONE — implemented, tested, not yet engineering-reviewed
**Date:** 2026-08-06
**Contract:** `docs/PHASE_3_MILESTONE_3_1_IMPLEMENTATION_ROADMAP.md` (P3-105 block, L2/L5, AC/DoD)
**Scope rule honored:** ONLY P3-105 implemented; no future task work. P3-106 (regression + fixture suite under all three engine paths) not started. No engine changes, no `pam doctor` reporting (roadmap marks it optional — deferred).

---

## 1. What Was Implemented

Per the frozen task block (Objective / Files expected to change / AC / DoD):

| Deliverable | Location | Notes |
|-------------|----------|-------|
| `ChunkingSettings` model | `app/core/config.py` | `sentence_tokenizer: Literal["auto", "nltk", "heuristic"] = "auto"`, `extra="forbid"` (matches every other settings block). Docstring documents the three modes and the `"auto"` = post-P3-104 behavior contract |
| `chunking` field on `Settings` | `app/core/config.py` (`Settings`) | `chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)` — consistent with the `intelligence`/`watcher`/`models` pattern; works both when the yaml supplies the block and when `Settings` is constructed directly (e.g. the `tmp_settings` test fixture) |
| `chunking:` block | `config/default.yaml` | `sentence_tokenizer: "auto"` with a one-line comment explaining the three modes (file's inline-comment style) |
| **Plumbing** | `app/pipelines/ingest_workflow.py` (line 247) | `create_default` now constructs `SemanticChunker(sentence_tokenizer=settings.chunking.sentence_tokenizer)`. Both production entry points — CLI ingest (`app/cli/entry.py:372`) and queue worker (`app/queue/worker.py:84`) — construct via `IngestionWorkflow.create_default(settings)`, so this single call site is the full production chain (L2 confirmed: one construction path, no divergence) |
| Stale docstring fix | `app/infrastructure/sentence_tokenizer.py` | Module docstring said "Nothing here is wired into ingestion yet" — false since P3-104 wired it through `SemanticChunker`. Updated to describe the P3-104/P3-105 wiring |

No engine, tokenizer, or chunker behavior changed. `get_sentence_tokenizer`, the heuristic and nltk engines, and all chunking math are untouched by P3-105.

## 2. Test Results

**New tests:** 3 in `tests/unit/test_config.py` + 1 wiring test in `tests/integration/test_knowledge_engine_persistence.py` (existing cases unchanged):

| Test | Verifies |
|------|----------|
| `test_chunking_defaults_reproduce_frozen_spec` | `load_settings().chunking == ChunkingSettings()` and `sentence_tokenizer == "auto"` |
| `test_chunking_sentence_tokenizer_environment_override` | `PAM_CHUNKING__SENTENCE_TOKENIZER=heuristic` reaches `settings.chunking.sentence_tokenizer` via the existing `_apply_environment_overrides` path |
| `test_chunking_invalid_sentence_tokenizer_fails_fast` | `ChunkingSettings(sentence_tokenizer="bogus")` → `ValidationError`; and a yaml with `chunking.sentence_tokenizer: bogus` → `ConfigurationError` at load (fail-fast at the config boundary, before any chunker construction) |
| `test_create_default_plumbs_chunking_settings` | Production wiring: `create_default` passes the configured value through — default yields `sentence_tokenizer == "auto"`; setting `"heuristic"` yields a chunker whose resolved engine is `_HeuristicSentenceTokenizer` |

| Gate | Result |
|------|--------|
| New tests (3 config + 1 wiring) | **4/4 passed** |
| `test_config.py` full | **18 passed** (15 existing + 3 new) |
| Full default suite | **1005 passed / 31 deselected** (P3-104 baseline 1001/31; **+4 net new, 0 regressions**) |
| Integration (non-live) | green within the full run; live-Ollama `smoke_test` remains deselected/31 (environmental, untouched path) |
| Mypy | **Clean on `config.py`** (the changed settings code). `ingest_workflow.py` reports only **pre-existing** findings (11 `object`-typed-injection errors at lines 130/343/360/612/751/759/774/776/780/792 — none touched by P3-105) plus 2 environmental import errors (`faster_whisper` missing stubs; `numpy/__init__.pyi` syntax on Python 3.14). Zero new findings from this change |
| Ruff | **Zero new findings** on all changed files |

## 3. Acceptance Criteria / DoD Verification

| Criterion (frozen) | Status |
|--------------------|--------|
| Config value drives engine selection end-to-end | ✅ live probe: `PAM_CHUNKING__SENTENCE_TOKENIZER=heuristic` + `create_default` → `_HeuristicSentenceTokenizer`; default `auto` + `create_default` → `_NltkSentenceTokenizer` (nltk present) |
| Default `"auto"` reproduces the post-P3-104 behavior | ✅ `load_settings().chunking.sentence_tokenizer == "auto"`; `create_default` passes it straight through — identical to the previous `SemanticChunker()` default construction |
| `"heuristic"` = deterministic stdlib path (the rollback position) | ✅ live probe resolves `_HeuristicSentenceTokenizer`; the P3-104 heuristic determinism test still passes unchanged |
| **DoD — config test + wiring test green for both entry points (CLI `entry.py:372`, worker `worker.py:84`)** | ✅ both call `IngestionWorkflow.create_default(settings)` (L2 single construction site); the wiring test exercises exactly that path |
| **DoD — no dead config (every value consumed — L5)** | ✅ `chunking.sentence_tokenizer` is the only added key/field and is consumed at `ingest_workflow.py:247`; all three legal values map to engines already known to `get_sentence_tokenizer`. No `chunking` value is written but unread |

## 4. Notes

- **Commit coupling (roadmap O-1) satisfied:** `ChunkingSettings`, the `chunking:` field on `Settings`, the `chunking:` yaml block, and the plumbing are one coherent change. Because `Settings` is `extra="forbid"`, the yaml key and the model must land together — they do, in this diff.
- **Env override path:** `PAM_CHUNKING__SENTENCE_TOKENIZER=heuristic` works through the existing `_apply_environment_overrides` → `_set_nested_value` machinery (no new parsing code; the value round-trips through `yaml.safe_load` as the literal string).
- **`pam doctor` (optional, deferred):** the roadmap allows reporting the resolved engine in `pam doctor` but marks it optional — skipped to keep the diff minimal; nothing in this phase's AC/DoD requires it.
- **Ruff/mypy baseline:** the `ingest_workflow.py` mypy findings predate P3-105 (the module type-hints its injected integrations as `object`); the full-tree mypy run also fails on environmental stub issues (`faster_whisper`, `numpy`). P3-105 adds no new findings.
- **Environment:** suite runs on the global `C:\Python314` interpreter (holds the `intelligence` extras incl. nltk 3.10.2 + `punkt_tab`), which is why `auto` resolves to nltk on the live probe; the same probe under an nltk-absent interpreter would resolve `auto` → heuristic (P3-104 D4 fallback, unchanged).

## 5. Files Changed

| File | Action |
|------|--------|
| `app/core/config.py` | **modified** — `ChunkingSettings` class + `chunking` field on `Settings` |
| `config/default.yaml` | **modified** — `chunking:` block |
| `app/pipelines/ingest_workflow.py` | **modified** — `chunker=SemanticChunker(sentence_tokenizer=settings.chunking.sentence_tokenizer)` at line 247 |
| `app/infrastructure/sentence_tokenizer.py` | **modified** — stale module docstring corrected (P3-104 wiring note) |
| `tests/unit/test_config.py` | **modified** — 3 new chunking tests; existing tests unchanged |
| `tests/integration/test_knowledge_engine_persistence.py` | **modified** — 1 new wiring test; existing tests unchanged |

No public API breakage: `Settings` gains one additive field with a default; `SemanticChunker`'s constructor is unchanged.

## 6. Rollback Plan

Revert the P3-105 changes (restore `SemanticChunker()` at `ingest_workflow.py:247`, remove the `ChunkingSettings` class + `chunking` field from `config.py`, drop the `chunking:` yaml block, drop the 4 new tests; the docstring fix in `sentence_tokenizer.py` is cosmetic and may stay).

**Verified:** with exactly those three source changes reverted (P3-104 left intact), the 4 new tests fail **and only those 4** — `ChunkingSettings` import fails, the env override is rejected as `extra_forbidden`, and the wiring test fails on `Settings` lacking `chunking`. All 21 pre-existing tests in the two affected files pass, i.e. the new tests gate exactly the P3-105 behavior and rollback to post-P3-104 state is clean. No schema migration or dependency change to unwind.

## 7. Next Steps (NOT part of this task)

Awaiting engineering review of P3-105. Then, in milestone order: P3-106 (regression + fixture suite under all three engine paths).

---

*End of P3-105 implementation report. Implementation stopped — awaiting engineering review.*
