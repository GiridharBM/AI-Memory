# P2-205 Engineering Review — Language propagation + prompt adaptation

**Task:** P2-205 (Milestone 2.2 — Metadata Extraction Framework)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` §P2-205 (lines 160–178)
**Reviewer:** Principal Engineering Reviewer
**Date:** 2026-08-01
**Review scope:** P2-205 implementation only (`routing/classifier.py`, `prompts/document_analysis.py`, `application/ai_processor.py`, `pipelines/ingest_workflow.py`, `tests/unit/test_language_propagation.py`, implementation report). No code modified.

---

## 1. Specification Compliance

| Frozen requirement (§P2-205) | Status | Evidence |
|---|---|---|
| Classifier calls `detect_language` on source text when `language_detection_enabled`; sets `classification.language` (step 1) | ✅ | `classifier.py:82` `__init__(mime_enabled, language_detection_enabled=True)`; `classify()` sets `language=self._detect_language(document)` (`classifier.py:91`); `_detect_language` returns `None` when gate off, else `detect_language(document.text)[0]` (`classifier.py:117-121`) |
| Gate consumed at the classifier call site (P2-205 step 1; §P2-204's deferred Config row) | ✅ | `ingest_workflow.py:102-105` — `DocumentClassifier(mime_enabled=…, language_detection_enabled=self._metadata().language_detection_enabled)`; `_metadata()` defaults to `MetadataSettings()` (`config.py:277`, default `True`) when no `settings` injected. Resolves the P2-204-review §5 note (gate now has a wired consumer) |
| Workflow propagates to `ProcessedDocument.language` (step 2) | ✅ | `run()` passes `language=classification.language` into `_run_routed_processor` (`ingest_workflow.py:258-260`); stamps `result.language = language` only when not `None` (`ingest_workflow.py:366-367`). `ProcessedDocument.language: str \| None = None` (`processed_document.py:21`) |
| Prompt gains a `language` argument; appends `"Respond in {language}."` when `language != "en"` (step 3) | ✅ | `document_analysis.py:145-174` — `build_document_analysis_user_prompt(document, language="en")`; exact string `f"{prompt}\n\nRespond in {language}."` |
| Keep the prompt byte-identical to today when `"en"` (default) (step 4) | ✅ | `git diff` proves the f-string body is **untouched** (only the param + conditional append added); pinned regression test asserts the exact pre-P2-205 string |
| Interface: `DocumentClassification.language: str \| None` populated from `detect_language` | ✅ | `routing.py:18` (pre-existing field); populated per `classify()` (row 1) |
| Interface: prompt optional `language: str = "en"` param | ✅ | `document_analysis.py:145-147`; exported via `prompts/__init__.py` |
| AC 2: French text ⇒ `language="fr"` + respond-in-French instruction | ✅ | `test_language_propagation.py::TestClassifierLanguage::test_french_detected_when_enabled` + `test_french_appends_instruction` (exact `…+ "\n\nRespond in fr."`) |
| DoD: unit tests for prompt string + propagation; English path byte-identical | ✅ | §4/§6 below — 14 tests; pinned English string; propagation stamped |
| Rollback: `language_detection_enabled: false` ⇒ `language=None` + today's prompt | ✅ | `test_disabled_returns_none`; `test_disabled_keeps_language_none` (workflow gate); prompt builder skips instruction for `"en"` (and `None` is never forwarded — `ai_processor.py:98` `language=self._language or "en"`) |

## 2. Language Propagation

- **Single, complete propagation point.** All production paths route through `IngestionWorkflow.run`: CLI (`entry.py:372-373`) and the queue worker (`worker.py:84`, `_process_item → IngestionWorkflow.create_default(settings).run`) both construct the workflow and call `run()`. Grep confirms `DocumentClassifier` (prod) is constructed only at `ingest_workflow.py:102` and `DocumentAIProcessor` (prod) only at `ingest_workflow.py:269` — no alternate processor path exists, so the per-doc propagation in `run()` is sufficient. The previously-deferred `LanguagePropagationService` is correctly **not needed**. ✅
- **Classification → ProcessedDocument chain:** `classification.language` → `_run_routed_processor(…, language=…)` → `result.language = language` on the processor's `ProcessedDocument`. Verified by `test_routed_processor_sets_language` (fr stamps; `None` leaves the field untouched). ✅
- **Classification → prompt chain:** `classification.language` → `DocumentAIProcessor(language=…)` → `_request_analysis` → prompt builder. Verified end-to-end by `test_run_passes_language_to_ai_processor` (built-in AI path receives `"fr"`). ✅
- **Empty/English text:** `detect_language("")` → `("en", 0.0)` ⇒ `classification.language = "en"` ⇒ stamped `"en"` and `language="en"` → byte-identical prompt. No observable prompt change; new `"en"` stamp is the intended additive propagation (see O2). ✅

## 3. Public Interfaces

All changes are additive; no existing signature, default, or return type removed:

- `DocumentClassifier.__init__(mime_enabled: bool = True, language_detection_enabled: bool = True)` — new keyword param, default matches `MetadataSettings` default (`True`). Existing positional/keyword callers unaffected. ✅
- `build_document_analysis_user_prompt(document, language: str = "en")` — new optional param (O4). ✅
- `DocumentAIProcessor.__init__(…, *, language: str | None = None)` — new keyword-only param; existing constructions (tests, `intelligence_test.py`) unaffected. ✅
- `IngestionWorkflow.run()` signature unchanged; `_run_routed_processor` is private, gains `language: str | None = None`, and has exactly one caller (updated). ✅

## 4. Prompt Integration

- Default (`"en"`/`None`) produces the **exact pre-P2-205 prompt** — proven by `git diff` (f-string body untouched) and pinned in `_EXPECTED_EN_PROMPT`. ✅
- Non-`"en"` appends `"\n\nRespond in {language}."` — additive suffix, R8 (schema/JSON contract unchanged; no structure alteration). ✅
- **Retry path safe:** `_request_analysis` appends the retry instruction *after* the language instruction (`ai_processor.py:96-101`), so the respond-in-language instruction survives validation retries. ✅
- **Gated-off path safe:** gate off ⇒ `language=None` ⇒ `DocumentAIProcessor._language is None` ⇒ `"en"` ⇒ byte-identical. ✅

## 5. Test Coverage

`tests/unit/test_language_propagation.py` — 14 tests, all passing (591 total unit: baseline 577 + 14, 0 regressions).

- **Classifier:** fr/de/ja detected; gate off ⇒ `None`; default constructor matches the config gate default. ✅
- **Prompt (DoD):** pinned byte-identical English string for both default and explicit `"en"`; fr/de produce exact `_EXPECTED_EN_PROMPT + "\n\nRespond in fr."/de."`. ✅
- **AI processor:** `language="fr"` ⇒ prompt contains "Respond in fr."; default ⇒ no "Respond in" substring. ✅
- **Propagation (DoD):** `_run_routed_processor` stamps `ProcessedDocument.language`; `None` is a no-op; `run()` hands `"fr"` to the built-in `DocumentAIProcessor`. ✅
- **Gate config:** workflow-built classifier honors `language_detection_enabled` from `Settings.intelligence.metadata`. ✅

Gaps (non-blocking): mixed-language/kana-in-English inputs untested (carries from P2-204 O2); the injected-`processor=` path is untested with a language-aware fake; `run()`'s language flow is tested with a stubbed `_run_routed_processor`, so the real stamping + AI-processor handoff are covered by two tests rather than one end-to-end. Frozen testing strategy is fully covered.

## 6. Documentation

- Implementation report (`PHASE_2_MILESTONE_2_2_P2-205_IMPLEMENTATION_REPORT.md`) — Summary/Files/Tests/Results/Risks verified against fresh gate runs; accurate. ✅
- Correctly states P2-208 is **not** implemented per prompt instruction. ✅
- Report claims verified: 591 unit / 10 integration (6 deselected, smoke excluded) / ruff 64 baseline / mypy 4 baseline. ✅

## 7. Backward Compatibility

- **Byte-identical English prompt** — `git diff` + pinned regression test. ✅
- **Additive signatures only** — no removed params, no changed defaults, no reordered positional args. ✅
- **Gate-off restores Phase-1 behavior exactly** — `language=None`, no instruction, `ProcessedDocument.language` untouched (stamp is conditional on non-`None`). ✅
- **Zero caller breakage** — prod callers of the three touched constructors/functions updated or unaffected; `tests/intelligence_test.py` (non-suite script) still constructs both unchanged. ✅

## 8. Regression Safety

| Gate | Result |
|---|---|
| `python -m pytest tests/unit -q` | **591 passed / 0 deselected** (baseline 577 + 14 new; 0 regressions) |
| `python -m pytest tests/integration -q --ignore=tests/integration/smoke_test.py` | 10 passed / 6 deselected (smoke excluded per convention) |
| `python -m ruff check app tests` | 64 errors — pre-existing baseline; **zero** in changed files |
| `python -m mypy app` | 4 pre-existing errors (fitz/pptx/whisper/numpy stubs); changed files clean |

---

## Findings (remediation required)

None.

## Observations (non-blocking)

1. **O1 — English docs now carry `language="en"`.** With the gate on (default), English documents get `classification.language = "en"` and `ProcessedDocument.language = "en"` where they previously held `None`. This is the intended propagation, produces no prompt change, and is fully reversible via the gate. Consumers reading `ProcessedDocument.language` should treat `"en"` as valid.
2. **O2 — Mixed-language/kana sensitivity carries from P2-204 O2:** a single kana character forces `ja` at 0.95 regardless of surrounding language, so kana-punctuated English can be misclassified and prompt-adapted. Inherent to the frozen character-set detector; add a kana-density guard if misclassification is observed in practice.
3. **O3 — Injected `processor=` path is not language-adapted.** When a caller injects a custom `DocumentAIProcessor` via `IngestionWorkflow(processor=…)`, the workflow cannot pass `language` (unknown API). The built-in path is adapted; the custom-processor path is a documented boundary, not a defect.
4. **O4 — `language` is positional-or-keyword, not keyword-only.** The implementation notes recorded keyword-only placement, but the code uses `language: str = "en"` without a `*` separator. The frozen contract ("optional `language: str = "en"` param") is satisfied; a bare `*` would enforce keyword-only strictness if desired.
5. **O5 — Warn-once consideration:** P2-204 O4 stands — every empty/short document emits a low-confidence warning through the language logger now that ingestion wires detection. Spec-mandated, compliant; temper if noisy.
6. **O6 — Minor test-gap:** propagation is proven by two tests (stamp + AI handoff) rather than one end-to-end `run()` over a real French document with a real processor. Adequate for DoD; a live-AC-2 check remains the next-step recommendation in the report.

---

## Verdict

✅ **Approved**

P2-205 is fully compliant with the frozen contract: the classifier sets `classification.language` from `detect_language` gated by `language_detection_enabled` (frozen step 1), the workflow propagates it to `ProcessedDocument.language` through the single `IngestionWorkflow.run` path and to the built-in `DocumentAIProcessor` (step 2), and `build_document_analysis_user_prompt` appends exactly `"Respond in {language}."` for non-`"en"` while remaining byte-identical for the `"en"` default — proven by `git diff` and a pinned regression test (steps 3–4, R8 additive rule). AC 2 (French ⇒ `"fr"` + respond-in-French instruction) and the DoD (prompt-string + propagation unit tests) are covered by 14 new tests. All interfaces are additive (classifier kwarg, prompt param, keyword-only `DocumentAIProcessor.language`), no production callers break, and the gate-off rollback restores Phase-1 behavior exactly. Regression safety is clean: 591 unit tests pass (577 baseline preserved), integration unaffected, ruff (64) and mypy (4) at pre-existing baselines with zero new findings. The remaining items are non-blocking observations (intended `"en"` stamping, kana sensitivity, custom-processor boundary, keyword-only strictness). No remediation required.
