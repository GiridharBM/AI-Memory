# Release Notes

Version history for **LLM-Wiki / Personal AI Memory (PAM)**, current version **V1.0.0** (Stable Local MVP, frozen). Individual milestone release notes are preserved in `docs/archive/release_notes/`.

## v1.0.0 — 2026-08-11 · RAG Question Answering (V1.0.0 finalization)
- **V1.0.0 — Stable Local MVP, frozen.** Canonical release version set in `pyproject.toml`; all active documentation synchronized.
- `pam ask`: retrieval-grounded question answering over the knowledge base — hybrid retrieval (dense + BM25/RRF) → grounded system prompt → local Ollama → answer with `[SOURCE N]` citations.
- `QAWorkflow` + `QAAnswer`/`QAError` (`app/application/qa_workflow.py`), `QA_SYSTEM_PROMPT` (`app/prompts/qa.py`), bounded context assembly (`MAX_CONTEXT_CHUNKS=8`, `MAX_CONTEXT_CHARS=12_000`).
- Answers are grounded only in retrieved notes; the model refuses when context is insufficient.
- Final gate: **1375 tests / 57 deselected / 0 failed; coverage 89.80%** (floor 80); 56 unit + 16 integration files; ruff/mypy clean on changed files; `pam status` / `pam search` / `pam ask` verified live against local Ollama.
- Status determined by code audit — see `docs/PROJECT_STATUS.md`.

## v0.12.0 — 2026-08-09 · Production Hardening & Final Validation
- **PROJECT COMPLETE.** Phase 6 delivered failure isolation, performance optimization, security/config audit, and end-to-end validation.
- Final: 1398 tests / 90.04% coverage, E2E 25/25, lint/type/pip-clean, perf verified (ingest 271 ms/20k, search ≈190 ms).
- Accepted and **APPROVED** (`PHASE_6_FINAL_APPROVAL.md`).

## v0.11.0 — 2026-08-09 · Hybrid Retrieval
- `pam search`: hybrid retrieval combining dense cosine + BM25, fused by RRF (k=60).
- Filters: top-k, source-type, min-score, exact-match metadata.
- SearchService facade with graceful degradation; BM25 k1=1.5, b=0.75.
- 1384 tests, 90.00% coverage.

## v0.10.0 — 2026-08-08 · Document Knowledge Graph
- Entity extraction, co-occurrence relationship detection, per-document graph with JSON persistence.
- Query layer (`get_entity`, `related_entities`, `nodes_by_source`, `query_graph`).
- Graph summary sections in generated notes; additive `schema_version` in `metadata.extra`.
- 1273 tests.

## v0.9.0 — 2026-08-08 · Hierarchical Semantic Chunking
- SemanticChunker over heading hierarchy with `heading_path`, `heading_level`, `parent_id` seams.
- Atomic list items/code blocks; byte-preserved structured content; adaptive chunking policy (min-chunk coalescing, snap overlap, heading boundaries).
- 1125 tests.

## v0.8.0 — 2026-08-06 · NLP Sentence Segmentation
- Pluggable SentenceTokenizer (NLTK `punkt_tab` auto, stdlib heuristic fallback).
- 1059 tests, 89.03% coverage.

## v0.7.0 — 2026-08-04 · Code & Notebook Intelligence (M2.6)
- stdlib-AST code structure + heuristic fallback; notebook cell/function inventory.
- 26+ code/notebook/web source suffixes. 947 tests, 88.88% coverage.

## v0.6.0 — 2026-08-04 · Image Intelligence (M2.5)
- EXIF extraction, drawio→Mermaid, PDF embedded-image extraction, config-driven preprocessing.
- 825 tests, 88.00% coverage.

## v0.5.0 — 2026-08-03 · Table Intelligence (M2.4)
- TableExtractor registry: CSV/TSV, spreadsheets (merged-cell flattening), PDF (pdfplumber default; camelot optional).
- `## Tables` note sections. 778 tests, 88.29% coverage.

## v0.4.0 — 2026-08-02 · Structure Analysis (M2.3)
- Heading-hierarchy + block detection → `DocumentStructure` with stable IDs and exact char offsets; `metadata.extra["structure"]`.
- 747 tests, 88.43% coverage.

## v0.3.0 — 2026-08-01 · Metadata Extraction (M2.2)
- Extractor registry (PDF/DOCX/PPTX/Notebook/Audio/Email), MIME (ADR-001) + language detection, pre/post hooks, email-attachment child ingestion.
- 605 tests, 86.80% coverage.

## v0.2.0 — 2026-08-01 · OCR Engine (M2.1)
- `OcrEngine` protocol + `DocumentOcrService`: vision model default, optional Tesseract fallback (`auto`), PDF page rendering (max 200), per-page confidence, opt-in preprocessing.
- 506 tests, 87.02% coverage.

## v0.1.0 — 2026-07-30/31 · Foundation Fixes (Phase 1)
- 21 foundation fixes: pipeline reliability, config validation, manifest + SHA-256 dedup, failed folder, watch/queue graceful shutdown, OCR/LLM error containment, missing-library routing, blank/empty/unsupported handling, knowledge-note quality.
- 421 tests, 86.07% coverage.
