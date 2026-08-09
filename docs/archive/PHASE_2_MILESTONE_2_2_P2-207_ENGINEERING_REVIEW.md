# P2-207 Engineering Review — Metadata Enrichment Wiring in Ingestion Service

**Task:** P2-207 (Milestone 2.2 — Metadata Extraction Framework)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` §P2-207 (lines 204–222)
**Reviewer:** Principal Engineering Reviewer
**Date:** 2026-08-01
**Review scope:** P2-207 implementation only (extractor enrichment wiring, config consumption, integration tests). No code modified.
**Environment note:** `python-docx 1.2.0` installed per review instruction — the DOCX integration test now runs (previously gated by `importorskip`).

---

## 1. Specification Compliance

| Frozen requirement (§P2-207) | Status | Evidence |
|---|---|---|
| `ingest()` order: size guard → pre-hooks → `ingestor.ingest()` → extractors-for-type merge → post-hooks | ✅ | `service.py:141-153`; enrichment inserted between `ingestor.ingest()` and `_run_post_hooks` at the single `_ingest_source` call site |
| Run `DocumentMetadataService` extractors for the source type and merge into `document.metadata` (superset of Phase 1) | ✅ | `_enrich_document` calls `self._metadata_service.extract()` + `DocumentMetadataService.merge()`; `service.py:165-171` |
| `enabled: false` skips the whole block — document identical to Phase 1 (R-4) | ✅ | `service.py:157-158` early return; disabled-path tests assert metadata + text byte-equal to direct ingestor output for PDF/DOCX/notebook/email |
| Guard each extraction in try/except — extractor failure → debug log, document unchanged | ✅ | `service.py:165-170`; `test_extractor_failure_leaves_document_unchanged` |
| One call site, no flow re-ordering | ✅ | single `_enrich_document` call in `_ingest_source`; no other call sites (grep-verified) |
| Config consumed: `intelligence.metadata.enabled` + `extractors` (values per §3) | ✅ | `enabled` gates the block; `extractors != "default"` skips with debug log; YAML default `"default"` already present from P2-206 |
| Public signatures unchanged | ✅ | `ingest()` untouched; `__init__` gains optional keyword-only `metadata_service` (backward compatible, same pattern as P2-206 `settings`/`hooks`) |
| Testing strategy: real files (PDF, docx, notebook, email) through `ingest()`, `enabled: false` Phase-1-identical, extractor failure isolation | ✅ | `tests/integration/test_ingestion_metadata.py` — 5 tests, all passing after python-docx install |
| Acceptance Criteria: `ingest()` runs extractors + hooks; result metadata superset of Phase 1 (AC 4) | ✅ | enrichment + hook chain both executed in-order; superset asserted per type |
| Definition of Done: integration test on real files; disabled-path regression | ✅ | both met |

## 2. Architecture Compliance

- **Wiring point is correct.** Enrichment lives in the ingestion service, not in the extractors or registry — matches the frozen "single wiring point" purpose. `DocumentMetadataService` is *invoked* (frozen §Classes), not modified.
- **P2-202 "built-ins exist" vs "built-ins wired" separation preserved.** The implementation does **not** mutate the global `get_default_metadata_service()`; the service owns a `DocumentMetadataService` seeded with `DEFAULT_EXTRACTORS` at construction. Global state stays clean; plugin registration via `register_extractor()` remains orthogonal to the built-in set.
- **Import direction safe.** `service.py` → `document_intelligence.metadata` and `metadata.extractors`; no reverse imports. `extractors.py` imports only `app.domain.documents` (P2-202 constraint honored). No cycles (verified by clean import + test run).
- **One-extractor-per-source-type model** (P2-202 design) means the enrichment merge for a given document is a single extractor — consistent with the service-level guard.
- **No-arg constructor preserved.** `DocumentIngestionService()` unchanged for existing consumers (`ingest_workflow.py:139` untouched; all existing pipeline tests pass).

## 3. Public Interfaces

- `DocumentIngestionService.ingest(source)` — signature and return type unchanged. ✅
- `DocumentIngestionService.__init__(ingestors=None, *, settings=None, hooks=None, metadata_service=None)` — additive optional keyword-only; fully backward compatible. ✅
- `DocumentMetadataService`, `DEFAULT_EXTRACTORS`, `DocumentMetadataService.merge` — all reused as-is from P2-201/P2-202; no public API modifications to the metadata package. ✅

## 4. Dependency Correctness

- **Frozen dependencies satisfied:** P2-202 (`DEFAULT_EXTRACTORS` = the six built-ins) and P2-206 (`enabled` gate, hook chain, `MetadataSettings`) both present and already reviewed/approved.
- **`extractors: "default"` wiring** uses the actual `DEFAULT_EXTRACTORS` tuple (not a hardcoded list) — auto-tracks any future P2-202 additions. ✅
- **No import cycle** (see §2). ✅
- **Test deps:** `fitz` and `python-docx` are runtime/optional deps of the ingestor stack already; fixtures are built in-test (hermetic), not committed binaries. The docx test is gated by `pytest.importorskip("docx")`, matching repo convention (`test_ocr_pipeline.py`). ✅

## 5. Error Handling

- Extractor/merge failure → `except Exception` → `logger.debug(..., exc_info=True)` → document returned unchanged; `ingest()` still succeeds. ✅
- `KeyboardInterrupt`/`SystemExit` are `BaseException`, correctly **not** swallowed by `except Exception`. ✅
- URL-sourced documents (`source_path=None`) reach `_enrich_document` only when their `source_type` matches an extractor; any `stat`/read on a bogus `Path(source_url)` is caught by the same guard → unchanged. Safe. ✅
- No error path converts an ingestion failure into a success — enrichment failure explicitly keeps the Phase-1 document. ✅

## 6. Logging

- Unsupported extractor set → `logger.debug("Unsupported extractor set ... skipping enrichment.")` — appropriate. ✅
- Extractor failure → `logger.debug("Metadata enrichment failed; document unchanged.", exc_info=True)` — matches frozen "debug log". ✅
- No-match source type → `DocumentMetadataService.extract()` debug "No metadata extractor registered." — fires per unenriched ingest (markdown/txt/etc.); debug-level, acceptable noise. Minor observation (O5).

## 7. Test Coverage

`tests/integration/test_ingestion_metadata.py` (5 tests, all passing):

- **PDF** (real PyMuPDF file): enriched superset (title/author/page_count/mime_type/subject) + `enabled: false` byte-equal to `PdfIngestor` output. ✅
- **DOCX** (real python-docx file, hermetic zip rewrite with `docProps/app.xml`): enriched `dc:title`/`dc:creator` superset + disabled-path equality. ✅ (now runs with python-docx 1.2.0)
- **Notebook** (real `.ipynb`): enriched `mime_type` + `extra.{cell_count,kernel,language}` superset + disabled-path equality. ✅
- **Email** (real RFC822 `.eml`): enriched `mime_type` + `extra.{subject,from}` superset + disabled-path equality. ✅
- **Extractor failure isolation:** raising extractor → `ingest()` succeeds, metadata + text byte-equal to `TextIngestor` baseline. ✅

Full suite **546 passed / 7 deselected** — zero regressions.

Coverage gaps (non-blocking, see Observations): the `extractors != "default"` skip path and the enrichment-before-post-hooks ordering are asserted only by code reading, not dedicated tests.

## 8. Documentation

`docs/PHASE_2_MILESTONE_2_2_P2-207_IMPLEMENTATION_REPORT.md` is accurate and complete (Summary, Files, Tests, Results, Risks, Next Task = P2-208). Its DOCX-skip note was environment-specific and is now resolved (python-docx installed; test passes). ✅

## 9. Performance

- **Enriched types** (pdf/docx/pptx/notebook/audio/email): extractor re-reads the source from disk (e.g., PDF opened twice). Inherent to the frozen extractor contract (extractors read from `SourceDocument` path, not ingestor memory); acceptable at this scope, flagged as O4.
- **Unenriched types** (markdown/txt/code/…): `extractors_for()` short-circuits with no matching extractor → empty extraction, **no file I/O**, one debug log line. ✅
- Service construction: `DocumentMetadataService(list(DEFAULT_EXTRACTORS))` = six small objects; negligible.

## 10. Regression Safety

- `python -m pytest tests -q`: **546 passed / 7 deselected** — baseline preserved, no regressions.
- `python -m pytest tests/integration/test_ingestion_metadata.py -m integration`: **5 passed / 0 skipped**.
- `python -m ruff check app tests`: **64 errors — unchanged pre-existing baseline**, none in changed files.
- `python -m mypy app`: **4 errors** (down from 5 — python-docx install removed the `docx` stub error). Remaining are pre-existing (`pptx`, `faster_whisper`, `numpy`); none in P2-207 files.
- Rollback contract verified end-to-end: `enabled: false` yields documents byte-identical to Phase 1 (asserted against direct ingestor output, all four real file types).
- Default-on behavior (`enabled: true` → enrichment active for bare constructor) matches the frozen §3 default and the P2-206-approved addendum.

---

## Observations (non-blocking)

1. **`extractors != "default"` path untested.** The skip-with-debug branch exists (`service.py:159-164`) but no test exercises a non-default config value. Future plugin-name selection will need it; today it is dead-but-defensive code.
2. **"Guard each extraction" is implemented as one outer guard.** A plugin registering multiple extractors for a single source type would lose all their values on one failure (no partial merge). Equivalent to the frozen requirement for the built-in set (one extractor per source type, each self-guarding); acceptable at frozen scope.
3. **Ordering contract (extractors → post-hooks) verified by code reading only.** No test combines enrichment with a post-hook observing the enriched metadata. Low risk given the single call site.
4. **Double file read for enriched types** (extractor re-reads the source the ingestor already read). Inherent to the frozen extractor design; a future optimization could pass in-memory content through the protocol, but that is out of scope.
5. **Per-ingest debug noise** — "No metadata extractor registered." logs on every unenriched type. Debug-level, harmless; could be suppressed at the source if it ever matters.

---

## Verdict

✅ **Approved**

P2-207 fully satisfies the frozen contract: all acceptance criteria and the Definition of Done (real-file integration + disabled-path regression) are met, the four real-file enrichment paths and failure isolation are verified passing, and all gates are clean (546 tests, ruff/mypy baselines unchanged; mypy improved after the python-docx install). The wiring is architecturally consistent with P2-201/202/206 and the rollback contract (R-4) is proven end-to-end. The five observations above are minor and require no code changes before proceeding to **P2-208 (email attachment parsing)**.
