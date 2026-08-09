# Milestone 2.5 Implementation Report — Image Intelligence

**Status: IMPLEMENTED.** All 6 tasks (P2-501…P2-506) implemented per the frozen spec v1.3; verification gates pass: **820 passed / 28 deselected**, coverage **88%** (floor 80%), M2.5 modules **80–100%** each, **0 new ruff errors**, **0 new mypy errors** in changed files. Rollback verified: `intelligence.images.*` toggles restore Phase-1 behavior (EXIF off proven live; diagram/preprocess off unit-tested). Per-task atomic commits remain pending at release time (§14, same as M2.2–M2.4).

---

## 1. Verdict

# ✅ Milestone Complete

Every task AC and DoD is satisfied (P2-501…P2-506): `ImageInfo`/`ImageExif` models with nullable fields; a single-owner EXIF extractor (R-3) with corrupt-EXIF → `None` containment and absent-Pillow degradation; the shared `imaging/preprocess.py` guard contract with `intelligence.images.max_dimensions`/`max_bytes` as the single source of truth (P2-503); `.drawio` → Mermaid diagram conversion with raw fallback (P2-504); prompt + `{language}` substitution at all three processor call sites, byte-identical Phase-1 defaults (P2-505, R-6); and multi-image PDF extraction with page provenance riding the existing `kind == "pdf"` classifier trigger through a self-contained `_enrich_images` helper at the shared P2-305 call site (P2-506, no invented routing conditions). A Windows-specific PyMuPDF handle-leak root cause was fixed via byte-stream open, clearing a worker regression. Rollback via `intelligence.images.*` toggles is verified. The only open item is the §14 release-time atomic-commit process step (same status as M2.2/M2.3/M2.4).

---

## 2. Completed Tasks

| Task | Description | Status |
|------|-------------|--------|
| P2-501 | `ImageInfo` / `ImageExif` domain models (pydantic, `extra="forbid"`, nullable `page_no`, `index`, EXIF raw+decoded) | DONE |
| P2-502 | EXIF/metadata extractor — `images/metadata.py` `ImageAnalyzer`/`analyze_image` (single owner, R-3); `ImageIngestor` attaches `metadata.extra["image_info"]` gated by `images.exif_enabled` | DONE |
| P2-503 | Shared `imaging/preprocess.py` guard contract — `max_dimensions`/`max_bytes` kwargs resolved at call time from `intelligence.images.*`, superseding the module `MAX_EDGE` constant for the M2.5 path | DONE |
| P2-504 | Diagram intelligence — `images/diagram.py` (`drawio_to_mermaid`, `DiagramParser`); `DiagramProcessor` emits Mermaid note / raw fallback, gated by `images.diagram_enabled` | DONE |
| P2-505 | Configurable processor prompts (Vision/OCR/Handwriting) + `{language}` substitution at call sites (P2-205); defaults byte-identical to Phase 1 (R-6) | DONE |
| P2-506 | Multi-image extraction — `images/multi.py` (`MultiImageExtractor`) with page provenance; `_enrich_images` helper at the shared call site, trigger `kind == "pdf"` (frozen R2 precedent) | DONE |

**Total: 6 / 6 complete.**

---

## 3. Verification Evidence

| Check | Result |
|-------|--------|
| Full suite | **820 passed / 28 deselected** (default run; baseline 778 / 24 at M2.4 → +42 unit tests, +4 integration deselected) |
| New unit suite | `tests/unit/test_image_intelligence.py` — **40 passed** (P2-501…P2-506: models 3, analyzer 7, ingestor 3, multi 5, preprocess 4, diagram 6, diagram-processor 3, language wiring 4, `_enrich_images` 5) |
| Config tests | `tests/unit/test_config.py` — +2 (`intelligence.images` frozen defaults + env override) |
| New integration suite | `tests/integration/test_image_pipeline.py` — **4 passed** via `-m integration` (photo→`image_info` + vision prompt; no-vision passthrough; PDF-with-image page provenance; text-only PDF has no `"images"` key) |
| Coverage | **88%** total (floor 80%) ✅; M2.5 modules: `images/metadata.py` 89%, `images/diagram.py` 91%, `images/multi.py` 80%, `imaging/preprocess.py` 95%, `image_ingestor.py` 93%, `document_intelligence.py` 100% |
| Ruff | 0 new errors in changed files (3 auto-fixable import issues in the new test file; 62 pre-existing errors remain in untouched files) |
| Mypy | 0 new type errors in changed files (3 pre-existing errors — pptx, faster_whisper, numpy — in untouched files) |
| Absent-Pillow DoD (C-3) | `ImageAnalyzer` degrades to file-level info (Pillow optional); preprocess skips with logged warning |
| Absent-PyMuPDF DoD | `MultiImageExtractor` returns `[]` with logged warning; workflow leaves document unchanged |
| Windows fix (root cause) | MuPDF leaks the file handle on **failed** `fitz.open(path)` → worker `shutil.move` got `PermissionError [WinError 32]`. Fixed by `path.read_bytes()` + `fitz.open(stream=data, filetype="pdf")` (bounded upstream by `max_file_size_mb`, 50 MiB default). Regression covered by `test_corrupt_pdf_returns_empty_and_releases_handle` |
| Rollback (R-4) | `exif_enabled: false` → no `"image_info"` key (proven live); `diagram_enabled: false` → `DiagramProcessor` passthrough (unit-tested); `preprocess` defaults `false` → Phase-1 behavior |
| Dependencies | PyMuPDF core (existing), Pillow/numpy in `intelligence` extra (existing) — **no new dependencies** |

---

## 4. Spec §4.5 Acceptance Criteria / DoD

| # | Task AC/DoD | Status |
|---|-------------|--------|
| 1 | P2-501 — dimensions, format, EXIF subset, nullable fields | ✅ `ImageInfo(path, format, width, height, size_bytes, mode, page_no=None, index=0, exif)`; `extra="forbid"`; JSON round-trip + defaults tests |
| 2 | P2-502 — JPEG EXIF → date/camera (GPS not by default); corrupt EXIF → None; sole raw-EXIF reader (R-3) | ✅ raw+decoded EXIF; corrupt image degrades to file-level info; `metadata/extractors.py` deliberately has no image reader; EXIF fixture tests |
| 3 | P2-502 absent-Pillow DoD (C-3) | ✅ `analyze_image` without Pillow → `ImageInfo`-level info only + logged warning |
| 4 | P2-503 — reuse shared `imaging/preprocess.py`; guards sourced from `intelligence.images.max_dimensions`/`max_bytes` — **config single source of truth, superseding module `MAX_EDGE = 8000`** | ✅ kwargs resolve at call time; `test_preprocess.py` monkeypatch tests (`mod.MAX_EDGE = 32`) still pass; override guard tests |
| 5 | P2-504 — `.drawio` fixture → Mermaid skeleton; parse fail → raw fallback | ✅ `drawio_to_mermaid` conversion + syntax-guard assertions; unparseable/unsupported → empty + raw fallback in `DiagramProcessor` |
| 6 | P2-505 — all three prompts resolve from `intelligence.prompts.*`; `{language}` substitution at call sites; defaults byte-identical to Phase 1 (R-6) | ✅ `_resolve_prompt(self._prompt or _prompt_templates()[...], self._language)`; `_run_routed_processor` passes `language=`; byte-identical default prompts confirmed |
| 7 | P2-506 — PDF-with-images → per-image extraction with page provenance; **trigger = existing `kind == "pdf"`**; self-contained `_enrich_images` at shared call site coexisting with table gate | ✅ `page_no` + `index` provenance; gate `kind != "pdf"` → `None`; `_enrich_images` sits at the shared P2-305 site beside `_enrich_tables`; no new routing conditions |
| 8 | Full suite green; coverage ≥ 80%; ruff/mypy zero new | ✅ 820 / 88% / 0 / 0 |
| 9 | Per-task atomic commits; rollback verified | ⚠️ rollback ✅; **commits not yet made** (release-time, same as M2.2–M2.4) |

---

## 5. Key Design Decisions (from the frozen spec)

- **Single-owner EXIF (R-3):** `images/metadata.py` is the sole raw-EXIF reader. `metadata/extractors.py` (M2.2) intentionally has no image reader; M2.2 owns `DocumentMetadata`-level fields only. EXIF rides `metadata.extra["image_info"]`, mirroring M2.3 `structure` and M2.4 `tables` (R-1/R-4 additive channel).
- **Shared preprocess module (R-3):** P2-503 reuses `imaging/preprocess.py` rather than duplicating guards. The config values (`intelligence.images.max_dimensions`/`max_bytes`) resolve **at call time**, so the existing P2-104 test monkeypatches on the module constant keep working (backward compatibility with the shared module's consumers).
- **Enrichment trigger (R2 precedent):** P2-506 uses the existing classifier condition `kind == "pdf"` — no invented routing conditions. `_enrich_images` is a self-contained helper at the shared P2-305 call site, coexisting with the `kind == "pdf"` table gate; per-image `ImageInfo` dumps land in `metadata.extra["images"]`.
- **Configurable prompts (R-6):** `_resolve_prompt(self._prompt or _prompt_templates()[...], self._language)` keeps the default prompt templates byte-identical to Phase 1; `{language}` substitution applies only when a language override exists, and only at the call sites (P2-205).
- **Best-effort failures (L4):** every M2.5 feature is additive and fails contained — unreadable image/PDF, missing dependency, or corrupt EXIF never aborts ingestion; the document/note is unchanged (R-4).
- **Windows handle-leak root cause:** MuPDF's `fitz.open(path)` leaks the file handle when the open **fails**, which locked source PDFs and broke the worker's post-processing move. The extractor reads bytes and opens from a stream, keeping the file path unlockable and the 50 MiB bound inherited from `max_file_size_mb`.
- **Optional deps:** PyMuPDF, Pillow, numpy are the only new runtime imports and are already declared (PyMuPDF core; Pillow/numpy in the `intelligence` extra). No `pyproject.toml` change was needed.

---

## 6. Files Changed

- `app/domain/document_intelligence.py` — `ImageInfo` / `ImageExif`
- `app/infrastructure/document_intelligence/images/__init__.py` — public API (`DiagramParser`, `drawio_to_mermaid`, `get_default_diagram_parser`, `ImageAnalyzer`, `analyze_image`, `MultiImageExtractor`, `get_default_multi_image_extractor`, `Preprocessor`, `preprocess_image`, `MAX_EDGE`, `DEFAULT_MAX_BYTES`)
- `app/infrastructure/document_intelligence/images/metadata.py` — P2-502 `ImageAnalyzer`/`analyze_image`
- `app/infrastructure/document_intelligence/images/diagram.py` — P2-504 `drawio_to_mermaid`/`DiagramParser`
- `app/infrastructure/document_intelligence/images/multi.py` — P2-506 `MultiImageExtractor` (byte-stream open)
- `app/infrastructure/document_intelligence/imaging/preprocess.py` — P2-503 `max_dimensions`/`max_bytes` kwargs, `DEFAULT_MAX_BYTES`
- `app/infrastructure/ingestion/image_ingestor.py` — P2-502 EXIF gating (`exif_enabled`) + `image_info` attachment
- `app/infrastructure/ingestion/service.py` — `_images()` accessor, `exif_enabled` wiring
- `app/infrastructure/routing/processor_impls.py` — P2-504 `DiagramProcessor` + `_diagram_enabled()`; P2-505 `_resolve_prompt` + `language` kwargs on Vision/OCR/Handwriting
- `app/pipelines/ingest_workflow.py` — P2-505 `language=` at processor call sites; P2-506 `_enrich_images` at shared call site
- `app/core/config.py` + `config/default.yaml` — `intelligence.images.*` (`preprocess`, `exif_enabled`, `diagram_enabled`, `max_dimensions`, `max_bytes`)
- Tests: `tests/unit/test_image_intelligence.py` (40), `tests/integration/test_image_pipeline.py` (4), `tests/unit/test_config.py` (+2)
- Fixtures: `tests/fixtures/images/{photo.png, plain.png, multi_image.pdf}` (photo has EXIF Make/Model/DateTime; multi-image PDF is 2 pages, one PNG each)

---

## 7. Non-Gate Warnings

1. **No per-task atomic commits (spec §14, process):** milestone work uncommitted; commit per-task atomic commits before release (same status as M2.2/M2.3/M2.4).
2. **62 pre-existing ruff errors and 3 pre-existing mypy errors** remain in files untouched by M2.5 (docx/pptx/spreadsheet ingestors, vision_client, whisper_transcriber, queue worker, templates, search, etc.). They predate this milestone and are not part of its gate.
3. **PDF-only extraction trigger:** per the frozen spec, embedded-image extraction fires on `kind == "pdf"` (text-bearing PDFs). Pure image PDFs classify as `scanned_pdf` and are intentionally skipped by the gate (no invented routing conditions) — their OCR path is unchanged.

---

## 8. Remediation Carried Forward

None — M2.5 required no spec remediation; the frozen spec v1.3 was implemented as written.

Pre-release actions:
1. Commit the M2.1–M2.5 work in per-task atomic commits.
2. Clear the pre-existing ruff/mypy debt noted in §7 before release if desired.
3. Future: consume `metadata.extra["image_info"]`/`["images"]` downstream (embeddings/search/similarity) in a later phase; consider an explicit scanned-PDF multi-image path if product need emerges.
