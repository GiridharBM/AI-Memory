# Changelog

All notable changes to LLM-Wiki (PAM) are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); project adheres to [Semantic Versioning](https://semver.org/).

---

## [0.12.0] — 2026-08-09 — Phase 6: Production Hardening & Final Validation (P6-101..P6-106)

### Added

- **Performance benchmark** (P6-102) — measured retrieval cost on a 20 000-document corpus (352 ms/query steady state) with memory-per-query tracking; used to justify the Phase 5 precomputed-norm/BM25-cache optimizations.
- **Failure isolation** (P6-103) — child-attachment processing failures no longer abort the parent document's ingestion (`app/pipelines/ingest_workflow.py`, F1); a manifest save failure keeps the item DONE instead of reverting it to PENDING and re-processing forever (`app/queue/worker.py`, F2). +2 tests.
- **Security/config audit fixes** (P6-104) — `PyMuPDF>=1.24.0` and `openpyxl>=3.1.0` added to `requirements.txt` (documented `pip install -r requirements.txt` path previously broke scanned-PDF OCR and silently lost `.xlsx` tables); `test_production_environment_separates_logging_defaults` locks production config separation.
- **Final end-to-end validation** (P6-105) — independent verification of all 15 flows × 10 non-functional dimensions against the live application: 25/25 automated checks plus the full gate suite.
- **Final project approval** (P6-106).

### Changed

- `.gitignore` extended to `data/inbox/*`, `data/processed/*`, `data/failed/*`, `data/manifests/*` (`.gitkeep` whitelist preserved); 34 personal runtime files untracked via `git rm --cached` (remain on disk, no behavior change). Runtime state no longer version-controlled.
- Documentation synchronized to the released state: README (test counts, config sample, hybrid-search description, roadmap), MEDD (v0.12.0, test/coverage figures, Phase 6 status note), this changelog, release notes.

### Tests

- Full suite **1398 passed / 0 failed / 59 deselected**; coverage **90.04%** (floor 80%).
- Integration **85 passed / 1 skipped** (Tesseract absent — environment) with the pre-existing live-Ollama content-miss flake as the only failure (LLM output variation, not a code defect; exercises no Phase 6 code).
- Ruff: 59 findings, all pre-existing on untouched lines (11 in `app/`, 40 in two dead harness test files, 8 in pre-existing test files); none in changed code. Mypy (scoped `app/core/`, `app/domain/`): clean apart from the pre-existing numpy-stub/Python 3.14 error.
- `pip check` clean; repo + git-history secret scan clean; `pam search`/`pam --help` verified; production config override verified (`PAM_ENVIRONMENT=production` → JSON logging, no colors).

---

## [0.11.0] — 2026-08-09 — Phase 5: Hybrid Retrieval (P5-101..P5-105)

### Added

- **Deterministic BM25 sparse retrieval** (`app/infrastructure/bm25.py`) — custom Okapi-BM25 implementation (`k1=1.5`, `b=0.75`) with tokenized term-frequency/IDF scoring; deterministic `(-score, doc_index)` tie-break for byte-stable result ordering; pure stdlib, no new dependency. (P5-101, P5-102)
- **Reciprocal Rank Fusion** (`app/infrastructure/search.py` `_rrf_fuse`) — fuses dense + BM25 candidate sets with `k=60` (roadmap 4.2), replacing the previous weighted-sum hybrid; fused results can combine both sources even when one scores low. (P5-102)
- **Scoring verification suite** (`tests/unit/test_scoring.py`) — asserts the roadmap 4.1 success criterion (keyword-exact "Python async" outranks a high-semantic-similarity "threading" doc), BM25-over-baseline ordering, RRF fusion correctness, and metadata preservation through ranking. (P5-103)
- **`SearchService` facade + `pam search` CLI** (`app/infrastructure/search.py:200`, `app/cli/entry.py:362`) — spec-facing `SearchService.search(query, *, top_k=5, filter=None, min_score=0.0) -> list[SearchHit]` (MEDD §7.6); `create_default(settings)` reads the same persisted `manifest_root/vector_store.json` the ingest pipeline writes; `pam search <query> [--top-k] [--filter] [--source-type] [--min-score]` renders a Rich table with score/source/snippet. CLI validates blank queries (exit 1), `--top-k >= 1` (exit 2), and `--filter` JSON (exit 1). (P5-104)
- **Retrieval optimization** (`app/infrastructure/vector_store.py`, `app/infrastructure/search.py`) — precomputed entry norms (`_norms`, O(1) cosine legs), a mutation counter (`store.version`) driving a version-keyed BM25 index cache, and deterministic `(-score, entry.id)` ordering; `SearchHit` carries `start_char`/`end_char` (new `VectorEntry` fields, additive, round-tripped through persistence) plus `source_type`/`chunk_index`/`metadata`. (P5-105)
- **Metadata filtering** — exact-match filters against entry fields then metadata keys (entry field wins) in `VectorStore.search(filters=...)` and `SearchService.search(filter=...)`; structured `$in` syntax deferred as roadmap 4.5. (P5-105)
- **Resilient fallback** — embedder failure/None degrades to lexical-only (BM25); BM25 build/search failure degrades to dense-only with cache reset (no poisoned cache, self-healing next query). (P5-104, P5-105)

### Changed

- `HybridSearch` is now RRF-based (dense + BM25) instead of the naive weighted-sum (`0.7*semantic + 0.3*keyword`) hybrid; the weighted-sum path is removed.
- `VectorStore.search` gains a deterministic tie-break (`(-score, entry.id)`) and precomputed-norm cosine scoring with the same semantics as `_cosine_similarity` (dim mismatch / zero vector → `0.0`).

### Tests

- Full suite **1384 passed / 0 failed / 59 deselected**; retrieval pipeline suite (BM25 + scoring + query pipeline + integration) **73 passed**.
- Integration **57 passed / 1 skipped** (Tesseract absent) with only the pre-existing live-Ollama smoke flake failing on this run — re-run in isolation **passes** (nondeterministic LLM output; exercises no retrieval code).
- Phase 5 module coverage: `bm25.py` **100%**, `app/domain/vector_store.py` **100%**, `search.py` **89%**, `vector_store.py` **88%**; repo-wide **90%** (floor 80%).
- Ruff: clean on all Phase 5 sources and tests. Mypy: clean on all four core retrieval modules.
- Performance (P5-105, 20k-corpus steady state): query 223 ms → **71 ms (3.1×)**, dense leg 115 → **51 ms (2.3×)**, peak memory 25.4 MB → **1.8 MB/query (14×)**.

---

## [0.10.0] — 2026-08-08 — Phase 4: Document Knowledge Graph (P4-101..P4-105)

### Added

- **Entity & relationship domain models** (`app/domain/entity_relationship.py`) — validated, deterministically serializable `Entity`, `Relationship`, `EntityMetadata`, `RelationshipMetadata`, `SourceReference`; reuse the existing `EntityType`/`ImportanceLevel`/`EdgeType` vocabulary and `DocumentChunk` provenance conventions; `extra="forbid"`, JSON-safe metadata, offset/self-loop validation. (P4-101)
- **Entity extraction** (`app/infrastructure/document_intelligence/entities/extractor.py`) — deterministic, offline, regex-based `EntityExtractor` (technology + person patterns); consumes `DocumentStructure` blocks when available with global offset stitching, code blocks excluded; "first rule wins" overlap resolution; `Entity.make_id` normalization. (P4-102)
- **Relationship detection** (`app/infrastructure/document_intelligence/relationships/detector.py`) — deterministic `RelationshipDetector`; `related_to` co-occurrence within a shared section/document; canonical lexicographic direction; evidence-merge dedup; deterministic ordering. (P4-103)
- **Document graph construction** (`app/infrastructure/document_intelligence/graph/builder.py`) — `DocumentGraphBuilder` maps entities/relationships onto the existing in-memory `KnowledgeGraph` (no graph DB); deterministic node/edge ordering, dedup, missing-endpoint edges skipped; `find_relationships` conjunctive filter; `graph_to_dict` mirrors the `KnowledgeGraph.save` shape. (P4-104)
- **Graph queries** (`app/infrastructure/document_intelligence/graph/query.py`) — `get_entity`, `related_entities` (undirected BFS, visited set, `max_depth`/`limit`), `nodes_by_source`, `query_graph` (roadmap §5.2 Python-API shape), `graph_from_dict` (consumes `metadata.extra["knowledge_graph"]` without a disk round-trip). (P4-105)
- **Config + wiring** — `EntitySettings`/`RelationshipSettings`/`GraphSettings` (`app/core/config.py:300-339`), `config/default.yaml:152-157` toggles, and `IngestionWorkflow` enrichment stages (`_enrich_entities`/`_enrich_relationships`/`_enrich_graph`, `ingest_workflow.py:576-598`); every stage failure-contained and R-4 rollback-capable.

### Changed

- `IngestionWorkflow` enrichment now attaches `metadata.extra["entities"]`, `metadata.extra["relationships"]`, and `metadata.extra["knowledge_graph"]` (additive; disabled toggles omit the keys for M2.2-identical output).

### Tests

- Full suite **1273 passed / 0 failed / 54 deselected**; integration **52 passed / 1 skipped** (Tesseract absent). Phase 4 modules at **100% coverage** (extractor 70, detector 32, builder 39, query 53, entity_relationship 105 statements); 0 new ruff/mypy findings.
- Rollback verified for all three toggles (`entities`/`relationships`/`graph` `enabled: false` → corresponding key absent, note generation unaffected).
- Environmental caveats (not Phase 4 regressions): live-Ollama smoke flake (O-3) and Tesseract skip.

---

## [0.9.0] — 2026-08-08 — Milestone 3.2: Hierarchical Semantic Chunking

### Added

- **Native heading hierarchy metadata** (`app/infrastructure/semantic_chunking.py`) — every emitted chunk carries `metadata.extra["heading"]`, `heading_path` (ancestry, e.g. `"M3 » §1 » ¶"`), and `heading_level`; heading-parent ID assignment resolved natively in-chunker (P3-201 O-1 — user-selected over the Milestone 2.3 `DocumentStructure` seam, recorded as a deviation). (P3-201)
- **List-aware chunking** — `_ListBlock` tokens split at whole top-level list items (consecutive numbered/bulleted/checklist lines grouped per item), so a list item is never split mid-item across chunks; non-list paragraph text is unaffected. (P3-202)
- **Code-aware chunking** — fenced code blocks emitted as single atomic chunks with `language` metadata (incl. `markdown` fences; language `"generic"` fallback); inline code during sentence splitting is masked so backticks cannot fragment a code span. (P3-203)
- **Structured-content preservation** — Markdown/HTML tables, blockquotes, callouts, and definition lists are emitted byte-for-byte as atomic chunks with `kind` metadata (`html_table`/`table`/`blockquote`/`callout`/`definition`), and block-boundary overlap is forced on (content integrity > overlap dedup). (P3-204)
- **Adaptive `ChunkingPolicy`** — frozen policy dataclass with `heading_size_step` (per-heading-depth char budget bump, `0` = flat), `min_chunk_chars` (short-item coalescing floor), `snap_overlap` / `snap_max_back` (sentence/paragraph/list-boundary snap-back), and `heading_overlap_boundary` (headings are hard boundaries); flat defaults reproduce the M3.1 algorithm bit-for-bit. (P3-205)
- **Config + plumbing** — `ChunkingSettings` (`app/core/config.py:364`) exposes the five policy fields (incl. `sentence_tokenizer`); `config/default.yaml:171-177` lists all keys with `"P3-205:"` comments; `create_default` (`app/pipelines/ingest_workflow.py:247-254`) builds the policy; CLI (`entry.py:372`) and queue worker (`worker.py:84`) both reach it. (P3-205)
- **Tests** — `TestAdaptiveChunkingPolicy` (6 tests) + R-2-style baseline re-run classes in `tests/unit/test_knowledge_engine.py` (P3-204/P3-205 defaults = P3-203 behavior); config contract + env-override tests in `tests/unit/test_config.py`; 2 end-to-end integration tests in `tests/integration/test_chunking_pipeline.py`. (P3-201..P3-205)

### Changed

- `SemanticChunker` is now a block tokenizer: top-level blocks are parsed first (`_split_blocks` — structured kinds + heading-led sections, paragraphs, lists), then decomposed with heading-aware recursion; the M3.1 recursive sentence-splitting path is preserved under flat defaults (P3-204 regression gate).
- `ChunkingPolicy` replaces scattered constructor kwargs; the chunker is now constructed with a `policy` field.
- `chunking.heading_size_step`, `chunking.min_chunk_chars`, `chunking.snap_overlap`, `chunking.snap_max_back`, `chunking.heading_overlap_boundary` added to `config/default.yaml`; all read via env override (prefix `LLMWIKI_`).
- MEDD G14 gap (flat chunk list → parent tracking) resolved; MEDD §7.4 Current Implementation / Interfaces rewritten.

### Tests

- Full suite **1125 passed / 0 failed / 39 deselected**; chunking integration suite **8 passed**; broader integration (code/structure/table/knowledge_engine_persistence/email/image/ingestion_metadata/queue_worker/complete_workflow) 26 + 10 passed; OCR 1 skipped (no Tesseract binary, environmental).
- Ruff: 0 new findings (4 pre-existing E501s in untouched test classes). Mypy clean on `semantic_chunking.py`. Coverage `semantic_chunking.py` **99%** (2 miss `458-461`, pre-existing defensive else); `config.py` 96%.
- Rollback verified: revert to P3-203 chunker → chunking test module fails collection (`ImportError: cannot import name 'ChunkingPolicy'`, proving P3-204/205 tests gate on the new API); restore → **124 passed** via `-k` chunking classes; byte-verified via SHA-256.
- Environmental caveats (not chunking regressions): live-Ollama smoke test flake (LLM output variance — generated note missing a section), 1 OCR skip (Tesseract absent).

---

## [0.8.0] — 2026-08-06 — Milestone 3.1: NLP Sentence Segmentation

### Added

- **Sentence tokenizer protocol + factory** (`app/infrastructure/sentence_tokenizer.py`) — `SentenceTokenizer` Protocol (`split(text) -> list[str]`, D5 contiguous-span contract: `text == s₁ + w₁ + s₂ + … + wₙ₋₁ + sₙ` with whitespace-only separators consumed at boundaries); engine registry + `register_sentence_tokenizer`; factory `get_sentence_tokenizer(engine="auto")`; unknown/unregistered engine → clear `SentenceTokenizerSelectionError`; empty/whitespace-only text → `[]`; engine selection resolved once per chunker instance (D8). (P3-101)
- **Heuristic stdlib engine** — `_HeuristicSentenceTokenizer` (registered unconditionally — the guaranteed `"auto"` fallback): abbreviation-aware (Dr., Mr., U.S.A., a.m., etc.), ellipses, decimal numbers, quoted sentences, `!?` terminators, and CJK `。！？` with empty boundary separators (D7). (P3-102)
- **Optional NLTK engine** — `_NltkSentenceTokenizer` (import-guarded): pretrained `PunktTokenizer("english")` backed by `nltk.download("punkt_tab")` (one-time setup for the optional `intelligence` extra; nltk ships no bundled data; runtime stays offline). Registered only when nltk and its data are present; `"auto"` prefers it. (P3-103)
- **`SemanticChunker` integration** — `sentence_tokenizer: str = "auto"` dataclass field; engine resolved once at construction (D8); `_split_by_sentences` delegates to the engine; `_SENTENCE_END` regex removed; heading/paragraph/overlap logic and the offsets math unchanged (D5/D5a). (P3-104)
- **Config + plumbing** — `ChunkingSettings` (`app/core/config.py:364`, `sentence_tokenizer: Literal["auto", "nltk", "heuristic"] = "auto"`) + top-level `chunking:` block (`config/default.yaml:171`) + the single construction site `create_default` → `SemanticChunker(sentence_tokenizer=...)` (`app/pipelines/ingest_workflow.py:247`); CLI (`entry.py:372`) and queue worker (`worker.py:84`) both reach it. (P3-105)
- **Regression + fixture suite** — `TestSemanticChunkingAllEnginePaths(TestSemanticChunking)` re-runs the full existing 15-test chunking suite under `heuristic`/`nltk`/`auto` (R-2; nltk path import-guarded); committed fixtures `tests/fixtures/chunking/{abbreviations.md, cjk.md}` with D5 span-reconstruction; new integration suite `tests/integration/test_chunking_pipeline.py`. (P3-106)

### Changed

- `chunking.sentence_tokenizer: "auto"` (default): prefers the NLTK `punkt_tab` engine when the `intelligence` extra is installed, otherwise degrades to the stdlib heuristic with one logged warning — ingestion never breaks (C-3 DoD).
- `overlap_chars` is now live: `SemanticChunker._apply_overlap` prepends the previous chunk's trailing `overlap_chars` characters to each subsequent chunk (previously dead code).
- `nltk>=3.9` added to the optional `intelligence` extra (D4/C-2 — no separate `chunking` extra; no new *required* runtime dependency).
- No `"regex"` legacy engine value retained (Phase 2 R-4); the heuristic is a superset of the old regex, and the regression gate proves all existing chunking tests pass unchanged.

### Tests

- Full suite **1059 passed / 33 deselected** (baseline 1005/31; +54, 0 regressions); R-2 regression class **45/45, 0 skips**; integration 31 passed / 1 skipped (Tesseract) / 1 pre-existing live-Ollama smoke flake (O-3, untouched).
- Coverage 89.03% against the 80% floor; `sentence_tokenizer.py` module 97.14% (target ≥ 90%).
- Rollback verified: revert → exactly **1005 passed / 31 deselected** (P3-105 baseline); restore byte-verified via SHA-256.

---

## [0.7.0] — 2026-08-04 — Milestone 2.6: Code & Notebook Intelligence

### Added

- **`CodeStructure` / `NotebookStructure` models** (`app/domain/document_intelligence.py`) — `CodeStructure` (language, imports, functions, classes, docstrings, char offsets), `CodeImport` (module, names, level), `CodeFunction` (name, args, docstring, line/char offsets), `CodeClass` (name, bases, methods, docstring, offsets), `NotebookCell` (`id`, `type: Literal["markdown","code","raw"]`, `source`, `outputs`, `execution_count`), `NotebookStructure` (cells, kernel, language). Additive, `extra="forbid"`, `end >= start` validation. (P2-601)
- **Language registry** (`app/infrastructure/document_intelligence/code/languages.py` — `language_from_filename`) — maps every `CODE_EXTENSIONS` suffix to a language name; unknown → `"generic"`; case-insensitive. (P2-602)
- **Python AST parser** (`app/infrastructure/document_intelligence/code/parser.py` — `_AstCodeParser`) — stdlib `ast` extraction of imports, functions (incl. `async def`), classes with methods, docstrings, exact offsets (3.12 `end_lineno`/`end_col_offset`). (P2-603)
- **Heuristic fallback parser** (`_HeuristicCodeParser`) — line-based regex for non-Python code and syntax-invalid Python; never raises. `parse_code()` dispatches Python → AST, others → heuristic. (P2-604)
- **Notebook parser** (`app/infrastructure/document_intelligence/code/notebook.py` — `NotebookParser`/`parse_notebook`) — ordered typed cells, `execution_count`, outputs capped at `max_cell_outputs` (`"[truncated]"` marker), kernel/language from metadata; never raises. `NotebookIngestor` attaches `metadata.extra["notebook_structure"]`, preserving flattened fenced text. (P2-605)
- **Pipeline enrichment** (`app/pipelines/ingest_workflow.py` — `_enrich_code`) — code/notebook structure attaches at the shared P2-305 call site: `metadata.extra["code_structure"]` (kind `code`) / `metadata.extra["notebook_structure"]` (kind `notebook`), gated by `intelligence.code.enabled` and `kind`. Processors remain passthrough. (P2-606)

### Changed

- **`intelligence.code` config** added (`CodeSettings` in `app/core/config.py`, `code:` block in `config/default.yaml`): `enabled: true`, `languages: "default"` (contract-only C-5), `max_cell_outputs: 10`, `max_code_chars: 100000` (str-length cap, truncate-with-warning), `include_docstrings: true` (contract-only C-5).
- `DocumentIngestionService` threads `max_cell_outputs`/`max_code_chars` from config into `NotebookIngestor` / `parse_code`.
- Rollback contract: `intelligence.code.enabled: false` ⇒ no `code_structure`/`notebook_structure` keys — Phase-1-identical output. (R-4)

### Tests

- Full suite **947 passed / 31 deselected** (integration-gated); hermetic integration set 28 passed + 1 skipped (Tesseract) / 14 deselected — the 29th test (a live-Ollama smoke test) requires a running Ollama server and is environmental, not an M2.6 defect.
- New unit suites (122 across 7 files): `test_code_models.py` (33), `test_code_languages.py` (34), `test_code_parser.py` (28: AST + heuristic), `test_notebook_parser.py` (14), `test_notebook_ingestor.py` (4: config wiring), `test_enrich_code.py` (6: hook on real workflow), `test_config.py` (+3 `CodeSettings` tests incl. env override).
- New integration suite `tests/integration/test_code_pipeline.py` (3 tests): `.py` e2e, `.ipynb` e2e, rollback (`enabled: false` → pre-M2.6 passthrough). Fixtures `tests/fixtures/code/{sample.py, sample.ipynb}`.
- Coverage 88.88% against the 80% floor.

---

## [0.6.0] — 2026-08-04 — Milestone 2.5: Image Intelligence

### Added

- **`ImageInfo` model** (`app/domain/document_intelligence.py`) — dimensions, format, EXIF (`ImageExif`, nullable), optional GPS; additive, `extra="forbid"`. (P2-501)
- **EXIF/metadata extractor** (`app/infrastructure/document_intelligence/images/metadata.py` — `ImageAnalyzer`/`analyze_image`) — the **single owner of the raw EXIF read** (R-3); `ImageIngestor` attaches `metadata.extra["image_info"]` for image kinds, gated by `intelligence.images.exif_enabled`. Corrupt/unreadable EXIF → empty `ImageExif(raw={}, decoded={})`, no crash. (P2-502)
- **Diagram intelligence** (`images/diagram.py` — `drawio_to_mermaid`, `DiagramParser`) — `.drawio` → Mermaid skeleton (fixed-fixture comparison); `.mmd` passthrough; parse failure → raw text fallback; gated by `intelligence.images.diagram_enabled`. (P2-504)
- **Configurable prompts + `{language}` wiring** — OCR/vision/handwriting prompts come from `intelligence.prompts.*` with the `{language}` slot substituted at the processor call site (P2-205 delta, R-6). (P2-505)
- **Multi-image (PDF-with-images) enrichment** — self-contained `_enrich_images` at the shared P2-305 call site, triggered by the existing `kind == "pdf"` classifier condition; per-embedded-image `ImageInfo` dumps land in `metadata.extra["images"]` with `page_no`/`index` provenance; coexists with the table gate (M2.4 R2 precedent). (P2-506)
- **Preprocessing now actually wired into OCR** — the shared `imaging/preprocess.py` `Preprocessor` is bridged into both engines (`ocr/__init__.py` `_shared_preprocessor`); the bridge is only built when at least one preprocess toggle (`ocr.preprocess` or `images.preprocess`) is enabled. All three processors carry an explicit `preprocess` kwarg driven by per-path config: `VisionProcessor` consumes `intelligence.images.preprocess`; `OCRProcessor` and `HandwritingProcessor` consume `intelligence.ocr.preprocess`. The `_extract_via_service` helper and `DocumentOcrService.extract` / `OcrEngine.run` defaults are `False` — no production path enables preprocessing without config. (R-a, review remediation, re-review)

### Changed

- **`intelligence.images` config** aligned to the frozen §4.5 contract: `max_dimensions: [8192, 8192]` (scalar max-edge int or `[width, height]` pair both accepted) and `max_bytes: 20 MB` (20,971,520) now supersede the historical `MAX_EDGE = 8000` / 25 MiB defaults. `ImageSettings.max_dimensions` is `int | tuple[int, int]`; invalid values are rejected at parse time. (review remediation)
- All three OCR/vision processors route through `_extract_via_service(..., preprocess=<config>)` — the single call site that hands the per-path config-driven `preprocess` flag to `DocumentOcrService.extract()`. The `_shared_preprocessor` bridge returns `None` when both toggles are off, preventing any unconfigured preprocessing.
- Protocol defaults: `OcrEngine.run(preprocess: bool = False)`, `DocumentOcrService.extract(preprocess: bool = False)` — preprocess is opt-in, never a config-bypassing default.
- Rollback contract: `intelligence.images.exif_enabled: false` ⇒ no `image_info` key; `diagram_enabled: false` ⇒ `.drawio` raw text passthrough; `preprocess: false` ⇒ no preprocessing — all Phase-1-identical. (R-4)

### Tests

- Full suite **823 passed / 28 deselected** (integration-gated); hermetic integration set 25 passed + 1 Tesseract skip (live-Ollama smoke excluded, pre-existing).
- New AC2 wiring tests: engines receive the shared preprocessor (config-gated); `preprocess=True` routes bytes through the shared bridge to the vision client; config accepts scalar/pair `max_dimensions` and rejects invalid shapes. AC2 regression test: `preprocess=false` sends identical bytes through the production `VisionProcessor.process` → `service.extract` path; `preprocess=true` sends real Pillow-transformed (grayscale CLAHE) bytes.
- Coverage 88% against the 80% floor.

---

## [0.5.0] — 2026-08-03 — Milestone 2.4: Table Intelligence

### Added

- **Table intelligence subsystem** (`app/infrastructure/document_intelligence/tables/`):
  - `Table` / `TableCell` / `TableRow` / `TableHeader` pydantic models (additive, in `app/domain/document_intelligence.py`, `extra="forbid"`) with `source_position` provenance (line/sheet/page). (P2-401)
  - `TableExtractor` protocol + `TableExtractorRegistry` (`source_kinds` → extractor; empty registry / unknown kind → `None`, never raises); composition root exposes `extract_tables(document)`, `get_table_extractor(...)`, `get_default_table_extractor()`. (P2-402)
  - **CSV/TSV extractor** — `csv.Sniffer` dialect sniff (fallback `csv.excel`), header sniffing, quoted/escaped field parsing, row/column caps. (P2-403)
  - **Spreadsheet extractor** — per-sheet tables via openpyxl (loaded non-read-only with `data_only=True` so `merged_cells.ranges` is available, per spec R1); merged-cell rectangles flattened by propagating the top-left value. (P2-404)
  - **PDF extractor** — pdfplumber default engine, camelot optional plugin with fallback (ADR-002); engine/formats missing → logged warning + empty list (flat fallback, C-3). (P2-405)
- **`MarkdownTableRenderer` + `render_tables_to_markdown`** — GitHub-flavored Markdown pipe tables with `\|` and newline (`<br>`) escaping; empty tables render to `""`. (P2-406)
- **Enrichment into the enriched document** — `_run_routed_processor` gained a `kind` parameter; after structure enrichment it calls `_enrich_tables` and stores `document.metadata.extra["tables"] = [table.model_dump(mode="json")]` when `tables.enabled` AND the classifier `kind` is `csv`/`spreadsheet`/`database`/`pdf` (R2). Best-effort: failures logged, key absent, flat text preserved. (P2-406)
- **Note-body table rendering** — `ObsidianMarkdownGenerator` renders a `## Tables` section (after Categories) from `metadata.extra["tables"]`; absent/empty tables key → Phase-1-identical note output (AC5). (P2-406)
- **Configuration** — `intelligence.tables.*` block (`enabled`, `pdf_engine`, `max_rows`, `max_cols`, `header_sniffing`) bound in `TableSettings`; `enabled: true` by default. The frozen §2.4 `min_confidence` key was removed (review R1 — pdfplumber exposes no per-table confidence; deviation recorded in the M2.4 remediation report). (P2-406)
- **Dependencies** — `openpyxl>=3.1.0` promoted to core deps; `pdfplumber>=0.11.0` added to the `intelligence` optional extra (wheel preflight verified for `cp314-win_amd64`). (P2-404, P2-405, R11)

### Changed

- `IngestionWorkflow._run_routed_processor` is the shared enrichment point (R-2): `_enrich_tables` sits beside `_enrich_structure`; the caller passes `classification.kind`.
- `ProcessedDocument` is **not** modified — tables ride the R-1 `metadata.extra["tables"]` channel; the note generator reads `SourceDocument` only.
- Rollback contract: `intelligence.tables.enabled: false` (or non-table kinds, or engine failure) returns Phase-1-identical flat notes — no `"tables"` key, no `## Tables` section (R-4). **This is a default-enabled user-visible change**: CSV/spreadsheet/PDF notes now include table sections.
- `spreadsheet_ingestor.py` is unchanged — flat text preserved in both modes; structured tables attach only at the enrichment stage (spec R3).

### Tests

- Full suite 778 passed / 24 deselected (integration-gated); hermetic integration suites 20 passed.
- New unit suite `tests/unit/test_table_intelligence.py` covers models (`extra="forbid"`), registry (incl. empty), CSV/TSV parsing + header sniffing + row caps, spreadsheet multi-sheet + merged-cell flattening + corrupt-file containment, PDF degraded path (strict — import forced to fail, review R2), escaping, golden-file CSV→Markdown (C-4), and note-body rendering.
- New integration suite `tests/integration/test_table_pipeline.py` (6 tests, `-m integration`) covers CSV → `extra["tables"]` + rendered note via the production wiring, `enabled: false` ⇒ no key + no `## Tables`, non-table kinds ⇒ no key; plus the engine-present PDF test (`@pytest.mark.integration`, skipped when pdfplumber absent, review R2).
- R2 fixture fix: `ruled_table.pdf` regenerated as a genuine ruled table (ReportLab GRID strokes — pdfplumber sees 8 lines); engine-present test asserts ≥1 `Table` + `| --- |` Markdown, proving the P2-405 AC.
- Coverage 88% against the 80% floor; `tables/` module at 81% (PDF engine paths are integration-gated).
- Fixtures committed in `tests/fixtures/tables/` (`people.csv`, `people.expected.md`, `multi_sheet.xlsx`, `ruled_table.pdf`).

---

## [0.4.0] — 2026-08-02 — Milestone 2.3: Document Structure Analysis

### Added

- **Document structure analysis subsystem** (`app/infrastructure/document_intelligence/structure/detector.py`):
  - `DocumentStructure` / `DocumentSection` / `DocumentBlock` pydantic models (additive, in `app/domain/document_intelligence.py`) with IDs, heading levels (1–6), `parent_id`, and exact char offsets; block offsets validated (`end_char >= start_char`, `len(text) == end_char - start_char`). (P2-301)
  - Heading hierarchy detector `_detect_headings` — nested ATX headings → correct parent/child tree; fenced `#` (triple-backtick blocks) never mis-split as headings; heading rule `^#{1,6}\s+\S`; levels > 6 normalize to 6. (P2-302)
  - Block detector `_detect_blocks` — paragraph / list / code fence / blockquote / Markdown table typed blocks with accurate `start_char`/`end_char`; list-continuation and pipe-table separator heuristics; O(log k) bisect range membership. (P2-303)
  - Structure tree builder `_build_tree` + `StructureAnalyzer.analyze()` — sections contain their blocks, offsets contiguous, stable path-style section IDs (`s-1`, `s-1-1`, …), block IDs `b-<section_id>-<n>`; degenerate/empty input → empty structure, never raises. (P2-304)
  - **Enrichment into the enriched document** — `_run_routed_processor` in `ingest_workflow.py` serializes the analyzer result to `document.metadata.extra["structure"] = structure.model_dump(mode="json")` for kinds in `TEXT_BEARING_KINDS` (`markdown`, `text`) when `structure.enabled: true`; analyzer failures contained (logged, no key, ingestion continues). (P2-305)
  - **Performance + cap guard** — `max_structure_text_bytes = 5_000_000` (text above is skipped with a single warning), `MAX_SECTIONS = 10_000` (warn + truncate, never raise), O(n) single linear scan within the ≤ 1 s / 1 MB ceiling. (P2-306)
  - **Configuration** — `intelligence.structure.*` block (`enabled`, `enrich_analysis_input`) bound in `StructureSettings`; `enrich_analysis_input` is contract-only this milestone (addendum 3 / R-7) — declared, not read by any code. (P2-305)
- **Public APIs** — `analyze_document_structure(text, source)`, `get_default_structure_analyzer()`, `StructureAnalyzer`, `DocumentStructure`, `DocumentSection`, `DocumentBlock`. Composition root `app/infrastructure/document_intelligence/__init__.py` exposes the first two. (P2-301, P2-304)

### Changed

- `IngestionWorkflow._run_routed_processor` now attaches structure enrichment after processor success and before chunking; the shared call site is the reuse point for Milestone 2.4/2.5/2.6 (R-2). (P2-305)
- `ProcessedDocument` is **not** modified — the structure rides the proven `metadata.extra["structure"]` channel exactly like `parent_id` (R-1 deviation from the frozen P2-305 wording; §5.4 of the M2.3 spec). (P2-305)
- Rollback contract: `intelligence.structure.enabled: false` returns M2.2-identical documents — no `"structure"` key is written (R-4). (P2-305)
- `SemanticChunker` is unchanged — it keeps its internal `_split_by_headings` copy; chunking behavior is byte-identical (AC5). (P2-302)
- Public API additions: `analyze_document_structure`, `get_default_structure_analyzer`. (P2-301, P2-304)

### Fixed

- Fenced code containing `#` lines is no longer a source of false headings in structure output (the fence-state machine runs before the heading match). (P2-302)

### Tests

- 733 unit tests pass (0 deselected); 14 integration tests pass (17 deselected); full suite 747 passed.
- Coverage 88.43% against an 80% floor; ruff and mypy report zero new findings in changed files.
- New unit suite `tests/unit/test_structure_analysis.py` (128 tests) covers hierarchy (AC1), fence disambiguation (AC2), block offsets on committed fixtures (AC3), model round-trip, caps, and the O(n) timing ceiling.
- New integration suite `tests/integration/test_structure_pipeline.py` (9 tests, `-m integration`) covers enrichment for markdown/text kinds (AC4), stable section IDs across repeated runs, `enabled: false` ⇒ key absent, non-text-bearing kinds ⇒ key absent, analyzer-failure containment, and oversize skip.
- Chunker regression preserved: `test_knowledge_engine.py` + `test_text_preprocessing.py` pass unchanged (AC5).
- Fixtures committed in `tests/fixtures/structure/` (`nested_headings.md`, `fenced_code.md`, `lists_and_quotes.md`, `blocks.md`, `table_block.md`, `empty.md`); oversize text generated in-test.

---

## [0.3.0] — 2026-08-01 — Milestone 2.2: Metadata Extraction Framework

### Added

- **Metadata extraction subsystem** (`app/infrastructure/document_intelligence/metadata/`):
  - `MetadataExtractor` protocol + `MetadataExtraction` model (known fields → `DocumentMetadata`, unknown keys → additive `extra`); deterministic behavior when no extractor matches — never raises. (P2-201)
  - `DocumentMetadataService` registry with `register_extractor()` public API. (P2-201)
  - Built-in stdlib-only extractors: `PdfExtractor`, `AudioExtractor`, `EmailExtractor`, `DocxExtractor`, `PptxExtractor`, `NotebookExtractor`; PDF metadata extraction moved out of `PdfIngestor`. (P2-202)
- **MIME detection** — `detect_mime(path)`: magic-number content sniff (first 512 bytes) with a pure-stdlib fallback table; optional `python-magic` loaded lazily via the `intelligence` extra (absent → single logged warning, system still works); extensionless files now correctly classified (e.g. Markdown via content). (P2-203)
- **Language detection** — `detect_language(text)` returning `(lang, confidence)`: optional `py3langid` (intelligence extra) with a pure-stdlib heuristic fallback covering en/fr/de/ja; low-confidence results fall back to `"en"` with a warning; `LanguageDetector` protocol + `register_language_detector()`; inspects at most the first 10 KB of text. (P2-204)
- **Metadata enrichment on processed documents** — `ProcessedDocument.language` and `ProcessedDocument.parent_id` fields (additive), plus document metadata merged into the document's `extra`. (P2-205, P2-207)
- **Ingestion hook framework** — `IngestionHook` protocol (pre/post); configurable pre/post hook chains run inside `DocumentIngestionService`; per-hook `try/except` so a failing hook never breaks ingestion; `register_hook()` public API. (P2-206)
- **Ingestion size/time limits** — `max_file_size_mb` reject-before-read guard (FR-ING-7); `url_timeout_seconds` config key added. (P2-206)
- **Email attachment parsing** — `EmailIngestor` extracts `Content-Disposition: attachment` parts to per-run temp child sources; children re-ingested recursively with `parent_id` linking; `max_attachments` cap, one-level depth guard, shared per-file size limit, and temp cleanup via `finally`. (P2-208)
- **Configuration** — `intelligence.metadata.*` block (`enabled`, `extractors`, `mime_enabled`, `language_detection_enabled`, `max_file_size_mb`, `url_timeout_seconds`, `email_attachments`, `max_attachments`, `hooks.pre`, `hooks.post`) bound in `MetadataSettings`. (P2-201, P2-208)

### Changed

- `DocumentIngestionService.ingest()` now runs size guard → pre-hooks → ingestor → extractor merge → post-hooks; `run()` split into `_process_document` + `_ingest_children` for email-attachment re-ingestion. (P2-207, P2-208)
- Metadata enrichment is additive only: `enabled: false` reproduces Phase-1 output byte-for-byte (rollback contract, R-4). (P2-207)
- Document classification consults `detect_mime` for extensionless/unknown files instead of relying on extension-only `mimetypes.guess_type`; known extensions still take precedence (ADR-001). (P2-203)
- Prompt language integration: the document-analysis user prompt takes a `language` argument and appends "Respond in {language}." for non-English documents; the English path remains byte-identical to Phase 1. (P2-205)
- Public API additions: `detect_mime`, `detect_language`, `register_extractor`, `register_hook`, `MetadataExtraction`, `DocumentMetadataService`. (P2-201, P2-203, P2-204, P2-206)

### Fixed

- Extensionless/unknown MIME types are now detected by content sniff rather than failing extension-only fallback. (P2-203)
- `language` is now populated on classified/processed documents (previously never set); heuristic fallback confirmed working with `py3langid` absent. (P2-204, P2-205)
- `mime_enabled` configuration now actually reaches `DocumentClassifier` (previously the flag was defined but never read). (P2-203)
- Production wiring now passes runtime settings to `DocumentIngestionService`, so `email_attachments` / `max_file_size_mb` are honored by the CLI and queue worker (previously dropped). (P2-208)
- Email attachments are no longer discarded: `Content-Disposition: attachment` parts are ingested as child documents with temp-file cleanup via `finally`. (P2-208)

### Security

- Email attachment filenames are sanitized (`_safe_attachment_name`) to strip any path components, preventing path traversal from crafted `Content-Disposition` headers; per-run temp child files are removed in a `finally` block. (P2-208)

### Tests

- 605 unit tests pass (0 deselected); 14 integration tests pass (7 deselected); frozen AC integration test for email attachments passes via `-m integration`.
- Coverage 86.80% against an 80% floor; ruff and mypy report only pre-existing baseline findings (zero new in changed files).
- Fallback paths tested without optional deps: MIME sniff with `python-magic` absent, language heuristic with `py3langid` absent. (P2-203, P2-204)
- Regression tests added for production wiring (settings reach `DocumentIngestionService`; `email_attachments` / `max_file_size_mb` honored). (P2-208)

---

## [0.2.0] — 2026-08-01 — Milestone 2.1: OCR Engine

### Added

- **OCR engine subsystem** (`app/infrastructure/document_intelligence/ocr/`):
  - `OcrEngine` protocol + `DocumentOcrService` registry with deterministic empty-registry error (`OCRSelectionError`). (P2-101)
  - `OcrResult` / `PageOcrResult` models with per-page confidence aggregation and empty/low-confidence page flagging. (P2-101, P2-106)
  - `VisionOcrEngine` — sequential per-page loop with bounded retry (1 retry), early stop on empty page, per-page degradation (never aborts the pass), temp-file cleanup via `finally`. (P2-102)
  - `render_pdf_pages` — PyMuPDF page rendering at configurable zoom, page limit (0 = all), and `max_pages` hard cap; per-page render-error isolation; in-memory PNG bytes (no temp files). (P2-103)
  - `TesseractOcrEngine` — optional offline OCR via pytesseract with lazy import, clear G06 `ImportError`, `tesseract_cmd`/`tesseract_lang` support, per-page confidence mapping. (P2-105)
  - `get_default_ocr_service(settings)` factory with `engine="auto"` (vision primary → Tesseract fallback), explicit engine selection, and `enabled: false` → empty registry (Phase-1 passthrough). (P2-108)
- **Shared image preprocessing** `app/infrastructure/document_intelligence/imaging/preprocess.py` — deskew → denoise (median) → CLAHE in fixed order; dimension guard; original path preserved on any error; optional-dep (Pillow/numpy) absent → logged-warning no-op. Shared with Milestone 2.5 (R-3). (P2-104)
- **OCR configuration** — `intelligence.ocr.*` block (`enabled`, `engine`, `page_limit`, `zoom`, `preprocess`, `tesseract_cmd`, `tesseract_lang`, `confidence_threshold`, `max_pages`) bound in `OcrSettings`. (P2-108)
- **Configurable prompt templates** — `intelligence.prompts.{ocr,handwriting,vision}` with a `{language}` slot; defaults byte-identical to the Phase-1 hardcoded prompts. (P2-107, R-6)
- **`pam doctor` OCR diagnostics** — reports OCR enabled/engine/page limit, vision-model presence, Tesseract binary on PATH/`tesseract_cmd`, and `pytesseract`/`Pillow` availability. (P2-108)
- **Confidence surfaced to notes** — `ProcessedDocument.ocr: OcrResult | None` (additive), frontmatter `ocr_confidence` + `- OCR Confidence` reference line. (P2-106)

### Changed

- `VisionProcessor`, `OCRProcessor`, `HandwritingProcessor` now delegate to `DocumentOcrService` instead of inline `_ocr_extract*` / `_looks_handwritten` helpers; identical `process()` signatures preserved. (P2-107)
- Legacy `vision_client=` kwarg still accepted via a thin `_ocr_service_from_client` wrapper for backward compatibility. (P2-107)
- Vision-required no-fallback guard preserved: processor failure for `image`/`scanned_pdf`/`handwritten` re-raises rather than sending images to a text-only model. (P2-107)

### Removed

- `_ocr_extract_from_pdf()`, `_ocr_extract()`, and `_looks_handwritten()` helpers deleted from `app/infrastructure/routing/processor_impls.py`. (P2-107)
- Hardcoded OCR/handwriting/vision prompts removed from processors (moved to config). (P2-107)

### Fixed

- Scanned-PDF OCR page cap is now configurable (`page_limit`, default 5 reproduces Phase 1) instead of hardcoded. (P2-102/P2-103)
- A single failed page no longer aborts the whole OCR pass. (P2-102/P2-103)
- PyMuPDF absent now raises a clear `ImportError` with install instructions instead of silent empty-text fallback (G06). (P2-103)

### Security

- `TesseractOcrEngine` invokes the pytesseract library API only — no shell subprocess. (P2-105)

---

## [0.1.0] — 2026-07-31 — Phase 1: Foundation Fixes

### Added

- Atomic vector-store and knowledge-graph writes (temp file + `os.replace`).
- PyMuPDF required with clear `ImportError` on scanned-PDF OCR (G06).
- Queue stats, edge validation, startup inbox scan, and retry on embeddings.

### Changed

- Watcher/worker extension lists unified; classifier made data-driven; config path resolvers consolidated.

### Removed

- `FileCreatedEvent` intermediate object; legacy/broken ingestor test fixtures.

### Fixed

- `NoteVersion.sha256` now populated; `RuntimeStats` latency bug; `ManifestManager` `_loaded` flag; `hash_for_path` ValueError propagation; analysis validation duplication.

---

[0.8.0]: https://github.com/GiridharBM/AI-Memory/releases/tag/0.8.0
[0.7.0]: https://github.com/GiridharBM/AI-Memory/releases/tag/0.7.0
[0.6.0]: https://github.com/GiridharBM/AI-Memory/releases/tag/0.6.0
[0.5.0]: https://github.com/GiridharBM/AI-Memory/releases/tag/0.5.0
[0.4.0]: https://github.com/GiridharBM/AI-Memory/releases/tag/0.4.0
[0.3.0]: https://github.com/GiridharBM/AI-Memory/releases/tag/0.3.0
[0.2.0]: https://github.com/GiridharBM/AI-Memory/releases/tag/0.2.0
[0.1.0]: https://github.com/GiridharBM/AI-Memory/releases/tag/0.1.0
