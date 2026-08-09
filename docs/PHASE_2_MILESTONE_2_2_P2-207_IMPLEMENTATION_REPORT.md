# P2-207 Implementation Report — Metadata Enrichment Wiring in Ingestion Service

**Task:** P2-207 (Milestone 2.2 — Metadata Extraction Framework)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` §P2-207 (lines 204–222)
**Date:** 2026-08-01
**Status:** Ready for engineering review

## Implementation Summary

Wired the P2-202 extractors into `DocumentIngestionService.ingest()` at the
single call site, so every ingested document gets merged metadata — a superset
of Phase-1 values — gated on `intelligence.metadata.enabled` (R-4).

- **Enrichment call site (`_enrich_document`):** inserted between
  `ingestor.ingest()` and `_run_post_hooks` in `_ingest_source`. Run order is
  now exactly the frozen Interfaces contract: size guard → pre-hooks →
  `ingestor.ingest()` → extractors-for-type merge → post-hooks. One call site,
  no flow re-ordering.
- **Extractor selection (config `extractors: "default"`):** the service owns a
  `DocumentMetadataService` seeded with `DEFAULT_EXTRACTORS` (the six built-ins:
  pdf, docx, pptx, notebook, audio, email) at construction; the P2-202
  "built-ins exist" vs "built-ins wired" split is closed by wiring here. A
  non-`"default"` value (future plugin names) logs a debug message and skips
  enrichment — no unknown-set code path.
- **Merge (superset of Phase 1):** `DocumentMetadataService.extract()` runs the
  matching extractor for `document.source_type` (no match → empty extraction,
  no-op) and `DocumentMetadataService.merge()` writes known fields directly and
  routes the rest into `metadata.extra` (additive; Phase-1 values preserved
  under equal keys).
- **Failure isolation (Step 3):** the whole extract+merge is wrapped in
  try/except — any extractor failure logs at debug and returns the document
  unchanged (also protects URL-sourced documents whose `source_path` is `None`,
  e.g. AudioExtractor's `stat`).
- **Rollback (R-4):** `enabled: false` skips the block entirely — the document
  is byte-identical to Phase 1 (asserted against the direct ingestor output).
- **Public signatures unchanged:** `ingest()` untouched; `DocumentIngestionService`
  gains an optional keyword-only `metadata_service` param (default seeds the
  six built-ins). No-arg constructor still works (`ingest_workflow.py:139`).

## Files Modified

| File | Change |
|------|--------|
| `app/infrastructure/ingestion/service.py` | `_enrich_document()` + wiring in `_ingest_source`; optional `metadata_service` ctor param; imports `DocumentMetadataService`, `DEFAULT_EXTRACTORS` |
| `tests/integration/test_ingestion_metadata.py` | **new** — real-file enrichment integration tests (pdf/docx/notebook/email), disabled-path regression, extractor-failure isolation |

No config changes were needed — the `intelligence.metadata` block landed in
P2-206 and already matches the frozen §3 normative block (`extractors: "default"`).

## Tests Executed

`python -m pytest tests -q` → **546 passed, 7 deselected** (0 regressions).

`python -m pytest tests/integration/test_ingestion_metadata.py -m integration` →
**4 passed, 1 skipped** (docx test skips via `pytest.importorskip("docx")` —
python-docx is not installed in this environment, so `DocxIngestor` itself
cannot ingest DOCX here).

New tests (DoD: integration on real files + disabled-path regression):

- **PDF** (real PyMuPDF file): `ingest()` result is a superset of
  `PdfIngestor` output — title/author/page_count/mime_type/subject extracted;
  `enabled: false` document metadata + text identical to `PdfIngestor().ingest()`.
- **DOCX** (real python-docx file with core + app properties; gated on
  python-docx availability): enriched title from `dc:title`, author from
  `dc:creator`, OOXML mime_type — superset of `DocxIngestor` (stem title only).
- **Notebook** (real `.ipynb`): enriched `mime_type` (top-level) +
  cell_count/kernel/language in `extra` — superset of `NotebookIngestor`.
- **Email** (real RFC822 `.eml`): enriched `mime_type` + subject/from in
  `extra` — superset of `EmailIngestor`.
- **Extractor failure isolation:** an injected extractor raising at runtime →
  `ingest()` still succeeds; document metadata + text identical to
  `TextIngestor().ingest()` (unchanged).
- **Disabled-path regression:** all four real-file tests assert the
  `enabled: false` document equals the direct ingestor's Phase-1 output.

## Test Results

| Gate | Result |
|------|--------|
| `python -m pytest tests -q` | 546 passed / 7 deselected (baseline preserved) |
| `python -m pytest tests/integration/test_ingestion_metadata.py -m integration` | 4 passed / 1 skipped (docx: python-docx absent) |
| `python -m ruff check app tests` | 64 errors (pre-existing baseline; no new) |
| `python -m mypy app` | 5 pre-existing errors (fitz/docx/pptx/whisper/numpy stubs); none in changed code |

## Remaining Risks

- **DOCX integration coverage is environment-gated:** `DocxIngestor` requires
  `python-docx`, which is not installed here; the docx real-file test skips.
  It will run in an environment with python-docx (the `_write_docx` helper is
  hermetic: builds the zip with stdlib, guarantees `docProps/core.xml` +
  `app.xml`).
- **URL-sourced documents** reach enrichment with `source_path=None`; the
  built-ins self-guard reads and the outer try/except keeps the document
  unchanged — no enrichment, no crash (same as pre-P2-207 behavior).
- **Unsupported extractor set** (`extractors` ≠ `"default"`) silently skips
  enrichment (debug log only); plugin-name selection is a future feature per
  frozen §3, not implemented here.

## Next Recommended Task

**P2-208 — Email attachment parsing (recursive ingestion):** extends
`EmailIngestor` to walk `Content-Disposition: attachment` parts, re-ingests
each child through `DocumentIngestionService` with `ProcessedDocument.parent_id`
(additive), enforcing `max_attachments` + `max_file_size_mb` per child and a
recursion guard. P2-207 unblocks it (enrichment wiring in place; P2-202 email
extractor consulted).
