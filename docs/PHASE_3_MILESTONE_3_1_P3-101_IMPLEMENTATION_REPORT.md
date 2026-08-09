# Milestone 3.1 — P3-101 Implementation Report

**Task:** P3-101 — Sentence tokenizer protocol + registry + factory (scaffold)
**Status:** DONE — implemented, tested, not wired into ingestion (per DoD)
**Date:** 2026-08-06
**Contract:** `docs/PHASE_3_MILESTONE_3_1_IMPLEMENTATION_ROADMAP.md` (P3-101 block)
**Scope rule honored:** ONLY P3-101 implemented; no future task work. P3-102 (heuristic engine), P3-103 (NLTK engine), P3-104, P3-105 (wiring into `SemanticChunker`), P3-106 not started.

---

## 1. What Was Implemented

Per the frozen task block (Objective / Interfaces / Implementation Steps):

| Deliverable | Location | Notes |
|-------------|----------|-------|
| `SentenceTokenizer` Protocol | `app/infrastructure/sentence_tokenizer.py` | `@runtime_checkable`; contract is `split(text: str) -> list[str]`; D5 docstring locked at the protocol surface |
| `SentenceTokenizerSelectionError` | same module | Raised when no engine is available for a selection (mirrors M2.1 `OCRSelectionError`) |
| Engine registry | `_ENGINE_REGISTRY` (module-level `dict[str, type[SentenceTokenizer]]`) | `register_sentence_tokenizer(name, engine)` — P3-102 registers `"heuristic"`, P3-103 registers `"nltk"`; `"auto"` is a pseudo-value resolved by the factory, not registered |
| `get_sentence_tokenizer(engine="auto")` factory | same module | `"auto"` prefers `"nltk"` when registered **and** importable (via `_nltk_available()`), else falls back to registered `"heuristic"` with **one** logged warning (D4); explicit `"heuristic"`/`"nltk"` return the registered engine; unknown engine value → clear error; known-but-unregistered → clear error; empty registry `"auto"` → clear error |
| `_nltk_available()` import guard | same module | `try: import nltk` under the repo's optional-import convention (`# type: ignore[import-not-found]`); false when the package is absent |
| Test module | `tests/unit/test_sentence_tokenizer.py` (new) | 12 tests, fake engines only |

### Design decisions
- **Registry stores engine *classes*, factory returns fresh instances** — tokenizers are stateless; each `get_sentence_tokenizer` call returns a new instance of the resolved class, and repeated calls with the same args resolve to the same engine type (selection is stable per call).
- **`"auto"` resolution separated from explicit selection** — `auto` consults both the registry and `_nltk_available()` (NLTK preferred only when actually usable); explicit names return the registered engine or raise. `_nltk_available` is a test seam (monkeypatched in the auto-resolution tests).
- **No real engines in this task** (scope-confirmed): the empty→`[]` behavior and the D5 reconstruction contract are *locked at the protocol level* via fake engines and verified in full once P3-102/P3-103 land real implementations.
- **No settings/config wiring** — this scaffold has no config surface; P3-105 owns the integration into `SemanticChunker`.

## 2. Test Results

**New tests:** `tests/unit/test_sentence_tokenizer.py` — **12 passed**.

Coverage (target module scope):
```
app\infrastructure\sentence_tokenizer.py   32 stmts  84%  (63-67 = _nltk_available true-branch)
```
The 5 uncovered lines are the NLTK-present branch of `_nltk_available()`/`auto` (real `nltk` not installed here; exercised via monkeypatch in `test_auto_prefers_nltk_when_available`). Repo floor is 80% — met.

**Full suite:** `python -m pytest` → **959 passed, 31 deselected** (baseline 947 passed / 31 deselected; +12 net new, 0 regressions).

| Gate | Result |
|------|--------|
| Unit tests (P3-101) | 12/12 passed |
| Full suite | 959 passed / 31 deselected (no regressions) |
| Coverage (new module) | 84% (repo floor 80%) |
| Ruff | All checks passed on new files |
| Mypy | No issues on new module |

Test coverage of the frozen testing strategy:
- Factory returns an engine for `"heuristic"` / `"nltk"` ✅ (`test_explicit_heuristic`, `test_explicit_nltk`)
- `"auto"` with nltk absent → heuristic + **one** logged warning ✅ (`test_auto_falls_back_to_heuristic_with_one_warning_when_nltk_absent` — asserts exactly one WARNING record mentioning the fallback)
- `"auto"` with nltk available → nltk ✅ (`test_auto_prefers_nltk_when_available`)
- Unknown engine value → clear config error ✅ (`test_unknown_engine_value_raises_clear_error`)
- Known-but-unregistered / empty-registry `"auto"` → clear selection error ✅ (`test_known_but_unregistered_raises`, `test_empty_registry_auto_raises_clear_error`)
- Selection stable per call ✅ (`test_selection_is_stable_per_call`)
- Protocol runtime-checkable + D5 empty/whitespace → `[]` contract ✅ (`test_runtime_checkable`, `test_empty_and_whitespace_text_yield_empty_list`)
- Registry isolation (autouse fixture snapshots/restores `_ENGINE_REGISTRY`) ✅

## 3. Acceptance Criteria / DoD Verification

| Criterion (frozen) | Status |
|--------------------|--------|
| `SentenceTokenizer` protocol exists with `split(text) -> list[str]` | ✅ unit-tested |
| Engine registry + factory scaffold | ✅ unit-tested (fakes) |
| Clear error for unknown/unavailable engine; empty-registry `"auto"` raises clear error | ✅ unit-tested |
| `"auto"` degrades nltk→heuristic with one logged warning (D4) | ✅ unit-tested (monkeypatched `_nltk_available`) |
| "Working tokenizer in every environment" / empty→`[]` ACs | ⏳ verified against fake engines now; **fully satisfied at P3-102/P3-103** when real engines are registered (scope-confirmed deferral) |
| Not wired into ingestion | ✅ no changes to `ingestion/`, `routing/`, `pipelines/`, `config/`, `semantic_chunking.py` |
| Interface reviewed (DoD) | ✅ awaiting engineering review |
| Unit-tested (DoD) | ✅ 12 tests |

## 4. Files Changed

| File | Action |
|------|--------|
| `app/infrastructure/sentence_tokenizer.py` | **new** — protocol, registry, factory, `_nltk_available` |
| `tests/unit/test_sentence_tokenizer.py` | **new** — 12 unit tests |

No configuration changes (`pyproject.toml` untouched), no existing-file edits, no engine modules.

## 5. Rollback Plan

Pure addition, not wired into any ingestion path — removal is a safe revert (frozen P3-101 rollback row). No config, no schema, no behavior change outside the new module.

## 6. Next Steps (NOT part of this task)

Awaiting engineering review of P3-101. Then, in milestone order: P3-102 (heuristic engine, registers `"heuristic"` — makes `"auto"` never raise) → P3-103 (NLTK `punkt_tab` engine, registers `"nltk"`) → P3-104 → P3-105 (wire into `SemanticChunker`) → P3-106.

---

*End of P3-101 implementation report. Implementation stopped — awaiting engineering review.*
