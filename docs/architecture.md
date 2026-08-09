# Architecture

Authoritative architecture summary for **LLM-Wiki / Personal AI Memory (PAM)**. The full design specification lives in `MASTER_ENGINEERING_DESIGN_DOCUMENT.md`; the current-state inventory and limitations live in `01_Current_Implementation_Report.md`.

## Design principles

Local First · Offline First · Modular · Plugin Based · Clean Architecture · SOLID · Interface Driven · High Cohesion / Low Coupling · Extensible · Replaceable · Testable · Observable · Secure by Design · Performance-Conscious · Config over Hardcoding.

Dependency direction is strictly one-way: **CLI → Pipelines → Domain + Infrastructure**, with Domain being pure Pydantic models that never import infrastructure.

## Layering

| Layer | Contents | Responsibility |
|-------|----------|----------------|
| `app/domain/` | Pydantic models (documents, routing, semantic_chunking, vector_store, analysis, knowledge_graph, entity_relationship, notes, processed_document) | Pure data contracts |
| `app/infrastructure/` | `ingestion/` (21 ingestors), `routing/` (classifier, router, processors), `document_intelligence/` (metadata, ocr, structure, imaging, tables, images, code, entities, relationships, graph), `llm/`, `search.py`, `bm25.py`, `vector_store.py`, `embeddings.py`, `semantic_chunking.py`, `sentence_tokenizer.py`, `knowledge_graph.py`, `state/`, `vault/`, `templates/` | Concrete implementations |
| `app/pipelines/` | `ingest_workflow.py` | Orchestration of the 12-step ingest pipeline |
| `app/queue/` + `app/watcher/` | Queue manager/worker/state + Watchdog-based folder watching | Continuous background processing |
| `app/cli/` | Typer CLI (`pam`) | Entry points: `ingest`, `watch`, `search`, `status`, `doctor`, `config` |

## End-to-end ingest flow

```
User saves document
        │
        ▼
 Watcher / CLI (pam ingest …)
        │
        ▼
      Queue                    (single worker, max_size 1000, JSON crash recovery)
        │
        ▼
 Duplicate detection          (SHA-256 against data/manifests/processed_files.json)
        │
        ▼
 IngestionService             (size guard → pre-hooks → ingestor → metadata enrichment → post-hooks)
        │
        ▼
 Classifier (24 kinds)        (extension + MIME + language → kind; app/infrastructure/routing/classifier.py)
        │
        ▼
 Router (20 processors)       (RoutedProcessor dispatch by kind)
        │
        ├─→ OCR / Vision / Audio / structure / tables / images / code enrichment
        │
        ▼
 AI analysis (Ollama)         21-field document intelligence, respond-in-{language}
        │
        ├─→ Semantic chunking (heading hierarchy) → embeddings (nomic-embed-text) → vector store
        ├─→ Knowledge graph builder → JSON persistence
        ├─→ Cross-document linking (vector similarity)
        │
        ▼
 Markdown generation → vault writer → wiki manager (index/overview/log, placeholder notes)
```

## Key subsystems

### Routing
- **Classifier:** `DocumentClassifier` maps extension (via `EXTENSION_KIND_MAP` over `app/core/extensions.py`) + MIME + language to a `kind` (24 possible kinds incl. derived `scanned_pdf`/`handwritten`). Feature flags derived: `requires_ocr`, `requires_vision`, `requires_table_extraction`, `requires_code_parsing`.
- **Router + processors:** 20 registered `RoutedProcessor`s (code, markdown, web, text, pdf, config, docx, pptx, research, table, database, notebook, image, scanned_pdf, handwritten, audio, video, archive, email).

### Document intelligence (`app/infrastructure/document_intelligence/`)
- **Metadata** (M2.2): extractor registry (PDF/DOCX/PPTX/Notebook/Audio/Email), MIME detection (extension → magic bytes → stdlib fallback, ADR-001), language detection (py3langid + stdlib heuristic), pre/post hooks, size/time limits, email-attachment child ingestion.
- **OCR** (M2.1): `OcrEngine` protocol + `DocumentOcrService` registry. Vision model primary, Tesseract optional fallback (`engine="auto"`). PDF page rendering (zoom, `page_limit`, `max_pages` 200), shared preprocessing (deskew → denoise → CLAHE, off by default), per-page confidence.
- **Structure** (M2.3): heading-hierarchy + block detection → `DocumentStructure` with stable IDs and exact char offsets; `metadata.extra["structure"]`.
- **Tables** (M2.4): `TableExtractor` registry — CSV/TSV (csv.Sniffer), spreadsheet (openpyxl, merged-cell flattening), PDF (pdfplumber default per ADR-002, camelot optional); `## Tables` note section.
- **Images** (M2.5): `ImageAnalyzer` EXIF (sole EXIF owner), drawio → Mermaid, PDF embedded-image extraction, config-driven preprocessing guards.
- **Code & notebooks** (M2.6): stdlib-AST parser (Python) + heuristic fallback, notebook parser, `code_structure` / `notebook_structure` metadata.
- **Entities/relationships/graph** (P4): deterministic regex `EntityExtractor`, co-occurrence `RelationshipDetector`, `DocumentGraphBuilder` onto the in-memory graph; `metadata.extra["entities"]`, `["relationships"]`, `["knowledge_graph"]`.

### Chunking (M3.1/M3.2)
`SemanticChunker` is a block tokenizer over the heading hierarchy. Pluggable sentence tokenizer (`auto` → NLTK `punkt_tab` if available else stdlib heuristic). Every chunk carries `heading`, `heading_path`, `heading_level`, and a `parent_id` linking to the nearest ancestor heading chunk. List items never split mid-item; fenced code blocks are atomic; structured content (tables/blockquotes/callouts) is preserved byte-for-byte. Adaptive `ChunkingPolicy` (heading size step, min-chunk coalescing, snap overlap, heading hard boundaries).

### Storage & search (P5)
- **Vector store:** in-memory `dict[str, VectorEntry]` with JSON persistence, precomputed norms, O(n) cosine scan, deterministic `(-score, entry.id)` ordering, exact-match metadata filtering, mutation version counter.
- **Search:** `SearchService` facade + `HybridSearch` — dense cosine + Okapi-BM25 (`k1=1.5`, `b=0.75`, pure stdlib) fused by reciprocal rank fusion (**RRF, k=60**). BM25 cache is version-keyed on the store; embedder/BM25 failures degrade gracefully. CLI: `pam search`.
- **Knowledge graph:** in-memory adjacency list (`KnowledgeNode`/`KnowledgeEdge`) with JSON persistence wired through the pipeline; query layer (`get_entity`, `related_entities`, `nodes_by_source`, `query_graph`).

### Note generation & vault
`ObsidianMarkdownGenerator` emits 21-field Obsidian notes with YAML frontmatter and `[[wiki links]]`. User content outside `<!-- PAM:BEGIN/END MANAGED -->` markers is preserved on regeneration. Vault writer + wiki manager maintain `index.md`, `overview.md`, `log.md`; duplicate-safe filenames; placeholder notes for unresolved links.

## Configuration contract

Four layers, highest wins:
1. Pydantic model defaults
2. `config/default.yaml`
3. `config/{environment}.yaml` (deep merge; `PAM_ENVIRONMENT=production`)
4. `PAM_*` environment variables (nested keys via `__`, e.g. `PAM_OLLAMA__MODEL`)

Settings groups: `app`, `paths`, `ollama`, `logging`, `watcher`, `queue`, `manifest`, `processing`, `models`, `intelligence.*`, `chunking.*`. Relative paths resolve against the project root.

## Key design decisions (ADR-style)

- **ADR-001** — extension-first MIME detection with magic-byte + stdlib fallback; known extensions win without reading content.
- **ADR-002** — pdfplumber is the default PDF table engine; camelot stays an optional plugin (config switch).
- **P3-201 O-1** — heading hierarchy is resolved natively in the chunker (not via the M2.3 `structure` seam); the seam remains as fallback.
- **M3.1 D1/D8** — NLTK `punkt_tab` over spaCy; sentence tokenizer resolved once per chunker instance.
- **R-4** — every `intelligence.*.enabled: false` toggle yields Phase-1/M2.2-identical documents (rollback = flag + additive schema, no legacy branches).
- **R-2/R-1** — a single shared enrichment call site (`_run_routed_processor`); enrichment rides `metadata.extra[...]`; `ProcessedDocument` is never modified.
- **C-1** — registries are reserved for genuinely extensible kinds (OCR engines, metadata extractors, table extractors); image and code/notebook components are fixed services.
- **C-2/C-5/R-7** — some config keys (`enrich_analysis_input`, `include_docstrings`, `languages`) are contract-only: declared for future contracts, read by no code.
