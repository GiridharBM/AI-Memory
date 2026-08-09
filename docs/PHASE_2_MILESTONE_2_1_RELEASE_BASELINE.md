# Milestone 2.1 Release Baseline

**Prepared by:** Release Manager
**Date:** 2026-08-01
**Branch:** `main` (`HEAD 4a8525e` — Phase-1 remediation; all M2.1 work uncommitted in working tree)
**Milestone:** Phase 2, Milestone 2.1 — OCR Engine (`docs/PHASE_2_MILESTONE_2_1_ENGINEERING_SPECIFICATION.md`)
**Scope rule:** documentation/release only — no implementation code modified in this release-baseline pass.

---

## 1. Milestone Version

| Attribute | Value |
|-----------|-------|
| Milestone | Phase 2 — Milestone 2.1 |
| Name | OCR Engine |
| Semantic version | **0.2.0** |
| Date | 2026-08-01 |
| pyproject.toml | ⚠️ still `0.1.0` — **bump to `0.2.0` required** (release step, see §10) |
| Changelog section | `## [0.2.0] — 2026-08-01 — Milestone 2.1: OCR Engine` |
| Release notes | `docs/release_notes/v0.2.0-milestone-2.1.md` |
| Tag (proposed) | `v0.2.0` (repo convention is `v`-prefixed, cf. existing `v2.0.0`) |

**Versioning note:** version history is maintained in the MEDD header (§0) and `docs/changelog.md` per Keep a Changelog + SemVer. The `0.2.0` bump marks the first feature milestone after the `0.1.0` baseline.

---

## 2. Release Notes

See `docs/release_notes/v0.2.0-milestone-2.1.md`. Summary of the headline content:

- **New OCR engine subsystem** — decoupled `DocumentOcrService` registry with an `OcrEngine` protocol; OCR is no longer inlined in processors.
- **Vision-primary with Tesseract fallback** — `engine="auto"` (vision first, CPU-only Tesseract fallback); explicit `engine="vision"|"tesseract"` supported.
- **Per-page confidence** — `OcrResult`/`PageOcrResult`, mean + per-page confidence, empty/low-confidence flags; surfaced as `ocr_confidence` frontmatter.
- **Configurable scanned-PDF OCR** — `page_limit` (default 5, 0 = all), zoom, `max_pages` cap replace the hardcoded first-5-pages limit; per-page failure isolation.
- **Shared image preprocessing** — deskew → denoise → CLAHE (`imaging/preprocess.py`), off by default, shared with M2.5.
- **Configurable OCR/vision/handwriting prompts** — `intelligence.prompts.*` with `{language}` slot; defaults byte-identical to Phase 1.
- **`pam doctor` OCR diagnostics** — 5 new OCR rows.
- **Robustness** — clear PyMuPDF `ImportError` (G06); no silent empty-text fallback; no temp-file leaks.

---

## 3. Milestone Summary

Milestone 2.1 delivers a production-shaped OCR engine: OCR is extracted from the Phase-1 inline helpers into a testable `DocumentOcrService` registry under `app/infrastructure/document_intelligence/ocr/`, with two interchangeable engines (vision + Tesseract), per-page confidence aggregation, configurable page/zoom/preprocessing, config-driven prompts, and `pam doctor` diagnostics — all while preserving Phase-1 behavior by default (`enabled: false` → passthrough; `page_limit: 5`; byte-identical prompts).

Architecture constraints honored: single shared preprocessing module (R-3), no `engine="legacy"` branch (R-4), optional-dep wheels verified on `cp314-win_amd64` (R-5), prompts from config (R-6), structures attach to the document not the analysis prompt (R-7). Out-of-scope items (layout preservation, multi-language selection, ML handwriting) were deliberately excluded.

The milestone completed 8/8 tasks. The §8 documentation gate (BLOCKER 1) has since been remediated (see §9); the remaining open items are process/commit work (§10) and the flaky pre-existing live-Ollama smoke test.

---

## 4. Completed Tasks

| Task | Description | Status | Evidence |
|------|-------------|--------|----------|
| P2-101 | OCR engine protocol + `DocumentOcrService` registry + `OcrResult`/`PageOcrResult` models + empty-registry error | DONE | `ocr/base.py`, `ocr/models.py`; `OCRSelectionError` tested |
| P2-102 | `VisionOcrEngine` — page loop, bounded retry, early stop, temp cleanup, preprocess hook | DONE | `ocr/engines.py:70-114`; page-limit + retry tests |
| P2-103 | `render_pdf_pages` — zoom/limit/max_pages, per-page error isolation, in-memory PNG | DONE | `ocr/pdf.py:44-62`; temp-cleanup test |
| P2-104 | Shared `imaging/preprocess.py` — deskew → denoise → CLAHE, default off, absent-Pillow guard | DONE | `imaging/preprocess.py`; transform + error-path tests |
| P2-105 | `TesseractOcrEngine` — lazy import, G06 clear error, per-page confidence mapping | DONE | `ocr/engines.py:172-239`; G06 message test |
| P2-106 | Confidence aggregation + additive `ProcessedDocument.ocr` field | DONE | `ocr/models.py:35-67`; `processed_document.py` |
| P2-107 | Processor integration — 3 processors consume `DocumentOcrService`; prompts from config; no-fallback guard | DONE ✅ reviewed | `ENGINEERING_REVIEW_P2_107.md` — no blockers |
| P2-108 | OCR config binding + `engine="auto"` selection + `pam doctor` rows | DONE | config tests (15), doctor test, live smoke |

**Total: 8 / 8 complete.**

---

## 5. Test Summary

| Layer | Result |
|-------|--------|
| Full unit suite | **506 passed / 2 deselected** (508 collected; `addopts -m 'not integration'`) |
| Integration (`-m integration`) | 1 skipped (Tesseract binary absent — expected); 1 live-Ollama smoke **flaky** (pre-existing model-output variance, 2 of 21 sections; exercised code untouched by M2.1) |
| Coverage | **87.02%** (floor 80%, target ≥ 84%) ✅ |
| Ruff | 64 errors — all pre-existing (HEAD baseline 66); **0 new from M2.1** |
| Mypy | Identical to HEAD — environment/stub gaps only (numpy `.pyi` py3.14, `yaml`/`fitz`/`docx`/`pptx`/`faster_whisper`); **0 new type errors** |
| New tests added | `tests/unit/test_ocr_engine.py`, `test_ocr_engines.py`, `test_ocr_models.py`, `test_ocr_pdf.py`, `test_ocr_tesseract.py`, `test_preprocess.py`, `tests/integration/test_ocr_pipeline.py` + config/processor/cli additions |
| Optional-dep wheels (R-5) | `pillow-12.3.0-cp314-cp314-win_amd64`, `pytesseract`, `packaging` resolve via `pip download --only-binary` ✅ |
| Manual checklist (§8.5) | Not yet re-run this release pass (no code change since completion) |

---

## 6. Known Limitations

| Limitation | Impact | Note |
|------------|--------|------|
| No layout preservation | Tables/columns lose reading order | Scope-out for M2.1; future M2.x / Epic 8 remaining work |
| Handwriting routed by source type, not ML | No ML handwriting recognition | Classifier-driven; vision-engine transcription only |
| Tesseract binary optional | Offline fallback requires external install | `pam doctor` reports availability; clear G06 error otherwise |
| Preprocessing off by default | `preprocess: false` | Enabling is one config line; optional Pillow/numpy |
| Live-Ollama integration smoke flaky | Model-output variance on hardcoded 21-section assert | Pre-existing; recommend required-subset assert in M2.2 |
| No benchmark report | `docs/05_Document_Intelligence_Benchmarks.md` absent | INFO 4 from completion report; carried to M2.2 (not a §8 gate item) |
| `pyproject.toml` version mismatch | Docs say 0.2.0, pyproject says 0.1.0 | Release step §10.2 |

---

## 7. Architecture Status

**Package layout matches frozen spec §7.2** (`docs/PHASE_2_MILESTONE_2_1_ENGINEERING_SPECIFICATION.md`):

```
app/infrastructure/document_intelligence/
├── ocr/
│   ├── __init__.py   # get_default_ocr_service (engine="auto")
│   ├── base.py       # OcrEngine protocol, DocumentOcrService registry, OCRSelectionError
│   ├── engines.py    # VisionOcrEngine, TesseractOcrEngine
│   ├── models.py     # OcrResult, PageOcrResult
│   └── pdf.py        # render_pdf_pages (PyMuPDF)
└── imaging/
    └── preprocess.py # shared deskew → denoise → CLAHE (single module, R-3)
```

- **Rollback contract:** `intelligence.ocr.enabled: false` → empty registry → Phase-1-identical passthrough; **no `engine="legacy"` branch retained** (R-4). Live-verified.
- **Additive schema only:** `ProcessedDocument.ocr: OcrResult | None`; no field removed/re-typed (R-7).
- **No-fallback guard preserved:** vision-required kinds re-raise on engine failure rather than sending images to a text-only model (`ingest_workflow.py:370-377`).
- **Confidence surfaced:** `OcrResult.confidence` → `ProcessedDocument.ocr` → frontmatter `ocr_confidence` + reference line.
- **MEDD §1.2 subsystem table** now includes the OCR Engine row; §7.2 fully rewritten to the current implementation.

---

## 8. Documentation Status

| Artifact | Status |
|----------|--------|
| `docs/changelog.md` | ✅ 0.2.0 section added (was placeholder) |
| `docs/01_Current_Implementation_Report.md` | ✅ §6 OCR rewritten; §7, §23, §24 updated; obsolete `_ocr_extract*`/`_looks_handwritten` removed |
| `docs/MASTER_ENGINEERING_DESIGN_DOCUMENT.md` | ✅ v0.2.0 + version history; §1.1/1.2/1.4/1.5/1.6, §3.2 (G33/G34), §5, §6 Epic 8, §7.2 rewritten; 84.77%→87.02%, 386→508 figures |
| `README.md` | ✅ optional Tesseract install note |
| `docs/release_notes/v0.2.0-milestone-2.1.md` | ✅ created (first release note) |
| `docs/DOCUMENTATION_UPDATE_REPORT.md` | ✅ generated |
| `docs/PHASE_2_MILESTONE_2_1_COMPLETION_REPORT.md` | ✅ produced (verdict: Needs Remediation → docs gate now satisfied) |
| `docs/05_Document_Intelligence_Benchmarks.md` | ❌ not present — deferred to M2.2 (INFO 4) |

The spec §8 gate items that were unmet at review time — changelog, 01 report §6, MEDD §7.2 (BLOCKER 1) — are all now satisfied.

---

## 9. Approval Checklist

| # | Item | Requirement | Status |
|---|------|-------------|--------|
| 1 | All 8 tasks (P2-101…P2-108) implemented | Spec §8 | ✅ |
| 2 | Registry + protocol; empty-registry error tested | §8 #1 | ✅ |
| 3 | Vision engine text-equal to Phase 1 (≤5 pages, mocked) | §8 #2 | ✅ |
| 4 | Render service: per-page isolation, zoom/limit, no temp leaks | §8 #3 | ✅ |
| 5 | Preprocessing: transforms tested, default off, absent-Pillow fallback | §8 #4 | ✅ |
| 6 | Tesseract: import-guarded, offline path, binary-absent error | §8 #5 | ✅ |
| 7 | Confidence aggregation + additive `ProcessedDocument.ocr` | §8 #6 | ✅ |
| 8 | All 3 processors consume service; prompts from config; no-fallback guard | §8 #7 | ✅ |
| 9 | `engine="auto"` selection, page limits, Phase-1 defaults, doctor hint | §8 #8 | ✅ |
| 10 | Pre-existing tests pass; coverage ≥ 80%; ruff/mypy no new errors | §8 #9 | ✅ 506 pass / 87.02% / 0 new |
| 11 | Per-task atomic commits; `enabled: false` rollback verified | §8 #10 | ⚠️ rollback ✅; **commits pending** |
| 12 | Optional-dep wheels verified; changelog + 01 report + MEDD §7.2 updated | §8 #11 | ✅ |
| 13 | Completion report produced | §8 #12 | ✅ |
| 14 | Docs updated (changelog, 01 report, MEDD, README, release notes) | §8 gate | ✅ (remediated 2026-08-01) |

**Release-manager sign-off:** approve once §10 commit/tag actions are completed and the checklist above shows all ✅.

---

## 10. Required Git Operations (identified — NOT performed)

Project policy (`docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` §10 Rollback — Process, and §8 #10) requires **per-task atomic commits** with docs committed alongside code, and a release needs a version bump and tag. These are not done:

### 10.1 Per-task atomic commits (policy-required)
All P2-101…P2-108 code, config, and tests are uncommitted (35 working-tree changes). Policy requires one atomic commit per task. Suggested grouping aligned to the dependency graph:

1. P2-101 — `ocr/{__init__,base,models}.py` + tests (`test_ocr_engine.py`, `test_ocr_models.py`)
2. P2-103 — `ocr/pdf.py` + `test_ocr_pdf.py`
3. P2-102 — `ocr/engines.py` (Vision) + `test_ocr_engines.py`
4. P2-104 — `imaging/preprocess.py` + `test_preprocess.py`
5. P2-105 — `ocr/engines.py` (Tesseract) + `test_ocr_tesseract.py`
6. P2-106 — `processed_document.py` ocr field + tests
7. P2-107 — `processor_impls.py`, `ingest_workflow.py` wiring + processor/wiring tests
8. P2-108 — `config.py`, `config/default.yaml`, `entry.py` doctor, CLI/config tests
9. Docs commit — changelog, 01 report, MEDD, README, release notes, update report, completion report

### 10.2 Version bump commit (release step)
- `pyproject.toml`: `version = "0.1.0"` → `"0.2.0"` (currently mismatched with all release docs).

### 10.3 Tag (release step)
- Create annotated tag **`v0.2.0`** on the release commit (repo convention: `v`-prefix, cf. `v2.0.0`). Optionally push with `--tags`.

### 10.4 Push (release step)
- Push commits and tag to `origin` (`https://github.com/GiridharBM/AI-Memory.git`, branch `main`).

**Per instructions, no git operations were performed.**

---

## 11. Release Readiness Verdict

**CONDITIONAL APPROVE.**

Code, tests, and documentation satisfy the milestone DoD (8/8 tasks; §8 gate fully remediated). The release is not yet shippable to a tag because the required per-task atomic commits, the `pyproject.toml` version bump to 0.2.0, the `v0.2.0` tag, and the push have not been executed (policy-required, intentionally left for explicit authorization).
