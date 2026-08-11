# Project Status & Version Audit

> **Project Status: V1.0.0 — Stable Local MVP (frozen)**
>
> The V1 release provides a complete local document ingestion, processing, embedding, hybrid retrieval, and grounded question-answering pipeline using Ollama. V1 is considered complete and is now frozen. Future enhancements are tracked under the V2 roadmap.

Audited **2026-08-11** against the live codebase (HEAD `5738880` + uncommitted RAG QA feature, finalized as V1.0.0). This document is the authoritative, code-verified statement of what the project is, what it does, and where it is going. Where this document disagrees with older files, **this document wins**.

**Version classification:**
- **Current:** V1.0.0 — Stable Local MVP
- **Historical:** v0.1.0–v0.12.0 (development phases/releases, kept as records)
- **Future:** V2 roadmap (§10) — explicitly not implemented

---

## 1. Current Version

**Current Version: 1.0.0 (stable MVP)**

Per the versioning framework, **1.0** is reached when a *stable MVP where the complete core pipeline works end-to-end* exists:

```
Document upload → file detection → content extraction → OCR when required →
table/image handling where supported → chunking → embeddings → indexing /
vector storage → retrieval → LLM response → source/citation information
```

Every stage of that pipeline is **implemented, wired into the production path, and covered by tests** (1375 passing, 89.80% coverage), including the recently added RAG question-answering command `pam ask` (retrieval → grounded prompt → Ollama → answer + sources). The system was verified live: `pam search` and `pam ask` both return grounded results against the real vector store.

**Why not 0.x?** The framework reserves 0.5–0.9 for "most core functionality exists but the system still has important limitations, missing features, or instability." The core functionality here is not just present but end-to-end and stable (all 1375 unit/regression tests pass; no known failing component). The missing pieces (reranking, external vector DB, API/UI, evaluation tooling) are all explicitly deferred *future* work, not gaps in the core MVP loop.

**Why not 2.0?** 2.0 implies advanced capabilities beyond the MVP — none of which (cross-encoder reranking, query expansion, ANN/FAISS, REST/Web UI, agentic workflows, evaluation framework) are implemented.

### Version sources (canonicalized at V1.0.0)

| Source | Value | Verdict |
|--------|-------|---------|
| `pyproject.toml:7` | `1.0.0` | ✅ **Canonical** — set at V1.0.0 finalization (was stale `0.1.0`) |
| Legacy docs (README, docs/) | `v0.12.0` → `v1.0.0` | ✅ Updated — active docs now say V1.0.0 |
| Git tag | `v2.0.0` | ⚠️ Stale cosmetic tag from 2026-07-10; not reflected in any doc. The canonical release label is **V1.0.0**. |
| **Actual code (this audit)** | **1.0.0** | **Authoritative** |

> Semver note: `0.x` pre-1.0 development releases (v0.1.0–v0.12.0) are historical records and are not rewritten.

---

## 2. Feature / Milestone Status

Legend: ✅ Complete · 🟡 Partial · 🔬 Experimental · ⚠️ Broken · ❌ Not implemented · ⏳ Planned

| Feature | Status | Evidence | Notes |
|---|---|---|---|
| File upload (watcher + CLI) | ✅ Complete | `app/watcher/service.py`, `app/cli/entry.py` | `pam watch` + `pam ingest` |
| File type detection | ✅ Complete | `app/infrastructure/routing/classifier.py`, `.../metadata/mime.py` | 90+ extensions, 24 kinds, extension-first MIME |
| PDF parsing | ✅ Complete | `app/infrastructure/ingestion/pdf_ingestor.py` | pypdf text-layer extraction |
| Scanned PDF OCR | 🟡 Partial | `app/infrastructure/document_intelligence/ocr/` | Auto-triggered (empty text layer), page-by-page via PyMuPDF, vision model + optional Tesseract |
| DOCX parsing | ⚠️ Broken out-of-box | `docx_ingestor.py` | Works only if `python-docx` installed — **not in `requirements.txt`** |
| Spreadsheet processing | 🟡 Partial | `spreadsheet_ingestor.py` | `.xlsx` works (openpyxl); `.xls` / `.ods` fail |
| Presentation processing | 🟡 Partial | `pptx_ingestor.py` | `.pptx` works only if `python-pptx` installed — **not in `requirements.txt`**; `.ppt`/`.odp` fail |
| Table extraction | ✅ Complete | `document_intelligence/table_intelligence.py` | Structured → GFM markdown in note body; raw flat text is searchable |
| Image extraction | 🟡 Partial | `image_ingestor.py` | Metadata only at ingest; PDF-embedded images extracted as metadata, never rendered |
| Image understanding | 🟡 Partial | `routing/processor_impls.py` (VisionProcessor) | Standalone images → vision OCR → text is embedded/searchable; **PDF-embedded images are not understood** |
| Metadata extraction | ✅ Complete | `metadata/` extractors | MIME, language, EXIF, structure, code/notebook, tables, entities |
| Chunking | ✅ Complete | `app/infrastructure/semantic_chunking.py` | Heading/block/list/sentence-aware, atomic code/tables, overlap |
| Multiple chunking strategies | ❌ Not implemented | — | One `SemanticChunker`; no strategy selector (fixed vs recursive vs …) |
| Embeddings | ✅ Complete | `app/infrastructure/embeddings.py` | `nomic-embed-text` via Ollama, batched, retry + count-mismatch guard |
| Vector database | 🟡 Partial | `app/infrastructure/vector_store.py` | In-memory + atomic JSON persistence, cosine, O(n); no ANN/FAISS |
| Retrieval | ✅ Complete | `app/infrastructure/search.py`, `bm25.py` | Hybrid dense + BM25 fused by RRF (k=60), filters, min-score |
| Reranking | ❌ Not implemented | — | Single-stage by design (roadmap 4.3, deferred) |
| RAG generation | ✅ Complete | `app/application/qa_workflow.py`, `app/prompts/qa.py` | `pam ask` — grounded prompt, injection guard, refusal on insufficient context |
| Citations / sources | 🟡 Partial | `qa_workflow.py`, `cli/entry.py` | Sources table (path, score) + `[SOURCE N]` in prompt; no post-hoc citation verification |
| Error handling | ✅ Complete | `ingestion/service.py`, workflow exception containment | Structured errors, `data/failed/`, best-effort enrichment |
| Testing | ✅ Complete | `tests/` | 1375 passed / 57 deselected; 89.80% coverage; CI workflow present |
| UI | ❌ Not implemented | — | Typer + Rich CLI only |
| API | ❌ Not implemented | — | CLI only |

---

## 3. Supported File Types

Three claims must be kept apart, because older docs conflate them:

- **Classifier map** = 90+ extensions / 24 kinds (what the *classifier* recognizes).
- **Watcher/`PROCESSABLE_EXTENSIONS`** = 53 extensions (what `pam watch` actually picks up).
- **Working end-to-end ingestors** = what this table lists.

### ✅ Fully supported (verified working)

| Type | Extensions | Parser |
|---|---|---|
| Markdown | `.md` | UTF-8 + clean_text |
| Plain text | `.txt` | UTF-8/UTF-8-SIG |
| PDF (text layer) | `.pdf` | pypdf |
| CSV / TSV | `.csv`, `.tsv` | raw read + table processor |
| Spreadsheet | `.xlsx` | openpyxl (declared dep) |
| Jupyter notebooks | `.ipynb` | JSON + cell extraction |
| Source code | 28 extensions (`.py .js .ts .java .c .cpp .go .rs …`) | raw read + structure analysis |
| Config files | `.toml .ini .cfg .conf .yaml .yml .env` | raw read |
| Email | `.eml` | stdlib email (incl. attachments) |
| SQLite databases | `.sqlite`, `.db` | schema + sample rows |
| Research | `.bib`, `.ris` | regex parsers |
| GitHub URL | — | GitHub README API |
| YouTube URL | — | `youtube_transcript_api` |

### 🟡 Partially supported (content limited / conditional)

| Type | Extensions | Limitation |
|---|---|---|
| Images | `.png .jpg .jpeg .gif .webp .bmp .tiff .heic .svg` | No text at ingest; searchable only after vision OCR (requires Ollama vision model); `.heic` degrades silently |
| Audio | `.mp3 .wav .m4a .flac .ogg .aac` | Transcription needs a Whisper backend; empty otherwise |
| Video | `.mp4 .mkv .mov .avi .webm` | **No extraction path** — metadata only, never understood |
| LaTeX | `.tex` | Raw source text, not rendered |
| Web formats | `.html .htm .xml .json .rss .log` | Raw text only (reachable via service, not watcher) |
| Diagrams | `.drawio`, `.mmd` | Label/source text only; `.vsdx` fails |
| Archives | `.zip .tar .gz` | File *listings* only, no content extraction |
| DOCX / PPTX | `.docx`, `.pptx` | Work only if undeclared deps (`python-docx`, `python-pptx`) are installed manually |

### ⚠️ Broken (claimed but failing)

| Type | Reason |
|---|---|
| EPUB `.epub` | `epub_ingestor.py:47` parses a path string as XML → always fails |
| RTF `.rtf`, ODT `.odt` | Registry order routes them to raw-text fallback; no real parsing |
| XLS `.xls`, ODS `.ods` | openpyxl cannot read them |
| PPT `.ppt`, ODP `.odp` | python-pptx reads `.pptx` only |
| Visio `.vsdx` | read as raw binary text → garbage |
| 7Z / RAR `.7z .rar` | explicitly not implemented |

### ❌ Not implemented (claimed in docs only)

`.msg` (no ingestor), `.enw`, `.sqlite3`, `.puml` (PlantUML), generic `http(s)` URLs.

> **Important:** `pam watch` only watches the 53 `PROCESSABLE_EXTENSIONS`. Types like `.docx`, `.epub`, `.ipynb`, `.eml`, `.bib`, `.ris`, `.tex`, `.html` are ingestible via direct service use but are **ignored by the watcher** unless added to `watcher.supported_extensions`.

---

## 4. Document Processing Pipeline

Every stage below is implemented and wired (`app/pipelines/ingest_workflow.py`).

| Stage | Implementation | Tech | Status | Limitations |
|---|---|---|---|---|
| Upload | watcher/CLI → queue | Watchdog, Typer | ✅ | Watcher covers 53 extensions |
| Validation | `ingestion/service.py` | exists/size (50 MB) | ✅ | No content validation |
| Type detection | `routing/classifier.py` | extension-first, MIME sniff | ✅ | — |
| Parser | per-ingestor | pypdf, openpyxl, … | ✅/⚠️ | see §3 |
| OCR (if required) | `document_intelligence/ocr/` | vision model + Tesseract, PyMuPDF page render | ✅ | Needs vision model or Tesseract binary |
| Normalization | `ingestion/utils.py` `clean_text` | stdlib | ✅ | Mild, structure-preserving |
| Metadata | `metadata/` extractors | MIME, language, EXIF | ✅ | Some enrichment is note-only, not searchable |
| Chunking | `semantic_chunking.py` | heading/block/sentence-aware | ✅ | size/overlap fixed at 2000/200 (not configurable) |
| Embedding | `embeddings.py` | `nomic-embed-text` | ✅ | empty-embedding chunks silently skipped |
| Vector storage | `vector_store.py` | in-memory + atomic JSON | ✅ | O(n), whole-store rewrite per save |
| Query embedding | `search.py:_embed_query` | same model | ✅ | failure degrades to lexical-only |
| Retrieval | `search.py`, `bm25.py` | dense cosine + BM25 + RRF(k=60) | ✅ | filters post-fusion |
| Reranking | — | — | ❌ | deferred (roadmap 4.3) |
| Context building | `qa_workflow.py:build_context` | capped 8 chunks / 12 000 chars | ✅ | flat, no parent-child |
| LLM generation | `ollama_client.py:generate_text` | Ollama, retries, typed errors | ✅ | single-shot, no answer validation |
| Answer + sources | `qa_workflow.py` | `QAAnswer(answer, sources, model)` | ✅ | citation markers unverified |

---

## 5. PDF, OCR, Table and Image Processing

### Normal PDFs
Text-layer extraction via pypdf (page-by-page), pages joined before chunking. Page numbers are **not** preserved at chunk level. Tables inside text-layer PDFs are extracted by table intelligence where detected. Images inside PDFs are recorded in metadata but **not rendered or understood**.

### Scanned PDFs
- **Trigger:** pypdf returns empty text → `source_type="scanned_pdf"` → OCR processor invoked automatically.
- **Engine:** vision model (default `qwen2.5vl:latest`), Tesseract as fallback (auto engine). Page-by-page via PyMuPDF rendering (zoom 2.0, page limit 5 by default).
- **Output:** OCR text replaces/joins `document.text` and **flows into the normal chunking/embedding pipeline** — so scanned content is retrievable.
- **Failure modes:** missing Tesseract binary is the one fatal path; otherwise OCR degrades to empty text + warning. OCR confidence is recorded but never gates retrieval.

### Tables
Detected (pipe + HTML tables), extracted to structured data, rendered as **GFM markdown in the note body** (`_tables_section`). Tables are **not embedded as a separate representation** — searchability comes from the raw flat text already present in the chunk. In short: tables are displayed well, retrieved only as text.

### Images
- **Extracted:** standalone images → metadata (EXIF) at ingest; PDF-embedded images → metadata only.
- **Understood:** only standalone images can be OCR'd by the vision model; the resulting text is embedded and **retrievable**. PDF-embedded images are **stored, never understood, never rendered, not searchable**.
- Captions/alt text are **not** processed.

Distinction made explicit: *image extracted* ≠ *image understood by RAG*. Only standalone-image OCR crosses that line.

---

## 6. Chunking Strategies

Exactly **one chunker**: `SemanticChunker` (`app/infrastructure/semantic_chunking.py`) — heading/block-aware, deterministic, offline. Not embedding-based despite the name. Chunk size (2000) and overlap (200) are hardcoded; five adaptive policy knobs are configurable (`chunking:` in `config/default.yaml`).

| Strategy | Status | Notes |
|---|---|---|
| Heading-aware (hierarchical) | ✅ | ATX headings → `heading`, `heading_path`, `parent_heading` |
| Block/paragraph-aware | ✅ | blank-line blocks; tables/code/blockquote/callout/definition atomic |
| Table-aware | ✅ | GFM pipe + HTML tables, never sentence-split |
| Code-aware (fenced) | ✅ | fenced blocks atomic with `language`; inline-code masked |
| List-aware | ✅ | splits at whole top-level items |
| Sentence-based | ✅ | paragraph overflow fallback (NLTK `punkt_tab` or heuristic) |
| Overlap | ✅ | 200 chars tail-prepend; structured chunks are hard boundaries |
| Adaptive budget (P3-205) | ✅ | per-heading-depth budget, `heading_size_step`/`min_chunk_chars` |
| Fixed-size (character) | ❌ | none |
| Recursive character splitter | ❌ | none |
| Page-based | ❌ | pages joined before chunking, not boundaries |
| Embedding-similarity ("semantic") | ❌ | name is aspirational |
| User-selectable strategy | ❌ | no CLI/YAML strategy flag |

Metadata preserved on chunks: `heading`, `heading_level`, `heading_path`, `parent_heading`, `language`, `structure_type`, `callout_type`, `chunk_index`, `start_char`, `end_char`.

---

## 7. RAG Architecture

```
Question
 → SearchService.search(question, top_k, min_score, filter)   # dense + BM25 + RRF
 → ranked SearchHit objects                                    # ranked, bounded
 → build_context()                                             # [SOURCE N] blocks, capped 8 / 12k chars
 → build_qa_user_prompt(question, context)                     # prompts/qa.py
 → OllamaClient.generate_text(QA_SYSTEM_PROMPT + prompt)
 → QAAnswer(answer, sources, model)
```

- **Retrieval:** hybrid — dense cosine (`nomic-embed-text`) + BM25, fused by RRF k=60. Embedder failure degrades to lexical-only.
- **Groundedness:** the system prompt forces answer-only-from-context, refuses when context is insufficient, treats retrieved text as data (not instructions) to block prompt injection, and asks the model to cite `[SOURCE N]`.
- **Sources:** returned as `SearchHit` objects (path, score, snippet) and rendered in a CLI Sources table. In-text `[SOURCE N]` markers are **prompt-requested but not verified**.
- **Context bounds:** `MAX_CONTEXT_CHUNKS = 8`, `MAX_CONTEXT_CHARS = 12_000`.

---

## 8. Current Limitations (honest list)

- **Format truth:** several advertised formats are broken (EPUB, XLS/ODS/PPT/ODP, RTF/ODT, VSDX, 7Z/RAR) or need undeclared deps (DOCX/PPTX). The watcher covers only 53 of the 90+ classified extensions.
- **Vector store:** in-memory, O(n) scan, whole-store JSON rewrite on every save; no ANN/FAISS; no document-level delete/GC.
- **No reranking, no query rewriting, no parent-child retrieval.**
- **No citation verification** — `[SOURCE N]` markers are not checked against the returned sources.
- **No token counting** — full source text is sent to the LLM at ingest.
- **PDF page numbers lost** at chunk level; PDF-embedded images not understood; tables searchable only as raw text.
- **No API, UI, auth, multi-user, Docker, or monitoring** — CLI + local files only.
- **No evaluation tooling** (retrieval/chunking quality metrics, hallucination detection).
- **`pam ask` requires a running Ollama server**; there is no offline/fallback answer path.
- **Stale git tag** `v2.0.0` predates the canonical version label; the release is V1.0.0 (`pyproject.toml` and all active docs agree).

---

## 9. Version 1.0 Definition of Done

V1 is **declared complete**. Evidence checklist — each stage exists, is wired into the production path, and is covered by tests:

- [x] Upload documents (CLI + watcher) and identify file type
- [x] Parse the supported document set (see §3 — working set only)
- [x] OCR scanned documents (vision model, page-by-page, into chunking)
- [x] Preserve useful metadata (MIME, language, EXIF, headings, structure)
- [x] Process supported tables (extract → markdown) and images (standalone OCR → searchable)
- [x] Chunk documents (heading/block/sentence-aware)
- [x] Generate embeddings (`nomic-embed-text`)
- [x] Store/index chunks (in-memory + JSON persistence)
- [x] Retrieve relevant chunks (hybrid dense + BM25 + RRF)
- [x] Accept a user query and generate a grounded answer (`pam ask`)
- [x] Provide source/citation information (Sources table + `[SOURCE N]`)
- [x] Meaningful error handling, unsupported-file handling, logging
- [x] Tests (1375 passing, 89.80% coverage) and reproducible local setup
- [x] Clear, accurate documentation

The V1 pipeline mapped onto the stages the user requested:

```
Document → Ingestion → File Type Detection → Parsing → OCR (where supported) →
Content Normalization → Chunking → Embedding → Vector Storage → Hybrid Retrieval →
Context Construction → Local LLM / Ollama → Grounded Answer → Source/Citation
```

All stages above are implemented and verified end-to-end (see §4 and §7).

**Stopping rule for V1:** do **not** add advanced features to reach V1 — it is reached. Do not let the V1 boundary drift; anything in §10 is explicitly V2+.

---

## 10. Version 2.0 / Future Work

Items explicitly **outside V1** (do not implement in the V1 phase). All **not implemented**:

- **Advanced retrieval:** cross-encoder reranking (roadmap 4.3), query rewriting (4.4), parent-child retrieval (4.6), metadata `$in`/range filters (4.5).
- **Scale & storage:** FAISS/ANN index, external vector DB (Chroma/Qdrant), document-level delete/GC, large-scale distributed ingestion.
- **Multimodal:** PDF-embedded image understanding, advanced table reasoning, OCR layout preservation, video content extraction.
- **Formats:** fix/bring-in EPUB, DOCX/PPTX deps, XLS/ODS/PPT/ODP, RTF/ODT, `.msg`, PlantUML, generic URL fetching.
- **RAG hardening:** citation verification, answer/hallucination evaluation, retrieval quality metrics, offline/fallback answering.
- **Product:** REST API, web UI, auth, multi-user architecture, Docker, monitoring/observability, production deployment.
- **Agents & evaluation:** autonomous agent (tutor/research assistant/daily summaries), advanced evaluation framework, benchmark datasets.

---

## 11. Known Bugs / Issues — Classification

Classified per the V1 finalization rule: only V1 blockers gate the release. **No V1 blockers exist.**

| # | Issue | Evidence | Classification |
|---|---|---|---|
| 1 | EPUB ingestion always fails | `epub_ingestor.py:47` `ElementTree.fromstring` on a path string | V1 non-blocking limitation (documented; format gap) |
| 2 | DOCX/PPTX fail on stock install | `python-docx` / `python-pptx` absent from `requirements.txt`/`pyproject.toml` | V1 non-blocking limitation (documented; optional deps) |
| 3 | `.rtf`/`.odt` routed to raw-text fallback | ingestor registry order `ingestion/service.py:66-88` | V1 non-blocking limitation (documented) |
| 4 | `.xls`/`.ods`/`.ppt`/`.odp`/`.vsdx`/`.7z`/`.rar` claimed but fail | openpyxl/python-pptx limits; binary raw-read | V1 non-blocking limitation (documented; V2 fix) |
| 5 | Watcher ignores 40+ classified extensions | `PROCESSABLE_EXTENSIONS` (53) vs classifier map (90+) | V1 non-blocking limitation (documented) |
| 6 | Video has no extraction path | `VideoProcessor` is passthrough | V2 / future improvement (deferred) |
| 7 | `pyproject.toml` version 0.1.0 / tag v2.0.0 contradict docs | §1 | **FIXED** at V1.0.0 (pyproject → `1.0.0`); stale git tag v2.0.0 remains as a historical record |
| 8 | Empty root files `PCB.md`, `Thermal Management.md` | stray 0-line files in repo root | Cosmetic / documentation issue (clean-up before publishing) |
| 9 | Pytest cache warning (`PytestCacheWarning`) on Windows | cosmetic | Cosmetic / documentation issue (no functional impact) |

---

## 12. Verified V1.0.0 Achievements (Resume / Portfolio Readiness)

Factual, code-verified metrics — safe to state on GitHub, a resume, or a portfolio:

- **V1.0.0 stable local MVP** — complete core RAG pipeline, frozen after a full audit.
- **1375 passing tests / 57 deselected / 0 failed; 89.80% coverage** (floor 80).
- **End-to-end RAG pipeline** — ingestion → file-type detection → parsing → OCR (where supported) → normalization → chunking → embedding → vector storage → hybrid retrieval → context construction → local Ollama generation → grounded answer with source citations.
- **Hybrid retrieval** — dense cosine (`nomic-embed-text`) + Okapi-BM25 fused by reciprocal rank fusion (RRF k=60), with top-k / source-type / min-score / metadata filters.
- **RAG question answering** — `pam ask` returns grounded, refusal-capable answers with `[SOURCE N]` citations.
- **OCR where supported** — auto-triggered scanned-PDF OCR (vision model default, Tesseract fallback).
- **Local, offline-first** — embeddings and LLM inference run entirely through local Ollama.
- **CLI product** — `pam status`, `pam search`, `pam ask`, `pam ingest`, `pam watch` (Typer + Rich).
- **Automated quality gates** — GitHub Actions CI (ruff, mypy, pytest + coverage); ruff/mypy clean on changed files; `git diff --check` clean.
- **Live verification** — `pam status`, `pam search`, and `pam ask` verified against a real local vector store and Ollama.

> Note: no performance benchmarks are fabricated. The only measured perf figures are the documented Phase-6 numbers (ingest ≈ 271 ms / 20k vectors, search ≈ 190 ms) reproduced in `docs/TESTING_AND_VERIFICATION.md`.
