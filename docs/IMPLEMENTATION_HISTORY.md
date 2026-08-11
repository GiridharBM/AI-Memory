# Implementation History

Chronological record of how LLM-Wiki / Personal AI Memory (PAM) was built, milestone by milestone. Per-task granularity is preserved in `docs/archive/` (original phase/milestone/review files). Completion evidence: `PHASE_6_FINAL_APPROVAL.md`; current state: `PROJECT_STATUS.md`.

## Timeline

| Version | Date | Milestone / Phase | Scope |
|---------|------|-------------------|-------|
| v0.1.0 | 2026-07-30/31 | **Phase 1 — Foundation** | 21 foundation fixes: pipeline reliability, config validation, manifest & dedup, failures folder, watch/queue shutdown, OCR/LLM errors, missing-library routing, blank/empty/unsupported content, knowledge markdown quality |
| v0.2.0 | 2026-08-01 | **M2.1 — OCR Engine** | `OcrEngine` protocol, DocumentOcrService, vision + Tesseract fallback, PDF rendering, confidence + preprocessing |
| v0.3.0 | 2026-08-01 | **M2.2 — Metadata** | Extractor registry (PDF/DOCX/PPTX/Notebook/Audio/Email), MIME detection (ADR-001), language detection, pre/post hooks, email attachments |
| v0.4.0 | 2026-08-02 | **M2.3 — Structure Analysis** | Heading-hierarchy + block detection → `DocumentStructure` with stable IDs and char offsets |
| v0.5.0 | 2026-08-03 | **M2.4 — Table Intelligence** | TableExtractor registry — CSV/TSV, spreadsheet (merged-cell flatten), PDF (pdfplumber default, ADR-002) → `## Tables` section |
| v0.6.0 | 2026-08-04 | **M2.5 — Image Intelligence** | EXIF, drawio→Mermaid, PDF embedded-image extraction, config-driven preprocessing |
| v0.7.0 | 2026-08-04 | **M2.6 — Code & Notebook** | stdlib-AST code parser + fallback, notebook parser → `code_structure` / `notebook_structure` |
| v0.8.0 | 2026-08-06 | **M3.1 — Sentence Segmentation** | SentenceTokenizer protocol, NLTK `punkt_tab` (auto), stdlib heuristic fallback |
| v0.9.0 | 2026-08-08 | **M3.2 — Hierarchical Chunking** | SemanticChunker over heading hierarchy, parent_id seam, adaptive policy, chunk guarantees |
| v0.10.0 | 2026-08-08 | **Phase 4 — Knowledge Graph** | EntityExtractor, RelationshipDetector, DocumentGraphBuilder, JSON persistence, query layer, graph docs in notes |
| v0.11.0 | 2026-08-09 | **Phase 5 — Hybrid Retrieval** | SearchService facade, BM25 (k1=1.5, b=0.75), RRF (k=60), filters, `pam search` |
| v0.12.0 | 2026-08-09 | **Phase 6 — Hardening & Validation** | Failure isolation, performance optimization, security/config audit, E2E validation → **APPROVED** |
| v1.0.0 | 2026-08-11 | **RAG Question Answering / V1.0.0 finalization** | `pam ask`: hybrid retrieval → grounded prompt → Ollama → answer + `[SOURCE N]` citations (`qa_workflow.py`, `prompts/qa.py`); canonical version 1.0.0 set → **Stable Local MVP, frozen** |

## Per-milestone summaries

### Phase 1 — Foundation (v0.1.0)
Established the engineering baseline: config loading/validation, SHA-256 dedup with manifest, failed-folder routing, watchdog/queue graceful shutdown, OCR and LLM error containment, missing-library fallbacks, blank/empty/unsupported file handling, and knowledge-note generation reliability. Result: a healthy, tested pipeline the later phases could build on.

### Phase 2 — Deep Document Extraction (v0.2.0–v0.7.0)
Six milestones that let the system "see" inside files:
- **M2.1 OCR**: vision-model OCR with an optional Tesseract fallback engine, per-page confidence, PDF rendering knobs.
- **M2.2 Metadata**: per-kind extractor registry, robust MIME + language detection (ADR-001), email-attachment child ingestion.
- **M2.3 Structure**: heading hierarchy and block structure with stable IDs and exact character offsets.
- **M2.4 Tables**: multi-engine table extraction (CSV/TSV/sheet/PDF) with merged-cell flattening; pdfplumber default per ADR-002.
- **M2.5 Images**: EXIF (single owner), drawio→Mermaid, PDF embedded-image extraction.
- **M2.6 Code & Notebook**: stdlib-AST code inventory with heuristic fallback, notebook cell/function inventory.

### Phase 3 — Semantic Chunking (v0.8.0, v0.9.0)
- **M3.1** introduced the pluggable sentence tokenizer (NLTK `punkt_tab` preferred, stdlib fallback).
- **M3.2** delivered the heading-hierarchy chunker with parent/child seams, atomic-list/code-block guarantees, and an adaptive chunking policy. This became the base unit for search and the graph.

### Phase 4 — Document Knowledge Graph (v0.10.0)
Deterministic entity extraction and co-occurrence relationship detection, built into a per-document graph persisted as JSON, with a query layer and graph summaries emitted into generated notes.

### Phase 5 — Hybrid Retrieval (v0.11.0)
Combined dense (cosine) and sparse (BM25) signals via RRF, added the `pam search` CLI, and shipped metadata/source-type/min-score/top-k filters with graceful degradation.

### Phase 6 — Production Hardening & Final Validation (v0.12.0)
Final hardening: failure isolation (mypy/scoped clean-up, ruff clean-up of new code), performance optimization (verified ingest + search latency), security & config audit, and end-to-end validation (unit + integration + E2E). Closed with the Phase 6 final approval.

### RAG Question Answering & V1.0.0 Finalization (v1.0.0)
Added the RAG use case: `pam ask` performs hybrid retrieval over the knowledge base, assembles a bounded grounded context (`qa_workflow.py`), and asks the local Ollama model to answer with `[SOURCE N]` citations (`prompts/qa.py`). This shipped the previously deferred "RAG context retrieval" roadmap row and established **V1.0.0 as the Stable Local MVP**, frozen after finalization (canonical version set, active docs synchronized). See `PROJECT_STATUS.md`.

## Remediation history

| Issue | Remediation | Resolved |
|-------|-------------|----------|
| Pre-M2.1 OCR/LLM error handling | Phase 1 error containment (documents routed to failed folder, service-level try/except) | v0.1.0 |
| Pre-M2.1 blank/empty/unsupported content handling | Phase 1 routing & skip rules | v0.1.0 |
| Pre-M2.1 extension set | 26+ source suffixes added for code/notebook/web | M2.6 |
| `metadata.extra` schema (backwards compat) | Additive `schema_version`, rollback-by-flag (R-4) | P4 |
| Tesseract dependency | Optional engine, config-gated, vision default | M2.1 |
| Table engine choice | ADR-002: pdfplumber default, camelot optional | M2.4 |
| Phase 3.1 chunking (structure seam) | P3-201 O-1: heading hierarchy resolved natively in chunker | M3.2 |

## Recording of decisions (ADR/minutes)

- ADR-001, ADR-002 — see `docs/archive/` (original ADR files) and summarized in `architecture.md`.
- P3-201 O-1, M3.1 D1/D8, R-2/R-1/R-4/R-7, C-1/C-2/C-5 — recorded in the original phase planning docs (`docs/archive/`).

## Engineering reviews & approvals

Each phase ended with an engineering review (`ENGINEERING_REVIEW_*`) and/or milestone/phase approval (`PHASE_*_MILESTONE_*`, `PHASE_*_FINAL_APPROVAL`), all preserved in `docs/archive/`. The Phase-6 approval is `PHASE_6_FINAL_APPROVAL.md` (kept in `docs/`); the current V1.0.0 state is `PROJECT_STATUS.md`.
