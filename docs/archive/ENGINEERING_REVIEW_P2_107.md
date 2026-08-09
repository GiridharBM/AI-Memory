# P2-107 Engineering Review

**Date:** 2026-08-01
**Scope:** Independent review of **P2-107 only** (processor integration into the OCR engine/service, prompt routing, legacy OCR-helper removal) against `PHASE_2_MILESTONE_2_1_ENGINEERING_SPECIFICATION.md`. P2-108 changes present in the same working tree (`intelligence.ocr` settings, service factory, doctor rows) were explicitly **excluded** from this review.
**Method:** Source inspection of the P2-107 change set, targeted test rerun, dead-code grep for the removed helpers, and prompt-contract verification. **No code was modified.**

---

## Verdict

# ✅ Approved

No BLOCKERs or WARNs. The three vision/OCR processors delegate cleanly to `DocumentOcrService`, prompt templates route correctly per processor kind, the removed legacy helpers have zero in-code consumers, and all 69 P2-107-scope tests pass. The only findings are INFOs documenting deliberate behavior changes and minor test-design redundancy.

---

## Verification areas

### 1. Processor integration — PASS

- `VisionProcessor`, `OCRProcessor`, `HandwritingProcessor` all accept `ocr_service: DocumentOcrService | None` and delegate through `_extract_via_service` (`app/infrastructure/routing/processor_impls.py:281-304, 363-386, 406-429`).
- Ingest workflow injects the service via the `_constructors` map in `_run_routed_processor` (`app/pipelines/ingest_workflow.py:331-338`); the legacy `vision_client=` kwarg is still honored via the `_ocr_service_from_client` wrapper (processor_impls.py:70-80).
- `_extract_via_service` catches the exact `ValueError` that `DocumentOcrService.extract` raises for a missing source path (`base.py:77-78`) — verified, not assumed — and falls back to document text.
- Engine-selection failures (`OCRSelectionError`) propagate and the `vision_required` no-fallback guard in `_run_routed_processor` re-raises rather than sending images to a text-only model (ingest_workflow.py:370-377).
- Tests: `TestOcrServiceDelegation` (asserts `extract` called with per-processor prompt), `test_configured_ocr_service_is_injected`, `test_ocr_service_none_passthroughs`, `test_no_fallback_raise_when_engine_missing`, `test_missing_source_path_falls_back_to_document_text`.

### 2. Prompt routing — PASS

- `_prompt_templates()` (`@lru_cache(maxsize=1)`) loads the three templates from config (processor_impls.py:56-62); each processor resolves its own template: `vision`/`ocr`/`handwriting`.
- `_resolve_prompt` substitutes the `{language}` slot (processor_impls.py:65-67); shipped defaults carry no slot, so runtime prompts are **byte-identical to Phase 1** (verified: config.py:220-234 vs the pinned test constants).
- Tests: `test_vision/ocr/handwriting_delegates_to_service` pin the exact prompt per processor; `test_intelligence_prompts_defaults_are_phase1_prompts` (test_config.py) pins the Phase-1 contract; `test_language_slot_substitution`.

### 3. Legacy removal — PASS

- `_looks_handwritten`, `handwriting_detected`, `_ocr_extract`, and `_ocr_extract_from_pdf` are gone from `app/`. Grep across all `.py` in `app/` confirms **zero code consumers**; the only remaining references are historical, in `docs/01_Current_Implementation_Report.md` and `docs/02_Current_Project_Status_Report.md`.
- `VisionOcrEngine.supported_kinds = {"scanned_pdf", "image", "handwritten"}` retains the handwritten capability (`ocr/engines.py:32`), pinned by `test_supported_kinds`; `HandwritingProcessor` remains reachable via classifier `source_type == "handwritten"` (`routing/classifier.py:108-109`).
- Behavior change is deliberate and safe — see INFO 1.

### 4. Architecture — PASS

- Processors are thin adapters over the OCR service layer; no import cycles (TYPE_CHECKING guards, `_OllamaVisionClient = object` alias). Service construction lives outside the routing layer; the workflow owns the service instance.
- The legacy `vision_client=` path is isolated in one wrapper, keeping backward compatibility without leaking vision-client logic into processors.
- No speculative abstraction introduced; delegation is linear and testable.

### 5. Tests — PASS

- Full P2-107 scope rerun this session: **69 passed / 0 failed** (`test_processors.py`, `test_config.py`, `test_processor_wiring.py`, `test_ocr_engines.py`).
- Coverage of the delegation paths, prompt routing, fallback, no-fallback guard, and wiring injection is strong. `test_scanned_pdf_requires_pymupdf` also verifies the G06 PyMuPDF gate through the new delegation path.

### 6. Performance — PASS

- `_prompt_templates` is cached (`lru_cache`); prompt resolution adds one string `replace` per processor invocation — negligible.
- No new per-document allocation; delegation adds one function-call indirection over the previous inline logic.

## Findings

### BLOCKER

None.

### WARN

None.

### INFO 1 — Behavior change: vision documents no longer emit `handwriting_detected` / `source_type="handwritten"`

The deleted `_looks_handwritten` heuristic previously auto-tagged image docs whose OCR text looked handwritten. After removal, all `VisionProcessor` output is `source_type="image"` with `model_used` metadata only (processor_impls.py:294). Handwritten files that are *classified* as `handwritten` still route to `HandwritingProcessor` (classifier.py:108), so the capability is intact. No in-code consumer of the old flag exists, so removal is safe — but this is a downstream-visible change and should be recorded in the phase summary / release notes.

### INFO 2 — `get_processor_by_name` returns a service-less passthrough for the three vision processors

`get_processor_by_name("OCRProcessor")` (processor_impls.py:491-495) constructs a processor with no service → silent passthrough with `model_used: False` (confidence 0.50/0.40). The ingest workflow never hits this (it uses the `_constructors` map), so production behavior is correct. Latent trap for future callers; worth a docstring note if the registry is treated as public API.

### INFO 3 — Prompt pin in `test_processors.py` is partially self-referential

`TestPromptTemplates.test_defaults_are_byte_identical_to_phase1` (test_processors.py:482-486) compares `_prompt_templates()` against `EXPECTED_*` constants defined in the same file, which duplicate the config defaults. The real Phase-1 contract pin is `test_config.py::test_intelligence_prompts_defaults_are_phase1_prompts`. If a future change edits both the defaults and the constants together, the former test passes vacuously — harmless, but redundant.

### INFO 4 — `{language}` slot renders empty when no language is passed

`_resolve_prompt("... {language}.")` with `language=None` yields `"... ."` (empty slot). Shipped defaults carry no slot, so no runtime impact; future templates must pass a language or omit the slot (documented in `PromptSettings` docstring, config.py:212-215).

---

## Remediation checklist

None required for P2-107 approval. Optional follow-ups:

1. (INFO 2) Add a docstring warning to `get_processor_by_name` that service-backed processors constructed via the registry bypass service injection.
2. (INFO 1) Record the `handwriting_detected` removal in the M2.1 completion report / release notes.
3. (INFO 3) Optionally drop the redundant prompt-pin test and rely on the test_config.py contract.

---

## Appendix: Test evidence (this session)

- `pytest tests/unit/test_processors.py tests/unit/test_config.py tests/unit/test_processor_wiring.py tests/unit/test_ocr_engines.py -q` → **69 passed**.
- Grep `handwriting_detected|_looks_handwritten|_ocr_extract` in `app/` → 0 hits.
- `DocumentOcrService.extract` missing-source-path → `ValueError` (base.py:77-78), matched by `_extract_via_service` handler.
