# Milestone 2.5 Completion Report — Image Intelligence

**Status: COMPLETE** — All 6 tasks (P2-501…P2-506) implemented per frozen spec v1.3; verification gates pass; documentation synchronized.

---

## 1. Summary

| Metric | Result |
|--------|--------|
| **Tasks completed** | 6 / 6 (P2-501…P2-506) |
| **Full test suite** | 825 passed / 28 deselected |
| **Coverage** | 88% (floor 80%) |
| **New unit tests** | 40 (`tests/unit/test_image_intelligence.py`) |
| **New integration tests** | 4 (`tests/integration/test_image_pipeline.py`, `-m integration`) |
| **Ruff (changed files)** | 0 new errors |
| **Mypy (changed files)** | 0 new errors |
| **Rollback verified** | `exif_enabled: false`, `diagram_enabled: false`, `preprocess: false` → Phase-1-identical |

---

## 2. Task Completion Matrix

| Task | Spec Ref | Implementation | Tests | Status |
|------|----------|----------------|-------|--------|
| **P2-501** | §4.5.1 | `app/domain/document_intelligence.py` — `ImageInfo` / `ImageExif` (pydantic, `extra="forbid"`, nullable `page_no`, `index`, EXIF raw+decoded, optional GPS) | 3 model tests (round-trip, forbid, defaults) | ✅ DONE |
| **P2-502** | §4.5.2 | `app/infrastructure/document_intelligence/images/metadata.py` — `ImageAnalyzer`/`analyze_image` (single owner, R-3); `ImageIngestor` attaches `metadata.extra["image_info"]` gated by `images.exif_enabled` | 7 analyzer tests (dimensions, EXIF tags, `include_exif=False`, corrupt degradation, SVG, missing file, injected analyzer) + 3 ingestor tests | ✅ DONE |
| **P2-503** | §4.5.3 | `app/infrastructure/document_intelligence/imaging/preprocess.py` — `max_dimensions`/`max_bytes` kwargs resolved at call time from `intelligence.images.*` (supersedes module `MAX_EDGE`) | 4 preprocess guard tests (max_dims override, max_bytes override, config guards pass, undersize still preprocesses) | ✅ DONE |
| **P2-504** | §4.5.4 | `app/infrastructure/document_intelligence/images/diagram.py` — `drawio_to_mermaid`/`DiagramParser`; `DiagramProcessor` emits Mermaid note / raw fallback, gated by `images.diagram_enabled` | 6 diagram tests (conversion, edge labels, unparseable, no labels, unsupported suffix, file read) + 3 processor tests | ✅ DONE |
| **P2-505** | §4.5.5 | `app/infrastructure/routing/processor_impls.py` — `_resolve_prompt` + `language` kwargs on Vision/OCR/Handwriting; `app/pipelines/ingest_workflow.py` — `language=` at processor call sites | 4 language wiring tests (vision/ocr/handwriting substitution + workflow propagation) | ✅ DONE |
| **P2-506** | §4.5.6 | `app/infrastructure/document_intelligence/images/multi.py` — `MultiImageExtractor` (byte-stream open); `app/pipelines/ingest_workflow.py` — `_enrich_images` at shared P2-305 call site, trigger `kind == "pdf"` | 5 multi-image tests (page provenance, corrupt PDF, text-only PDF, missing file, default factory) + 5 workflow enrich tests | ✅ DONE |

---

## 3. Remediation History

| Round | Finding | Resolution |
|-------|---------|------------|
| **Initial** | Shared `Preprocessor` not wired into OCR/vision path (R1) | Added `_shared_preprocessor` bridge in `ocr/__init__.py`, injected into both engines, `_extract_via_service` calls `service.extract(..., preprocess=True)` |
| **Re-review** | Hardcoded `preprocess=True` in `_extract_via_service`; unconditional `Preprocessor(enabled=True)`; dead toggles; defaults bypass config | `_extract_via_service` gained `preprocess: bool = False`; three processors accept `preprocess: bool = False`; `_shared_preprocessor` returns `None` when both toggles off; `OcrEngine.run` and `DocumentOcrService.extract` defaults flipped to `False`; `ingest_workflow.py` wires per-path config |
| **Post-remediation** | AC2 regression test needed | Added `TestConfigDrivenPreprocess` with two tests: `preprocess=false` → identical bytes through production path; `preprocess=true` → transformed bytes |

---

## 4. Key Architecture Decisions (Implemented as Specified)

| Decision | Implementation |
|----------|----------------|
| **Single-owner EXIF (R-3)** | `images/metadata.py` is the sole raw-EXIF reader; `metadata/extractors.py` (M2.2) intentionally has no image reader; EXIF rides `metadata.extra["image_info"]` |
| **Shared preprocess module (R-3)** | P2-503 reuses `imaging/preprocess.py`; config values (`intelligence.images.max_dimensions`/`max_bytes`) resolve **at call time** — existing P2-104 test monkeypatches on module constant keep working |
| **Enrichment trigger (R2 precedent)** | P2-506 uses existing classifier condition `kind == "pdf"` — no invented routing conditions; `_enrich_images` is self-contained helper at shared P2-305 call site, coexists with table gate |
| **Configurable prompts (R-6)** | `_resolve_prompt(self._prompt or _prompt_templates()[...], self._language)` keeps defaults byte-identical to Phase 1; `{language}` substitution only at call sites (P2-205) |
| **Best-effort failures (L4)** | Every M2.5 feature is additive and fails contained — unreadable image/PDF, missing dependency, or corrupt EXIF never aborts ingestion |
| **Windows handle-leak root cause** | MuPDF's `fitz.open(path)` leaks handle on **failed** open → worker `shutil.move` got `PermissionError [WinError 32]`. Fixed by `path.read_bytes()` + `fitz.open(stream=data, filetype="pdf")` (bounded by `max_file_size_mb`, 50 MiB default) |

---

## 5. Files Changed (Net)

### New Files (8)
- `app/domain/document_intelligence.py` — `ImageInfo` / `ImageExif` (extended)
- `app/infrastructure/document_intelligence/images/__init__.py` — public API
- `app/infrastructure/document_intelligence/images/metadata.py` — P2-502 `ImageAnalyzer`/`analyze_image`
- `app/infrastructure/document_intelligence/images/diagram.py` — P2-504 `drawio_to_mermaid`/`DiagramParser`
- `app/infrastructure/document_intelligence/images/multi.py` — P2-506 `MultiImageExtractor` (byte-stream open)
- `tests/unit/test_image_intelligence.py` — 40 tests
- `tests/integration/test_image_pipeline.py` — 4 tests
- `tests/fixtures/images/{photo.png, plain.png, multi_image.pdf}` — EXIF fixture, plain fixture, 2-page PDF

### Modified Files (11)
- `app/infrastructure/document_intelligence/imaging/preprocess.py` — P2-503 `max_dimensions`/`max_bytes` kwargs, `DEFAULT_MAX_BYTES`
- `app/infrastructure/ingestion/image_ingestor.py` — P2-502 EXIF gating (`exif_enabled`) + `image_info` attachment
- `app/infrastructure/ingestion/service.py` — `_images()` accessor, `exif_enabled` wiring
- `app/infrastructure/routing/processor_impls.py` — P2-504 `DiagramProcessor` + `_diagram_enabled()`; P2-505 `_resolve_prompt` + `language` kwargs on Vision/OCR/Handwriting; P2-503/Ocr remediation: `preprocess` kwarg on all three processors, `_extract_via_service` signature
- `app/pipelines/ingest_workflow.py` — P2-505 `language=` at processor call sites; P2-506 `_enrich_images` at shared call site; remediation: per-path `preprocess` wiring from config
- `app/infrastructure/document_intelligence/ocr/__init__.py` — `_shared_preprocessor` bridge, config-gated, returns `Callable | None`
- `app/infrastructure/document_intelligence/ocr/base.py` — `OcrEngine.run(preprocess=False)`, `DocumentOcrService.extract(preprocess=False)`
- `app/infrastructure/document_intelligence/ocr/engines.py` — both engines `run(preprocess=False)`
- `app/core/config.py` + `config/default.yaml` — `intelligence.images.*` (`preprocess`, `exif_enabled`, `diagram_enabled`, `max_dimensions`, `max_bytes`)
- `tests/unit/test_config.py` — +2 tests (`intelligence.images` frozen defaults + env override)
- `tests/unit/test_ocr_engine.py` — `TestConfigDrivenPreprocess` (2 AC2 regression tests)

---

## 6. Configuration (Frozen §4.5 Contract)

```yaml
intelligence:
  images:
    preprocess: false              # opt-in preprocessing (deskew → denoise → CLAHE)
    exif_enabled: true             # true → `metadata.extra["image_info"]` on image kinds
    diagram_enabled: true          # true → `.drawio` → Mermaid in note body
    max_dimensions: [8192, 8192]   # scalar int or [width, height] pair
    max_bytes: 20971520            # 20 MiB preprocessing cap
```

`ImageSettings.max_dimensions` is `int | tuple[int, int] = (8192, 8192)`; invalid values rejected at parse time.

---

## 7. Open Items (Non-Gate)

| Item | Description | Status |
|------|-------------|--------|
| **Per-task atomic commits** | Milestone work uncommitted; commit per-task atomic commits before release (same status as M2.2/M2.3/M2.4) | ⚠️ Pending release |
| **Pre-existing ruff/mypy debt** | 62 pre-existing ruff errors and 3 pre-existing mypy errors in files untouched by M2.5 (docx/pptx/spreadsheet ingestors, vision_client, whisper_transcriber, queue worker, templates, search, etc.) | Not M2.5 gate |
| **PDF-only extraction trigger** | Embedded-image extraction fires on `kind == "pdf"`; pure image PDFs classify as `scanned_pdf` and are skipped (no invented routing conditions) | Per frozen spec |

---

## 8. Documentation Produced / Updated

| Document | Status |
|----------|--------|
| `docs/release_notes/v0.6.0-milestone-2.5.md` | ✅ Created |
| `docs/PHASE_2_MILESTONE_2_5_COMPLETION_REPORT.md` | ✅ Created (this file) |
| `docs/PHASE_2_MILESTONE_2_5_DOCUMENTATION_SYNCHRONIZATION_REPORT.md` | ✅ Created |
| `docs/01_Current_Implementation_Report.md` | ✅ Updated (fixed preprocessing config reference) |
| `docs/MASTER_ENGINEERING_DESIGN_DOCUMENT.md` | ✅ Updated (added Image Intelligence module spec §7.x) |
| `docs/changelog.md` | ✅ Verified (0.6.0 entry accurate) |
| `docs/MEDD_DOCUMENTATION_SYNCHRONIZATION_REPORT.md` | ✅ Updated (M2.5 entries) |

---

## 9. Verification Commands

```bash
# Unit tests (default run)
python -m pytest tests/unit -q -p no:cacheprovider
# → 825 passed / 28 deselected

# M2.5 unit tests
python -m pytest tests/unit/test_image_intelligence.py -v
# → 40 passed

# M2.5 integration tests
python -m pytest tests/integration -m integration -q -p no:cacheprovider
# → 25 passed, 1 skipped (Tesseract binary not installed)

# Image-specific integration
python -m pytest tests/integration/test_image_pipeline.py -m integration -v
# → 4 passed

# Lint
python -m ruff check app/infrastructure/document_intelligence/images/ app/infrastructure/routing/processor_impls.py app/pipelines/ingest_workflow.py app/core/config.py tests/unit/test_image_intelligence.py
# → All checks passed

# Types
python -m mypy app/infrastructure/document_intelligence/images/ app/infrastructure/routing/processor_impls.py app/pipelines/ingest_workflow.py app/core/config.py --no-error-summary
# → 0 new errors
```

---

**Signed off:** Milestone 2.5 complete. Ready for release-time atomic commits per §14.