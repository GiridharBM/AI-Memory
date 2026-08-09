# Milestone 3.2 Implementation Report — Hierarchical Semantic Chunking (P3-201..P3-205)

**Date:** 2026-08-08
**Milestone:** Phase 3, Milestone 3.2 (MEDD gap G14) — hierarchical semantic chunking
**Status:** COMPLETE — all five tasks implemented, tested, and individually approved (see per-task engineering reviews `docs/PHASE_3_2_P3-20X_ENGINEERING_REVIEW.md`)

---

## 1. Scope

Convert the flat chunk list produced by `SemanticChunker` (`app/infrastructure/semantic_chunking.py`) into a heading-hierarchy-aware, content-type-aware tokenizer, while keeping the M3.1 sentence-segmentation engine and byte-compatible behavior under flat policy defaults.

| Task | Deliverable | Verdict |
|------|-------------|---------|
| P3-201 | Native heading hierarchy metadata (`heading`, `heading_path`, `heading_level`) + in-chunker parent-ID assignment (O-1) | APPROVED |
| P3-202 | List-aware chunking — `_ListBlock` splits at whole top-level list items | APPROVED |
| P3-203 | Code-aware chunking — fenced-code atomic blocks with `language` metadata + inline-code masking | APPROVED |
| P3-204 | Structured-content preservation — byte-for-byte tables/blockquotes/callouts/definitions with forced block-boundary overlap | APPROVED |
| P3-205 | Adaptive `ChunkingPolicy` (heading-depth budget, min-chunk coalescing, snap overlap, heading hard boundaries) + config wiring | APPROVED |

---

## 2. Implementation Summary

- **`ChunkingPolicy`** (`semantic_chunking.py:33`) — frozen dataclass carrying all tunables: `max_chunk_chars`, `overlap_chars`, `sentence_tokenizer`, `heading_size_step`, `min_chunk_chars`, `snap_overlap`, `snap_max_back`, `heading_overlap_boundary`. Defaults reproduce the M3.1 algorithm bit-for-bit (P3-204 gate).
- **Block tokenizer** — `_split_blocks` parses top-level blocks (Markdown/HTML tables, fenced code, blockquotes, callouts, definition lists, heading-led sections, paragraphs, lists); heading-aware recursion decomposes sections; every chunk gets `heading` / `heading_path` / `heading_level` in `metadata.extra` and a heading-derived `parent_id`.
- **Adaptive overlap** — `_apply_overlap` snap-splits at sentence/paragraph/list boundaries within `snap_max_back` and treats headings as hard boundaries when `heading_overlap_boundary` is set; structured blocks force overlap on regardless (content integrity).
- **Config plumbing** — `ChunkingSettings` (`config.py:364`) + `config/default.yaml:171-177` (all keys annotated `"P3-205:"`) + `IngestionWorkflow.create_default` → `ChunkingPolicy` (`ingest_workflow.py:247-254`); CLI (`entry.py:372`) and worker (`worker.py:84`) both reach it.

---

## 3. Key Decisions

- **O-1 (P3-201):** native in-chunker heading detection for parent-ID assignment, over the Milestone 2.3 `metadata.extra["structure"]` consumption seam (user-selected; recorded as a documented deviation in the MEDD).
- **P3-203:** inline-code masking during sentence splitting (backticks cannot fragment a code span) instead of special-casing the sentence engine.
- **P3-204:** block-boundary overlap forced on for structured content — byte-for-byte preservation outranks overlap dedup.
- **P3-205:** flat defaults (`heading_size_step: 0`, `snap_overlap: false`, `heading_overlap_boundary: false`) are the shipped configuration — adaptive behavior is opt-in, keeping M3.1 output stable for existing ingestions.

---

## 4. Verification

- Full suite: **1125 passed / 0 failed / 39 deselected** (M3.1 baseline 1059/33; +66, 0 regressions).
- Chunking integration `tests/integration/test_chunking_pipeline.py`: **8 passed**.
- Broader integration: 26 + 10 passed; OCR 1 skipped (no Tesseract binary — environmental); live-Ollama smoke 1 failed (pre-existing LLM-output flake — environmental, unrelated).
- Ruff: 0 new findings (4 pre-existing E501s in untouched test classes). Mypy clean on `semantic_chunking.py`. Coverage `semantic_chunking.py` 99% (2 miss `458-461`, pre-existing); `config.py` 96%.
- Rollback: P3-203 revert → chunking test module fails collection (`ImportError: cannot import name 'ChunkingPolicy'`); restore → 124 chunking tests pass; byte-verified via SHA-256.

---

## 5. Files Changed

- `app/infrastructure/semantic_chunking.py` — block tokenizer + `ChunkingPolicy` (548 lines)
- `app/core/config.py:364` — `ChunkingSettings` policy fields
- `config/default.yaml:171-177` — policy keys
- `app/pipelines/ingest_workflow.py:40,247-254` — policy wiring
- `tests/unit/test_knowledge_engine.py` (line 29; `TestAdaptiveChunkingPolicy` ~881-1000)
- `tests/unit/test_config.py` — 2 new P3-205 tests
- `tests/integration/test_chunking_pipeline.py` — 2 new integration tests

Docs: `docs/changelog.md` (0.9.0), `docs/release_notes/v0.9.0-milestone-3.2.md`, `docs/MASTER_ENGINEERING_DESIGN_DOCUMENT.md` (0.9.0, §7.4, G14 rows), this report, the doc-sync report, and `docs/PHASE_3_2_FINAL_APPROVAL.md`.

---

## 6. Rollback

- Single-file revert of `semantic_chunking.py` to the P3-203 baseline restores the pre-milestone state (baseline tests pass; P3-204/205 tests fail collection as expected — gated on the new API).
- Config: default policy values are the M3.1 behavior; no data/schema change (`DocumentChunk` and the vector-store schema untouched — additive `metadata.extra` keys only).
