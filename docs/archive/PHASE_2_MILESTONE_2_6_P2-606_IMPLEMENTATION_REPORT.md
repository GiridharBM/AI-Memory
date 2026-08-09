# P2-606 Implementation Report — Code & Notebook Enrichment (Config + Pipeline Wiring)

**Task:** P2-606 — Processor + pipeline enrichment for Code & Notebook
**Spec:** `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` (frozen P2-606 row, line 381)
**Roadmap:** `docs/PHASE_2_MILESTONE_2_6_IMPLEMENTATION_ROADMAP.md` (P2-606 section)
**Date:** 2026-08-04
**Status:** COMPLETE

---

## Summary

Added `CodeSettings` to `IntelligenceSettings` and a `code:` block to `config/default.yaml`, and wired a new `_enrich_code()` structure-attachment hook into `_run_routed_processor()` at the P2-305 shared hook. Code documents get `code_structure` from `parse_code(text, filename, max_chars=...)`; notebook documents pass through the `NotebookStructure` that `NotebookIngestor` already stored in `metadata.extra["notebook_structure"]`. Per the frozen spec the `CodeProcessor`/`NotebookProcessor` routing processors remain passthrough — structure attachment happens at the shared hook, gated by `intelligence.code.enabled` and `kind in {"code", "notebook"}` (mirrors `_enrich_tables()`/`_enrich_images()`).

## Files Changed

| File | Change |
|------|--------|
| `app/core/config.py` | **New** `CodeSettings(BaseModel)` after `ImageSettings`; added `code: CodeSettings = Field(default_factory=CodeSettings)` to `IntelligenceSettings` |
| `config/default.yaml` | **Extended** — `code:` block under `intelligence:` after `images:` (5 fields + C-5/R-4 comments) |
| `app/infrastructure/document_intelligence/code/parser.py` | **Extended** — `_truncate(..., max_chars)`, `CodeParser.parse(..., max_chars)`, `parse_code(..., max_chars)`; AST + heuristic branches both honor it |
| `app/infrastructure/document_intelligence/code/notebook.py` | **Extended** — `NotebookParser.parse(raw, max_cell_outputs)`, `parse_notebook(raw, max_cell_outputs)` |
| `app/infrastructure/ingestion/notebook_ingestor.py` | **Extended** — `__init__(*, max_cell_outputs=None)`; passes cap to `parse_notebook` |
| `app/infrastructure/ingestion/service.py` | **Extended** — `_code()` accessor (settings None → `CodeSettings()`); constructs `NotebookIngestor(max_cell_outputs=...)` |
| `app/pipelines/ingest_workflow.py` | **Extended** — `_code()` accessor; `_enrich_code()` hook; called in `_run_routed_processor()` after images; notebook rollback drop (`enabled: false` → pop `notebook_structure`) |
| `tests/unit/test_config.py` | **Extended** — 4 new CodeSettings tests |
| `tests/unit/test_enrich_code.py` | **New** — 6 `_enrich_code` hook tests |
| `tests/unit/test_code_parser.py` | **Extended** — `test_max_chars_parameter_overrides_default` |
| `tests/unit/test_notebook_parser.py` | **Extended** — `test_max_cell_outputs_parameter_overrides_default` |
| `tests/unit/test_notebook_ingestor.py` | **Extended** — `test_ingest_wires_max_cell_outputs_config` |
| `tests/integration/test_code_pipeline.py` | **New** — 3 end-to-end tests incl. rollback (`enabled: false`) |
| `tests/fixtures/code/sample.py`, `sample.ipynb` | **New** — fixtures for the integration tests |

## Implementation

**Config.** `CodeSettings` matches the frozen spec exactly: `enabled: bool = True`, `languages: Literal["default"] = "default"`, `max_cell_outputs: int = Field(default=10, ge=1)`, `max_code_chars: int = Field(default=100000, ge=1)`, `include_docstrings: bool = True`. Defaults reproduce the pre-config parser constants (`_MAX_CELL_OUTPUTS = 10`, `_MAX_CODE_CHARS = 100000`). `languages` and `include_docstrings` are contract-only this milestone (C-5 precedent); the yaml comments state no code reads them yet.

**Parser parameterization.** `parse_code(text, filename, max_chars=None)` and `parse_notebook(raw, max_cell_outputs=None)` accept explicit overrides; `None` keeps the module-level default. Existing tests that monkeypatch the module caps keep working, and the new tests prove the explicit param wins.

**Enrichment hook.** `_enrich_code(document, kind) -> dict[str, object] | None` in `ingest_workflow.py`:
- `kind == "notebook"` → returns `metadata.extra["notebook_structure"]` (serialized) when enabled, else `None`.
- `kind == "code"` → `parse_code(document.text, document.filename, max_chars=cfg.max_code_chars)`, wrapped in `try/except Exception` → warning log + `None` (never crashes the pipeline), returns `structure.model_dump(mode="json")`.

**Call site.** In `_run_routed_processor()` after the images hook: resolves `doc_kind = kind or result.source_type`, attaches `"code_structure"` for code / `"notebook_structure"` for notebook. On the disabled path (`enabled: false`) the notebook branch explicitly pops `notebook_structure` from `extra` so rollback documents are Phase-1-identical (R-4).

## Acceptance Criteria Met

| Criterion | Status |
|-----------|--------|
| `CodeSettings` added to `IntelligenceSettings` with frozen-spec defaults | `test_intelligence_settings_has_code`, `test_intelligence_code_defaults_reproduce_frozen_spec` |
| Default yaml `code:` block (5 fields) with C-5/R-4 comments | verified by config load + `test_intelligence_code_environment_override` |
| `_enrich_code()` called in `_run_routed_processor()` after images | `test_enrich_code.py` (real workflow, mock deps) |
| Code → `parse_code(text, filename)` → attach `code_structure` | `test_attaches_python_structure` |
| Notebook → pass through `metadata.extra["notebook_structure"]` from `NotebookIngestor` | `test_passes_notebook_structure` |
| Rollback: `enabled: false` → no structure keys, Phase-1-identical | `test_skips_when_disabled`, `test_notebook_rollback_drops_structure_when_disabled`, `test_rollback_enabled_false` (integration) |
| `max_code_chars` / `max_cell_outputs` wired from config | `test_max_code_chars_wired_from_config`, `test_ingest_wires_max_cell_outputs_config`, `test_max_chars_parameter_overrides_default`, `test_max_cell_outputs_parameter_overrides_default` |
| Processors stay passthrough (spec constraint) | unchanged `CodeProcessor`/`NotebookProcessor` |

## Verification

| Check | Result |
|-------|--------|
| `ruff check` (changed files) | All checks passed |
| `ruff check app tests` (CI scope) | 0 findings in any touched file |
| `mypy` (scoped `--follow-imports=skip`, changed files) | 0 errors; the 11 errors reported in `ingest_workflow.py` are pre-existing `object`-typed ctor params / `NoteGenerator` protocol issues, none on added lines |
| New unit tests (12) | All passed |
| New integration tests (3) | All passed |
| Full suite | **947 passed, 31 deselected, 0 failed** (935 baseline + 12 new) |
| Integration suite | **29 passed, 1 skipped (Tesseract), 14 deselected** |

**mypy note:** bare mypy over the repo remains blocked by pre-existing env issues (missing `python-pptx` stub; `numpy` stub requiring Python ≥3.12 under 3.14; `faster_whisper` untyped). Scoped runs over the changed files report no issues.

## Downstream / Notes

- `languages` and `include_docstrings` are contract-only (C-5 precedent) — no code reads them yet; `CodeSettings` must be extended when a follow-up phase consumes them.
- Notebook structure is attached by `NotebookIngestor` unconditionally and dropped by the workflow when `enabled: false`, keeping rollback Phase-1-identical without changing ingestor behavior (R-4).
