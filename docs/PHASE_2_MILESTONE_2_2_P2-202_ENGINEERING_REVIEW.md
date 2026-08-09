# P2-202 Engineering Review — Built-in Metadata Extractors

**Reviewer:** Principal Engineering Reviewer
**Task:** P2-202 — Built-in extractors (pdf/audio/email/docx/pptx/notebook)
**Reviewed artifacts:**
- `app/infrastructure/document_intelligence/metadata/extractors.py` (new)
- `app/infrastructure/ingestion/pdf_ingestor.py` (refactored — metadata helpers relocated)
- `tests/unit/test_metadata_extractors.py` (new)
- `docs/PHASE_2_MILESTONE_2_2_P2-202_IMPLEMENTATION_REPORT.md` (new)
- Frozen contract: `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` §P2-202

**Date:** 2026-08-01
**Scope rule honored:** implementation contains ONLY P2-202 work; extractors are not wired into ingestion (correctly deferred to P2-207).

---

## 1. Verification Results

### 1.1 Specification Compliance ✅

| Frozen spec requirement (§P2-202) | Status |
|---|---|
| Six extractors: `PdfExtractor`, `AudioExtractor`, `EmailExtractor`, `DocxExtractor`, `PptxExtractor`, `NotebookExtractor` | ✅ All present |
| Each implements `MetadataExtractor`; `source_types` match classifier kinds (`pdf`, `audio`, `email`, `docx`, `pptx`, `notebook`) | ✅ Verified by `test_all_builtins_implement_protocol` + `test_default_extractors_cover_all_six_source_types` |
| docx/pptx core properties via stdlib `zipfile` + `ElementTree` (`docProps/core.xml`, `docProps/app.xml`) — **no `python-docx`** | ✅ `_extract_ooxml` uses only stdlib; no new deps added to `pyproject.toml` |
| notebook top-level `json` fields — **no `nbformat`** | ✅ cells/kernelspec/language_info read via `json` |
| audio deterministic file-level fields — **no tag library** | ✅ stem title, `_file_timestamp`, per-extension MIME map |
| email subject/from/date headers as today's `EmailIngestor` | ✅ identical field set (`title`, `subject`, `from`, `to`, `date`) |
| **R-3: no second EXIF reader** | ✅ No image/EXIF extractor created at all; image fields deferred to 2.5 `ImageInfo` consumption at P2-207 |
| Move PDF metadata logic out of `PdfIngestor`; behavior preserved | ✅ `clean_pdf_string`/`parse_pdf_datetime` relocated verbatim; `PdfIngestor` imports them and still constructs identical `DocumentMetadata` |
| Each type fills title/author/dates/page_count/mime deterministically | ✅ Per-type deterministic output, tested |
| Rollback safe (not wired to ingestion) | ✅ `DEFAULT_EXTRACTORS` exposed but unregistered |

### 1.2 Architecture Compliance ✅

- Extractors live in the correct layer: `app/infrastructure/document_intelligence/metadata/extractors.py`, beside the P2-201 registry. No domain-layer leakage.
- `DEFAULT_EXTRACTORS` tuple cleanly separates "built-ins exist" (P2-202) from "built-ins registered/wired" (P2-207). No premature registration into `get_default_metadata_service()`.
- No new dependencies; no cross-layer imports from the metadata package into ingestion (the only coupling is the sanctioned one: `PdfIngestor` → extractor helpers).
- Module is self-contained (reimplements the trivial 3-line `file_timestamp` as `_file_timestamp` to avoid an ingestion→document_intelligence cycle — acceptable, noted as an observation).
- R-3 boundary respected; the module docstring states it explicitly.

### 1.3 Interface Correctness ✅

- `extract(document: SourceDocument) -> dict[str, Any]` signature matches the P2-201 `MetadataExtractor` protocol (runtime-checkable, verified by test).
- Returned dicts use the P2-201 merge convention: known `DocumentMetadata` fields (`title`, `author`, `created_at`, `modified_at`, `page_count`, `mime_type`) as top-level keys; type-specific extras (`producer`, `subject`, `last_modified_by`, `cell_count`, `kernel`, `language`, `from`, `to`, `date`) as unknown keys routed to `metadata.extra` by `DocumentMetadataService.merge` (verified against `__init__.py:92-110`).
- Extractor output is a **superset consistent with** each ingestor's current `extra`: PDF `producer`/`subject`, email `subject`/`from`/`to`/`date`, notebook `cell_count`/`kernel`/`language` all match the ingestor field names — so a P2-207 merge will be additive and non-conflicting.
- MIME values match the ingestor constants exactly (PDF `application/pdf`, DOCX/PPTX OOXML MIME, audio map identical to `AudioIngestor._guess_mime`).

### 1.4 Error Handling ✅

- PDF/notebook/email extractors catch all exceptions around I/O + parse and return `{}` — never raise, matching the registry contract (`extract` never raises).
- OOXML extractor degrades to deterministic file-level fallback (`title`=stem, `modified_at`, `mime_type`) when the archive/core.xml is unreadable — no partial-parse ambiguity.
- `parse_pdf_datetime` and `_parse_w3cdtf` return `None` on malformed dates rather than raising.
- Non-numeric OOXML page count guarded by `ValueError` catch.
- Edge cases tested: corrupt `.pdf`, invalid `.ipynb` JSON, non-zip `.docx`, binary-garbage `.eml`.

**Minor observation (non-blocking):** `_file_timestamp` (like the original `file_timestamp`) calls `path.stat()` and would raise if the source file vanished between ingestion and extraction. Acceptable in the current flow since `SourceDocument` is always produced from an existing file; noted only for P2-207 wiring awareness.

### 1.5 Tests ✅

`python -m pytest tests -q` → **534 passed, 2 deselected** (baseline 520 + 14 new; zero regressions; 2 integration tests deselected by `-m 'not integration'`).

- PDF regression test (`test_pdf_extractor_output_equals_pdf_ingestor_metadata`) is the core DoD check: builds a **real** PDF with PyMuPDF (title/author/creationDate/producer/subject), ingests it, and asserts `PdfExtractor` output equals `PdfIngestor` metadata field-for-field — proving the relocation preserved behavior byte-identically.
- Fixtures are built in-memory (`tmp_path`) rather than committed binaries: real docx/pptx zip archives, real ipynb JSON, real eml text. This satisfies DoD ("per-type unit tests") with a cleaner repo; **noted as a minor deviation** from the testing strategy's literal "committed fixture each" wording.
- No integration test added — appropriate, since extractors are not yet wired (P2-207 owns the integration test on real files per the frozen spec).

### 1.6 Documentation ✅

- `docs/PHASE_2_MILESTONE_2_2_P2-202_IMPLEMENTATION_REPORT.md` accurately describes scope, files, tests, results, risks, and next task (P2-207).
- Module docstring documents the stdlib-only intent and the R-3 boundary.
- No stale documentation; no spec files were altered.

### 1.7 Backward Compatibility ✅

- `PdfIngestor` public behavior (`SourceDocument` structure, `scanned_pdf` branch, metadata values) is byte-identical: the existing `test_ingestion.py::test_pdf_ingestor_extracts_text_and_metadata` (monkeypatched `PdfReader`) still passes with `title == "Paper Title"`, `author == "Ada"`, `page_count == 1`.
- The scanned-PDF branch is untouched.
- No changes to `DocumentMetadata`, `SourceDocument`, or the registry API — P2-201 surface unchanged.
- Full-suite pass (534) confirms no downstream breakage.

---

## 2. Findings

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| P2-202-F1 | Observation | Testing strategy literally says "committed fixture each"; tests generate fixtures in-memory instead | **Accepted** — real file formats used; DoD (per-type tests + unchanged `PdfIngestor`) met; keeps binary blobs out of repo |
| P2-202-F2 | Observation | `_file_timestamp` duplicates the 3-line helper in `ingestion/utils.py` | **Accepted** — intentional to avoid a package import cycle; trivial duplication |
| P2-202-F3 | Observation | `DEFAULT_EXTRACTORS` typed as `tuple[Any, ...]` | **Accepted** — could be `tuple[MetadataExtractor, ...]`; cosmetic, no runtime impact |
| P2-202-F4 | Observation | Naive (no-`Z`) OOXML datetimes would flow into `created_at`/`modified_at` unmodified | **Accepted** — matches W3CDTF reality (most files carry `Z`/offset); `None` on failure; correct-on-edge-cases per stdlib |

No correctness, security, or scope defects found. No blocking findings.

---

## 3. Recommendation

Approve. P2-202 is ready to proceed to **P2-207 (metadata enrichment wiring)** in milestone order. The four observations require no code changes.

---

## Verdict

✅ Approved
