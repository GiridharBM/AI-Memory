# P2-605 Implementation Report — Notebook Parser + Ingestor Upgrade

**Task:** P2-605 — Notebook (ipynb) parser and notebook ingestor upgrade
**Spec:** `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` (frozen §4.5.2, §4.7, line 379)
**Date:** 2026-08-04
**Status:** COMPLETE

---

## Summary

Added `NotebookParser` / `parse_notebook()` in `app/infrastructure/document_intelligence/code/notebook.py` — a never-raising parser that turns a parsed `.ipynb` dict into an ordered `NotebookStructure`. Upgraded `NotebookIngestor` to call it and store the structure in `metadata.extra["notebook_structure"]` while keeping the existing flattened text in `text` (Option 2 from the roadmap). Config wiring stays out of scope per user instruction (P2-606).

## Files Changed

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/code/notebook.py` | **New** — `NotebookParser` class + `parse_notebook()` public function |
| `app/infrastructure/document_intelligence/code/__init__.py` | Extended — exports `NotebookParser`, `parse_notebook` |
| `app/infrastructure/ingestion/notebook_ingestor.py` | Extended — calls `parse_notebook(notebook)`; stores structure in `metadata.extra["notebook_structure"]` |
| `tests/unit/test_notebook_parser.py` | **New** — 13 parser tests (roadmap §Tests) |
| `tests/unit/test_notebook_ingestor.py` | **New** — 3 ingestor upgrade tests (roadmap §Tests) |

## Implementation

`code/notebook.py` (extracts from the full notebook dict that `json.loads` produces):

- **`parse(raw: dict) -> NotebookStructure`** — iterates the `cells` array; malformed cells (missing/non-dict) are **skipped with a logged warning**; **never raises**.
- **`NotebookCell` mapping** — `id` (falls back to zero-based index), `type` (only markdown/code/raw accepted; unknown types logged + skipped), `source` (list of lines or a single string joined), `outputs` (best-effort string form, capped), `execution_count` (kept only when a real `int`).
- **Outputs** — capped at `max_cell_outputs` (constant `_MAX_CELL_OUTPUTS = 100`, `ponytail:` comment defers config wiring to P2-606); entries beyond the cap are replaced with `"[truncated]"`.
- **Kernel/language** — `metadata.kernelspec.display_name` → `kernel`; `metadata.language_info.name` → `language`.
- **Structure returned** — `NotebookStructure(cells, kernel, language)`; also exposed as `parse_notebook(raw)` for the ingestor.

`notebook_ingestor.py` — after `json.loads(notebook_path.read_text(...))`, the extra dict now includes `"notebook_structure": parse_notebook(notebook)` alongside the existing `cell_count`, `kernel`, `language`; flat text remains in `text`.

## Acceptance Criteria Met

| Criterion | Status |
|-----------|--------|
| `parse(raw)` accepts full notebook dict; extracts `cells` → ordered `NotebookCell` | `test_parse_valid_notebook`, `test_parse_orders_cells` |
| `id`, `type`, `source` (joined), `outputs` (capped), `execution_count` populated | parser tests + `test_parse_caps_outputs` |
| `metadata.kernelspec.display_name` → `kernel`; `language_info.name` → `language` | `test_parse_extracts_kernel`, `test_parse_extracts_language` |
| **Never raises** on malformed cells — skip + log warning | `test_parse_skips_malformed_cells`, `test_never_raises` |
| Outputs capped; excess replaced with `"[truncated]"` | `test_parse_caps_outputs` (monkeypatched `_MAX_CELL_OUTPUTS`) |
| Ingestor calls parser, stores structure in `metadata.extra` | `test_ingest_calls_parser` |
| Existing flat text preserved in `text` | `test_ingest_preserves_flat_text` |
| Existing `cell_count`/`kernel`/`language` kept | `test_ingest_populates_metadata` + integration test unchanged |

## Verification

| Check | Result |
|-------|--------|
| `ruff check` | All checks passed |
| `mypy` | `notebook.py` — Success; `notebook_ingestor.py` — Success (scoped `--follow-imports=skip`, see note) |
| New tests (16) | All passed |
| `notebook.py` coverage | **100%** (57/57 stmts) |
| `notebook_ingestor.py` coverage | **84%** — above the 80% floor; uncovered lines 32-35/45/51 are pre-existing error/edge paths (JSON decode, read failure, string source, raw cell) |
| Full suite | **935 passed, 28 deselected, 0 failed** (919 baseline + 16 new) |
| Regressions | None — existing notebook integration test (`test_notebook_ingest_enriches_metadata_superset`) unchanged and passing |

**mypy note:** bare `mypy app/infrastructure/ingestion/notebook_ingestor.py` is blocked by pre-existing repo-wide env issues (missing `python-pptx` stub in `pptx_ingestor.py`; `numpy` stub requiring Python ≥3.12 under 3.14). The scoped run over the changed file reports no issues.

## Downstream Dependencies (not implemented)

- **P2-606** — config wiring: `_MAX_CELL_OUTPUTS` replaced by `CodeSettings.max_cell_outputs`; enrichment hook consumes `NotebookStructure`.
