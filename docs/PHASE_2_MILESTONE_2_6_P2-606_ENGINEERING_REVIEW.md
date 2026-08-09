# P2-606 Engineering Review — Processor + Pipeline Enrichment (Code & Notebook)

**Reviewer:** Principal Engineering Reviewer
**Date:** 2026-08-04
**Task:** P2-606 — Processor + pipeline enrichment for Code & Notebook
**Spec:** `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` (frozen §4.6, line 381); roadmap `## P2-606 — Processor + Pipeline Enrichment`

---

## Verdict

**Approved**

---

## Verification Results

### 1. Frozen Specification & Roadmap Compliance

| Spec / roadmap requirement | Implementation | Verdict |
|----------------------------|---------------|---------|
| §4.6 AC: `ProcessedDocument` carries `code_structure` (code) / `notebook_structure` (notebook) in `metadata.extra` | `ingest_workflow.py:537-547` attaches via `_enrich_code()`; asserted by integration `test_python_file_end_to_end` / `test_notebook_file_end_to_end` on `result.document.metadata.extra` | Pass |
| §4.6 AC: processors remain passthrough (M2.4 TableProcessor) | `CodeProcessor` (`processor_impls.py:159`) and `NotebookProcessor` (:253) unchanged — both `_passthrough`, no structure logic added | Pass |
| §4.6 AC: structure attachment in new `_enrich_code()` at the P2-305 shared hook | `ingest_workflow.py:693`; invoked at :538 immediately after `_enrich_images` (:534-536) — same call site as tables/images | Pass |
| §4.6 AC: gated by `intelligence.code.enabled` and `kind in {"code", "notebook"}` | `_enrich_code` lines 710-714: notebook branch checks `cfg.enabled`; code branch requires `kind == "code" and cfg.enabled`; all other kinds → `None` | Pass |
| §4.6 AC: `CodeSettings` added to `IntelligenceSettings` | `config.py:375` — `code: CodeSettings = Field(default_factory=CodeSettings)` | Pass |
| §4.6 AC: rollback test passes (`enabled=false` → pre-M2.6 passthrough) | `test_rollback_enabled_false` (integration), `test_skips_when_disabled`, `test_notebook_rollback_drops_structure_when_disabled` (unit) | Pass |
| Roadmap Files: `CodeSettings` fields `enabled=True`, `languages=Literal["default"]`, `max_cell_outputs=10`, `max_code_chars=100000`, `include_docstrings=True` | `config.py:357-361` — exact values; `ge=1` bound on the two ints; `extra="forbid"` consistent with sibling settings | Pass |
| Roadmap Files: `code:` block under `intelligence:` after `images:` | `config/default.yaml:164-169` — all 5 fields with R-4/C-5 comments | Pass |
| Roadmap Files: `_enrich_code` for `kind == "code"` calls `parse_code(text, filename)` and attaches `code_structure` | `ingest_workflow.py:717-730` — `parse_code(document.text, document.filename, max_chars=cfg.max_code_chars)` → `model_dump(mode="json")` | Pass |
| Roadmap Files: `kind == "notebook"` reads `metadata.extra["notebook_structure"]` and passes through | `ingest_workflow.py:711-712` — identity passthrough of the `NotebookIngestor`-attached structure (P2-605) | Pass |
| DoD: `CodeSettings` wired config → workflow → enrichment hook | `_code()` accessor (:161); `DocumentIngestionService._code()` + `NotebookIngestor(max_cell_outputs=...)` (`service.py:70,100-103`) — verified end-to-end (see §3) | Pass |
| DoD: all unit + integration + regression tests pass; no new lint errors | Full suite 947 passed; ruff clean (see §6-8) | Pass |

### 2. Configuration (independently verified)

| Check | Result |
|-------|--------|
| `CodeSettings()` default construction matches frozen spec | ✅ `test_intelligence_code_defaults_reproduce_frozen_spec` — asserts `load_settings().intelligence.code == CodeSettings()` with all five fields (this also proves the repo `default.yaml` `code:` block loads and matches the model) |
| `IntelligenceSettings().code` is a `CodeSettings` | ✅ `test_intelligence_settings_has_code` |
| Env override `PAM_INTELLIGENCE__CODE__ENABLED` / `__MAX_CELL_OUTPUTS` / `__MAX_CODE_CHARS` | ✅ `test_intelligence_code_environment_override` — `load_settings()` chain is yaml → `_apply_environment_overrides` → `Settings(...)` validation (`config.py:413-461`); env wins over yaml |
| `ge=1` bounds reject zero/negative | ✅ field-level `Field(ge=1)` on both ints (model-safe; consistent with `TableSettings` precedent) |
| `extra="forbid"` on `CodeSettings` | ✅ unknown yaml/env keys under `code:` fail validation fast (matches sibling settings) |

### 3. Runtime Wiring (independently verified)

| Link | Evidence |
|------|----------|
| Classifier → kind: `.py` → `code`, `.ipynb` → `notebook` | `EXTENSION_KIND_MAP` (`classifier.py:33,41`); `CODE_EXTENSIONS` contains `.py`, `NOTEBOOK_EXTENSIONS = {".ipynb"}` (`extensions.py:6,42`) |
| kind flows into `_run_routed_processor` | `ingest_workflow.py:310-316` — `kind=classification.kind` |
| `_enrich_code` call site after images | `ingest_workflow.py:537-547`; `doc_kind = kind or result.source_type` handles `kind=None` |
| Code parse honors `max_code_chars` | `parse_code(text, filename, max_chars)` threaded through AST and heuristic parsers + `SyntaxError` fallback (`parser.py:32-38,128-129,182-183,246-262`); config override proven by `test_max_code_chars_wired_from_config` (`char_end == 5`) |
| Notebook cap honors `max_cell_outputs` | `parse_notebook(raw, max_cell_outputs)` → `NotebookParser.parse` (`notebook.py:62-63,111-117`); ingestor default preserved when `None` |
| Config → ingestor thread | ✅ **independent runtime check:** `DocumentIngestionService(settings)` produces a `NotebookIngestor` whose `_max_cell_outputs == settings.intelligence.code.max_cell_outputs` (10 default, 3 after override) |
| Notebook passthrough identity | `test_passes_notebook_structure` asserts `extra["notebook_structure"] is structure` — the same model object, no copy/serialization drift |

### 4. Acceptance Criteria

All six frozen ACs met (table in §1). Roadmap test matrix:

| Roadmap test | Implemented as | Result |
|--------------|----------------|--------|
| `test_code_settings_defaults` | `test_intelligence_code_defaults_reproduce_frozen_spec` | ✅ |
| `test_intelligence_settings_has_code` | same name | ✅ |
| `test_enrich_code_skips_when_disabled` | same name — asserts `extra == {}` | ✅ |
| `test_enrich_code_skips_unknown_kind` | same name (`kind="markdown"`) | ✅ |
| `test_enrich_code_attaches_python_structure` | same name | ✅ |
| `test_enrich_code_passes_notebook_structure` | same name | ✅ |
| `test_code_file_through_workflow` / `test_notebook_file_through_workflow` (roadmap: extend `test_ingest_workflow.py`) | `test_enrich_code.py` drives the **real** `_run_routed_processor` with passthrough processors + integration `test_python_file_end_to_end` / `test_notebook_file_end_to_end` through real `IngestionWorkflow.run()` | ✅ (AC covered via integration, stronger than the suggested unit path) |
| `test_python_file_end_to_end`, `test_notebook_file_end_to_end`, `test_rollback_enabled_false` | `tests/integration/test_code_pipeline.py` | ✅ 3/3 passed |

### 5. Rollback Contract (R-4)

| Case | Verified |
|------|----------|
| `code.enabled=false` → code doc has no `code_structure` | `test_skips_when_disabled` asserts full `extra == {}`; integration `test_rollback_enabled_false` asserts key absence on the real `.py` fixture |
| `code.enabled=false` → notebook doc has no `notebook_structure` despite `NotebookIngestor` attaching it unconditionally (P2-605) | `_enrich_code` returns `None` for disabled notebook → `extra.pop("notebook_structure", None)` at `ingest_workflow.py:543-547`; unit `test_notebook_rollback_drops_structure_when_disabled` (`extra == {}`) + integration key-absence check |
| No other enrichment leaks into code/notebook docs | `TEXT_BEARING_KINDS = {"markdown", "text"}` (`structure/detector.py:19`) excludes code/notebook, so no `structure` key; tables/images gated on `requires_table_extraction`/`kind=="pdf"` — code/notebook unaffected. Rollback docs are truly Phase-1-identical |
| Scope of the pop | Confined to the `enabled=false`/missing-structure path (`elif doc_kind == "notebook"`), so the enabled path is untouched |

### 6. Tests (independently re-run)

| Gate | Result |
|------|--------|
| `tests/unit/test_config.py`, `test_enrich_code.py`, `test_code_parser.py`, `test_notebook_parser.py`, `test_notebook_ingestor.py` | **67 passed** in 1.44s |
| `tests/integration/test_code_pipeline.py` (`-m integration`) | **3 passed** |
| Full suite | **947 passed, 31 deselected, 0 failed** (935 baseline + 12 new) — no regressions |
| Integration suite (default-deselected) | 29 passed, 1 skipped (Tesseract), 14 deselected |

### 7. Coverage

| File | Coverage | Notes |
|------|----------|-------|
| `code/notebook.py` | **100%** (58/58) | incl. `max_cell_outputs` override path |
| `code/parser.py` | **100%** (114/114) | incl. `max_chars` override on AST + heuristic + fallback |
| `core/config.py` | **96%** | missing lines are pre-existing env/error paths (107, 138, 205, 471, 476, 481-482, 485, 526, 538-539) — none are P2-606 |
| `notebook_ingestor.py` | **85%** | above 80% floor; missing 36-39 (JSON-decode/read `IngestionError`) and 49, 55 (single-string source, raw-cell branch) are pre-existing flattening paths |
| `service.py` / `ingest_workflow.py` | P2-606 delta covered | `NotebookIngestor(max_cell_outputs=...)` (:70) and `_code()` settings path (:103) hit; call site (:537-547) and `_enrich_code` happy paths (:710-722, :730) hit; only the defensive `except Exception` (:723-729) and `settings=None` fallbacks are uncovered |
| Repo-wide floor | **88.88%** total — above `fail_under=80` | `947 passed` with `--cov=app` |

### 8. Ruff

`python -m ruff check` over all 12 changed files → **All checks passed** (E/F/I/B/UP, line-length 100). Full `ruff check app tests` reports 0 findings in any touched file.

### 9. Mypy

Scoped `mypy --follow-imports=skip` over the six changed source files → **0 issues on P2-606 lines**. The 11 errors reported in `ingest_workflow.py` are all pre-existing (lines 130, 341, 358, 610, 749, 757, 772, 774, 778, 790 — `object`-typed ctor params, `NoteGenerator` protocol kwargs, pre-M2.6 `_run_knowledge_engine` blocks); none fall on P2-606 additions (161-164, 537-547, 693-730). Bare repo-wide mypy remains blocked by pre-existing env issues (`python-pptx` stub, `numpy` stub under Python 3.14, `faster_whisper` untyped) — reported identically in prior milestone reviews.

---

## Notes (non-blocking)

1. **`_enrich_code` return annotation** is `dict[str, object] | None`, but the notebook branch returns the `NotebookStructure` model (identity passthrough), not a serialized dict. Harmless — `metadata.extra` is `dict[str, Any]` and Pydantic v2 serializes the nested model on `model_dump()` (P2-605 already stored the object the same way). Could be widened to `object | None` for accuracy.
2. **Parser module defaults remain** (`_MAX_CODE_CHARS = 1_000_000`, `_MAX_CELL_OUTPUTS = 100`) as direct-call fallbacks; production always overrides them with `CodeSettings` values (100000 / 10) via the wiring in §3, matching the frozen spec. Consistent with how P2-605 left its constant in place.
3. **`test_skips_unknown_kind` harness** drives `NotebookProcessor` with `kind="markdown"`. The processor choice is irrelevant — the `kind` gate short-circuits first — but the construction is slightly confusing. No functional impact.
4. **Pop happens at the workflow hook, not the ingestor.** A notebook that bypasses `_run_routed_processor` (only reachable if `NotebookProcessor` were unregistered — it is not) would retain `notebook_structure`. Consistent with the frozen Option-2 design; no change required.

---

## Summary

All nine review dimensions pass. `CodeSettings` is a faithful frozen-spec model (five exact fields, `ge=1` bounds, `extra="forbid"`) loaded from `default.yaml` and overridable via `PAM_INTELLIGENCE__CODE__*`; the config→workflow→hook thread is proven end-to-end, including an independent runtime check that `DocumentIngestionService` threads `max_cell_outputs` into `NotebookIngestor`. `_enrich_code()` follows the `_enrich_tables()`/`_enrich_images()` best-effort pattern exactly, is gated per the frozen ACs, attaches `code_structure` from `parse_code(..., max_chars)` and passes `notebook_structure` through by identity. The rollback contract holds on both code (no key) and notebook (key dropped despite the unconditional P2-605 attach) paths, and `TEXT_BEARING_KINDS` excludes code/notebook so no other enrichment key leaks — rollback documents are Phase-1-identical. Coverage is 100% on both parser modules and above the 80% floor everywhere else (repo total 88.88%), ruff is clean, mypy shows no new errors, and the full suite passes at 947 with no regressions. All observations are non-blocking. No findings require remediation.

---

**Signed:** Principal Engineering Reviewer
**Date:** 2026-08-04
