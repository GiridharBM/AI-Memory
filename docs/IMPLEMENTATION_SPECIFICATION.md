# Implementation Specification

Technical contracts and data schemas that downstream consumers (chunking, search, graph, vault) depend on. Ground truth is the source code (`app/`) and `config/default.yaml`; this file summarizes the stable contracts.

## 1. Document metadata (`metadata.extra` keys)

All extraction results ride `DocumentMetadata.extra` as flat JSON-serializable keys. The `ProcessedDocument` object is immutable — nothing downstream mutates it.

| Key | Phase | Contents |
|-----|-------|----------|
| `language` | M2.2 | ISO code from py3langid (or stdlib heuristic); also mirrored to `metadata.language` |
| `mime_type` | M2.2 | Magic-byte sniffed MIME (RFC-2046-style), ADR-001 chain |
| `extraction_method` | M2.2 | `internal` / `ocr` / `native-extraction` / `missing-library` / `stringio` |
| `ocr` | M2.1 | `{engine, pages, config, per_page_conf, quality}` (vision + optional Tesseract fallback) |
| `structure` | M2.3 | `DocumentStructure` block model: `{block_type, block_id, level, content, start, end, is_list_item}` + `derived_blocks`, `structure_type` (`headings_and_blocks`) |
| `tables` | M2.4 | List of extracted `{index, page, headers, rows}` table dicts |
| `images` | M2.5 | List of image records `{index, caption, alt, mime_type, ocr, page}` (+ EXIF for the sole image owner) |
| `code_structure` | M2.6 | AST-based code inventory (Python): `{imports, functions, classes, module_docstring}` (+ heuristic fallback) |
| `notebook_structure` | M2.6 | Notebook inventory `{cells, functions, classes, top_level_imports}` |
| `entities` | P4 | Entity `{id, name, type, context, confidence, occurrences}` records |
| `relationships` | P4 | Relationship `{source_id, target_id, type, confidence}` records |
| `knowledge_graph` | P4 | `{nodes, edges}` summaries attached to the document |
| `schema_version` | P4 | Bumped on additive schema change (rollback = flag + additive schema, no legacy branches) |

## 2. OCR contract (M2.1)

- Protocol: `OcrEngine` (`app/infrastructure/document_intelligence/ocr/engine.py`) — implementers return `[OcrPageResult(text, confidence, page_number)]` via `process_document(document)`.
- `engine` config: `"vision"` (Ollama vision model, default), `"tesseract"`, `"auto"` (vision → Tesseract fallback).
- PDF rendering honors `zoom`, `page_limit`; hard cap `max_pages=200`. Shared preprocessing (deskew → denoise → CLAHE) is opt-in per pipeline and **off by default**.
- A no-OCR document falls back to original text; empty-OCR documents are routed by the classifier (e.g. `scanned_pdf`).

## 3. Chunking contract (M3.2)

`SemanticChunker.chunk(document) -> list[SemanticChunk]`. A `SemanticChunk` is `{id, content, chunk_type, heading, heading_path, heading_level, start, end, metadata}`.

- **Heading block model**: heading + body until the next heading of `level <= current level`.
- **parent_id seam**: each chunk references the nearest ancestor heading chunk (`parent_id`); top-level chunks are root chunks.
- **Guarantees**: list items never split mid-item; fenced code blocks are atomic; tables/blockquotes/callouts are preserved byte-for-byte; heading content flows into the chunk text so flat stores still group correctly.
- **Adaptive policy**: heading size step, min-chunk coalescing (too-small children merge into the parent when under `min_chunk_size`), snap overlap (`overlap_chars` snapped to nearest word boundary), heading hard boundaries.
- **Sentence tokenization** (M3.1): `SentenceTokenizer` protocol, `auto` mode → NLTK `punkt_tab` if importable, else stdlib heuristic; resolved once per chunker instance.
- **Embedding**: `OllamaEmbeddingClient` on nomic-embed-text; each chunk gets a `VectorEntry {id, document_id, content, embedding, metadata}`; vectors persisted as JSON (`data/vector_store.json`). Batched (default 16) with 1s delay; embed-failure = chunking skipped, chunker remains healthy.

## 4. Search contract (P5)

- `SearchService` facade over `HybridSearch` (`dense` + `bm25` + `rrf`).
- Dense: cosine similarity over precomputed-norm in-memory vectors; `(-score, id)` deterministic tiebreak; exact-match metadata filter.
- BM25: pure-stdlib implementation, `k1=1.5`, `b=0.75`, cached with a version key tied to the store.
- Fusion: reciprocal rank fusion, **RRF `k=60`**.
- CLI: `pam search "query"` → ranked results with score, document, chunk, snippet, and source metadata. Supports top-k, source-type, min-score, and metadata filters.
- Graceful degradation: embedder/BM25 failures fall back without breaking the pipeline.

## 5. Knowledge graph contract (P4)

- Persistence: in-memory adjacency list (`KnowledgeNode` / `KnowledgeEdge`) with JSON persistence (`data/knowledge_graph.json`).
- Built via `DocumentGraphBuilder` from entity + relationship extraction results.
- Query layer: `get_entity`, `related_entities`, `nodes_by_source`, `query_graph`.

## 6. Note generation & vault contract

- `ObsidianMarkdownGenerator` emits 21-field notes (metadata frontmatter, summary, key concepts, definitions, entities, related topics, tags, Q&A, flashcards, MCQs, short/long-answer questions, revision notes, suggested links) with `[[wiki links]]`.
- User content outside `<!-- PAM:BEGIN/END MANAGED -->` markers survives regeneration.
- Vault writer: duplicate-safe filenames; wiki manager: `index.md`, `overview.md`, `log.md`, placeholder notes for unresolved links.

## 7. Runtime & config contracts

- **Python:** 3.11+ runtime; code is 3.14-tested.
- **CLI:** Typer-based `pam` with subcommands `ingest`, `watch`, `search`, `status`, `doctor`, `config`; `pam search` added in P5 (CLI entry `app/cli/entry.py`).
- **Config precedence:** model defaults → `default.yaml` → `{environment}.yaml` (deep merge, `PAM_ENVIRONMENT=production`) → `PAM_*` env vars (nested via `__`).
- **Queue:** single worker, `max_size=1000`, JSON crash recovery.
- **Contract-only config:** `enrich_analysis_input`, `include_docstrings`, `languages` are declared for future contracts and read by no code (C-2/C-5/R-7).
