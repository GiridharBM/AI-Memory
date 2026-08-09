# P2-204 Implementation Report — Language Detection Service

**Task:** P2-204 (Milestone 2.2 — Metadata Extraction Framework)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` §P2-204 (lines 138–156)
**Date:** 2026-08-01
**Status:** Ready for engineering review

## Implementation Summary

Implemented the language detection service per the frozen §P2-204 contract
(MEDD G16 — today `language` is never populated for any document; this task
provides the service, P2-205 owns propagation).

- **`detect_language(text: str) -> tuple[str, float]` API**
  (`app/infrastructure/document_intelligence/metadata/language.py`): returns
  `(language, confidence)`. Only the first `_MAX_TEXT_BYTES` (10 KB) of input
  are inspected (frozen step 5 performance ceiling). Confidence below
  `_CONFIDENCE_THRESHOLD` (0.5) returns `("en", 0.0)` with a warning — the R7
  mitigation for mis-classified short/technical text (frozen step 3).
- **`LanguageDetector` Protocol (§2) + registration:** a
  `@runtime_checkable` Protocol with `detect(text) -> tuple[str, float]`,
  plus `get_default_language_detector()` (lazy process-wide singleton) and
  `register_language_detector()` — the "register-able detector per the §2
  Protocol" requirement (frozen step 4).
- **Optional `py3langid` fast path:** imported lazily per call inside
  `_Py3LangIdDetector.detect()`; if absent, a debug log is emitted and the
  stdlib heuristic is used (frozen step 1). `py3langid>=0.2.0` added to the
  `intelligence` extra in `pyproject.toml` (frozen "Files likely affected");
  **not installed here**, so the heuristic fallback is the tested default.
  Langid verdicts are normalized via `math.exp(log_confidence)` so confidence
  is a 0–1 probability like the heuristic's.
- **Pure-stdlib `_language_heuristic` (frozen step 2):** fixed small set —
  Japanese detected by the `[\u3040-\u30ff]` kana character set
  (`("ja", 0.95)`), en/fr/de by stopword density over the matched word list.
  Empty/whitespace or no-stopword text returns `("en", 0.0)`.
- **Public API:** `detect_language` exported from
  `app/infrastructure/document_intelligence/metadata/__init__.py`, mirroring
  the P2-203 `detect_mime` resolution of the P2-201 review line-63 deferral.
- **Out of scope (P2-205, frozen):** the `language_detection_enabled` gate is
  **not** consumed here — P2-205's frozen step 1 applies it at the classifier
  call site and sets `classification.language`; this module is
  strategy-agnostic and additive (rollback via `language_detection_enabled:
  false`, frozen Rollback Plan).

## Files Modified

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/metadata/language.py` | **new** — `detect_language()`, `LanguageDetector` Protocol, `_language_heuristic` (en/fr/de/ja), `_Py3LangIdDetector` (lazy py3langid fast path + fallback), `get_default_language_detector`/`register_language_detector`, `_MAX_TEXT_BYTES`/`_CONFIDENCE_THRESHOLD` |
| `app/infrastructure/document_intelligence/metadata/__init__.py` | export `detect_language` in public API + `__all__` |
| `pyproject.toml` | `py3langid>=0.2.0` added to `intelligence` extra |
| `tests/unit/test_language_detection.py` | **new** — 14 tests (heuristic accuracy, fallback, threshold, text slice, py3langid path, registry) |

No config changes needed — `MetadataSettings.language_detection_enabled: bool
= True` already exists (`app/core/config.py:277`); consumed by P2-205, not
P2-204.

## Tests Executed

`python -m pytest tests/unit -q` → **577 passed, 0 deselected** (baseline
563 pre-existing tests preserved + 14 new; 0 regressions).

`python -m pytest tests/integration -q --ignore=tests/integration/smoke_test.py`
→ **10 passed, 6 deselected** (unaffected by this change; `smoke_test.py`
excluded per convention — it is the flaky live-LLM test).

New tests:

- **Heuristic accuracy:** en/fr/de sample sentences → correct language at
  confidence ≥ 0.5; Japanese kana text → `("ja", 0.95)`.
- **Fallback:** empty string, whitespace-only, and no-stopword text → `("en",
  0.0)` (no crash, spec-compliant default).
- **Threshold:** a 1-stopword-in-21-words text returns `("en", 0.0)` **and**
  emits a warning containing "below threshold".
- **Text slice:** with mocked `langid`, a 30 KB input yields exactly
  `_MAX_TEXT_BYTES` (10,000) chars delivered to `classify` — the 10 KB ceiling
  is enforced.
- **py3langid path:** mocked `sys.modules["langid"]` returning `("fr", -0.3)`
  → `("fr", math.exp(-0.3) ≈ 0.74)`; absent-langid debug log + heuristic used
  (`langid` is genuinely not installed in this environment).
- **Registry:** default detector is a lazy singleton; `register_language_detector`
  replaces it; `__all__` matches the frozen public surface.

## Test Results

| Gate | Result |
|------|--------|
| `python -m pytest tests/unit -q` | 577 passed / 0 deselected (baseline 563 preserved + 14 new) |
| `python -m pytest tests/integration -q --ignore=tests/integration/smoke_test.py` | 10 passed / 6 deselected |
| `python -m ruff check app tests` | 64 errors (pre-existing baseline; zero in new/changed files) |
| `python -m mypy app` | 4 pre-existing errors (fitz/pptx/whisper/numpy stubs); changed files clean |

## Remaining Risks

- **Heuristic is a small fixed set, not exhaustive:** en/fr/de/ja only;
  other languages and CJK-Han-without-kana text fall back to `("en", 0.0)`
  (R7). When `py3langid` is installed via the `intelligence` extra, accuracy
  improves with no code change; the heuristic stays as the offline fallback.
- **`py3langid` path untested against the real package:** exercised via mocked
  `sys.modules["langid"]` only (not installed here). The import-normalization
  assumption (`langid.classify` returns `(str, float)`) is standard, but a
  real-package smoke test should be added when the extra is installed.
- **Per-call lazy import:** `_try_import_langid()` runs on every `detect` —
  after the first real import Python's `sys.modules` cache makes it a dict
  lookup, so the overhead is negligible (no re-import cost).
- **Flaky live smoke test:** `smoke_test.py::test_live_ollama_…` fails
  intermittently independent of this change; excluded from integration runs.

## Next Recommended Task

**P2-205 — Language propagation + prompt adaptation (frozen):** classifier
calls `detect_language` on the source text when `language_detection_enabled`
and sets `classification.language`; workflow propagates to
`ProcessedDocument.language`; `build_document_analysis_user_prompt` gains a
`language` argument (byte-identical to today when `"en"`). P2-204 provides
the `detect_language` API and the register-able `LanguageDetector` Protocol
it consumes.
