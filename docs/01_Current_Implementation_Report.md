# LLM Wiki – Current Implementation Report

> Generated from live codebase inspection. Every claim references a specific file, class, and method.

---

## 1. Project Overview

**Name:** Personal AI Memory System (PAM)  
**Purpose:** Local-first tool that ingests source documents (PDFs, web content, images, audio, emails, etc.), enriches them with extracted metadata (MIME type, language, document properties), analyzes them via a local LLM (Ollama), and generates structured Obsidian-compatible Markdown notes in a personal wiki vault.  
**Language:** Python 3.11+ (tested on 3.14)  
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
│   - analysis.py    │    ├── document_intelligence/    │
│   - documents.py   │    │   ├── metadata/             │
│   - notes.py       │    │   │   ├── extractors.py     │
│   - routing.py     │    │   │   ├── mime.py           │
│   - vector_store.py│    │   │   ├── language.py       │
│   - knowledge_graph│    │   │   ├── hooks.py          │
│   - semantic_chunk │    │   │   └── __init__.py       │
│   - document_intel │    │   ├── ocr/                  │
│                    │    │   ├── structure/            │
│                    │    │   └── imaging/              │
│                    │    ├── llm/ (Ollama, vision)     │
│                    │    ├── embeddings.py             │
│                    │    ├── vector_store.py           │
│                    │    ├── semantic_chunking.py      │
│                    │    ├── knowledge_graph.py        │
│                    │    ├── search.py                 │
│                    │    ├── routing/ (classify)       │
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
│   ├── document_intelligence.py # MetadataExtraction + DocumentStructure/Section/Block models
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
│   │   ├── service.py          # DocumentIngestionService (registry + dispatch + enrichment + hooks)
│   │   ├── utils.py            # clean_text(), file_timestamp()
│   │   ├── archive_ingestor.py
│   │   ├── audio_ingestor.py
│   │   ├── code_ingestor.py
│   │   ├── config_ingestor.py
│   │   ├── csv_ingestor.py
│   │   ├── database_ingestor.py
│   │   ├── diagram_ingestor.py
│   │   ├── docx_ingestor.py
│   │   ├── email_ingestor.py   # headers + body + attachment extraction
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
│   ├── document_intelligence/
│   │   ├── metadata/
│   │   │   ├── __init__.py     # MetadataExtractor, DocumentMetadataService, register_extractor
│   │   │   ├── extractors.py   # Pdf/Docx/Pptx/Notebook/Audio/Email extractors + DEFAULT_EXTRACTORS
│   │   │   ├── mime.py         # detect_mime (extension → magic → fallback table)
│   │   │   ├── language.py     # detect_language (py3langid + stdlib heuristic)
│   │   │   └── hooks.py        # IngestionHook protocol, HookRegistry, register_hook
│   │   ├── ocr/
│   │   │   ├── __init__.py       # get_default_ocr_service (engine="auto")
│   │   │   ├── base.py           # OcrEngine, DocumentOcrService, OCRSelectionError
│   │   │   ├── engines.py        # VisionOcrEngine, TesseractOcrEngine
│   │   │   ├── models.py         # OcrResult, PageOcrResult
│   │   │   └── pdf.py            # render_pdf_pages (PyMuPDF)
│   │   ├── structure/
│   │   │   └── detector.py       # StructureAnalyzer, _detect_headings, _detect_blocks, _build_tree
│   │   └── imaging/
│   │       └── preprocess.py     # deskew → denoise → CLAHE
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── ollama_client.py    # OllamaClient (text + JSON generation)
│   │   ├── vision_client.py    # OllamaVisionClient (image OCR)
│   │   └── whisper_transcriber.py  # Audio transcription
│   ├── routing/
│   │   ├── classifier.py       # DocumentClassifier (heuristic + MIME + language)
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
source → IngestService (size guard → pre-hooks → ingestor
         → metadata enrichment → post-hooks) → SourceDocument
       → Classify (kind + MIME + language) → DocumentClassification
       → Process → ProcessedDocument (language, parent_id, extra metadata)
       → Structure analyze (markdown/text, enabled) → extra["structure"]
       → Code/notebook enrich (code/notebook, enabled) → extra["code_structure"] / extra["notebook_structure"]
       → Chunk → list[DocumentChunk]
       → Analyze (LLM, respond-in-{language} for non-English) → DocumentAnalysis
       → Build Graph → KnowledgeGraph
       → Generate Note → ObsidianNote
       → Write to Vault → VaultWriteResult
       → Ingest email attachment children (recursive, capped)
```

**How it works** (`ingest_workflow.py`):
- `run()` ingests the source via `DocumentIngestionService` — which applies the size guard, pre-hooks, ingestor selection, metadata enrichment, and post-hooks (see §5 and §7)
- Classifies via `DocumentClassifier` into a kind (pdf, markdown, image, scanned_pdf, etc.), populating `mime_type` and `language` (see §7)
- Selects a processor from the `ProcessorRouter` based on kind
- Routes to the appropriate model (general_text, programming, vision, scanned_ocr, etc.)
- Processes into `ProcessedDocument` (carrying `language`; child documents carry `parent_id`)
- Runs structure analysis (Milestone 2.3) for `markdown`/`text` kinds when `intelligence.structure.enabled: true`, storing the serialized `DocumentStructure` under `metadata.extra["structure"]` on the enriched document — see §8
- Runs code/notebook enrichment (Milestone 2.6) for `code`/`notebook` kinds when `intelligence.code.enabled: true`, attaching `metadata.extra["code_structure"]` (parsed) / `metadata.extra["notebook_structure"]` (passthrough) — see §10b
- Chunks via `SemanticChunker`
- Analyzes via `OllamaClient.generate_json()` with `DocumentAnalysis` response model; the user prompt receives the detected language and appends "Respond in {language}." for non-English documents
- Builds knowledge graph via `KnowledgeGraphBuilder`
- Generates Obsidian note via `ObsidianMarkdownGenerator`
- Writes to vault via `VaultWriter`
- Returns `IngestionResult` with document, note, write result, AI result, graph result
- When the source is an email with attachments, `_ingest_children()` re-ingests each extracted attachment as a child document (parent/child relationship) — see §7

**Dependencies:** All infrastructure modules, Ollama runtime  
**Limitations:** Sequential processing; no parallelization per document; LLM analysis is the bottleneck (single Ollama call per document); email attachment children are ingested after the parent's note is written (not before)

---

## 5. Ingestion

**File:** `app/infrastructure/ingestion/service.py`  
**Class:** `DocumentIngestionService`  
**Key method:** `ingest(source: str | Path)` → `DocumentIngestionResult`

**How it works:** Maintains a list of 21 `BaseIngestor` instances plus a `DocumentMetadataService` seeded with `DEFAULT_EXTRACTORS`. On `ingest()`, normalizes the source (URL or Path) and dispatches to `_ingest_source()`, which runs, in order: the file-size guard (`_enforce_size_limit`), the pre-hook chain (`_run_pre_hooks`), ingestor selection (`_select_ingestor`), the ingestor itself, metadata enrichment (`_enrich_document`), and the post-hook chain (`_run_post_hooks`). Returns a `DocumentIngestionResult` with either a `SourceDocument` or a `DocumentIngestionError`.

The service accepts `settings: Settings | None` at construction; when supplied, `intelligence.metadata.*` settings (`enabled`, `max_file_size_mb`, `email_attachments`, `max_attachments`, `hooks.pre`, `hooks.post`) are honored. Production wiring passes runtime settings through `IngestionWorkflow.create_default()`.

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
| `notebook_ingestor.py` | `NotebookIngestor` | `.ipynb` | JSON parse, extract code+markdown cells; attaches `metadata.extra["notebook_structure"]` (M2.6, gated by config at enrichment time) |
| `email_ingestor.py` | `EmailIngestor` | `.eml` | `email` stdlib; extracts headers, body, and `Content-Disposition: attachment` parts to temp child sources |
| `epub_ingestor.py` | `EpubIngestor` | `.epub` | `ebooklib` |
| `archive_ingestor.py` | `ArchiveIngestor` | `.zip/.tar.gz/.tar/.tgz` | `zipfile`/`tarfile` |
| `database_ingestor.py` | `DatabaseIngestor` | `.db/.sqlite/.sqlite3` | `sqlite3` |
| `diagram_ingestor.py` | `DiagramIngestor` | `.drawio/.vsdx/.puml` | XML parse |
| `research_ingestor.py` | `ResearchIngestor` | `.bib/.ris/.enw` | Parses citation format |
| `github_readme_ingestor.py` | `GitHubReadmeIngestor` | GitHub repo URLs | HTTP fetch of README |
| `youtube_transcript_ingestor.py` | `YouTubeTranscriptIngestor` | YouTube URLs | `youtube_transcript_api` |

**Canonical output:** `SourceDocument` (`app/domain/documents.py`) with `source`, `source_path`, `source_type`, `filename`, `text`, `metadata`. Email documents additionally expose `metadata.extra.attachments` (filenames) and `metadata.extra.attachment_paths` (temp paths).

**Text normalization:** `clean_text()` in `utils.py` normalizes whitespace, normalizes headings/lists/tables/blockquotes, protects code blocks via token substitution.

**Dependencies:** `pypdf`, `python-docx`, `python-pptx`, `openpyxl`/`xlrd`, `ebooklib`, `youtube_transcript_api`, `ollama` (for all)

**Limitations:**
- No incremental/chunked reading for large files (entire file in memory)
- Image/video/audio ingestors return text placeholder, actual extraction delegated to later processing (VisionProcessor/WhisperTranscriber)
- `GitHubReadmeIngestor` only fetches README, not full repo
- No rate limiting for URL-based ingestors
- Email attachment extraction is limited to `.eml`; nested email attachments are extracted but not re-ingested (depth guard)
- Size limit applies to the file path only (not to already-downloaded remote bodies)

---

## 6. OCR

**Status:** Implemented (Milestone 2.1)

**Files involved:**
- `app/infrastructure/document_intelligence/ocr/` — `base.py` (`OcrEngine` protocol, `DocumentOcrService` registry, `OCRSelectionError`), `engines.py` (`VisionOcrEngine`, `TesseractOcrEngine`), `models.py` (`OcrResult`, `PageOcrResult`), `pdf.py` (`render_pdf_pages`), `__init__.py` (`get_default_ocr_service`)
- `app/infrastructure/document_intelligence/imaging/preprocess.py` — shared preprocessing (deskew → denoise → CLAHE)
- `app/infrastructure/routing/processor_impls.py` — `VisionProcessor`, `OCRProcessor`, `HandwritingProcessor` (thin adapters over `DocumentOcrService`)
- `app/infrastructure/routing/classifier.py` — `DocumentClassifier` sets `requires_ocr: True` for `scanned_pdf`, `handwritten`, `image`
- `app/pipelines/ingest_workflow.py` — `IngestionWorkflow` constructs/injects the OCR service; vision-required no-fallback guard
- `app/cli/entry.py` — `pam doctor` OCR diagnostics

**How it works:**
1. `DocumentClassifier.classify()` detects scanned PDFs and images (`classifier.py`)
2. `ProcessorRouter` routes `scanned_pdf` → `OCRProcessor`, `handwritten` → `HandwritingProcessor`, `image` → `VisionProcessor`
3. The routed processor delegates to `DocumentOcrService.extract()`:
   - `OCRProcessor` → OCR prompt, `HandwritingProcessor` → handwriting prompt, `VisionProcessor` → vision prompt
4. `DocumentOcrService.select()` picks the first registered engine whose `supported_kinds` includes the document kind (`engine="auto"` → vision primary, Tesseract fallback; explicit `engine=` selects directly)
5. The selected engine runs: `VisionOcrEngine` renders PDF pages via `render_pdf_pages` (zoom 2× default, configurable `page_limit` 0 = all, `max_pages` cap) and calls `OllamaVisionClient.describe_image()` per page with a bounded retry and early stop on empty page; `TesseractOcrEngine` calls pytesseract per page and maps `image_to_data` confidence
6. `OcrResult.from_pages()` aggregates mean confidence and flags empty/low-confidence pages; results attach to `ProcessedDocument.ocr` and surface in note frontmatter (`ocr_confidence`) and the reference line (`- OCR Confidence`)

**Configuration (`config/default.yaml` → `intelligence.ocr.*`):**
- `enabled: true` — `false` returns an empty registry and processors passthrough (Phase-1 behavior; no legacy branch retained)
- `engine: "auto"` — vision primary, Tesseract fallback; or explicit `"vision"` / `"tesseract"`
- `page_limit: 5` (0 = all pages), `zoom: 2.0`, `max_pages: 200`, `preprocess: false`
- `tesseract_cmd`, `tesseract_lang`, `confidence_threshold`
- Prompts via `intelligence.prompts.{ocr,handwriting,vision}` with a `{language}` slot

**Dependencies:** `ollama` (required), `PyMuPDF` (required for scanned-PDF OCR — clear `ImportError` if absent), `pytesseract` + Tesseract binary + `Pillow` (optional, offline/fallback and preprocessing)

**Limitations:**
- No layout preservation (tables, columns lost)
- No ML-based handwriting recognition (routed by classifier source type, not ML detection)
- Tesseract binary must be installed separately for the offline fallback; `pam doctor` reports availability

---

## 7. Metadata Extraction Framework

**Status:** Implemented (Milestone 2.2)

**Files involved:**
- `app/infrastructure/document_intelligence/metadata/__init__.py` — `MetadataExtractor` protocol, `DocumentMetadataService` registry, `get_default_metadata_service()`, `register_extractor()`
- `app/infrastructure/document_intelligence/metadata/extractors.py` — `PdfExtractor`, `DocxExtractor`, `PptxExtractor`, `NotebookExtractor`, `AudioExtractor`, `EmailExtractor`, `DEFAULT_EXTRACTORS`
- `app/infrastructure/document_intelligence/metadata/mime.py` — `detect_mime(path)`
- `app/infrastructure/document_intelligence/metadata/language.py` — `LanguageDetector` protocol, `detect_language(text)`, `get_default_language_detector()`, `register_language_detector()`
- `app/infrastructure/document_intelligence/metadata/hooks.py` — `IngestionHook` protocol, `HookRegistry`, `get_default_hook_registry()`, `register_hook()`
- `app/domain/document_intelligence.py` — `MetadataExtraction` model
- `app/infrastructure/ingestion/service.py` — enrichment + hook chain + size guard wiring
- `app/infrastructure/ingestion/email_ingestor.py` — attachment extraction
- `app/infrastructure/routing/classifier.py` — MIME/language population
- `app/pipelines/ingest_workflow.py` — child (attachment) re-ingestion
- `app/prompts/document_analysis.py` — language-aware user prompt

### 7.1 Extractor Protocol and Registry

- **`MetadataExtractor`** (`__init__.py`) — protocol with `source_types: tuple[str, ...]` and `extract(document) -> dict[str, Any]`.
- **`DocumentMetadataService`** — holds registered extractors; `extractors_for(source_type)` filters by declared source type; `extract(document)` runs every matching extractor in registration order and merges values (later extractors override earlier keys); a source type with no matching extractor yields an empty `MetadataExtraction` and never raises.
- **`DocumentMetadataService.merge(metadata, extraction)`** — additive merge: known `DocumentMetadata` fields (`title`, `author`, `created_at`, `modified_at`, `page_count`, `mime_type`, `encoding`) are written directly; unknown keys are routed into `metadata.extra`.
- **`get_default_metadata_service()`** — lazy process-wide singleton; **`register_extractor()`** is the public registration alias.

### 7.2 Built-in Extractors

| Extractor | Source types | Extracts |
|---|---|---|
| `PdfExtractor` | `pdf` | pypdf metadata (`/Title`, `/Author`, `/CreationDate`, `/Producer`, `/Subject`), page count, `application/pdf`; logic moved out of `PdfIngestor` |
| `DocxExtractor` | `docx` | `docProps/core.xml` + `app.xml` via stdlib `zipfile` + `ElementTree`: title, author, created/modified dates, `last_modified_by`, page count |
| `PptxExtractor` | `pptx` | Same OOXML core/app properties; slide count |
| `NotebookExtractor` | `notebook` | Top-level notebook JSON: `cell_count`, kernel display name, kernel language |
| `AudioExtractor` | `audio` | Deterministic file-level fields: title (stem), modified_at, MIME from extension map |
| `EmailExtractor` | `email` | Header fields: subject, from, to, date (as both known and `extra` keys) |

All are stdlib-only except `PdfExtractor` (reuses pypdf). Image EXIF/metadata is owned by the Milestone 2.5 image-intelligence path (single owner, R-3): `ImageIngestor` attaches `metadata.extra["image_info"]` via `images/metadata.py` (`ImageAnalyzer`) when `intelligence.images.exif_enabled`, and `_enrich_images` attaches per-embedded-image `ImageInfo` dumps under `metadata.extra["images"]` for `kind == "pdf"`. `DEFAULT_EXTRACTORS` registers all six; `DocumentIngestionService` seeds its `DocumentMetadataService` with them.

### 7.3 MIME Detection

**`detect_mime(path)`** (`mime.py`) resolves a MIME type with three-tier precedence (ADR-001):

```
Extension (mimetypes.guess_type + .ipynb supplement)
    ↓  (extensionless or unknown extension only)
Magic-byte sniff: python-magic from_buffer (if importable)
    ↓  (absent, or libmagic returns generic text/plain or octet-stream)
Stdlib fallback table (_sniff_mime)
```

- Known extensions resolve without reading the file (extension wins, ADR-001).
- Extensionless/unknown-extension files are sniffed from the first 512 bytes: optional `python-magic` (lazy import, warn-once when absent — a missing libmagic never crashes) then the stdlib `_sniff_mime` table covering `%PDF-`, PK zip, PNG/JPEG/GIF/WebP, WAVE/Ogg/MP3, XML, HTML, JSON, a Markdown heuristic (leading `# ` / `---`), and a printable-ratio plain-text check; else `application/octet-stream`.
- libmagic's generic `text/plain` verdict never overrides the stdlib Markdown heuristic (libmagic does not identify Markdown).
- Consumed by `DocumentClassifier._detect_mime` when `mime_enabled: true` and a `source_path` exists; the result is stored on `DocumentClassification.mime_type`.

### 7.4 Language Detection

**`detect_language(text) -> (lang, confidence)`** (`language.py`):
- Inspects only the first 10 KB of text (performance ceiling).
- Default detector `_Py3LangIdDetector`: `py3langid` (`langid.classify`, confidence exponentiated) when importable; otherwise the pure-stdlib `_language_heuristic` (Japanese kana check + stopword scoring for en/fr/de/ja).
- Confidence below `0.5` returns `("en", 0.0)` with a warning (R7 mitigation).
- `LanguageDetector` protocol; `get_default_language_detector()` lazy singleton; `register_language_detector()` replaces the default.
- Consumed by `DocumentClassifier._detect_language` when `language_detection_enabled: true`; stored on `DocumentClassification.language`, propagated to `ProcessedDocument.language`, and passed to the analysis prompt (see §7.6).

### 7.5 Enrichment Pipeline and Hook System

Inside `DocumentIngestionService._ingest_source`, the flow is:

```
_enforce_size_limit (max_file_size_mb, reject before read)
    → _run_pre_hooks (metadata.hooks.pre)
    → _select_ingestor → ingestor.ingest(source)
    → _enrich_document (metadata service extract + merge)
    → _run_post_hooks (metadata.hooks.post)
```

- **`_enrich_document`** — when `intelligence.metadata.enabled: true` and `extractors == "default"`, runs `metadata_service.extract(document)` and `DocumentMetadataService.merge`. With `enabled: false` the document is returned unchanged — Phase-1-identical output (rollback contract R-4). Any extraction failure leaves the document unchanged (debug-logged), never raising.
- **`IngestionHook`** — protocol with `name`, `pre(source) -> SourceReference`, `post(document) -> SourceDocument`. Hooks are resolved by name from `intelligence.metadata.hooks.pre` / `hooks.post`; lookup checks instance hooks then the default `HookRegistry`. Unregistered names log a warning and are skipped. `IngestionError` raised by a pre-hook aborts ingestion; any other hook exception is logged and skipped (a failing hook never breaks ingestion). `register_hook()` is the public registration alias.
- The size guard (`max_file_size_mb`, default 50 MB) rejects a file-path source before any read. `url_timeout_seconds` is defined in `MetadataSettings` but not yet consumed by any ingestor — `GitHubReadmeIngestor` still uses its hardcoded 30s timeout.

### 7.6 Prompt Language Integration

`build_document_analysis_user_prompt(document, language="en")` (`app/prompts/document_analysis.py`) appends `\n\nRespond in {language}.` when `language != "en"`; the English path is byte-identical to Phase 1. `DocumentAIProcessor` receives the detected language from `classification.language`.

### 7.7 Email Attachment Ingestion and Parent/Child Documents

- **`EmailIngestor`** (`.eml`, stdlib `email`): extracts the text/plain body (or stripped text/html when no plain part) plus a header block (From/To/Date/Subject). When `metadata.enabled` and `metadata.email_attachments` are both true, `_extract_attachments()` walks `msg.iter_attachments()` and writes every `Content-Disposition: attachment` part to a per-run temp directory (`pam_email_attachments_*`). Filenames are sanitized (`_safe_attachment_name` takes `Path(filename).name`, blocking path traversal) and deduplicated (`_unique_name`). Results are exposed as `metadata.extra.attachments` (names) and `metadata.extra.attachment_paths` (temp paths). An empty temp directory is removed immediately.
- **`IngestionWorkflow._ingest_children`** (P2-208): after the parent note is written, each `attachment_paths` entry is re-ingested through the same `DocumentIngestionService` (reusing the `max_file_size_mb` guard), capped at `metadata.max_attachments`. Each child's `metadata.extra.parent_id` is set to the parent source path. Recursion is depth-limited to one level — a nested email's own attachments are extracted but not re-ingested (no infinite recursion). Temp files are cleaned in a `finally` block regardless of child outcome.
- `ProcessedDocument` gained additive fields `language` and `parent_id`; document metadata extracted by the framework is merged into the document's metadata `extra`.

### 7.8 Configuration

`intelligence.metadata.*` block in `config/default.yaml`, bound to `MetadataSettings` in `app/core/config.py`:

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Master toggle; `false` → Phase-1-identical ingestion (R-4) |
| `extractors` | `"default"` | Extractor set (only `"default"` supported) |
| `mime_enabled` | `true` | Populate `DocumentClassification.mime_type` via `detect_mime` |
| `language_detection_enabled` | `true` | Populate `DocumentClassification.language` via `detect_language` |
| `max_file_size_mb` | `50` | Reject-before-read size limit (FR-ING-7) |
| `url_timeout_seconds` | `30` | Defined (FR-ING-6); not yet consumed — `GitHubReadmeIngestor` uses a hardcoded 30s timeout |
| `email_attachments` | `true` | Extract email attachments to temp child sources |
| `max_attachments` | `20` | Per-email attachment cap |
| `hooks.pre` | `[]` | Named pre-hooks |
| `hooks.post` | `[]` | Named post-hooks |

### 7.9 Limitations

- Extractors are stdlib-only; PDF uses pypdf; image EXIF/metadata is read once by the Milestone 2.5 `images/metadata.py` single owner (R-3) and consumed via `metadata.extra` channels, not by these extractors.
- Language heuristic supports en/fr/de/ja only (py3langid adds breadth when installed).
- `parent_id` is recorded on child documents but not yet consumed downstream (e.g., no parent/child linking in notes).
- Email attachment children are ingested after the parent note; a failed child is skipped with a warning.

---

## 8. Document Structure Analysis

**Status:** Implemented (Milestone 2.3)

**Files involved:**
- `app/infrastructure/document_intelligence/structure/detector.py` — `StructureAnalyzer` (`analyze`), `_detect_headings`, `_detect_blocks`, `_build_tree`, `get_default_structure_analyzer`
- `app/domain/document_intelligence.py` — `DocumentStructure`, `DocumentSection`, `DocumentBlock`, `BlockType` (additive, alongside `MetadataExtraction`)
- `app/infrastructure/document_intelligence/__init__.py` — composition root exposing `get_default_document_graph_builder`, `get_default_entity_extractor`, `get_default_relationship_detector`, `get_default_structure_analyzer`, and `graph_to_dict`
- `app/pipelines/ingest_workflow.py` — enrichment call site (`_run_routed_processor` → `_enrich_structure`)
- `app/core/config.py` + `config/default.yaml` — `StructureSettings` (`intelligence.structure.*`)

### 8.1 Domain Models

`DocumentStructure` holds `sections: list[DocumentSection]`. Each `DocumentSection` carries `id`, `title`, `level` (1–6, from ATX heading depth), `parent_id: str | None`, `start_char`, `end_char`, and `blocks: list[DocumentBlock]`. Each `DocumentBlock` carries `block_id`, `type` (`paragraph` | `list` | `code` | `blockquote` | `table`), `text`, `start_char`, `end_char`. Pydantic validators enforce `end_char >= start_char` and, for blocks, `len(text) == end_char - start_char` — offsets are exact slices of the analyzed text. Section IDs are stable path-style IDs by traversal order (`s-1`, `s-2`, `s-1-1`, …); block IDs are `b-<section_id>-<n>`.

### 8.2 Heading Hierarchy Detector (P2-302)

`_detect_headings(lines)` scans the exact text line-by-line and recognizes ATX headings with the rule `^#{1,6}\s+\S` (level marks must be followed by a space and non-blank content). A document-global triple-backtick fence toggle suppresses heading detection inside fenced code blocks — a `#` inside a code fence is never a heading. Each heading attaches to the nearest preceding heading with a strictly lower level (a level-skip such as `# A` → `### C` makes `C.parent_id = A.id`). Levels > 6 normalize to 6 (`MAX_HEADING_LEVEL`).

### 8.3 Block Detector (P2-303)

`_detect_blocks(text, ranges)` classifies each line into five block types with exact char offsets into the analyzed text:

- **paragraph** — contiguous non-blank, non-special lines; split on blank lines
- **list** — lines matching `[-*+]` / `\d+[.)]` markers, with best-effort continuation
- **code** — triple-backtick fenced blocks (document-global fence state; one block per fence)
- **blockquote** — lines starting with `>`
- **table** — pipe-led runs whose separator line matches `\|?[\s:-]+(\|[\s:-]+)+\|?`

Blocks are emitted in document order and attributed to the section whose body range contains the block start via a single advancing pointer; bisect membership on sorted range starts keeps the whole scan O(n).

### 8.4 Structure Tree Builder + Analyzer (P2-304 / P2-306)

`StructureAnalyzer.analyze(text, source)` runs `_detect_headings` then a single all-ranges `_detect_blocks` call (blocks are attributed to the section whose body range contains their start) and assembles a nested `DocumentStructure`. Degenerate input (empty/whitespace-only text, no headings) yields an empty structure — never an exception. Caps (code constants, `ponytail:` fixed defaults): `max_structure_text_bytes = 5_000_000` (analysis skipped with a single warning above this), `MAX_SECTIONS = 10_000` (warn + truncate in tree order). The scan is a single O(n) linear pass within the ≤ 1 s per 1 MB ceiling (asserted in the unit suite).

### 8.5 Enrichment Wiring (P2-305)

`_run_routed_processor` (in `ingest_workflow.py`) calls `_enrich_structure(text, source, source_type)` after the routed processor succeeds and before chunking. The result is stored on the enriched `SourceDocument`: `enriched.metadata.extra["structure"] = structure.model_dump(mode="json")` — the same `metadata.extra` channel `parent_id` already rides on (`ProcessedDocument` is **not** modified; R-1 deviation). The key is written only when all of these hold:

- `intelligence.structure.enabled: true` (plumbed through `Settings → create_default → _run_routed_processor`),
- `source_type in TEXT_BEARING_KINDS` (`{"markdown", "text"}`),
- text ≤ 5 MB (oversize → logged skip),
- the analyzer returns (a raised analyzer is logged and skipped — ingestion continues; L4).

`enabled: false` or any non-text-bearing kind ⇒ no `"structure"` key ⇒ M2.2-identical documents (R-4 rollback contract). The call site is the shared enrichment point Milestones 2.4/2.5/2.6 reuse (R-2).

### 8.6 Configuration

`intelligence.structure.*` in `config/default.yaml`, bound to `StructureSettings` in `app/core/config.py`:

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | `false` ⇒ no `"structure"` key; M2.2-identical documents (R-4) |
| `enrich_analysis_input` | `false` | Contract-only this milestone (addendum 3 / R-7); declared for the future structure-aware-prompting contract, read by no code |

### 8.7 Limitations

- Regex-based, best-effort parsing: `#` inside HTML/attributes, deeply nested markup, and exotic list nesting are not fully handled (only fenced-code disambiguation is guaranteed).
- `TEXT_BEARING_KINDS` is pinned to `markdown`/`text`; PDF/OCR-prose kinds are excluded this milestone (upgrade path: extend the set when a consumer exists).
- The structure is consumed for chunking context: M3.2 (P3-201) resolved hierarchy natively in the chunker (heading path/parent/level metadata per chunk) over the earlier `metadata.extra["structure"]` → `DocumentSection.id` → `parent_id` seam; no note-template/TOC rendering from structure.
- `enrich_analysis_input` is declared but not consumed (contract-only field, R-7).

---

## 9. Images

**File:** `app/infrastructure/llm/vision_client.py`  
**Class:** `OllamaVisionClient`  
**Key method:** `describe_image(image_path, prompt)` → `str`

**File:** `app/infrastructure/routing/processor_impls.py`  
**Class:** `VisionProcessor`  
**Key method:** `process(document)` → `ProcessedDocument`

**How it works:**
- `ImageIngestor` reads image bytes but extracts no text (returns `SourceDocument` with placeholder text)
- `DocumentClassifier` classifies as `image` kind, sets `requires_vision: True`
- `VisionProcessor.process()` delegates to `DocumentOcrService.extract()` with the configurable vision prompt (`intelligence.prompts.vision`, default: "Analyze this image...")
- The vision engine sends the image to `OllamaVisionClient.describe_image()` via Ollama's `generate()` with `images=[b64]`
- Optional preprocessing (deskew → denoise → CLAHE) applies when `intelligence.images.preprocess: true` (image path) or `intelligence.ocr.preprocess: true` (OCR/handwriting path); both disabled by default (`preprocess: false`)
- Output confidence: 0.85 with vision engine, 0.70 passthrough without

**Dependencies:** `ollama`, vision model (`qwen2.5vl:latest`)  
**Limitations:**
- No multi-page image support (PDF with images goes through OCR path)
- Preprocessing is disabled by default (`preprocess: false`)
- Vision model is a local Ollama requirement, not bundled

---

## 10. Tables

**Status:** Implemented (Milestone 2.4)

**Files:**
- `app/infrastructure/document_intelligence/tables/extractor.py` — `TableExtractor` protocol, `TableExtractorRegistry`, `CsvTableExtractor`, `SpreadsheetTableExtractor`, `PdfTableExtractor`, `get_table_extractor` / `get_default_table_extractor` / `extract_tables`
- `app/infrastructure/document_intelligence/tables/render.py` — `MarkdownTableRenderer` / `render_tables_to_markdown`
- `app/domain/document_intelligence.py` — `Table` / `TableCell` / `TableRow` / `TableHeader` models
- `app/pipelines/ingest_workflow.py` — `_enrich_tables` beside `_enrich_structure` in `_run_routed_processor`
- `app/templates/obsidian_note.py` — `## Tables` note-body section

**How it works:** Table extraction is an enrichment stage, not a processor. After the routed processor succeeds, `_run_routed_processor` calls `_enrich_tables(document, kind)` for classifier kinds `csv`/`spreadsheet`/`database`/`pdf` when `intelligence.tables.enabled: true`, and writes `document.metadata.extra["tables"] = [table.model_dump(mode="json")]` (best-effort — failures are logged and the key is absent). `ObsidianMarkdownGenerator` renders a `## Tables` section in the note body from that key; no key ⇒ Phase-1-identical output.

- **CSV/TSV** — `csv.Sniffer` dialect sniff (fallback `csv.excel`), header sniffing, row/column caps.
- **Spreadsheet** — per-sheet tables via openpyxl loaded non-read-only (`data_only=True`) so `merged_cells.ranges` is available; merged rectangles flattened by propagating the top-left value.
- **PDF** — pdfplumber default engine (ADR-002), camelot optional plugin with fallback; missing engine ⇒ logged warning + flat fallback.

**Config:** `intelligence.tables.*` (`enabled`, `pdf_engine`, `max_rows`, `max_cols`, `header_sniffing`). The frozen §2.4 `min_confidence` key was removed — pdfplumber exposes no per-table confidence to gate on (review R1; deviation recorded in the M2.4 remediation report).

**Dependencies:** `openpyxl` (core), `pdfplumber` (optional `intelligence` extra)  
**Limitations:**
- `database` kind sets the enrichment flag but has no extractor this milestone — registry miss ⇒ no tables, flat text preserved.
- `TableProcessor` remains a passthrough for flat-text extraction; structured tables attach only at the enrichment stage (spreadsheet ingestor unchanged).
- PDF extraction is engine-gated: without pdfplumber installed, PDFs degrade to flat fallback with a logged warning.

---

## 10b. Code & Notebook Intelligence

**Status:** Implemented (Milestone 2.6)

**Files:**
- `app/domain/document_intelligence.py` — `CodeStructure`, `CodeImport`, `CodeFunction`, `CodeClass`, `NotebookCell`, `NotebookStructure` models
- `app/infrastructure/document_intelligence/code/languages.py` — `language_from_filename`
- `app/infrastructure/document_intelligence/code/parser.py` — `_AstCodeParser`, `_HeuristicCodeParser`, `parse_code`
- `app/infrastructure/document_intelligence/code/notebook.py` — `NotebookParser` / `parse_notebook`
- `app/infrastructure/ingestion/notebook_ingestor.py` — attaches `metadata.extra["notebook_structure"]`
- `app/pipelines/ingest_workflow.py` — `_enrich_code` beside `_enrich_structure`/`_enrich_tables`/`_enrich_images` in `_run_routed_processor`
- `app/core/config.py` + `config/default.yaml` — `CodeSettings` (`intelligence.code.*`)

**How it works:** Code/notebook structure is an enrichment stage, not a processor. `_run_routed_processor` calls `_enrich_code(document, kind)` after the routed processor succeeds (at the shared P2-305 enrichment point reused by Milestones 2.3/2.4/2.5), gated by `intelligence.code.enabled` **and** `kind in {"code", "notebook"}`:

- **`kind == "code"`** — `parse_code(document.text, document.filename)` (Python → `_AstCodeParser`; all other `CODE_EXTENSIONS` and syntax-invalid Python → `_HeuristicCodeParser`) → `document.metadata.extra["code_structure"] = structure.model_dump(mode="json")`.
- **`kind == "notebook"`** — `NotebookIngestor` already attached `metadata.extra["notebook_structure"]` during ingestion; `_enrich_code` passes it through untouched.

`CodeProcessor` / `NotebookProcessor` remain passthrough (M2.4 TableProcessor pattern). Parser failures are logged and the key is absent — ingestion continues (L4). `CodeSettings.max_code_chars` / `max_cell_outputs` are threaded from config through `DocumentIngestionService` into `parse_code` / `NotebookIngestor` → `parse_notebook`; oversized source is truncated at parse time with a logged warning; beyond-cap notebook outputs become `"[truncated]"`.

**Rollback contract (R-4):** `intelligence.code.enabled: false` ⇒ no `"code_structure"` / `"notebook_structure"` keys (notebook structure is popped from `extra` in the disabled path) ⇒ Phase-1-identical documents.

### 10b.1 Configuration

`intelligence.code.*` in `config/default.yaml`, bound to `CodeSettings` in `app/core/config.py`:

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | `false` ⇒ no `code_structure`/`notebook_structure` keys; Phase-1-identical (R-4) |
| `languages` | `"default"` | Contract-only (C-5); built-in `code/languages.py` suffix→language map over the `CODE_EXTENSIONS` suffix set; other values deferred |
| `max_cell_outputs` | `10` | Notebook cell outputs capped during `NotebookParser.parse()`; beyond-cap → `"[truncated]"` |
| `max_code_chars` | `100000` | Python `str`-length cap; oversized code truncated with logged warning |
| `include_docstrings` | `true` | Contract-only (C-5); read by no code this milestone |

### 10b.2 Limitations

- Heuristic parser char offsets are approximated from line starts (line numbers exact); Python AST offsets are exact.
- `languages` / `include_docstrings` are declared but not consumed (contract-only fields, C-5).
- Structures are an input contract only — no consumer yet. Phase 3 hierarchical chunking reads `metadata.extra["structure"]`; code/notebook structure consumption is future work.

---

## 11. Chunking

**File:** `app/infrastructure/semantic_chunking.py`  
**Sentence tokenizer:** `app/infrastructure/sentence_tokenizer.py` (M3.1, G12)  
**Class:** `SemanticChunker`  
**Key method:** `chunk(text, source, source_type)` → `list[DocumentChunk]`

**Domain model:** `DocumentChunk` (`app/domain/semantic_chunking.py`) with `chunk_id`, `text`, `source`, `source_type`, `chunk_index`, `start_char`, `end_char`, `metadata`.

**How it works (three-tier splitting):**

1. **`_split_by_headings()`** (`semantic_chunking.py`): Splits on Markdown headings (`^#{1,6}\s+.+` regex). Each heading and its content becomes a section.
2. **`_split_long_section()`** (`semantic_chunking.py`): For sections exceeding `max_chunk_chars` (default 2000), splits by paragraph breaks (`\n\s*\n`).
3. **`_split_by_sentences()`** (`semantic_chunking.py`): For paragraphs still exceeding limit, delegates to the sentence-tokenizer engine (P3-104) — the old `_SENTENCE_END` regex is removed.

**Sentence tokenizer (M3.1):** `SemanticChunker.sentence_tokenizer: str = "auto"` selects the engine — resolved **once per chunker instance** (D8) through `get_sentence_tokenizer()` (`sentence_tokenizer.py`):

- `"auto"` (default) — NLTK `PunktTokenizer("english")` (`punkt_tab`) when the optional `intelligence` extra is installed; otherwise the stdlib heuristic with one logged warning (C-3 DoD).
- `"heuristic"` — stdlib abbreviation-aware engine: abbreviations (Dr., Mr., U.S.A., a.m., etc.), ellipses, decimal numbers, quoted sentences, `!?` terminators, CJK `。！？` (empty separators). No new runtime dependency.
- `"nltk"` — forces the NLTK `punkt_tab` engine (import-guarded; nltk/data absent → clear `SentenceTokenizerSelectionError`).

The splitter contract (D5) partitions text into contiguous sentence spans with whitespace consumed only at sentence boundaries, so the single-space re-join and `start_char`/`end_char` math are unchanged (D5a).

**Config:** `max_chunk_chars: int = 2000`, `overlap_chars: int = 200`, `sentence_tokenizer: "auto"` (via the `chunking:` block / `ChunkingSettings`, `config/default.yaml:171`, `app/core/config.py:364`). `overlap_chars` is **implemented**: `_apply_overlap` prepends each subsequent chunk with the previous chunk's trailing `overlap_chars` characters.

**Chunk ID format:** `"{source}::chunk_{index}"`

**Dependencies:** None required; `nltk>=3.9` optional in the `intelligence` extra (D4/C-2; one-time `nltk.download("punkt_tab")` setup step, runtime offline).  
**Limitations:**
- Sizing is character-based (`max_chunk_chars`), not token-aware (G13 / M3.3)
- No semantic/topic boundary detection beyond headings → paragraphs → sentence boundaries
- No sliding window
- Heuristic engine is abbreviation-list-bound (punkt_tab is the upgrade path via the nltk engine)
- Heading hierarchy metadata (`heading`, `heading_path`, `heading_level`) emitted on every chunk since M3.2 (G14, P3-201..205)

---

## 12. Tokenization

**Not Implemented.**

There is no tokenization module, no token counting, no token-aware truncation, and no integration with any tokenizer (tiktoken, HuggingFace tokenizers, or Ollama's internal tokenizer). The codebase uses character length (`max_chunk_chars: int = 2000`) as the chunk size proxy, not token counts. The LLM prompt (`app/prompts/document_analysis.py`) sends the full source text without any token budget management.

---

## 13. Embeddings

**File:** `app/infrastructure/embeddings.py`  
**Class:** `EmbeddingService`  
**Key methods:** `embed(text)` → `EmbeddingResult`, `embed_batch(texts)` → `list[EmbeddingResult]`

**How it works:**
- Wraps `ollama.Client.embed()` which calls Ollama's `/api/embed` endpoint
- `embed()` sends a single text string
- `embed_batch()` sends a list of texts (Ollama-native batching)
- Response normalized via `model_dump()` or `dict()` fallback
- Returns `EmbeddingResult` with model name and `list[float]` embedding vector

**Default model:** `"nomic-embed-text"` (`embeddings.py`, also in `config.py`)

**Dependencies:** `ollama`, Ollama running with `nomic-embed-text` model  
**Limitations:**
- No embedding caching/memoization
- No dimension validation (assumes all embeddings same dimension)
- No retry logic (unlike `OllamaClient` which has retries)
- Batch size unbounded — large batch could timeout
- No async support

---

## 14. Vector Database

**File:** `app/infrastructure/vector_store.py`  
**Class:** `VectorStore`  

**How it works:** Pure in-memory `dict[str, VectorEntry]`. No third-party vector database (not ChromaDB, not FAISS, not Qdrant).

**Storage:**
- `self._entries: dict[str, VectorEntry]` — all vectors in a dict keyed by entry ID
- `add(entry)` / `add_batch(entries)` — inserts into dict, precomputes each entry's norm into `self._norms`, bumps `self._version`
- `get(entry_id)` — dict lookup
- `remove(entry_id)` — dict deletion, norm removal, version bump
- `entries()` — all entries in insertion order (deterministic)
- `version` — integer mutation counter (every add/remove/load); drives the BM25 cache in `HybridSearch`

**Search:**
- `search(query_embedding, top_k=5, min_score=0.0, filters=None)` → `list[SearchResult]`
- Brute-force cosine scan over **all entries** using precomputed entry norms (`_norms`); semantics match the removed per-query `_cosine_similarity` (dimension mismatch or zero vector → `0.0`, included when `min_score <= 0.0`)
- `filters` (exact-match) applied before scoring via `_matches_filter` — entry fields win, then metadata keys; structured `$in` syntax is roadmap 4.5
- Results sorted by `(-score, entry.id)` (deterministic), limited to `top_k`

**Persistence:**
- `save()` writes all entries as JSON array to `persistence_path`
- `_load()` reads JSON and reconstructs `VectorEntry` objects, repopulating norms and bumping the version; tolerates missing `start_char`/`end_char` (`None`)
- `persistence_path: Path | None` set at construction

**Domain model:** `VectorEntry` (`app/domain/vector_store.py`) with `id`, `text`, `embedding: list[float]`, `source`, `source_type`, `chunk_index`, `start_char` (optional), `end_char` (optional), `metadata`.

**Dependencies:** None (pure Python)  
**Limitations:**
- O(n) search — every query scans all entries
- No indexing (no IVF, HNSW, or any approximate nearest neighbor)
- Full save on every write — no incremental append
- No atomic write in `save()` (direct `write_text()`, may corrupt on partial write)
- Entire store loaded into memory on construction
- Exact-match filtering only; no range or `$in` operators yet
- No versioning or migration for embedding dimension changes

---

## 15. Search

**File:** `app/infrastructure/search.py`

### SemanticSearch
**Class:** `SemanticSearch`  
**Key method:** `search(query_embedding, top_k=5, min_score=0.0)` → `list[SearchHit]`

Phase 1 dense-only wrapper around `VectorStore.search()`. Still live: the ingest workflow uses it for cross-document linking (`ingest_workflow.py:1007` `_find_cross_document_links`). Retained unchanged; the interactive query path uses `SearchService` instead.

### SearchService
**Class:** `SearchService`  
**Key method:** `search(query, *, top_k=5, filter=None, min_score=0.0)` → `list[SearchHit]`

Spec-facing retrieval facade (MEDD §7.6). `create_default(settings, *, embed=None)` builds the production service — it reads the same persisted `manifest_root/vector_store.json` the ingest pipeline writes and embeds via the configured model (`embed` injectable for tests). Blank queries return `[]` without embedding; `filter` applies exact-match on hit fields then metadata keys after fusion.

**Fallback:** if the embedder raises or returns a `None`/empty embedding, search degrades to lexical-only (BM25) instead of failing.

### HybridSearch
**Class:** `HybridSearch`  
**Key method:** `search(query, query_embedding, top_k=5, min_score=0.0)` → `list[SearchHit]`

Combines:
- Dense: cosine similarity over `VectorStore.search()`
- Sparse: deterministic BM25 (`app/infrastructure/bm25.py`, `k1=1.5`, `b=0.75`), rebuilt lazily and cached with a version key (`store.version`), so the index is rebuilt exactly when the corpus changes
- Fusion: reciprocal rank fusion with `k=60` (`_rrf_fuse`)

Fetches `top_k * 5` (min 50) candidates per leg, fuses by RRF, then applies `min_score` and truncates to `top_k`.

**Fallback:** BM25 build or search failure logs a warning and degrades to dense-only, resetting the cache (no poisoned cache; self-heals on the next query).

**SearchHit** carries `text`, `source`, `score`, `entry_id`, `parent_section` (metadata `parent_section_id`, roadmap 4.6 slot — `None` until parent-child retrieval ships), `source_type`, `chunk_index`, `start_char`, `end_char`, `metadata`.

**CLI:** `pam search <query> [--top-k N] [--filter JSON] [--source-type T] [--min-score F]` (`app/cli/entry.py:362`) renders a Rich table with score/source/snippet; validates blank query (exit 1), `--top-k >= 1` (exit 2), and `--filter` JSON (exit 1).

**Dependencies:** `VectorStore`, `BM25Index` (stdlib-only)  
**Limitations:**
- No cross-encoder re-ranking (roadmap 4.3)
- No query rewriting (roadmap 4.4)
- Parent-child retrieval not implemented (roadmap 4.6)
- Structured `$in` filter syntax not implemented (roadmap 4.5)
- No phrase matching or proximity scoring
- No search across multiple stores
- No result highlighting

---

## 16. Knowledge Graph

### Domain Model
**File:** `app/domain/knowledge_graph.py`

- `KnowledgeNode`: `id`, `label`, `node_type` (entity|concept|topic|note|definition), `source`, `metadata`
- `KnowledgeEdge`: `source_id`, `target_id`, `edge_type` (related_to|defined_in|mentioned_in|part_of|depends_on), `weight`, `metadata`
- `KnowledgeGraph`: In-memory dict of nodes + list of edges
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

## 17. Prompt Generation

**File:** `app/prompts/document_analysis.py`

### System Prompt
**`DOCUMENT_ANALYSIS_SYSTEM_PROMPT`**: 138-line prompt instructing the LLM to:
- Extract durable knowledge from source material
- Return valid JSON matching the `DocumentAnalysis` schema
- Follow constraints (max items per field, format rules, no nulls, no duplicates)
- Short summary ≤ 80 words, detailed summary ≤ 300 words

### User Prompt Builder
**`build_document_analysis_user_prompt(document, language="en")`**:
- Wraps source text with source metadata header
- Passes full document text in the prompt (no truncation)
- Appends `\n\nRespond in {language}.` when `language != "en"`; English path byte-identical to Phase 1 (Milestone 2.2)

### Configurable Templates
OCR/vision/handwriting prompts are configurable via `intelligence.prompts.{ocr,handwriting,vision}` with a `{language}` slot (Milestone 2.1).

**Dependencies:** `SourceDocument` domain model  
**Limitations:**
- No token budget management — full source text sent regardless of length
- No few-shot examples
- No system prompt versioning
- Analysis system prompt is a single hardcoded template (only OCR/vision/handwriting prompts are configurable)
- No multi-turn refinement (single generate call, no follow-up questions)

---

## 18. LLM Integration

### Text Generation
**File:** `app/infrastructure/llm/ollama_client.py`  
**Class:** `OllamaClient`  
**Key methods:**
- `generate_text(request)` → `OllamaTextResponse`
- `generate_json(request, response_model)` → `OllamaJsonResponse | ResponseModelT`

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
- `is_available()` → `client.ps()`
- `model_exists(name)` → checks `client.list()`

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

## 19. Obsidian Integration

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

## 20. CLI

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

## 21. Queue

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

**Config** (`config.py`): `workers: 1` (hard-coded max 1), `max_size: 1000`, `state_path` for persistence.

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

## 22. Logging

**File:** `app/core/logging.py`  
**Setup function:** `setup_logging(settings)` — configures logging based on `LoggingSettings`

**Features:**
- Console logging (with optional color)
- File logging (rotating file handler, `max_bytes: 10MB`, `backup_count: 5`)
- Format options: `console` (human-readable) or `json` (structured)
- Level configuration: CRITICAL / ERROR / WARNING / INFO / DEBUG

**Usage pattern:** `logger = get_logger(__name__)` throughout the codebase. Structured extra data passed via `logger.info("msg", extra={...})`.

**Config** (`config.py`): `level: "INFO"`, `format: "console"`, `console_enabled: True`, `file_enabled: True`, `use_colors: True`, `filename: "application.log"`.

**Dependencies:** Python `logging` stdlib  
**Limitations:**
- No structured logging library (no structlog, no loguru)
- `extra` dict is not automatically indexed (raw Python logging)
- No remote log shipping
- No correlation ID for pipeline tracing
- No log sampling for high-volume events

---

## 23. Configuration

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
- `intelligence`:
  - `ocr.*` — OCR engine, page limits, zoom, preprocessing, tesseract, confidence threshold (Milestone 2.1)
  - `prompts.{ocr,handwriting,vision}` — configurable prompt templates with `{language}` slot (Milestone 2.1)
  - `metadata.*` — metadata enrichment, MIME/language detection, size/time limits, email attachments, hooks (Milestone 2.2)
  - `structure.*` — document structure analysis (`enabled`; `enrich_analysis_input` is contract-only, read by no code) (Milestone 2.3)
  - `code.*` — code & notebook intelligence (`enabled`; `max_cell_outputs`, `max_code_chars`; `languages`/`include_docstrings` contract-only) (Milestone 2.6)

**Path resolution:** All relative paths resolved against project root (discovered by walking up from `config.py` looking for `pyproject.toml`).

**Error handling:** `ConfigurationError` raised for missing files, invalid YAML, validation failures.

**Dependencies:** `pydantic`, `pydantic_settings`, `yaml`, `pyyaml`  
**Limitations:**
- Environment variable values parsed via `yaml.safe_load()` (surprising behavior for string values)
- No config hot-reload
- No secrets management (API keys, tokens stored in plain config)
- No schema versioning for config migration

---

## 24. Error Handling

**Status:** Partially Implemented

Error handling exists at multiple levels but is not consistently applied:

| Layer | Mechanism | File |
|---|---|---|
| Ollama client | Typed exception hierarchy with retries | `ollama_client.py` |
| Ingestion | `IngestionError` → `UnsupportedSourceError` | `ingestion/base.py` |
| Metadata enrichment | Failures leave the document unchanged (debug-logged), never raise | `ingestion/service.py` |
| Ingestion hooks | `IngestionError` in pre-hook aborts; other hook errors logged + skipped | `ingestion/service.py` |
| Size limit | `IngestionError` before any read (`max_file_size_mb`) | `ingestion/service.py` |
| Configuration | `ConfigurationError` | `config.py` |
| Pipeline | `AIProcessingError` | `application.py` |
| Pipeline workflow | `IngestionWorkflowError` | `ingest_workflow.py` |
| CLI | `typer.Exit(1)` on failures | `entry.py` |
| Manifest | Corrupted file detection + quarantine | `manifest.py` |
| Vector store | Silent failure on corrupt JSON | `vector_store.py` |

**Pattern:** Most errors are caught, logged via `logger.exception()`, and wrapped in a domain-specific exception. CLI commands catch exceptions and exit with code 1.

**Limitations:**
- No centralized error handler or middleware
- Vector store silently ignores corrupt JSON (just logs warning)
- Ingestors have inconsistent error handling — some raise, some return empty text
- Queue has no dead letter handling for permanently failed items
- No health check endpoint for programmatic monitoring

---

## 25. Current Limitations

| Area | Limitation | Impact |
|---|---|---|
| Vector search | O(n) brute-force scan of all entries | Slow at scale (>10K vectors) |
| Chunking | Sentence splitting via pluggable `sentence_tokenizer` (M3.1: auto → nltk `punkt_tab` / stdlib heuristic); `overlap_chars` implemented (`_apply_overlap`, default 200); sizing remains character-based (`max_chunk_chars: 2000`), not token-aware | Chunk overlap provided; no token-aware sizing (G13 / M3.3) |
| Tokenization | Not implemented | No token-aware truncation; full source text sent to LLM |
| Table extraction | No structure parsing, passthrough only | Tables are flat text in notes |
| OCR | Configurable `page_limit` (default 5, 0 = all), `max_pages` cap 200; vision + optional Tesseract fallback; per-page confidence | Layout not preserved; Tesseract binary optional |
| Metadata | Stdlib-only extractors; image EXIF/metadata read by the M2.5 single owner (`images/metadata.py`) and attached via `metadata.extra` channels; language heuristic covers en/fr/de/ja | Richer formats need optional libs or future milestones |
| Structure analysis | Regex-based best-effort parsing; `TEXT_BEARING_KINDS` limited to `markdown`/`text`; structure stored under `metadata.extra["structure"]`; chunker emits native heading hierarchy (heading path/parent/level) since M3.2 (P3-201) | Hierarchical chunking shipped (M3.2); no note-template/TOC rendering from structure |
| Email attachments | One-level depth (nested attachments not re-ingested); `.eml` only; `parent_id` recorded but not consumed downstream | Nested email chains not fully traversed |
| Queue | Single worker only | No parallel processing |
| Watcher | Polling at 1s interval | No real-time file detection |
| Search | `SearchService` facade + `HybridSearch` (RRF dense+BM25) with `pam search` CLI (P5-104); reads persisted `manifest_root/vector_store.json` | No REST API binding |
| Knowledge graph | In-memory `KnowledgeGraph` with JSON persistence wired into the pipeline (`graph_persistence_path` → `knowledge_graph.json`, P4-105); traversal via domain methods `KnowledgeGraph.neighbors()` / `subgraph()` | No external graph DB (Neo4j/NetworkX) |
| LLM provider | Ollama only | No cloud fallback |
| No persistence | Vector store save() is called by pipeline but on every document | No incremental checkpointing |
| Image preprocessing | Implemented (deskew/denoise/CLAHE) but disabled by default (`preprocess: false`) | Requires enabling in config; Pillow/numpy optional |
| Code/notebook structure | Implemented (M2.6) for `code`/`notebook` kinds when `intelligence.code.enabled: true`; heuristic parser offsets approximate for non-Python; `languages`/`include_docstrings` contract-only | Structures not yet consumed downstream (input contract only) |
| Prompt engineering | OCR/vision/handwriting prompts configurable via `intelligence.prompts.*`; analysis prompt language-aware via `{language}` | Analysis system prompt still single hardcoded template |

---

## 26. Missing Features

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
| **Search API/CLI** | **Implemented** | `SearchService` facade + `pam search` CLI (`app/cli/entry.py:362`, P5-104); no REST API yet |
| **Graph visualization** | **Not Implemented** | No frontend for knowledge graph, no export to graphviz |
| **Batch processing** | **Not Implemented** | No batch mode for multiple files |
| **Progress reporting** | **Implemented** | Rich progress bars for `pam watch` stages and ingest reporting |
| **Field extraction (tables)** | **Partially Implemented** | Cell content extracted, no structure preserved |
| **Hierarchical chunking** | **Implemented** | Block tokenizer over heading hierarchy with `heading`/`heading_path`/`heading_level` metadata per chunk (M3.2, P3-201..205) |
| **Handwriting OCR** | **Partially Implemented** | Routed by source type to `HandwritingProcessor`; vision-engine transcription; no ML detection |
| **Image/EXIF metadata** | **Implemented** | `images/metadata.py` `ImageAnalyzer` (single EXIF owner, R-3): `ImageInfo` with dimensions/format/EXIF + optional GPS; attached as `metadata.extra["image_info"]` (image kinds, gated `exif_enabled`) and `metadata.extra["images"]` (PDF embedded images with page provenance) |
| **Code/Notebook structure** | **Implemented** | `code/` module (M2.6): `parse_code` (Python AST + heuristic fallback) → `metadata.extra["code_structure"]`; `parse_notebook` → `metadata.extra["notebook_structure"]` (gated `code.enabled`); processors passthrough |
| **Cloud LLM support** | **Not Implemented** | Ollama-only, no OpenAI/Anthropic adapters |
| **Automated testing in CI** | **Not Implemented** | Tests exist locally but no CI runner |
