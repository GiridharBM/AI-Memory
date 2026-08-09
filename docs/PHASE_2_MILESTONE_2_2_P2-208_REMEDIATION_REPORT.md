# P2-208 Remediation Report — R1 (production settings wiring)

**Task:** P2-208 (Milestone 2.2 — Metadata Extraction Framework; milestone gate)
**Review:** `docs/PHASE_2_MILESTONE_2_2_P2-208_ENGINEERING_REVIEW.md` — ❌ Needs Remediation
**Date:** 2026-08-01
**Status:** Ready for engineering re-review

## R1 Finding (verbatim intent)

`DocumentIngestionService()` was built without passing runtime settings in the
production wiring, so `intelligence.metadata.email_attachments` and
`intelligence.metadata.max_file_size_mb` were ignored on the production path —
breaking the frozen rollback contract.

## Required Fix — Applied

### 1. Production wiring passes runtime settings

`IngestionWorkflow.from_runtime` (`app/pipelines/ingest_workflow.py:150`) now
constructs

```python
ingestion_service=DocumentIngestionService(settings=settings)
```

following the same dependency-injection pattern used elsewhere in the wiring.
`create_default` already threaded `settings` into `from_runtime`, so both
production entry points — `app/cli/entry.py:372-373` and
`app/queue/worker.py:84` — now hand runtime `MetadataSettings` to the
`DocumentIngestionService`. The service's `_metadata()` therefore reflects
`email_attachments` (extraction gate) and `max_file_size_mb`
(`_enforce_size_limit`). `max_attachments` was never broken (enforced
workflow-side via `self._metadata()`); it is covered below for completeness.

No unrelated modules touched; no new functionality; backward compatible
(one additive optional parameter).

### 2. Regression test net via the production wiring

Four `test_create_default_*` tests added to
`tests/integration/test_email_attachment_ingestion.py`. Each builds the
workflow through `IngestionWorkflow.create_default(settings)` — the production
wiring — with network-dependent steps replaced by fakes after construction.

| Test | Verifies |
|------|----------|
| `test_create_default_wires_metadata_settings_to_service` | The service the workflow built actually holds `email_attachments=False`, `max_file_size_mb=7`, `max_attachments=3` from the runtime settings (direct proof the R1 bug is closed). |
| `test_create_default_email_attachments_false_extracts_nothing` | `email_attachments=false` → 1 document (no children), and the set of `pam_email_attachments_*` dirs in `tempfile.gettempdir()` is unchanged (no temp dirs remain). |
| `test_create_default_enforces_max_file_size_mb` | `max_file_size_mb=1` → a 1 MiB + 1 byte file is rejected through the production-built service with a size-limit error. |
| `test_create_default_honors_max_attachments` | `max_attachments=1` → only the first of two attachments becomes a child, and no temp dirs remain. |

These tests would have failed before the fix: without settings, the
production-built service read default `MetadataSettings()` (extraction on,
64 MiB limit), so the `email_attachments=false` and `max_file_size_mb=1` cases
would have produced children / accepted the oversized file. The unit-level
`_workflow` helper passes settings to both the service and the workflow, which
is exactly why R1 slipped — the new net exercises the real wiring.

### 3. Implementation report amended

`docs/PHASE_2_MILESTONE_2_2_P2-208_IMPLEMENTATION_REPORT.md` updated:

- **Limits paragraph:** new bullet documents the settings wiring and that the
  rollback contract and size-limit enforcement now hold on the production path.
- **Files modified table:** `from_runtime` wiring change and the R1 regression
  net recorded.
- **Test results table:** integration gate is now `14 passed / 7 deselected`.
- **Remaining risks:** over-size-child entry now references the
  production-wiring size-limit regression test.
- **Milestone readiness:** reflects R1 remediation complete, pending re-review.

## Test Results (post-remediation)

| Gate | Result |
|------|--------|
| `python -m pytest tests/unit -q` | 605 passed / 0 deselected (baseline preserved) |
| `python -m pytest tests/integration -q --ignore=tests/integration/smoke_test.py` | 14 passed / 7 deselected (10/6 baseline + 4 R1 regression tests; AC test integration-marked) |
| `python -m pytest tests/integration/test_email_attachment_ingestion.py -m integration` | 1 passed (frozen AC) |
| `python -m ruff check app tests` | 64 errors (pre-existing baseline; 0 in new/changed files) |
| `python -m mypy app` | 4 pre-existing errors (fitz/pptx/whisper/numpy stubs); changed files clean |

## Files Changed

| File | Change |
|------|--------|
| `app/pipelines/ingest_workflow.py` | `from_runtime` → `DocumentIngestionService(settings=settings)` (one line) |
| `tests/integration/test_email_attachment_ingestion.py` | +4 `test_create_default_*` regression tests, `_write_eml` / `_production_workflow` / `_temp_attachment_dirs` helpers; removed unused `email.policy` import |

## Out of Scope (unchanged)

Engineering-review observations O1–O5 were non-blocking and not addressed per
the remediation instruction. `max_attachments` cap, depth guard, and temp
cleanup behavior are unchanged.
