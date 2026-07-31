# LLM Wiki – Current Implementation Report

> Generated from live codebase inspection. Every claim references a specific file, class, and method.

---

## 1. Project Overview

**Name:** Personal AI Memory System (PAM)  
**Purpose:** Local-first tool that ingests source documents (PDFs, web content, images, audio, etc.), analyzes them via a local LLM (Ollama), and generates structured Obsidian-compatible Markdown notes in a personal wiki vault.  
**Language:** Python 3.14+  
**Package manager:** `uv` (see `pyproject.toml`)

---

## 2. Architecture

The system follows a layered architecture:

```
┌──────────────────────────────────────────────────────┐
│                    CLI (typer)                        │
│              app/cli/entry.py                         │
├──────────────────────────────────────────────────────┤
│                   Pipelines                           │
│           app/pipelines/ingest_workflow.py            │
├──────────────────────────────────────────────────────┤
│   Domain Models    │    Infrastructure                │
│   app/domain/      │    app/infrastructure/           │
│                    │    ├── ingestion/ (21 ingestors)  │
│   - analysis.py    │    ├── llm/ (Ollama, vision)     │
│   - documents.py   │    ├── embeddings.py             │
│   - notes.py       │    ├── vector_store.py           │
│   - routing.py     │    ├── semantic_chunking.py      │
│   - vector_store.py│    ├── knowledge_graph.py        │
│   - knowledge_graph│    ├── search.py                 │
│   - semantic_chunk │    ├── routing/ (classify)       │
│                    │    ├── vault/ (writer)           │
│                    │    ├── state/ (manifest)         │
│                    │    └── templates/ (obsidian)     │
├──────────────────────────────────────────────────────┤
│              Core (config, logging)                   │
│              app/core/                                │
├──────────────────────────────────────────────────────┤
│           Queue │ Watcher │ Workers                   │
│    app/queue/  │ app/watcher/                        │
└──────────────────────────────────────────────────────┘
```

**Dependency direction:** CLI → Pipelines → Domain + Infrastructure. Domain has zero infrastructure imports.

---

## 3. Folder Structure

```
app/
├── __init__.py
├── application.py              # AIProcessingError definition
├── cli/
│   ├── __init__.py
│   └── entry.py                # typer CLI (ingest, status, doctor, config, watch)
├── core/
│   ├── __init__.py
│   ├── config.py               # Pydantic settings, YAML+env loading
│   ├── extensions.py           # File extension constant sets
│   └── logging.py              # Structured logging setup
├── domain/
│   ├── __init__.py
│   ├── analysis.py             # DocumentAnalysis Pydantic model
│   ├── documents.py            # SourceDocument, DocumentIngestionResult
│   ├── knowledge_graph.py      # KnowledgeGraph, KnowledgeNode, KnowledgeEdge
│   ├── notes.py                # ObsidianNote model
│   ├── processed_document.py   # ProcessedDocument model
│   ├── routing.py              # DocumentClassification, ProcessorSelection
│   ├── semantic_chunking.py    # DocumentChunk dataclass
│   └── vector_store.py         # VectorEntry, SearchResult dataclasses
├── infrastructure/
│   ├── __init__.py
│   ├── embeddings.py           # EmbeddingService → Ollama /api/embed
│   ├── knowledge_graph.py      # KnowledgeGraphBuilder
│   ├── search.py               # SemanticSearch, HybridSearch
│   ├── semantic_chunking.py    # SemanticChunker
│   ├── vector_store.py         # In-memory VectorStore with JSON persistence
│   ├── ingestion/
│   │   ├── base.py             # BaseIngestor ABC
│   │   ├── service.py          # DocumentIngestionService (registry + dispatch)
│   │   ├── utils.py            # clean_text(), file_timestamp()
│   │   ├── archive_ingestor.py
│   │   ├── audio_ingestor.py
│   │   ├── code_ingestor.py
│   │   ├── config_ingestor.py
│   │   ├── csv_ingestor.py
│   │   ├── database_ingestor.py
│   │   ├── diagram_ingestor.py
│   │   ├── docx_ingestor.py
│   │   ├── email_ingestor.py
│   │   ├── epub_ingestor.py
│   │   ├── github_readme_ingestor.py
│   │   ├── image_ingestor.py
│   │   ├── markdown_ingestor.py
│   │   ├── notebook_ingestor.py
│   │   ├── pdf_ingestor.py
│   │   ├── pptx_ingestor.py
│   │   ├── research_ingestor.py
│   │   ├── spreadsheet_ingestor.py
│   │   ├── txt_ingestor.py
│   │   ├── video_ingestor.py
│   │   └── youtube_transcript_ingestor.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── ollama_client.py    # OllamaClient (text + JSON generation)
│   │   ├── vision_client.py    # OllamaVisionClient (image OCR)
│   │   └── whisper_transcriber.py  # Audio transcription
│   ├── routing/
│   │   ├── classifier.py       # DocumentClassifier (heuristic)
│   │   ├── processor_impls.py  # 20+ processor implementations
│   │   ├── processors.py       # processor registration
│   │   └── router.py           # RoutedProcessor, ProcessorRouter
│   ├── state/
│   │   ├── hashing.py          # compute_file_hash (SHA-256)
│   │   ├── manifest.py         # ManifestManager (dedup tracking)
│   │   └── models.py           # ManifestEntry, ManifestState
│   ├── templates/
│   │   └── obsidian_note.py    # ObsidianMarkdownGenerator
│   └── vault/
│       ├── __init__.py
│       ├── wiki_manager.py     # WikiManager
│       └── writer.py           # VaultWriter
├── pipelines/
│   └── ingest_workflow.py      # IngestionWorkflow (full pipeline orchestrator)
├── prompts/
│   └── document_analysis.py    # LLM prompt templates for analysis
├── queue/
│   ├── __init__.py
│   ├── manager.py              # QueueManager
│   ├── models.py               # Queue task models
│   ├── state.py                # QueueStateStore
│   ├── stats.py                # Queue statistics
│   └── worker.py               # QueueWorker
└── watcher/
    ├── __init__.py
    ├── events.py               # File events
    ├── filters.py              # Extension filters
    ├── scanner.py              # Directory scanner
    └── service.py              # WatchService (polling watcher)
```

---

## 4. Pipeline

**File:** `app/pipelines/ingest_workflow.py`  
**Class:** `IngestionWorkflow`  
**Key method:** `run(source, expected_source_type)` → `IngestionResult`

The pipeline orchestrates these steps in sequence:

```
source → IngestService → SourceDocument
       → Classify → DocumentClassification
       → Process → ProcessedDocument
       → Chunk → list[DocumentChunk]
       → Analyze (LLM) → DocumentAnalysis
       → Build Graph → KnowledgeGraph
       → Generate Note → ObsidianNote
       → Write to Vault → VaultWriteResult
```

**How it works** (`ingest_workflow.py`):
- `run()` ingests the source via `DocumentIngestionService`
- Classifies via `DocumentClassifier` into a kind (pdf, markdown, image, scanned_pdf, etc.)
- Selects a processor from the `ProcessorRouter` based on kind
- Routes to the appropriate model (general_text, programming, vision, scanned_ocr, etc.)
- Processes into `ProcessedDocument`
- Chunks via `SemanticChunker`
- Analyzes via `OllamaClient.generate_json()` with `DocumentAnalysis` response model
- Builds knowledge graph via `KnowledgeGraphBuilder`
- Generates Obsidian note via `ObsidianMarkdownGenerator`
- Writes to vault via `VaultWriter`
- Returns `IngestionResult` with document, note, write result, AI result, graph result

**Dependencies:** All infrastructure modules, Ollama runtime  
**Limitations:** Sequential processing; no parallelization per document; LLM analysis is the bottleneck (single Ollama call per document)

---

## 5. Ingestion

**File:** `app/infrastructure/ingestion/service.py`  
**Class:** `DocumentIngestionService`  
**Key method:** `ingest(source: str | Path)` → `DocumentIngestionResult`

**How it works:** Maintains a list of 21 `BaseIngestor` instances. On `ingest()`, normalizes the source (URL or Path), selects the first matching ingestor via `_select_ingestor()`, calls `ingestor.ingest()`, and returns a `DocumentIngestionResult` with either a `SourceDocument` or a `DocumentIngestionError`.

### Registered Ingestors

| File | Class | Supported Sources | Mechanism |
|---|---|---|---|
| `pdf_ingestor.py` | `PdfIngestor` | `.pdf` | `pypdf` extraction |
| `markdown_ingestor.py` | `MarkdownIngestor` | `.md` | Direct text read |
| `txt_ingestor.py` | `TextIngestor` | `.txt` | Direct text read |
| `docx_ingestor.py` | `DocxIngestor` | `.docx` | `python-docx` |
| `pptx_ingestor.py` | `PptxIngestor` | `.pptx` | `python-pptx` |
| `image_ingestor.py` | `ImageIngestor` | `.jpg/.png/.gif/.bmp/.tiff/.webp` | Reads bytes, returns metadata only |
| `audio_ingestor.py` | `AudioIngestor` | `.mp3/.wav/.m4a/.flac/.ogg` | Reads duration, returns metadata only |
| `video_ingestor.py` | `VideoIngestor` | `.mp4/.avi/.mov/.mkv` | Reads duration, returns metadata only |
| `code_ingestor.py` | `CodeIngestor` | 20+ code extensions | Direct text read |
| `config_ingestor.py` | `ConfigIngestor` | `.yaml/.json/.toml/.ini/.cfg/.conf` | Direct text read |
| `csv_ingestor.py` | `CSVIngestor` | `.csv` | Raw text read |
| `spreadsheet_ingestor.py` | `SpreadsheetIngestor` | `.xlsx/.xls` | `openpyxl` or `xlrd` |
| `notebook_ingestor.py` | `NotebookIngestor` | `.ipynb` | JSON parse, extract code+markdown cells |
| `email_ingestor.py` | `EmailIngestor` | `.eml/.msg` | `email` stdlib |
| `epub_ingestor.py` | `EpubIngestor` | `.epub` | `ebooklib` |
| `archive_ingestor.py` | `ArchiveIngestor` | `.zip/.tar.gz/.tar/.tgz` | `zipfile`/`tarfile` |
| `database_ingestor.py` | `DatabaseIngestor` | `.db/.sqlite/.sqlite3` | `sqlite3` |
| `diagram_ingestor.py` | `DiagramIngestor` | `.drawio/.vsdx/.puml` | XML parse |
| `research_ingestor.py` | `ResearchIngestor` | `.bib/.ris/.enw` | Parses citation format |
| `github_readme_ingestor.py` | `GitHubReadmeIngestor` | GitHub repo URLs | HTTP fetch of README |
| `youtube_transcript_ingestor.py` | `YouTubeTranscriptIngestor` | YouTube URLs | `youtube_transcript_api` |

**Canonical output:** `SourceDocument` (`app/domain/documents.py:27`) with `source`, `source_path`, `source_type`, `filename`, `text`, `metadata`.

**Text normalization:** `clean_text()` in `utils.py:16` normalizes whitespace, normalizes headings/lists/tables/blockquotes, protects code blocks via token substitution.

**Dependencies:** `pypdf`, `python-docx`, `python-pptx`, `openpyxl`/`xlrd`, `ebooklib`, `youtube_transcript_api`, `ollama` (for all)

**Limitations:**
- No incremental/chunked reading for large files (entire file in memory)
- Image/video/audio ingestors return text placeholder, actual extraction delegated to later processing (VisionProcessor/WhisperTranscriber)
- `GitHubReadmeIngestor` only fetches README, not full repo
- No rate limiting for URL-based ingestors

---

## 6. OCR

**Status:** Partially Implemented

**Files involved:**
- `app/infrastructure/llm/vision_client.py` — `OllamaVisionClient`
- `app/infrastructure/routing/processor_impls.py` — `OCRProcessor`, `HandwritingProcessor`
- `app/infrastructure/routing/classifier.py` — `DocumentClassifier` sets `requires_ocr: True` for `scanned_pdf`, `handwritten`, `image`

**How it works:**
1. `DocumentClassifier.classify()` detects scanned PDFs and images (`classifier.py`)
2. `ProcessorRouter` routes `scanned_pdf` → `OCRProcessor`, `handwritten` → `HandwritingProcessor`
3. `OCRProcessor.process()` (`processor_impls.py`) calls `_ocr_extract()`:
   - For PDFs: opens with PyMuPDF (`fitz`), renders first 5 pages as PNG images at 2x zoom, sends each to `OllamaVisionClient.describe_image()`
   - For images: sends directly to `OllamaVisionClient.describe_image()`
4. `OllamaVisionClient.describe_image()` (`vision_client.py:46`) reads image bytes, base64-encodes them, sends to Ollama vision model (`qwen2.5vl:latest` or configured) via `client.generate(model=..., prompt=..., images=[b64])`

**OCR for scanned PDFs:** `_ocr_extract_from_pdf()` uses PyMuPDF (1st 5 pages only, 2x zoom). Falls back to empty string if PyMuPDF not installed.

**Handwriting detection:** `_looks_handwritten()` heuristic checks average line length < 80 chars and mixed capitalization ratio between 0.1 and 0.6.

**Dependencies:** `ollama` (required), `PyMuPDF` (optional, for scanned PDFs), vision model in Ollama (`qwen2.5vl:latest`)

**Limitations:**
- Scanned PDF OCR limited to first 5 pages
- Falls back to empty string if PyMuPDF not installed
- Handwriting detection is heuristic, not ML-based
- No layout preservation (tables, columns lost)
- No confidence scoring per page/region

---

## 7. Images

**File:** `app/infrastructure/llm/vision_client.py`  
**Class:** `OllamaVisionClient`  
**Key method:** `describe_image(image_path, prompt)` → `str`

**File:** `app/infrastructure/routing/processor_impls.py`  
**Class:** `VisionProcessor`  
**Key method:** `process(document)` → `ProcessedDocument`

**How it works:**
- `ImageIngestor` reads image bytes but extracts no text (returns `SourceDocument` with placeholder text)
- `DocumentClassifier` classifies as `image` kind, sets `requires_vision: True`
- `VisionProcessor.process()` calls `_ocr_extract()` with a general prompt: "Analyze this image..."
- `_ocr_extract()` delegates to `OllamaVisionClient.describe_image()` which base64-encodes the image and sends it to the vision model via Ollama's `generate()` with `images=[b64]`
- Output confidence: 0.85 with vision client, 0.70 without

**Dependencies:** `ollama`, vision model (`qwen2.5vl:latest`)  
**Limitations:**
- No multi-page image support (PDF with images goes through OCR path)
- No image preprocessing (deskew, denoise, contrast adjustment)
- Prompt is hardcoded, not configurable
- Vision model is a local Ollama requirement, not bundled

---

## 8. Tables

**Status:** Partially Implemented

**File:** `app/infrastructure/routing/processor_impls.py`  
**Class:** `TableProcessor`  
**Key method:** `process(document)` → `ProcessedDocument`

**How it works:** `TableProcessor` is a passthrough — it takes the raw text from `CSVIngestor` or `SpreadsheetIngestor` (which extract cells as text) and passes it through unchanged via `_passthrough()`. There is no dedicated table structure extraction or CSV-to-Markdown-table conversion.

**File:** `app/infrastructure/routing/classifier.py` — `DocumentClassifier.classify()` sets `requires_table_extraction: False` for csv/spreadsheet. The flag exists but is not consumed anywhere in the pipeline.

**Dependencies:** `openpyxl`/`xlrd` for spreadsheets  
**Limitations:**
- No table structure parsing (no column type detection, no row grouping)
- No Markdown table formatting
- No extraction of nested tables or merged cells
- `requires_table_extraction` flag is defined but never used by any processor

---

## 9. Chunking

**File:** `app/infrastructure/semantic_chunking.py`  
**Class:** `SemanticChunker`  
**Key method:** `chunk(text, source, source_type)` → `list[DocumentChunk]`

**Domain model:** `DocumentChunk` (`app/domain/semantic_chunking.py:9`) with `chunk_id`, `text`, `source`, `source_type`, `chunk_index`, `start_char`, `end_char`, `metadata`.

**How it works (three-tier splitting):**

1. **`_split_by_headings()`** (`semantic_chunking.py:70`): Splits on Markdown headings (`^#{1,6}\s+.+` regex). Each heading and its content becomes a section.
2. **`_split_long_section()`** (`semantic_chunking.py:85`): For sections exceeding `max_chunk_chars` (default 2000), splits by paragraph breaks (`\n\s*\n`).
3. **`_split_by_sentences()`** (`semantic_chunking.py:114`): For paragraphs still exceeding limit, splits by sentence boundaries (`(?<=[.!?])\s+(?=[A-Z\d])`).

**Config:** `max_chunk_chars: int = 2000`, `overlap_chars: int = 200`.  
Note: `overlap_chars` is declared but **never used** in the splitting logic.

**Chunk ID format:** `"{source}::chunk_{index}"`

**Dependencies:** None (pure Python regex)  
**Limitations:**
- `overlap_chars` field is dead code (declared, not used)
- No semantic boundary detection beyond regex
- No sliding window
- No language-aware sentence splitting (relies on simple regex)
- No metadata propagation between parent section and child chunks

---

## 10. Tokenization

**Not Implemented.**

There is no tokenization module, no token counting, no token-aware truncation, and no integration with any tokenizer (tiktoken, HuggingFace tokenizers, or Ollama's internal tokenizer). The codebase uses character length (`max_chunk_chars: int = 2000`) as the chunk size proxy, not token counts. The LLM prompt (`app/prompts/document_analysis.py`) sends the full source text without any token budget management.

---

## 11. Embeddings

**File:** `app/infrastructure/embeddings.py`  
**Class:** `EmbeddingService`  
**Key methods:** `embed(text)` → `EmbeddingResult`, `embed_batch(texts)` → `list[EmbeddingResult]`

**How it works:**
- Wraps `ollama.Client.embed()` which calls Ollama's `/api/embed` endpoint
- `embed()` sends a single text string
- `embed_batch()` sends a list of texts (Ollama-native batching)
- Response normalized via `model_dump()` or `dict()` fallback
- Returns `EmbeddingResult` with model name and `list[float]` embedding vector

**Default model:** `"nomic-embed-text"` (`embeddings.py:32`, also in `config.py:197`)

**Dependencies:** `ollama`, Ollama running with `nomic-embed-text` model  
**Limitations:**
- No embedding caching/memoization
- No dimension validation (assumes all embeddings same dimension)
- No retry logic (unlike `OllamaClient` which has retries)
- Batch size unbounded — large batch could timeout
- No async support

---

## 12. Vector Database

**File:** `app/infrastructure/vector_store.py`  
**Class:** `VectorStore`  

**How it works:** Pure in-memory `dict[str, VectorEntry]`. No third-party vector database (not ChromaDB, not FAISS, not Qdrant).

**Storage:**
- `self._entries: dict[str, VectorEntry]` — all vectors in a dict keyed by entry ID
- `add(entry)` / `add_batch(entries)` — inserts into dict
- `get(entry_id)` — dict lookup
- `remove(entry_id)` — dict deletion

**Search:**
- `search(query_embedding, top_k=5, min_score=0.0)` → `list[SearchResult]`
- Brute-force cosine similarity scan over **all entries** (`_cosine_similarity()` at `vector_store.py:15`)
- Results sorted by score descending, limited to `top_k`

**Persistence:**
- `save()` writes all entries as JSON array to `persistence_path` (`vector_store.py:70-91`)
- `_load()` reads JSON and reconstructs `VectorEntry` objects (`vector_store.py:93-111`)
- `persistence_path: Path | None` set at construction

**Domain model:** `VectorEntry` (`app/domain/vector_store.py:9`) with `id`, `text`, `embedding: list[float]`, `source`, `source_type`, `chunk_index`, `metadata`.

**Dependencies:** None (pure Python)  
**Limitations:**
- O(n) search — every query scans all entries
- No indexing (no IVF, HNSW, or any approximate nearest neighbor)
- Full save on every write — no incremental append
- No atomic write in `save()` (direct `write_text()`, may corrupt on partial write)
- Entire store loaded into memory on construction
- No filtering by source/type during search
- No versioning or migration for embedding dimension changes

---

## 13. Search

**File:** `app/infrastructure/search.py`

### SemanticSearch
**Class:** `SemanticSearch`  
**Key method:** `search(query_embedding, top_k=5, min_score=0.0)` → `list[SearchHit]`

Wraps `VectorStore.search()` and converts results to `SearchHit` objects with `text`, `source`, `score`, `entry_id`.

### HybridSearch
**Class:** `HybridSearch`  
**Key method:** `search(query, query_embedding, top_k=5, min_score=0.0)` → `list[SearchHit]`

Combines:
- Semantic score: cosine similarity (weight: 0.7)
- Keyword score: fraction of query words present in text (weight: 0.3)
- Formula: `0.7 * semantic_score + 0.3 * keyword_score`

Fetches `top_k * 2` candidates from vector store, then re-ranks with combined score.

**Dependencies:** `VectorStore`  
**Limitations:**
- No BM25 or TF-IDF for keyword scoring (simple word presence only)
- Keyword matching is case-insensitive substring, not token-aware
- No phrase matching or proximity scoring
- No search across multiple stores
- No result highlighting
- Neither search class is wired into any CLI command or API endpoint (they are library classes only)

---

## 14. Knowledge Graph

### Domain Model
**File:** `app/domain/knowledge_graph.py`

- `KnowledgeNode` (`knowledge_graph.py:15`): `id`, `label`, `node_type` (entity|concept|topic|note|definition), `source`, `metadata`
- `KnowledgeEdge` (`knowledge_graph.py:26`): `source_id`, `target_id`, `edge_type` (related_to|defined_in|mentioned_in|part_of|depends_on), `weight`, `metadata`
- `KnowledgeGraph` (`knowledge_graph.py:37`): In-memory dict of nodes + list of edges
  - `add_node(node)`, `add_edge(edge)` — edge only added if both endpoints exist
  - `neighbors(node_id)` → `list[(KnowledgeNode, KnowledgeEdge)]` — bidirectional traversal
  - `subgraph(node_id, depth=1)` — BFS limited traversal
  - `save(path)` / `load(path)` — JSON serialization

### Builder
**File:** `app/infrastructure/knowledge_graph.py`  
**Class:** `KnowledgeGraphBuilder`  
**Key method:** `build_from_analysis(analysis, source)` → `GraphBuildResult`

**How it works:**
Creates nodes and edges from `DocumentAnalysis`:
1. One `note` node from `suggested_note_title`
2. `concept` nodes from `key_concepts` with `mentioned_in` edges
3. `definition` nodes from `definitions` with `defined_in` edges
4. `entity` nodes from `important_entities` with `mentioned_in` edges
5. `topic` nodes from `related_topics` with `related_to` edges
6. Cross-edges between concepts and entities (weight 0.5)

**ID convention:** `"{node_type}::{label_lower_snake_case}"`

**`merge_graphs(*graphs)`** — union merge of multiple graphs.

**Dependencies:** None  
**Limitations:**
- Entirely in-memory — JSON persistence exists but is never called outside tests
- No graph query language (no Cypher, SPARQL, or Gremlin)
- No pathfinding, centrality, or any graph algorithms
- No incremental updates — full rebuild on each document
- `subgraph()` is O(n) BFS with list pop(0) (inefficient)

---

## 15. Prompt Generation

**File:** `app/prompts/document_analysis.py`

### System Prompt
**`DOCUMENT_ANALYSIS_SYSTEM_PROMPT`** (`document_analysis.py:7`): 138-line prompt instructing the LLM to:
- Extract durable knowledge from source material
- Return valid JSON matching the `DocumentAnalysis` schema
- Follow constraints (max items per field, format rules, no nulls, no duplicates)
- Short summary ≤ 80 words, detailed summary ≤ 300 words

### User Prompt Builder
**`build_document_analysis_user_prompt(document)`** (`document_analysis.py:145`):
- Wraps source text with source metadata header
- Passes full document text in the prompt (no truncation)

**Dependencies:** `SourceDocument` domain model  
**Limitations:**
- No token budget management — full source text sent regardless of length
- No few-shot examples
- No system prompt versioning
- Prompt is hardcoded, not configurable
- No multi-turn refinement (single generate call, no follow-up questions)

---

## 16. LLM Integration

### Text Generation
**File:** `app/infrastructure/llm/ollama_client.py`  
**Class:** `OllamaClient`  
**Key methods:**
- `generate_text(request)` → `OllamaTextResponse` (`ollama_client.py:133`)
- `generate_json(request, response_model)` → `OllamaJsonResponse | ResponseModelT` (`ollama_client.py:149`)

**How it works:**
- Wraps `ollama.Client.generate()` API
- Two output modes: raw text or structured JSON (with optional Pydantic validation)
- Retry logic: configurable `request_retries` (default 3), exponential backoff
- System prompt support via `request.system_prompt`
- Model override per request via `request.model`

**Error handling:**
- `OllamaConnectionError` — transport failures
- `OllamaTimeoutError` — request timeout
- `OllamaResponseError` — bad HTTP status, empty response, JSON parse failure, schema mismatch
- Server errors (500+) and timeouts are retried; 404 is not

**Availability checks:**
- `is_available()` → `client.ps()` (`ollama_client.py:100`)
- `model_exists(name)` → checks `client.list()` (`ollama_client.py:110`)

### Vision
**File:** `app/infrastructure/llm/vision_client.py`  
**Class:** `OllamaVisionClient`  
**Methods:** `describe_image(image_path)`, `describe_image_bytes(image_bytes)`

Sends base64-encoded images to Ollama vision model via `client.generate(model=..., images=[b64])`.

### Audio
**File:** `app/infrastructure/llm/whisper_transcriber.py`  
**Class:** `WhisperTranscriber` (inferred from `AudioProcessor` usage — specific implementation details not inspected)

**Dependencies:** `ollama`, local Ollama server  
**Limitations:**
- Single LLM provider (Ollama only — no OpenAI, Anthropic, or cloud support)
- No streaming responses
- No async/parallel generation
- Long documents may exceed context window (no truncation strategy)
- Vision model pull is not automated (user must `ollama pull qwen2.5vl:latest`)

---

## 17. Obsidian Integration

### Note Generation
**File:** `app/templates/obsidian_note.py`  
**Class:** `ObsidianMarkdownGenerator`  
**Key method:** `generate(document, analysis, ...)` → `ObsidianNote`

**How it works:**
Generates a complete Obsidian-compatible Markdown note with:
- **YAML frontmatter** (`_frontmatter()`): title, source, source_type, filename, generated_date, reading_time_minutes, difficulty, categories, keywords, tags, confidence scores
- **Sections** (conditional on data presence):
  - Summary (short + detailed), Reading Time, Difficulty Level
  - Table of Contents (`[[#section]]` links)
  - Keywords, Categories
  - Key Concepts (with `[[wiki links]]`), Definitions, Important Entities, Related Topics
  - Suggested Related Notes, Suggested Backlinks
  - FAQs, Flashcards, MCQs, Short/Long Answer Questions, Revision Notes
  - Tags, Metadata, References
- `_safe_filename()` strips `<>:"/\\|?*` and null bytes
- `_wiki_link()` → `[[label]]` format
- `_clean_tags()` → lowercase, hyphenated, no `#`

### Vault Writer
**File:** `app/infrastructure/vault/writer.py`  
**Class:** `VaultWriter`  
**Key method:** `write(note)` → `VaultWriteResult` (with `note_path`, `created`, `updated`)

Writes `.md` files to `vault_root / Notes / {safe_filename}.md`.

### Wiki Manager
**File:** `app/infrastructure/vault/wiki_manager.py`  
**Class:** `WikiManager` — vault structure management

### Domain Model
**File:** `app/domain/notes.py` — `ObsidianNote` with `title`, `filename`, `markdown`, `generated_at`, `tags`, `source`, `source_type`.

**Dependencies:** None (pure Python string generation)  
**Limitations:**
- No Obsidian API integration (file-based only)
- No conflict resolution if filename already exists
- No backlink index updating in vault
- No graph view refresh trigger
- YAML frontmatter does not escape all special characters for multi-line values

---

## 18. CLI

**File:** `app/cli/entry.py`  
**Framework:** `typer` (with `rich` for formatting)

### Commands

| Command | Function | Description |
|---|---|---|
| `ingest pdf <path>` | `ingest_pdf()` | Ingest a PDF file |
| `ingest markdown <path>` | `ingest_markdown()` | Ingest a Markdown file |
| `ingest txt <path>` | `ingest_txt()` | Ingest a plain text file |
| `ingest github <url>` | `ingest_github()` | Ingest a GitHub repo README |
| `ingest youtube <url>` | `ingest_youtube()` | Ingest a YouTube video transcript |
| `status` | `status()` | Show project, vault, and queue status (rich table) |
| `doctor` | `doctor()` | Check configuration, dependencies, folders, Ollama |
| `config` | `config()` | Show resolved configuration |
| `watch` | `watch()` | Start file watcher for inbox |

**`_run_ingest()`** builds `IngestionWorkflow` from runtime components (OllamaClient, VaultWriter, routing config, optional VisionClient) and runs the full pipeline.

**`doctor` command** checks:
- Configuration validity
- Required Python modules (`ollama`, `pydantic`, `pypdf`, `rich`, `typer`, `yaml`, `youtube_transcript_api`)
- Directory writability (project root, vault, inbox, processed, failed, manifest, log, cache)
- Queue state file integrity
- Ollama server availability and model presence

**`status` command** shows: watcher state, inbox readiness, queue/manifest counts, Ollama connection, vault status, generated notes count.

**Dependencies:** `typer`, `rich`  
**Limitations:**
- No tab completion support (`add_completion=False`)
- No `--help` text on subcommands (typer auto-generates minimal help)
- No JSON output mode (except `config --json`)
- No progress bars for long-running operations
- `_ensure_runtime_directories()` creates all directories upfront even if unused

---

## 19. Queue

**Files:** `app/queue/`

### State
**File:** `app/queue/state.py`  
**Class:** `QueueStateStore` — persists pending queue items to JSON for crash recovery.

### Stats
**File:** `app/queue/stats.py` — processing metrics tracking.

### Manager
**File:** `app/queue/manager.py`  
**Class:** `QueueManager` — enqueue/dequeue lifecycle.

### Worker
**File:** `app/queue/worker.py`  
**Class:** `QueueWorker` — single consumer loop.

**Config** (`config.py:140`): `workers: 1` (hard-coded max 1), `max_size: 1000`, `state_path` for persistence.

**How it works:**
- Single-worker queue (`workers: 1`, `max_size: 1000`)
- State persisted to JSON for crash recovery via `QueueStateStore`
- Ingest tasks are enqueued by the watcher or CLI and consumed sequentially

**Dependencies:** None  
**Limitations:**
- Single worker only (config enforces `ge=1, le=1`)
- No priority queue
- No retry mechanism within the queue itself
- Queue state is append-only JSON, no compaction
- No dead letter queue

---

## 20. Logging

**File:** `app/core/logging.py`  
**Setup function:** `setup_logging(settings)` — configures logging based on `LoggingSettings`

**Features:**
- Console logging (with optional color)
- File logging (rotating file handler, `max_bytes: 10MB`, `backup_count: 5`)
- Format options: `console` (human-readable) or `json` (structured)
- Level configuration: CRITICAL / ERROR / WARNING / INFO / DEBUG

**Usage pattern:** `logger = get_logger(__name__)` throughout the codebase. Structured extra data passed via `logger.info("msg", extra={...})`.

**Config** (`config.py:73`): `level: "INFO"`, `format: "console"`, `console_enabled: True`, `file_enabled: True`, `use_colors: True`, `filename: "application.log"`.

**Dependencies:** Python `logging` stdlib  
**Limitations:**
- No structured logging library (no structlog, no loguru)
- `extra` dict is not automatically indexed (raw Python logging)
- No remote log shipping
- No correlation ID for pipeline tracing
- No log sampling for high-volume events

---

## 21. Configuration

**File:** `app/core/config.py`  
**Function:** `load_settings()` → `Settings`  
**Model:** `Settings` (Pydantic `BaseSettings`)

**Loading order:**
1. `config/default.yaml` — base configuration
2. `config/{environment}.yaml` — environment override (default: `development`)
3. `PAM_*` environment variables — final override (nested via `__` delimiter)

**Key settings sections:**
- `app`: name, environment
- `paths`: project_root, vault_root, inbox_root, staging_root, manifest_root, cache_root, log_root
- `ollama`: host (default: `http://localhost:11434`), model (`qwen3:8b`), timeout, retries
- `logging`: level, format, console/file flags, rotation
- `watcher`: enabled, paths, recursive, interval (1s), supported extensions
- `queue`: enabled, workers (1), max_size (1000), state_path
- `manifest`: enabled, path
- `processing`: move_processed, move_failed
- `models`: model routing (general_text, programming, vision, OCR, audio, embeddings)

**Path resolution:** All relative paths resolved against project root (discovered by walking up from `config.py` looking for `pyproject.toml`).

**Error handling:** `ConfigurationError` raised for missing files, invalid YAML, validation failures.

**Dependencies:** `pydantic`, `pydantic_settings`, `yaml`, `pyyaml`  
**Limitations:**
- Environment variable values parsed via `yaml.safe_load()` (surprising behavior for string values)
- No config hot-reload
- No secrets management (API keys, tokens stored in plain config)
- No schema versioning for config migration

---

## 22. Error Handling

**Status:** Partially Implemented

Error handling exists at multiple levels but is not consistently applied:

| Layer | Mechanism | File |
|---|---|---|
| Ollama client | Typed exception hierarchy with retries | `ollama_client.py:23-37` |
| Ingestion | `IngestionError` → `UnsupportedSourceError` | `ingestion/base.py:13-19` |
| Configuration | `ConfigurationError` | `config.py:20` |
| Pipeline | `AIProcessingError` | `application.py` |
| Pipeline workflow | `IngestionWorkflowError` | `ingest_workflow.py` |
| CLI | `typer.Exit(1)` on failures | `entry.py` |
| Manifest | Corrupted file detection + quarantine | `manifest.py:52-56` |
| Vector store | Silent failure on corrupt JSON | `vector_store.py:110-111` |

**Pattern:** Most errors are caught, logged via `logger.exception()`, and wrapped in a domain-specific exception. CLI commands catch exceptions and exit with code 1.

**Limitations:**
- No centralized error handler or middleware
- Vector store silently ignores corrupt JSON (just logs warning)
- Ingestors have inconsistent error handling — some raise, some return empty text
- Queue has no dead letter handling for permanently failed items
- No health check endpoint for programmatic monitoring

---

## 23. Current Limitations

| Area | Limitation | Impact |
|---|---|---|
| Vector search | O(n) brute-force scan of all entries | Slow at scale (>10K vectors) |
| Chunking | `overlap_chars` is declared but never used | No chunk overlap |
| Tokenization | Not implemented | No token-aware truncation; full source text sent to LLM |
| Table extraction | No structure parsing, passthrough only | Tables are flat text in notes |
| OCR | Limited to first 5 pages, PyMuPDF optional | Scanned PDFs >5 pages truncated |
| Queue | Single worker only | No parallel processing |
| Watcher | Polling at 1s interval | No real-time file detection |
| Search | `SemanticSearch`/`HybridSearch` are library classes only | No CLI or API binding for search |
| Knowledge graph | In-memory only, JSON save never called in pipeline | Graph data lost on restart |
| LLM provider | Ollama only | No cloud fallback |
| No persistence | Vector store save() is called by pipeline but on every document | No incremental checkpointing |
| Image preprocessing | None | Poor OCR on noisy/dark images |
| Prompt engineering | Single hardcoded prompt | No configurable or versioned prompts |

---

## 24. Missing Features

| Feature | Status | Evidence |
|---|---|---|
| **Web UI** | **Not Implemented** | No frontend code, no HTTP server, no API routes |
| **REST API** | **Not Implemented** | No Flask/FastAPI/any web framework |
| **Authentication** | **Not Implemented** | No auth, no user accounts, no sessions |
| **Multi-user** | **Not Implemented** | No user model, single vault assumption |
| **ChromaDB / FAISS** | **Not Implemented** | Vector store is custom in-memory dict |
| **Tokenization** | **Not Implemented** | No token counting/truncation anywhere |
| **Caching layer** | **Not Implemented** | No Redis, no LRU, no memoization |
| **CI/CD** | **Not Implemented** | No GitHub Actions, no CI config |
| **Async processing** | **Not Implemented** | All pipeline steps are synchronous |
| **Database** | **Not Implemented** | No PostgreSQL, SQLite (except ingestors for .db files), or any app database |
| **Docker** | **Not Implemented** | No Dockerfile or docker-compose |
| **Search API/CLI** | **Not Implemented** | `SemanticSearch` exists as library class but has no command binding |
| **Graph visualization** | **Not Implemented** | No frontend for knowledge graph, no export to graphviz |
| **Batch processing** | **Not Implemented** | No batch mode for multiple files |
| **Progress reporting** | **Not Implemented** | No progress bars (rich Progress not used) |
| **Field extraction (tables)** | **Partially Implemented** | Cell content extracted, no structure preserved |
| **Handwriting OCR** | **Partially Implemented** | Heuristic detection only, ML model passthrough |
| **Cloud LLM support** | **Not Implemented** | Ollama-only, no OpenAI/Anthropic adapters |
| **Automated testing in CI** | **Not Implemented** | Tests exist locally but no CI runner |
