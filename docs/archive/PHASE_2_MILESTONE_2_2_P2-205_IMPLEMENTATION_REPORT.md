# P2-205 Implementation Report — Language propagation + prompt adaptation

**Task:** P2-205 (Milestone 2.2 — Metadata Extraction Framework)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` §P2-205 (lines 160–178)
**Date:** 2026-08-01
**Status:** Ready for engineering review

## Implementation Summary

Implemented language propagation and prompt adaptation per the frozen §P2-205
contract. P2-204 already provided `detect_language(text) -> tuple[str, float]`;
this task consumes it at the classifier call site, propagates the result to
`ProcessedDocument.language`, and adapts the analysis user prompt.

- **Classifier call site (frozen step 1):**
  `DocumentClassifier` (`app/infrastructure/routing/classifier.py`) gains a
  `language_detection_enabled: bool = True` constructor parameter (mirroring
  the P2-203 `mime_enabled` precedent). `classify()` now sets
  `classification.language = self._detect_language(document)`, which returns
  `None` when the gate is off, else `detect_language(document.text)[0]`. The
  gate is threaded from `MetadataSettings.language_detection_enabled`
  (`app/core/config.py:277`) via `IngestionWorkflow.__init__` — the same
  plumbing P2-203 uses for `mime_enabled`.
- **Workflow propagation (frozen step 2):**
  `IngestionWorkflow.run` passes `classification.language` into
  `_run_routed_processor`, which stamps `result.language = language` on the
  returned `ProcessedDocument` (only when language is not `None`, so the
  gated-off path leaves the document untouched). It also passes
  `classification.language` to the `DocumentAIProcessor` constructor so the
  analysis prompt is adapted even when the document's text was extracted by a
  vision/audio/OCR processor.
- **Prompt adaptation (frozen steps 3+4):**
  `build_document_analysis_user_prompt(document, language: str = "en")`
  (`app/prompts/document_analysis.py`) appends
  `"\n\nRespond in {language}."` when `language != "en"`. The default `"en"`
  returns the byte-identical pre-P2-205 prompt string (R8 — schema/JSON
  contract unchanged; verified by a pinned regression test). `DocumentAIProcessor`
  (`app/application/ai_processor.py`) gains a keyword-only `language` parameter
  and forwards it to the prompt builder.
- **Rollback:** `language_detection_enabled: false` ⇒ `classification.language
  is None` ⇒ no prompt instruction and no `ProcessedDocument.language` stamp —
  today's behavior preserved exactly (frozen Rollback Plan).

## Files Modified

| File | Change |
|------|--------|
| `app/infrastructure/routing/classifier.py` | `__init__` gains `language_detection_enabled: bool = True`; `classify()` sets `language`; new `_detect_language` (gate → `detect_language(document.text)[0]`); import of `detect_language` |
| `app/prompts/document_analysis.py` | `build_document_analysis_user_prompt(document, language: str = "en")` appends `"\n\nRespond in {language}."` for non-`"en"`; default byte-identical |
| `app/application/ai_processor.py` | `DocumentAIProcessor.__init__` gains keyword-only `language: str | None`; `_request_analysis` passes `language=self._language or "en"` |
| `app/pipelines/ingest_workflow.py` | gate `language_detection_enabled` at classifier construction; `run()` threads `classification.language` into `_run_routed_processor` and `DocumentAIProcessor`; `_run_routed_processor` stamps `result.language` on `ProcessedDocument` when not `None` |
| `tests/unit/test_language_propagation.py` | **new** — 14 tests (classifier language, prompt adaptation + byte-identical default, AI-processor language, workflow propagation, gate config) |

No config changes — `MetadataSettings.language_detection_enabled: bool = True`
already exists and is now consumed.

## Tests Executed

`python -m pytest tests/unit -q` → **591 passed, 0 deselected** (baseline 577
pre-existing tests preserved + 14 new; 0 regressions).

`python -m pytest tests/integration -q --ignore=tests/integration/smoke_test.py`
→ **10 passed, 6 deselected** (unaffected; `smoke_test.py` excluded per
convention — the flaky live-LLM test).

New tests:

- **Classifier language:** French/German/Japanese text → `language` is
  `"fr"`/`"de"`/`"ja"` (P2-205 AC 2); `language_detection_enabled=False` →
  `None`; default constructor matches the `MetadataSettings` gate default.
- **Prompt adaptation (DoD):** `"fr"`/`"de"` produce exactly the English
  prompt plus `"\n\nRespond in fr."`/`"\n\nRespond in de."`; the default
  (and explicit `"en"`) produce a pinned byte-identical regression string.
- **AI processor:** `DocumentAIProcessor(client, language="fr")` sends a
  prompt containing "Respond in fr."; the default sends no instruction.
- **Workflow propagation (DoD):** `_run_routed_processor(..., language="fr")`
  stamps `ProcessedDocument.language == "fr"`; `language=None` leaves it
  untouched; `run()` constructs the `DocumentAIProcessor` with
  `language="fr"` for a French document; the workflow-built classifier
  honors `language_detection_enabled` from settings.

## Test Results

| Gate | Result |
|------|--------|
| `python -m pytest tests/unit -q` | 591 passed / 0 deselected (baseline 577 preserved + 14 new) |
| `python -m pytest tests/integration -q --ignore=tests/integration/smoke_test.py` | 10 passed / 6 deselected |
| `python -m ruff check app tests` | 64 errors (pre-existing baseline; zero in new/changed files) |
| `python -m mypy app` | 4 pre-existing errors (fitz/pptx/whisper/numpy stubs); changed files clean |

## Remaining Risks

- **Prompt instruction is a suffix, not a slot:** "Respond in {language}."
  is appended as a trailing sentence (frozen step 3 verbatim). 2.1/2.5 prompt
  template work still owns binding the `{language}` slot into
  `intelligence.prompts.*` (frozen "Configuration Changes"); this task only
  establishes the contract on the analysis user prompt.
- **`DocumentAIProcessor.language` only affects prompts, not output schema:**
  the JSON `extracted_metadata.language` field is the model's own extraction,
  independent of the detected language — unchanged from the pre-P2-205
  contract (out of scope, R8 additive rule).
- **Heuristic coverage:** en/fr/de/ja only (P2-204 heuristic); other
  languages still fall back to `("en", 0.0)` per R7 and produce no
  instruction. A py3langid install improves detection with no code change.
- **Flaky live smoke test:** `smoke_test.py::test_live_ollama_…` fails
  intermittently independent of this change; excluded from integration runs.

## Next Recommended Task

Frozen checklist item: verify AC 2 end-to-end with a live French document
(respond-in-French prompt), then mark P2-205 complete. Remaining frozen
Milestone 2.2 tasks on the critical path: P2-202, P2-206, P2-207, P2-208
(do not implement P2-208 per prompt instruction).
