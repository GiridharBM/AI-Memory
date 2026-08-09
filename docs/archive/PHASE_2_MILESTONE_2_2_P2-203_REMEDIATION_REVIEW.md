# P2-203 Remediation Review — Config Plumbing for `mime_enabled` (F1)

**Task:** P2-203 (Milestone 2.2 — Metadata Extraction Framework)
**Review scope:** P2-203 remediation for blocking finding F1 only. No code modified.
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` §P2-203 (lines 116–134) + §3 Normative Configuration + R-4 rollback
**Reviewer:** Principal Engineering Reviewer
**Date:** 2026-08-01

---

## 1. F1 Resolution — `intelligence.metadata.mime_enabled` is consumed

| Verification point | Status | Evidence |
|---|---|---|
| Config value is read from `settings.intelligence.metadata` | ✅ | `_metadata()` helper returns `self._settings.intelligence.metadata` (`ingest_workflow.py:122-125`) |
| `DocumentClassifier` receives the configured value | ✅ | `DocumentClassifier(mime_enabled=self._metadata().mime_enabled)` (`ingest_workflow.py:102`) |
| Full production chain plumbed | ✅ | `create_default(settings)` → `from_runtime(..., settings=settings)` → `cls(..., settings=settings)` → `__init__` (`ingest_workflow.py:202`, `:150`, `:102`). Production callers `cli/entry.py:372` and `queue/worker.py:84` both construct via `create_default(settings)` — the config now reaches the classifier in the running system |
| Pattern matches P2-207 precedent | ✅ | same optional `settings: Settings \| None` keyword + `_metadata()` default-to-`MetadataSettings()` helper as `service.py:56,90-93` |

## 2. Behavior Matrix

| `mime_enabled` | Classifier path | Evidence |
|---|---|---|
| `true` | `detect_mime(source_path)` (extension-primary, content-sniff fallback) | `classifier.py:108-112`; workflow test `test_true_uses_detect_mime` (spy asserts `detect_mime` called with the path, result `text/markdown`) |
| `false` | `mimetypes.guess_type(document.filename)` — stdlib path, no magic sniff (frozen §3) | `classifier.py:111-112`; workflow test `test_false_bypasses_detect_mime` (`detect_mime` spy raises if touched; result `mime_type is None` for extensionless filename) |
| `settings=None` (all pre-existing callers) | `mime_enabled=True` via `MetadataSettings()` default | `_metadata()` returns fresh `MetadataSettings()` (`mime_enabled: true` frozen default) — identical to prior `DocumentClassifier()` construction |

## 3. Existing Behavior Preservation

- **All existing `IngestionWorkflow(...)` constructions** (integration `test_complete_workflow`, `test_queue_worker_pipeline`, `test_e2e_complete`, `test_knowledge_engine`, `test_processor_wiring`) omit `settings` → fall back to the frozen default `true`, behaviorally identical to the pre-remediation `DocumentClassifier()`. ✅
- **`from_runtime` signature** gains one optional keyword-only `settings` param — additive, no breaking change. ✅
- **No unrelated modules modified.** The diff to `ingest_workflow.py` is limited to the `settings` plumbing, `_metadata()`, and the classifier construction line (the OCR wiring hunks visible in `git diff` are pre-existing uncommitted work from an earlier phase, not part of this remediation). ✅

## 4. Test Coverage (both configuration paths)

`tests/unit/test_mime_detection.py` — `TestWorkflowMimeEnabledConfig` (3 new tests, all passing):

1. **`test_true_uses_detect_mime`** — default settings (`mime_enabled: true`) → workflow classifier invokes `detect_mime` (spy records `[str(path)]`) and yields `text/markdown` for an extensionless Markdown file.
2. **`test_false_bypasses_detect_mime`** — `mime_enabled=false` → workflow classifier never touches `detect_mime` (spy raises on call) and returns `mime_type is None` (stdlib `guess_type` result).
3. **`test_from_runtime_plumbs_settings`** — `from_runtime(settings=…)` with `mime_enabled=false` → `workflow._classifier._mime_enabled is False`.

Classifier-level coverage retained: `test_mime_enabled_detects_extensionless_markdown` (true path) and `test_mime_disabled_keeps_stdlib_behavior` (false path). The monkeypatch binding is correct — `classifier._detect_mime` resolves the module-global `detect_mime` imported at `classifier.py:29`, so patching `app.infrastructure.routing.classifier.detect_mime` exercises the real dispatch seam. ✅

## 5. Regression Safety (independently re-run by reviewer)

| Gate | Result |
|---|---|
| `python -m pytest tests -m "not integration" -q` | **573 passed / 7 deselected** (570 baseline + 3 new; 0 regressions) |
| `python -m pytest tests/unit/test_mime_detection.py tests/unit/test_processor_wiring.py -q` | 40 passed |
| `python -m pytest tests/integration -m integration -q --ignore=tests/integration/smoke_test.py` | 5 passed / 1 skipped (Tesseract absent) — workflow integration tests pass with the new keyword |
| `python -m ruff check app tests` | 64 errors — pre-existing baseline, unchanged |
| `python -m mypy app` | 4 errors — pre-existing (fitz/pptx/whisper/numpy stubs), unchanged |

The excluded `smoke_test.py` failure is the known-flaky live-LLM assertion (llama3.1:8b section presence), unrelated to P2-203 and its remediation.

## 6. Observations O2–O6

Re-checked; none became blockers: O2 (internal API name `_magic_fallback`) and O6 (report mislabeling next task as P2-204) are documentation/naming items unchanged by this remediation; O3/O4/O5 were informational in the original review and remain so. Informational only.

---

## Verdict

✅ **Approved**

F1 is fully resolved: `intelligence.metadata.mime_enabled` is consumed from settings and passed into `DocumentClassifier` along the complete production chain (`create_default` → `from_runtime` → `__init__`), following the exact P2-207 plumbing pattern. Both configuration paths are verified by behavior-level tests (`true` → `detect_mime()` spy-invoked; `false` → `detect_mime()` bypassed, stdlib `guess_type` path), existing behavior is preserved for all callers via the frozen `MetadataSettings()` default, and all gates are clean with zero regressions (573 unit, 5 integration, ruff/mypy baselines unchanged). No further remediation required.
