# P2-203 Remediation Report — Config Plumbing for `mime_enabled` (F1)

**Task:** P2-203 (Milestone 2.2 — Metadata Extraction Framework)
**Blocking finding:** F1 (P2-203 Engineering Review, `docs/PHASE_2_MILESTONE_2_2_P2-203_ENGINEERING_REVIEW.md`)
**Date:** 2026-08-01
**Status:** Ready for engineering review

## Summary

Resolved the single blocking finding (F1): `intelligence.metadata.mime_enabled`
is now consumed and drives the classifier construction, using the exact
configuration-plumbing pattern established by P2-207 (`DocumentIngestionService`
optional `settings` keyword + `_metadata()` helper defaulting to
`MetadataSettings()`).

- **`IngestionWorkflow.__init__`** gains an optional keyword-only
  `settings: Settings | None = None` (additive; existing no-arg callers and all
  test constructions unchanged). The classifier is now built as
  `DocumentClassifier(mime_enabled=self._metadata().mime_enabled)`.
- **`_metadata()` helper** mirrors P2-207's `service.py:_metadata()`: returns
  `settings.intelligence.metadata` when settings are provided, else a fresh
  `MetadataSettings()` (whose frozen default is `mime_enabled: true`) — so all
  existing call sites behave exactly as before.
- **`from_runtime`** accepts and forwards `settings`; **`create_default`**
  passes `settings=settings` — the production paths (`cli/entry.py:372`,
  `queue/worker.py:84`) now honor `mime_enabled` from config.
- **Behavior matrix preserved:** `mime_enabled=true` → `detect_mime()`
  (extension-primary, content sniff fallback); `mime_enabled=false` →
  `mimetypes.guess_type(document.filename)` stdlib path (frozen §3 rollback:
  "false ⇒ stdlib guess_type path, no magic sniff").
- No architecture change, no new features, no unrelated modules touched.

## Files Modified

| File | Change |
|------|--------|
| `app/pipelines/ingest_workflow.py` | import `MetadataSettings`; `settings` keyword on `__init__`/`from_runtime`; `self._settings`; `_metadata()` helper; `DocumentClassifier(mime_enabled=…)`; `settings=settings` forwarded through `from_runtime`/`create_default` |
| `tests/unit/test_mime_detection.py` | new `TestWorkflowMimeEnabledConfig` (3 tests) — workflow behavior follows the configured value |

No changes to `classifier.py`, `mime.py`, or config files.

## Tests Executed

Added `TestWorkflowMimeEnabledConfig` (3 tests) to `tests/unit/test_mime_detection.py`:

1. **`mime_enabled=true` uses `detect_mime()` at the workflow level** — monkeypatches
   `classifier.detect_mime` with a spy; builds a workflow with default settings
   (`mime_enabled: true`); `workflow._classifier.classify()` calls the spy
   (asserted `calls == [str(path)]`) and yields `text/markdown` for an
   extensionless Markdown file.
2. **`mime_enabled=false` bypasses `detect_mime()`** — monkeypatches
   `classifier.detect_mime` to raise if invoked; sets
   `settings.intelligence.metadata.mime_enabled = False`; `classify()` succeeds
   without touching the spy and returns `mime_type is None` (stdlib `guess_type`
   result for an extensionless filename — the frozen disabled path).
3. **`from_runtime` plumbs the configured value** — `mime_enabled=false` settings
   → `workflow._classifier._mime_enabled is False`.

Classifier-level requirements (1) and (2) remain covered by the existing
`TestClassifierMimeConsult` tests (`test_mime_enabled_detects_extensionless_markdown`,
`test_mime_disabled_keeps_stdlib_behavior`).

## Test Results

| Gate | Result |
|------|--------|
| `python -m pytest tests -m "not integration" -q` | **573 passed / 7 deselected** (570 baseline + 3 new; 0 regressions) |
| `python -m pytest tests/unit/test_mime_detection.py tests/unit/test_processor_wiring.py -q` | 40 passed (new + workflow-wiring regression) |
| `python -m pytest tests/integration -m integration -q --ignore=tests/integration/smoke_test.py` | 5 passed / 1 skipped (Tesseract absent) — workflow integration tests (`test_complete_workflow`, `test_queue_worker_pipeline`, `test_e2e_complete`) pass with the new constructor keyword |
| `python -m ruff check app tests` | 64 errors — pre-existing baseline; zero in changed files |
| `python -m mypy app` | 4 pre-existing errors (fitz/pptx/whisper/numpy stubs); none in changed code |

The known-flaky live-LLM smoke test (`smoke_test.py`) was excluded from the
integration gate run — it does not exercise the classifier or ingestion and was
failing before this remediation (recorded in the P2-203 implementation report).

## Remaining Risks

- None introduced. The `settings` keyword is additive; `None` preserves the
  frozen default (`mime_enabled: true`) for every existing construction site.
  The remaining minor observations (O2–O6) from the engineering review are
  non-blocking and unchanged by this remediation.
