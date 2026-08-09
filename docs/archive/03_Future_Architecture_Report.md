# LLM Wiki – Future Architecture & Enhancement Report

> Target architecture for a production-grade personal knowledge system.
> This is a forward-looking design document, not a description of the current implementation.

---

## 1. Enterprise Architecture (Target)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Client Layer                                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────────────┐  │
│  │   CLI    │  │ Web UI   │  │  Mobile   │  │ Obsidian Plugin   │  │
│  │ (typer)  │  │ (React)  │  │ (PWA)     │  │ (iframe/API)      │  │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  └────────┬──────────┘  │
│       │              │              │                  │             │
├───────┼──────────────┼──────────────┼──────────────────┼─────────────┤
│       └──────────────┴──────────────┴──────────────────┘             │
│                              │  REST + WebSocket                     │
│                     ┌────────┴────────┐                              │
│                     │   API Gateway   │                              │
│                     │  (FastAPI)      │                              │
│                     │  Rate Limit     │                              │
│                     │  Auth (JWT)     │                              │
│                     └────────┬────────┘                              │
├──────────────────────────────┼──────────────────────────────────────┤
│                              ▼                                       │
│                   ┌──────────────────┐                              │
│                   │  Use-Case Layer  │                              │
│                   │  (Application)   │                              │
│                   │                  │                              │
│                   │  • IngestSource  │                              │
│                   │  • SearchWiki    │                              │
│                   │  • QueryGraph    │                              │
│                   │  • GenerateNote  │                              │
│                   │  • AnalyzeDoc    │                              │
│                   │  • BatchProcess  │                              │
│                   └────────┬─────────┘                              │
├────────────────────────────┼──────────────────────────────────────┤
│                            ▼                                        │
│                   ┌──────────────────┐                              │
│                   │  Domain Layer    │                              │
│                   │  (Entities)      │                              │
│                   │                  │                              │
│                   │  Same as current │                              │
│                   │  + VectorIndex   │                              │
│                   │  + GraphQuery    │                              │
│                   └────────┬─────────┘                              │
├────────────────────────────┼──────────────────────────────────────┤
│                            ▼                                        │
│              ┌─────────────────────────────┐                       │
│              │      Infrastructure Layer   │                       │
│              │                             │                       │
│              │  ┌──────┐ ┌──────┐ ┌─────┐  │                       │
│              │  │Ollama│ │FAISS │ │Qdrant│  │                       │
│              │  └──┬───┘ └──┬───┘ └──┬──┘  │                       │
│              │  ┌──┴───┐ ┌──┴───┐ ┌──┴──┐  │                       │
│              │  │OpenAI│ │Redis │ │Neo4j │  │                       │
│              │  └──────┘ └──────┘ └─────┘  │                       │
│              │  ┌──────┐ ┌──────┐ ┌─────┐  │                       │
│              │  │S3/GCS│ │Celery│ │Docker│  │                       │
│              │  └──────┘ └──────┘ └─────┘  │                       │
│              └─────────────────────────────┘                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Why it is useful
Separates concerns into API Gateway → Use Cases → Domain → Infrastructure. Enables independent scaling, testing, and replacement of each layer.

### Benefits
- Clear contract between layers (Pydantic models as API schemas)
- Web UI, CLI, and Obsidian plugin share the same API
- Rate limiting and auth at gateway level

### Complexity: High
### Priority: Medium (Phase 4)
### Effort: 4–6 weeks for full API + UI

---

## 2. Modular Design

### Current state
Monolithic CLI app. All modules import directly from each other.

### Target
```
packages/
├── pam-core/          # Domain models + interfaces (pip install pam-core)
├── pam-ingestion/     # Ingestors as plugins (pip install pam-ingestion-pdf)
├── pam-ollama/        # Ollama provider (pip install pam-llm-ollama)
├── pam-openai/        # OpenAI provider (pip install pam-llm-openai)
├── pam-qdrant/        # Qdrant vector store
├── pam-faiss/         # FAISS vector store
├── pam-neo4j/         # Neo4j knowledge graph
├── pam-web/           # FastAPI web app
└── pam-cli/           # Typer CLI (bundles selected plugins)
```

### Why it is useful
- Pluggable providers for every external dependency
- Users install only what they need
- Third parties can write custom ingestors/providers without forking
- Clear versioning and dependency boundaries

### Benefits
- `pip install pam[qdrant,openai,web]` instead of one monolithic package
- Provider can be swapped at config time without code changes

### Complexity: High
### Priority: Low (Phase 6)
### Effort: 3–4 weeks for extraction + plugin API

---

## 3. Intelligent Ingestion

### Current state
21 ingestors that extract raw text. Image/video ingestors return metadata only. No incremental reading.

### Target additions

| Feature | What it does |
|---|---|
| **Incremental/streaming ingestion** | Read large files in chunks, process as stream |
| **MIME type detection** | Use `python-magic` content-based detection (not just extension) |
| **Language detection** | Auto-detect source language via `fast-langdetect` |
| **URL content type negotiation** | Fetch only README vs full repo vs API response based on Accept header |
| **Email attachment parsing** | Extract and recursively process attachments from .eml/.msg |
| **Archive recursion** | Configurable depth for nested archives |
| **Ingestion pipeline hooks** | Pre/post processing hooks for custom transformations |

### Why it is useful
Handles edge cases: extensionless files, misnamed files, nested archives, emails with attachments.

### Benefits
- Catches more content correctly on first pass
- Reduces manual cleanup

### Complexity: Medium
### Priority: Medium (Phase 3)
### Effort: 2 weeks

---

## 4. Advanced OCR

### Current state
`DocumentOcrService` registry: `VisionOcrEngine` (primary) renders PDF pages via PyMuPDF (`render_pdf_pages`, configurable `zoom`/`page_limit`/`max_pages`) and sends each page to the vision model with bounded retry + early stop on empty page; `TesseractOcrEngine` (optional fallback) provides offline printed-text OCR with per-page confidence. Missing PyMuPDF raises a clear `ImportError`. Handwriting is routed by the classifier to the vision engine.

### Target additions

| Feature | What it does |
|---|---|
| **PaddleOCR** | Additional local OCR engine (Tesseract fallback already shipped as `TesseractOcrEngine`) |
| **Layout preservation** | Detect columns, headers, footers, page numbers (layoutparser) |
| **Full-page OCR batching** | Page limit is already configurable (`page_limit`, 0 = all); add batched/parallel page processing for throughput |
| **Table detection in images** | Detect table boundaries, extract structured rows/columns |
| **Formula/equation OCR** | LaTeX extraction from scientific documents (LaTeX-OCR) |
| **Multi-language OCR** | Per-page language detection + model selection |
| **Region-level OCR confidence** | Per-page confidence is done (`PageOcrResult.confidence`); add per-region confidence stored in metadata |
| **Image preprocessing enhancements** | Deskew → denoise → CLAHE pipeline exists (`imaging/preprocess.py`, default off); add binarize/contrast auto-tuning and enable by default |
| **Document layout analysis** | Detect reading order, column flow, section hierarchy |

### Why it is useful
Scanned PDFs and handwritten notes are a primary use case for a personal knowledge system. Core OCR works (vision + Tesseract fallback); layout preservation and region-level confidence remain.

### Benefits
- Full-page OCR with layout preservation
- Works offline (Tesseract) or with GPU (PaddleOCR)
- Strucutred output (bounding boxes, confidence, reading order)

### Complexity: High
### Priority: High (Phase 2)
### Effort: 4–5 weeks

---

## 5. Hybrid Chunking

### Current state
Three-tier regex splitting (headings → paragraphs → sentences). `overlap_chars` declared but unused. Character-based.

### Target architecture

```
Document
  │
  ├─ 1. Semantic Boundary Detection
  │    ├─ NLP sentence segmentation (spaCy / nltk)
  │    └─ Topic shift detection (embedding cosine distance between windows)
  │
  ├─ 2. Hierarchical Structure Preservation
  │    ├─ Section → subsections → paragraphs via heading level
  │    └─ Store parent-child relationships (document → section → chunk)
  │
  ├─ 3. Sliding Window with Overlap
  │    ├─ Configurable overlap (characters AND sentences)
  │    └─ No truncation mid-sentence
  │
  ├─ 4. Semantic Chunking (ML)
  │    ├─ Embed sentence windows, split at cosine distance peaks
  │    └─ Merge small adjacent chunks of same topic
  │
  └─ 5. Token-Aware Sizing
       ├─ Count tokens via tiktoken (or Ollama's tokenizer endpoint)
       └─ Target: 512-1024 tokens per chunk (model-specific)
```

### Parent-child retrieval
```
                  ┌──────────────┐
                  │  Document    │ (embedding = mean of child embeddings)
                  │  (level 0)   │
                  └──────┬───────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
     ┌────┴────┐   ┌────┴────┐   ┌────┴────┐
     │ Section │   │ Section │   │ Section │ (level 1)
     │         │   │         │   │         │
     └────┬────┘   └────┬────┘   └────┬────┘
          │              │              │
     ┌────┴────┐   ┌────┴────┐   ┌────┴────┐
     │ Chunk   │   │ Chunk   │   │ Chunk   │ (level 2 - leaf)
     └─────────┘   └─────────┘   └─────────┘
```
**Retrieval:** Search at leaf level → return parent section/document as context window.

### Why it is useful
Current regex chunking breaks mid-sentence, loses topic continuity, and has no overlap. Parent-child retrieval gives the LLM full section context when answering from a chunk.

### Benefits
- Topic-coherent chunks
- LLM gets full section context (parent-child)
- Token-aware = no context window overflow
- Configurable overlap per model

### Complexity: Medium
### Priority: High (Phase 2)
### Effort: 2–3 weeks

---

## 6. Multi-Modal Embeddings

### Current state
Single embedding model (`nomic-embed-text`) via Ollama. Text only.

### Target

| Modality | Model | Storage |
|---|---|---|
| **Text** | `nomic-embed-text-v1.5` or `gte-large` | FAISS index |
| **Code** | `voyage-code-2` or `starcoder2` embedding | Separate FAISS index |
| **Image** | CLIP / SigLIP | Image-only FAISS index |
| **Table** | table-embedding or structured-text encoder | Table index |
| **Audio** | Whisper encoder embedding | Audio index |
| **Late interaction** | ColBERTv2 (token-level) | ColBERT index for re-ranking |

### Architecture
```
Query
  │
  ├─ Text query → embed(nomic-embed-text) → text index
  ├─ Image query → embed(CLIP) → image index
  ├─ Code query → embed(voyage-code) → code index
  │
  └─ Cross-modal (text query → image index via CLIP text encoder)
```

### Why it is useful
A user should be able to ask "show me that diagram about attention mechanisms" and retrieve images, not just text.

### Benefits
- Search across all content types from one query
- CLIP enables text→image and image→image search
- Late interaction (ColBERT) preserves token-level matching for better re-ranking

### Complexity: Very High
### Priority: Low (Phase 5)
### Effort: 6–8 weeks

---

## 7. Hybrid Retrieval

### Current state
`HybridSearch` with 70/30 semantic/keyword weighting. No BM25, no re-ranking, no filtering.

### Target architecture

```
Query
  │
  ├── 1. Query Rewriting
  │      ├─ LLM generates 3 query variants (decomposition, expansion)
  │      └─ All variants searched in parallel
  │
  ├── 2. Sparse Retrieval (BM25)
  │      ├─ Tokenize query → BM25 over all chunks
  │      └─ Returns top-k sparse results
  │
  ├── 3. Dense Retrieval (FAISS / Qdrant)
  │      ├─ Embed query → ANN search over vector index
  │      └─ Returns top-k dense results
  │
  ├── 4. Late Interaction (ColBERTv2)
  │      └─ Token-level matching for fine-grained relevance
  │
  ├── 5. Fusion (Reciprocal Rank Fusion)
  │      ├─ Merge sparse + dense + late interaction results
  │      └─ RRF score = Σ 1/(k + rank)
  │
  ├── 6. Metadata Filtering
  │      ├─ Filter by source, source_type, date, tags, categories
  │      └─ Applied before or after retrieval (configurable)
  │
  ├── 7. Re-Ranking
  │      ├─ Cross-encoder (Cohere rerank / BGE-reranker)
  │      └─ Scores top-50 candidates with high-precision model
  │
  └── 8. Result
       └─ Ranked, filtered, re-ranked hits with scores + metadata
```

### Query rewriting examples
| Original | Variants |
|---|---|
| "attention mechanism" | "self-attention in transformers", "how does attention work", "attention is all you need" |
| "python async" | "python asyncio patterns", "async/await in python", "concurrent python code" |

### Why it is useful
Sparse retrieval (BM25) catches exact keywords that dense retrieval misses. Dense catches semantic matches that BM25 misses. RRF fuses both. Re-ranking with a cross-encoder is the highest-accuracy retrieval method available.

### Benefits
- Significantly higher recall than either sparse or dense alone
- Cross-encoder re-ranking is SOTA for relevance
- Metadata filtering enables "search only PDFs from 2024"

### Complexity: Very High
### Priority: Medium (Phase 3)
### Effort: 4–5 weeks

---

## 8. Re-Ranking

### Target component
```
                          ┌─────────────┐
                          │  Query      │
                          └──────┬──────┘
                                 │
  ┌──────────────────────────────┼──────────────────────────────┐
  │                              ▼                              │
  │  ┌─────────────────────────────────────────────────────┐   │
  │  │      Bi-Encoder (FAISS) → Top-100 candidates        │   │
  │  └─────────────────────────────────────────────────────┘   │
  │                              │                              │
  │                              ▼                              │
  │  ┌─────────────────────────────────────────────────────┐   │
  │  │      Cross-Encoder (BGE-reranker) → Score top-50    │   │
  │  │      [query + candidate] → relevance score 0.0-1.0  │   │
  │  └─────────────────────────────────────────────────────┘   │
  │                              │                              │
  │                              ▼                              │
  │  ┌─────────────────────────────────────────────────────┐   │
  │  │      Sort by re-rank score → Return top-k            │   │
  │  └─────────────────────────────────────────────────────┘   │
  └──────────────────────────────────────────────────────────────┘
```

### Why it is useful
FAISS ANN retrieves candidates that are "close" in embedding space but may not be relevant. A cross-encoder jointly attends to query+candidate and produces a much more accurate relevance score.

### Benefits
- Typically +10-20% relevance over dense retrieval alone
- Can run on CPU (BGE-reranker models are small, ~500MB)

### Complexity: Medium
### Priority: Medium (Phase 3)
### Effort: 2 weeks

---

## 9. Query Rewriting

### Target component

```
User Query: "transformer attention"
    │
    ▼
┌─────────────────────────────────────┐
│           LLM (small model)          │
│  "Generate 3 search variants for    │
│   the query 'transformer attention' │
│   that would help find relevant     │
│   information in a knowledge base." │
└──────────────────┬──────────────────┘
                   │
                   ▼
  ┌────────────────────────────────────────┐
  │ 1. "transformer attention mechanism"   │ ← original + context
  │ 2. "self-attention in transformers"    │ ← decomposition
  │ 3. "multi-head attention explained"    │ ← expansion
  └────────────────────────────────────────┘
                   │
                   ▼
          All 3 searched in parallel
                   │
                   ▼
           Results fused via RRF
```

### Why it is useful
A single query might not match the vocabulary used in the stored documents. Query rewriting generates variants that cover different phrasings and levels of specificity.

### Benefits
- Captures documents that use different terminology for the same concept
- 3 parallel searches cost ~same latency as 1 (parallel)

### Complexity: Low
### Priority: High (Phase 2)
### Effort: 1 week

---

## 10. Metadata Filtering

### Current state
`VectorStore.search()` has no filtering — searches all entries.

### Target

```
Search(
    query="transformer attention",
    metadata_filter={
        "source_type": {"$in": ["pdf", "markdown"]},
        "date": {"$gte": "2024-01-01"},
        "tags": {"$contains": "deep-learning"},
        "categories": {"$eq": "Research Papers"},
        "difficulty": {"$in": ["beginner", "intermediate"]},
    }
)
```

### Why it is useful
Users need to scope searches: "only technical PDFs from 2024", "only beginner-friendly content".

### Benefits
- Precision improves dramatically with filter scoping
- Reduces result set before re-ranking (performance)

### Complexity: Low
### Priority: High (Phase 2)
### Effort: 1 week

---

## 11. Parent-Child Retrieval

### Current state
Flat chunk list. No hierarchy. Search returns individual chunks with no context about the parent section or document.

### Target

```
Query: "how does multi-head attention work?"
    │
    ▼
  Vector Search
    │
    ▼
  Chunk matched: "multi-head attention splits into h heads..."
                    │
                    ▼
  Retrieve parent:  "Section 3: Attention Mechanisms"
                    │
                    ▼
  Retrieve siblings: ["Scaled dot-product attention",
                      "Multi-head attention",
                      "Masked attention"]
                    │
                    ▼
  Context window:
    ┌────────────────────────────────────────┐
    │ Section: Attention Mechanisms          │
    │                                        │
    │ [chunk 1] Scaled dot-product...        │
    │ [chunk 2] Multi-head attention... ←    │ ← matched chunk
    │ [chunk 3] Masked attention...          │
    └────────────────────────────────────────┘
                    │
                    ▼
  LLM gets full section as context
```

### Why it is useful
A chunk alone often lacks context. Returning the parent section (or even the full document) gives the LLM the surrounding content needed for accurate answers.

### Benefits
- Significantly better answer quality from LLM
- Enables "what section is this from?" in results

### Complexity: Low
### Priority: High (Phase 2)
### Effort: 1 week (requires hierarchical chunking first)

---

## 12. Knowledge Graph Improvements

### Current state
In-memory `KnowledgeGraph` with nodes/edges from document analysis. JSON persistence exists but never called in pipeline. No query language. No graph algorithms.

### Target

```
┌────────────────────────────────────────────────────────┐
│                 Knowledge Graph Layer                    │
├────────────────────────────────────────────────────────┤
│                                                         │
│  1. Storage ← Neo4j (self-hosted) or json-graph         │
│     │          ← Query: Cypher or GraphQL               │
│     │          ← Persistence: automatic on every write   │
│     │                                                    │
│  2. Enrichment                                           │
│     │  ├─ Entity resolution: "Apple" (company) vs        │
│     │  │   "apple" (fruit) via graph context             │
│     │  ├─ Relationship inference: if A is_in    │
│     │  │   field_of(X) and B works_on(X), infer          │
│     │  │   A collaborates_with B                        │
│     │  └─ Temporal edges: "worked_at" with from/to       │
│     │                                                    │
│  3. Graph-Augmented Retrieval (GAR)                      │
│     │  ├─ Query: "What did I learn about attention?"     │
│     │  ├─ Graph traversal: note → concept → related notes│
│     │  └─ Result: subgraph fed to LLM as context         │
│     │                                                    │
│  4. Graph Algorithms                                     │
│        ├─ PageRank: find most central concepts          │
│        ├─ Community detection: topic clusters           │
│        └─ Shortest path: how are two concepts connected? │
│                                                         │
└────────────────────────────────────────────────────────┘
```

### Why it is useful
The current graph is generated and discarded every run. A persistent graph enables cross-document discovery: "what concepts connect these two notes?" "which entities appear most frequently?"

### Benefits
- Graph-augmented retrieval catches relationships that vector similarity misses
- Entity resolution prevents wrong merges
- Graph algorithms surface insights invisible to search
- Temporal edges track knowledge evolution over time

### Complexity: High
### Priority: Medium (Phase 3)
### Effort: 4–6 weeks

---

## 13. AI Agents

### Target architecture

```
                         ┌──────────────────────┐
                         │   Orchestrator Agent  │
                         │  (LLM + tool loop)    │
                         └──────┬───────┬───────┘
                                │       │
              ┌─────────────────┼───────┼──────────────────┐
              │                 │       │                   │
              ▼                 ▼       ▼                   ▼
     ┌────────────────┐ ┌──────────┐ ┌────────┐ ┌──────────────┐
     │ Research Agent │ │ Writing  │ │ Review │ │ Knowledge    │
     │                │ │ Agent    │ │ Agent  │ │ Agent        │
     │ 1. Search wiki │ │ 1. Draft │ │ 1. Fact│ │ 1. Extract   │
     │ 2. Read source │ │    note  │ │   check│ │    entities  │
     │ 3. External    │ │ 2. Format│ │ 2. Cite│ │ 2. Link      │
     │    search      │ │ 3. Link  │ │ 3. Flag│ │    concepts  │
     │ 4. Summarize   │ │    notes │ │   gaps │ │ 3. Suggest   │
     └────────────────┘ └──────────┘ └────────┘ │    relations │
                                                └──────────────┘
```

### Use cases

| Agent | Purpose | Example |
|---|---|---|
| **Research Agent** | Search + synthesize across notes and external sources | "Find everything I've saved about RLHF and write a summary" |
| **Writing Agent** | Draft new notes from zero or from source material | "Turn this transcript into a structured note" |
| **Review Agent** | Fact-check, cite sources, flag contradictions | "Does this note contradict what I wrote last month?" |
| **Knowledge Agent** | Extract entities, suggest links, find gaps | "This note mentions 'LoRA' but has no link to the LoRA note" |

### Why it is useful
Moves the system from passive note-taking to active knowledge management. Agents proactively find connections, fill gaps, and maintain quality.

### Benefits
- Automated cross-referencing between notes
- Proactive knowledge gap detection
- Research synthesis without manual search

### Complexity: Very High
### Priority: Low (Phase 5)
### Effort: 6–8 weeks per agent

---

## 14. Table Intelligence

### Current state
Cells extracted as flat concatenated text. No structure preserved.

### Target

```
Raw table (CSV/PDF/image)
    │
    ├── 1. Table Detection (Camelot / Tabula / TableTransformer)
    │        Detect table boundaries, even in PDFs and images
    │
    ├── 2. Structure Parsing
    │        │
    │        ├─ Identify header rows vs data rows
    │        ├─ Detect merged cells, multi-level headers
    │        ├─ Column type inference (text, number, date, currency)
    │        └─ Row grouping / hierarchical rows
    │
    ├── 3. Normalization
    │        │
    │        ├─ Convert to Markdown table
    │        ├─ Generate HTML table (for rich rendering)
    │        └─ Embed as structured JSON in vector store
    │
    └── 4. Table Embedding
             │
             ├─ Encode table as structured text + columns
             └─ Enable "find tables where column X > Y" queries
```

### Why it is useful
Tables are the most information-dense content type. Current flat-text handling loses all the structure that makes tables useful.

### Benefits
- Table-aware retrieval ("find the table about model benchmarks")
- Markdown tables in generated notes (readable)
- Structured JSON enables column-level filtering

### Complexity: Medium
### Priority: Medium (Phase 3)
### Effort: 2–3 weeks

---

## 15. Image Intelligence

### Current state
Vision model via Ollama (image kind routed to `VisionOcrEngine`). Optional preprocessing pipeline exists (deskew → denoise → CLAHE, `imaging/preprocess.py`, default off). No layout analysis.

### Target

```
Image
  │
  ├── 1. Preprocessing
  │      ├─ Deskew (correct rotation)
  │      ├─ Denoise (remove compression artifacts)
  │      ├─ Binarize (threshold for OCR)
  │      ├─ Contrast enhancement
  │      └─ Super-resolution (if small)
  │
  ├── 2. Analysis
  │      │
  │      ├─ Vision LLM (Qwen2.5VL / GPT-4V)
  │      │   ├─ Extract all text
  │      │   ├─ Describe diagrams and charts
  │      │   └─ Identify figure type (photo, diagram, chart, screenshot)
  │      │
  │      ├─ OCR Engine (Tesseract + PaddleOCR)
  │      │   ├─ Bounding boxes with confidence
  │      │   └─ Reading order reconstruction
  │      │
  │      └─ Diagram-specific (for drawio, excalidraw, etc.)
  │          ├─ Extract shapes and connectors
  │          └─ Generate mind-map or Mermaid representation
  │
  ├── 3. Indexing
  │      ├─ CLIP embedding (text-to-image search)
  │      ├─ Caption generation (BLIP / Vision LLM)
  │      └─ Store image + caption + embedding
  │
  └── 4. Retrieval
         ├─ Text-to-image: "find the architecture diagram"
         └─ Image-to-image: "find similar diagrams"
```

### Why it is useful
Diagrams, screenshots, and photos are knowledge artifacts, not just decorations. The system should extract and index their content.

### Benefits
- Search images by described content
- Diagram text extraction (flowcharts, architecture diagrams)
- Image-to-image similarity search

### Complexity: Very High
### Priority: Low (Phase 5)
### Effort: 6–8 weeks

---

## 16. Monitoring

### Target stack

```
┌────────────────────────────────────────────────────┐
│                   Application                        │
│                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │ OpenTelemetry│  │ Prometheus   │  │ Structured│  │
│  │ Tracing     │  │ Metrics      │  │ Logging   │  │
│  │ (spans)     │  │ (counters,   │  │ (JSON)    │  │
│  │             │  │  histograms)  │  │           │  │
│  └──────┬──────┘  └──────┬───────┘  └─────┬─────┘  │
│         │                │                 │         │
└─────────┼────────────────┼─────────────────┼─────────┘
          │                │                 │
          ▼                ▼                 ▼
   ┌──────────┐    ┌──────────────┐   ┌──────────┐
   │ Jaeger   │    │  Grafana     │   │ Loki     │
   │ (traces) │    │  (dashboards)│   │ (logs)   │
   └──────────┘    └──────────────┘   └──────────┘
```

### Metrics to track

| Metric | Type | What it measures |
|---|---|---|
| `pam_ingestion_duration_seconds` | Histogram | Time to ingest a file |
| `pam_llm_generation_duration_seconds` | Histogram | Time for LLM analysis |
| `pam_llm_tokens_total` | Counter | Total tokens consumed |
| `pam_chunks_created_total` | Counter | Chunks created |
| `pam_embeddings_created_total` | Counter | Embeddings generated |
| `pam_search_duration_seconds` | Histogram | Search latency |
| `pam_errors_total` | Counter | Errors by type |
| `pam_queue_depth` | Gauge | Current queue size |
| `pam_vector_store_size` | Gauge | Entries in vector store |
| `pam_notes_created_total` | Counter | Notes written |

### Why it is useful
Without monitoring, there is no way to know if the system is healthy, what's slow, or what's failing.

### Benefits
- Trace a single document through the entire pipeline
- Alert on error rate spikes
- Capacity planning (how many tokens per day?)

### Complexity: Medium
### Priority: Low (Phase 4)
### Effort: 2 weeks

---

## 17. Security

### Target

| Layer | Measure |
|---|---|
| **API** | JWT authentication, rate limiting (100 req/min per user) |
| **Storage** | SQLite/PostgreSQL at rest encryption, vector store encryption |
| **Transport** | TLS for all external communication |
| **Configuration** | Secrets vault (env vars → .env → OS keychain) |
| **File upload** | MIME type validation, size limits, malware scanning |
| **LLM** | Prompt injection detection, output sanitization |
| **Audit** | All access logged (who accessed what, when) |
| **Data isolation** | Multi-user: per-user vault, per-user vector index |

### Why it is useful
Current system has zero security — no auth, no encryption, no access control. Even for a personal tool, encryption at rest and safe file handling are baseline requirements.

### Benefits
- Safe to expose web UI externally
- Multi-user ready
- Audit trail for compliance

### Complexity: Medium
### Priority: Medium (Phase 4)
### Effort: 3–4 weeks

---

## 18. Scalability

### Current bottleneck
Single process, single worker, O(n) vector search, synchronous pipeline.

### Target architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Scale Strategy                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Vertical (single user, <100K chunks)                 │   │
│  │  ├─ FAISS IVF index (O(log n) search)                │   │
│  │  ├─ SQLite for metadata + graph store                 │   │
│  │  └─ Async pipeline with ThreadPoolExecutor            │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Horizontal (multi-user, >100K chunks)                │   │
│  │  ├─ Qdrant/Weaviate for distributed vector search     │   │
│  │  ├─ PostgreSQL for metadata + graph                   │   │
│  │  ├─ Celery for async processing                       │   │
│  │  ├─ Redis for caching + rate limiting                 │   │
│  │  ├─ S3/GCS for file storage                           │   │
│  │  └─ Kubernetes or docker-compose swarm                │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Library-scale (single user, <1M chunks)              │   │
│  │  ├─ FAISS IVF-PQ (product quantization for memory)   │   │
│  │  ├─ SQLite for metadata (still fits in RAM)           │   │
│  │  └─ Single process, async, batch indexing             │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Why it is useful
The current O(n) scan works for hundreds of chunks but breaks at thousands. FAISS IVF provides O(log n) search and fits within the single-user budget.

### Benefits
- Path from hobbyist to enterprise without rewriting
- Each tier reuses the same domain models
- Tested at each scale before moving up

### Complexity: Medium (vertical) → Very High (horizontal)
### Priority: High (Phase 2: FAISS IVF)
### Effort: 2 weeks (FAISS IVF) → 8–12 weeks (horizontal)

---

## 19. Deployment

### Current
Manual `uv run` with local Ollama.

### Target

```
┌─────────────────────────────────────────────────────────────┐
│                   Deployment Options                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Tier 1: Local (docker-compose)                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  ollama:latest                                        │   │
│  │  pam-app:latest                                       │   │
│  │  qdrant:latest (optional, else FAISS in-process)      │   │
│  │  └─ docker compose up -d                              │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  Tier 2: Self-hosted (docker-compose + S3)                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Add:                                                  │   │
│  │  ├─ PostgreSQL (metadata + graph)                     │   │
│  │  ├─ Redis (cache + queue)                             │   │
│  │  ├─ S3-compatible storage (MinIO)                     │   │
│  │  └─ Traefik/Caddy (TLS reverse proxy)                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  Tier 3: Cloud (AWS/GCP)                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  ├─ ECS/GKE (Docker containers)                      │   │
│  │  ├─ RDS/Cloud SQL (PostgreSQL)                       │   │
│  │  ├─ ElastiCache/Memorystore (Redis)                  │   │
│  │  ├─ S3/GCS (file storage)                            │   │
│  │  ├─ Qdrant Cloud / Pinecone (vector DB)              │   │
│  │  └─ Cloudflare/API Gateway (auth + rate limit)       │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Why it is useful
Docker eliminates the "works on my machine" problem. Cloud deployment enables multi-user access and backups.

### Benefits
- One-command setup for new users
- Automated backups of vector store + notes
- URL-accessible web UI

### Complexity: Low (Tier 1) → Very High (Tier 3)
### Priority: Medium (Phase 3: Tier 1 Docker)
### Effort: 1 week (Tier 1) → 4 weeks (Tier 2) → 8 weeks (Tier 3)

---

## 20. Cloud Architecture

### Target: Hybrid Local + Cloud

```
┌──────────────────────────────────┐   ┌──────────────────────────────┐
│         Local Machine            │   │         Cloud (optional)     │
│                                  │   │                              │
│  ┌────────────────────────────┐  │   │  ┌────────────────────────┐  │
│  │  Ollama (local LLM)       │  │   │  │  API Gateway (FastAPI) │  │
│  │  └─ qwen3:8b              │  │   │  │  └─ /search            │  │
│  │  └─ nomic-embed-text      │  │   │  │  └─ /ingest            │  │
│  │  └─ qwen2.5vl (vision)    │  │   │  │  └─ /notes             │  │
│  └────────────────────────────┘  │   │  └───────────┬────────────┘  │
│                                  │   │              │               │
│  ┌────────────────────────────┐  │   │              ▼               │
│  │  PAM App                   │  │   │  ┌────────────────────────┐  │
│  │  └─ Ingestion              │  │   │  │  Cloud Services        │  │
│  │  └─ Chunking               │  │   │  │  └─ PostgreSQL         │  │
│  │  └─ Template generation    │  │   │  │  └─ Redis              │  │
│  │  └─ CLI + optional UI     │  │   │  │  └─ S3/GCS             │  │
│  └────────────────────────────┘  │   │  └────────────────────────┘  │
│                                  │   │                              │
│  ┌────────────────────────────┐  │   │  ┌────────────────────────┐  │
│  │  Local Cache               │  │   │  │  Cloud LLM (optional)  │  │
│  │  └─ FAISS index           │  │   │  │  └─ OpenAI GPT-4o      │  │
│  │  └─ SQLite (metadata)     │  │   │  │  └─ Claude Sonnet      │  │
│  │  └─ JSON graph store      │  │   │  │  └─ Gemini Pro         │  │
│  └────────────────────────────┘  │   │  └────────────────────────┘  │
│                                  │   │                              │
│  ┌────────────────────────────┐  │   │  ┌────────────────────────┐  │
│  │  Obsidian Vault (local)   │  │   │  │  Vector DB (optional)  │  │
│  │  └─ Notes/*.md            │  │   │  │  └─ Qdrant Cloud       │  │
│  │  └─ .obsidian/            │  │   │  │  └─ Pinecone           │  │
│  └────────────────────────────┘  │   │  └────────────────────────┘  │
└──────────────────────────────────┘   └──────────────────────────────┘
```

### Why it is useful
Local-first for privacy and offline use. Cloud for search, sharing, and backup. LLM runs locally for sensitive data; cloud models optional for capacity.

### Benefits
- Data never leaves local machine unless user chooses
- Cloud search index available from anywhere
- Sync vault to cloud for backup

### Complexity: Very High
### Priority: Low (Phase 6)
### Effort: 10–12 weeks

---

## 21. Evaluation Framework

### Target

```
┌────────────────────────────────────────────────────────────┐
│                    Evaluation Framework                      │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Chunking Quality                                        │
│     ├─ Metric: semantic coherence (cosine within vs across) │
│     ├─ Metric: chunk size distribution (target: 512±128 t) │
│     └─ Tool: pytest-benchmark + chunking test suite         │
│                                                             │
│  2. Embedding Quality                                       │
│     ├─ Metric: retrieval recall@10 on labeled queries       │
│     ├─ Metric: mean reciprocal rank (MRR)                   │
│     └─ Tool: custom eval dataset from user's own vault      │
│                                                             │
│  3. Retrieval Quality                                       │
│     ├─ Metric: precision@k, recall@k, NDCG@k                │
│     ├─ Metric: latency p50/p95/p99                          │
│     └─ Tool: pytest + time/perf counters                    │
│                                                             │
│  4. LLM Analysis Quality                                    │
│     ├─ Metric: field completion rate (what % fields filled) │
│     ├─ Metric: hallucination rate (verified against source)  │
│     └─ Tool: automated script comparing analysis to source  │
│                                                             │
│  5. End-to-End                                               │
│     ├─ Metric: pipeline success rate (%)                    │
│     ├─ Metric: average pipeline duration                    │
│     ├─ Metric: note quality score (section coverage)        │
│     └─ Tool: existing intelligence_test.py extended         │
│                                                             │
│  6. Regression                                              │
│     ├─ CI gate: all eval metrics must not regress           │
│     ├─ CI gate: test coverage >= 85%                        │
│     └─ Tool: GitHub Actions + pytest-cov + eval comparison  │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

### Why it is useful
Without evaluation, improvements are guesses. An eval framework measures whether a new chunking strategy or embedding model actually improves results.

### Benefits
- Data-driven decisions (not intuition)
- Catch regressions before merge
- Compare providers objectively

### Complexity: Medium
### Priority: Medium (Phase 3)
### Effort: 3–4 weeks

---

## 22. Summary: Complexity vs Priority Matrix

```
                    │
    Very High       │  Multi-modal Embs     Cloud Arch
                    │  AI Agents             │
                    │  Image Intelligence    │
                    │                        │
    High            │  Advanced OCR          │
                    │  Hybrid Retrieval      │
                    │  Neo4j KG             │
                    │  Table Intelligence   │
                    │  Eval Framework       │
                    │                        │
    Medium          │  Docker                │
                    │  Re-ranking            │
                    │  Security              │
                    │  Monitoring            │
                    │                        │
    Low             │  Parent-Child Retrieval│
                    │  Query Rewriting       │
                    │  Metadata Filtering   │
                    │  Plugin Architecture   │
                    │  Hybrid Chunking       │
                    │  FAISS IVF             │
                    │                        │
                    └────────────────────────┴──────────
                       Low      Med      High    Very High
                                        Priority
```

---

## 23. Phased Roadmap

### Phase 1: Foundation (Current + 4 weeks)
**Theme: Fix the critical gaps before adding features**

| Task | Effort | Depends on |
|---|---|---|
| FAISS IVF index for O(log n) vector search | 2 weeks | — |
| Token counting + truncation for LLM prompts | 1 week | — |
| Call `KnowledgeGraph.save()` in pipeline | 1 day | — |
| Implement chunk overlap (`overlap_chars`) | 1 day | — |
| Make PyMuPDF a required dependency + clear error | 1 day | — |
| Atomic write for vector store (`.tmp` → `os.replace`) | 1 day | — |
| Add progress bars to CLI (rich Progress) | 2 days | — |
| Wire search into CLI (`pam search <query>`) | 2 days | FAISS IVF |

### Phase 2: Retrieval & Chunking (Weeks 5–8)
**Theme: Make search useful**

| Task | Effort | Depends on |
|---|---|---|
| Hierarchical chunking with parent-child relationships | 2 weeks | Phase 1 |
| Query rewriting (LLM generates 3 variants) | 1 week | — |
| Metadata filtering in search | 1 week | Phase 1 FAISS |
| Parent-child retrieval (return section context) | 1 week | Hierarchical chunking |
| Advanced OCR (Tesseract + layout analysis) | 4 weeks | — |

### Phase 3: Quality (Weeks 9–14)
**Theme: Polish, evaluate, and expand**

| Task | Effort | Depends on |
|---|---|---|
| Hybrid retrieval (BM25 + dense + RRF) | 4 weeks | Phase 2 |
| Cross-encoder re-ranking | 2 weeks | Hybrid retrieval |
| Evaluation framework (chunking, retrieval, analysis) | 3 weeks | Phase 2 |
| Docker setup (Tier 1) | 1 week | — |
| Table intelligence (Camelot + Markdown format) | 2 weeks | — |
| Knowledge graph persistence (Neo4j or JSON on every write) | 4 weeks | Phase 1 |
| Intelligent ingestion (MIME, language, hooks) | 2 weeks | — |

### Phase 4: Security & Observability (Weeks 15–18)
**Theme: Production readiness**

| Task | Effort | Depends on |
|---|---|---|
| FastAPI web app + REST API | 3 weeks | Phase 3 |
| JWT authentication + rate limiting | 2 weeks | Web app |
| Basic web UI (React, search + browse notes) | 4 weeks | REST API |
| OpenTelemetry + Prometheus + Grafana | 2 weeks | — |
| Local deployment docs + scripts | 1 week | Docker |

### Phase 5: Intelligence (Weeks 19–26)
**Theme: Advanced features**

| Task | Effort | Depends on |
|---|---|---|
| Multi-modal embeddings (CLIP, code, audio) | 6 weeks | Phase 3 |
| AI agents (Research + Writing + Review) | 8 weeks | Phase 4 API |
| Image intelligence (preprocessing + diagram parsing) | 6 weeks | Phase 2 OCR |
| Cloud LLM providers (OpenAI, Anthropic adapters) | 3 weeks | Phase 4 |

### Phase 6: Scale (Weeks 27–32)
**Theme: Multi-user, cloud, ecosystem**

| Task | Effort | Depends on |
|---|---|---|
| Plugin architecture (modular packages) | 4 weeks | Phase 4 |
| Cloud architecture (hybrid local + cloud) | 10 weeks | Phase 5 |
| Multi-user support | 4 weeks | Phase 4 auth |
| Mobile PWA | 6 weeks | Phase 4 API |
| Obsidian plugin (API client) | 3 weeks | Phase 4 API |

### Summary timeline

```
Phase 1: Foundation        ─── Weeks 1-4       ████████░░░░░░░░░░░░░░░░░░░░░░
Phase 2: Retrieval         ─── Weeks 5-8       ░░░░░░░░████████░░░░░░░░░░░░░░
Phase 3: Quality           ─── Weeks 9-14      ░░░░░░░░░░░░░░░░████████████░░
Phase 4: Security/UI       ─── Weeks 15-18     ░░░░░░░░░░░░░░░░░░░░░░░░████░░
Phase 5: Intelligence      ─── Weeks 19-26     ░░░░░░░░░░░░░░░░░░░░░░░░░░░░████
Phase 6: Scale             ─── Weeks 27-32     ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░████
```

**Total estimated time: 32 weeks (8 months)** for full production-grade system. Phase 1 alone (4 weeks) addresses the most critical gaps and can be shipped as v1.1.
