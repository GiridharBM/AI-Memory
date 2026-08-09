# Phase 2 — Milestone 2.4 Remediation Report

Date: 2026-08-03
Scope: Required findings R1 + R2 from the Principal Engineering Review of Milestone 2.4.
Mandate: apply only Required findings; no unrelated changes; re-run tests/ruff/mypy; verify every finding resolved.

## R1 — Dead `min_confidence` config (Removed)

**Verdict (review):** `min_confidence` was dead configuration. Verified against the `pdfplumber-0.11.10` wheel: zero references in the package; `TableSettings.resolve` silently ignores unknown keys; camelot path never reads confidence. Review offered (a) remove or (b) add a real consumer.

**Resolution — option (a) remove.** Recorded as a deviation from the frozen §2.4 contract (`docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md`, which stays untouched as a historical artifact).

| Change | File |
| --- | --- |
| `PdfTableExtractor.__init__` drops `min_confidence` param; docstring records the removal | `app/infrastructure/document_intelligence/tables/extractor.py` |
| `page.extract_tables()` call drops `table_settings={"min_confidence": ...}` | same |
| `get_table_extractor` drops the kwarg and forwarding | same |
| `TableSettings` drops `min_confidence` field; docstring documents deviation | `app/core/config.py` |
| `intelligence.tables` block drops `min_confidence` | `config/default.yaml` |
| `_enrich_tables` drops `min_confidence=cfg.min_confidence` from the call | `app/pipelines/ingest_workflow.py` |
| default-spec assert removed | `tests/unit/test_config.py` |
| docs corrected (config knobs, tuning claims, key-design-decisions) | `docs/changelog.md`, `docs/MASTER_ENGINEERING_DESIGN_DOCUMENT.md`, `docs/01_Current_Implementation_Report.md`, `docs/PHASE_2_MILESTONE_2_4_IMPLEMENTATION_REPORT.md` |

**Verification:** grep confirms zero `min_confidence` references in `app/` and `tests/`; remaining occurrences are limited to docs/spec/historical review files.

## R2 — Unenforceable PDF test (Fixed)

**Verdict (review):** `test_absent_engine_degrades_to_flat_fallback` asserted `tables == [] or all(isinstance(t, Table)...)`, which could never fail; P2-405 AC ("Ruled-table PDF → Markdown table") had zero enforceable coverage.

**Resolution — two-part strict coverage:**

1. **Strict degraded path** (`tests/unit/test_table_intelligence.py::TestPdfExtraction::test_absent_engine_degrades_to_flat_fallback`): monkeypatches `builtins.__import__` with the exact `__import__` signature (mypy-clean) to force `ImportError("pdfplumber disabled for test")`; asserts `tables == []` **and** a `pdfplumber` warning is logged. Enforceable in every environment.
2. **Engine-present AC test** (`test_engine_present_extracts_ruled_table`, `@pytest.mark.integration`, `pytest.importorskip("pdfplumber")`): asserts ≥1 `Table`, all `Table` instances, and rendered Markdown starting `|` with a `| --- |` separator row.

**Fixture fix uncovered by the new test:** the committed `ruled_table.pdf` was a mislabeled text-only PDF (0 lines / 0 rects under pdfplumber) — the AC could never pass. Regenerated `tests/fixtures/tables/ruled_table.pdf` as a genuine ruled table (ReportLab GRID line strokes; pdfplumber sees 8 lines and extracts exactly the expected 3×3 grid). Generator: `gen_ruled_pdf.py` (temp; parameters recorded in changelog).

## Verification

| Check | Command | Result |
| --- | --- | --- |
| Full suite (default, integration deselected) | `pytest --cov=app` | 778 passed, 24 deselected |
| Coverage floor 80% | same | 88.27% |
| Hermetic integration (table/structure/metadata) | `pytest -m integration` on the 3 suites | 20 passed |
| Engine-present PDF AC (pdfplumber installed) | `pytest ... -m integration -k Pdf` | PASSED |
| Degraded-path PDF | `pytest ... -k Pdf` default | PASSED |
| Lint | `ruff check` on all changed files | All checks passed |
| Types | `mypy` on changed files | no issues found |
| Dead config sweep | grep `min_confidence` in `app/` + `tests/` | 0 matches |

## Status

Both Required findings resolved and verified. Recommended (non-blocking) items from the review were intentionally not touched: BOM leak, changelog gate wording, template→infrastructure import, disabled-test duplication, registry rebuild.
