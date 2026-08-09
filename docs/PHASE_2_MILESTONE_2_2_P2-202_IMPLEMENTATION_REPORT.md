# P2-202 Implementation Report — Built-in Metadata Extractors

**Task:** P2-202 — Built-in extractors (pdf/audio/email/docx/pptx/notebook)
**Milestone:** 2.2 — Metadata Enrichment
**Status:** ✅ Implemented (awaiting engineering review)
**Date:** 2026-08-01
**Scope rule honored:** ONLY P2-202 implemented; P2-203/204/205/206/207/208 not started.

---

## 1. Implementation Summary

Six built-in metadata extractors now live in
`app/infrastructure/document_intelligence/metadata/extractors.py`, each
implementing the `MetadataExtractor` protocol from P2-201 with `source_types`
matching the classifier kinds:

| Extractor | `source_types` | Reads from | Deterministic fields |
|---|---|---|---|
| `PdfExtractor` | `("pdf",)` | pypdf `/Title`, `/Author`, `/CreationDate`, `/Producer`, `/Subject` + page count | title, author, created_at, modified_at, page_count, mime_type, producer, subject |
| `DocxExtractor` | `("docx",)` | `docProps/core.xml`, `docProps/app.xml` via stdlib `zipfile` + `ElementTree` | title, author, created_at, modified_at, page_count (Pages), mime_type, last_modified_by |
| `PptxExtractor` | `("pptx",)` | same as docx | title, author, created_at, modified_at, page_count (Slides), mime_type, last_modified_by |
| `NotebookExtractor` | `("notebook",)` | top-level JSON `cells`/`metadata.kernelspec` | title, created_at, modified_at, mime_type, cell_count, kernel, language |
| `AudioExtractor` | `("audio",)` | filename + filesystem | title, modified_at, mime_type (per-extension map) |
| `EmailExtractor` | `("email",)` | RFC822 headers | title, created_at, modified_at, mime_type, subject, from, to, date |

Design points per the frozen spec (§4.2 P2-202):

- **Stdlib-only** for docx/pptx (`zipfile`+`ElementTree`), notebook (`json`), audio
  (file-level), email (`email` stdlib). No new dependencies added — `pypdf` was
  already a project dependency and is reused for PDF.
- **No EXIF reader (R-3).** No image extractor was written; image metadata is
  owned by 2.5 (`ImageInfo`) and consumed later at wiring time (P2-207).
- **`PdfIngestor` behavior preserved.** The metadata helpers
  (`clean_pdf_string`, `parse_pdf_datetime`) moved verbatim into
  `extractors.py`; `PdfIngestor` now imports them, producing byte-identical
  `SourceDocument` metadata (verified by the regression test below).
- **Never raises.** Every extractor wraps fallible reads; corrupt input yields
  `{}` (PDF/notebook/email) or the deterministic file-level fallback
  (docx/pptx), matching the registry contract (`extract` never raises).
- **Not wired into ingestion** — that is P2-207. `DEFAULT_EXTRACTORS` tuple
  exposes the six built-ins for the future wiring step.

## 2. Files Modified

| File | Change |
|---|---|
| `app/infrastructure/document_intelligence/metadata/extractors.py` | **new** — six extractors + `DEFAULT_EXTRACTORS` + moved PDF helpers |
| `app/infrastructure/ingestion/pdf_ingestor.py` | **modified** — removed local `_clean_pdf_string`/`_parse_pdf_datetime`, imports them from `extractors.py`; `SourceDocument` output unchanged |
| `tests/unit/test_metadata_extractors.py` | **new** — 14 per-type unit tests |

## 3. Tests Executed

`python -m pytest tests -q` → **534 passed, 2 deselected** (baseline 520 + 14 new, zero regressions).

New tests in `tests/unit/test_metadata_extractors.py`:

- Protocol conformance + coverage of all six source types
- **PDF regression:** `PdfExtractor` output == `PdfIngestor` metadata for a real
  PyMuPDF-generated PDF with title/author/creation date/producer/subject
- PDF fallback to stem when `/Title` absent; PDF never raises on corrupt bytes
- DOCX/PPTX core properties (title, author, dates, page count, last-modified-by, mime)
- DOCX fallback on non-zip input (title from stem, no author)
- Notebook kernelspec/cell count; never raises on invalid JSON
- Audio deterministic fields + per-extension MIME
- Email header extraction (title/subject/from/to) + binary-garbage tolerance

## 4. Lint & Type Check

- `python -m ruff check app tests` → 64 errors, identical to the pre-P2-202 baseline; new files pass clean.
- `python -m mypy app` → only pre-existing findings (fitz/docx/pptx/whisper stubs, numpy 3.12 syntax in site-packages); no new errors in changed files.

## 5. Remaining Risks

| Risk | Level | Mitigation |
|---|---|---|
| PDF helper names now shared between `PdfIngestor` and `PdfExtractor` | Low | Regression test pins byte-identical behavior |
| OOXML `created`/`modified` may be naive or absent in real files | Low | `_parse_w3cdtf` returns `None` on unparseable values; file mtime fallback retained |
| Extractor output not yet surfaced in ingestion | None (by design) | P2-207 wires `DEFAULT_EXTRACTORS` into `DocumentIngestionService` |

## 6. Next Recommended Task

**P2-207** — Metadata enrichment wiring in ingestion service (depends on P2-202 + P2-206).
