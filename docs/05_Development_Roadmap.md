# LLM Wiki – Development Roadmap

> Priority-based roadmap derived from current implementation gaps. Every task includes description, dependencies, difficulty, effort, impact, and success criteria.

---

## Phase 1: Critical Fixes

**Theme:** Fix the gaps that will break the system at scale or silently corrupt data.

### 1.1 Add FAISS IVF Vector Index

| Field | Value |
|---|---|
| **Description** | Replace O(n) brute-force cosine search with FAISS IVF index. Keep the same `VectorStore` API but back it with FAISS for O(log n) search. IVF (Inverted File Index) with 100 centroids. |
| **Current status** | O(n) scan over all entries. Measured: ~0.1s at 10K entries, estimated ~1s at 100K. |
| **Dependencies** | `faiss-cpu` (pip package, ~50MB) |
| **Priority** | Critical |
| **Difficulty** | Low |
| **Effort** | 2 weeks |
| **Expected impact** | Search latency drops from O(n) to O(log n). 100K entries search in ~5ms instead of ~1s. |
| **Success criteria** | Search of 100K entries completes in <50ms. All existing vector store tests pass. FAISS index saves/loads correctly. |

### 1.2 Add Token Counting + LLM Prompt Truncation

| Field | Value |
|---|---|
| **Description** | Before sending source text to Ollama LLM, count tokens using Ollama's tokenizer endpoint or tiktoken. Truncate to fit within the model's context window (minus system prompt + expected output tokens). |
| **Current status** | Full source text sent regardless of length. No token counting anywhere. |
| **Dependencies** | None (tiktoken is pure Python, or use `ollama.Client().tokenize()`) |
| **Priority** | Critical |
| **Difficulty** | Low |
| **Effort** | 1 week |
| **Expected impact** | Prevents silent context overflow. Large documents (>8K tokens) are truncated gracefully instead of producing garbage or errors. |
| **Success criteria** | Document of 32K tokens is truncated to 7K before LLM call. Warning logged when truncation occurs. Token count tracked in metadata. |

### 1.3 Persist Knowledge Graph in Pipeline

| Field | Value |
|---|---|
| **Description** | Call `KnowledgeGraph.save()` in `IngestionWorkflow._run_knowledge_engine()` after building the graph. Load existing graph first, merge, then save. |
| **Current status** | `KnowledgeGraph.save()` and `load()` exist but are never called in the pipeline. Graph data is generated and discarded every run. |
| **Dependencies** | None (2 lines of code) |
| **Priority** | Critical |
| **Difficulty** | Trivial |
| **Effort** | 1 day |
| **Expected impact** | Knowledge graph accumulates across documents instead of being discarded. Enables cross-document graph queries. |
| **Success criteria** | After processing 3 documents, graph JSON file contains nodes from all 3. Loading and re-saving does not duplicate nodes. |

### 1.4 Implement Chunk Overlap

| Field | Value |
|---|---|
| **Description** | Use the declared-but-unused `overlap_chars` field in `SemanticChunker`. After splitting by headings/paragraphs/sentences, append `overlap_chars` characters from the end of the previous chunk to the start of the next chunk. |
| **Current status** | `overlap_chars: int = 200` declared at `semantic_chunking.py:23` but never read. |
| **Dependencies** | None |
| **Priority** | Critical |
| **Difficulty** | Low |
| **Effort** | 1 day |
| **Expected impact** | Chunks have context continuity. A sentence split across two chunks is preserved in both. |
| **Success criteria** | Adjacent chunks share `overlap_chars` characters of text. Total chunk count does not decrease (same splits, just overlapping). |

### 1.5 Atomic Vector Store Writes

| Field | Value |
|---|---|
| **Description** | Replace `VectorStore.save()` direct `write_text()` with atomic write: write to `.tmp` file, then `os.replace()`. |
| **Current status** | `vector_store.py:88` uses direct `write_text()`. Partial write on crash or power loss corrupts the entire store. |
| **Dependencies** | None |
| **Priority** | Critical |
| **Difficulty** | Trivial |
| **Effort** | 1 day |
| **Expected impact** | Vector store survives crash during save. Corrupted file is impossible (either old file or complete new file). |
| **Success criteria** | If process is killed during `save()`, the store file is either the old version or the complete new version, never a partial file. |

### 1.6 Require PyMuPDF with Clear Error for OCR

| Field | Value |
|---|---|
| **Description** | Make PyMuPDF a required dependency. Replace the silent fallback with a clear `ImportError` at module level when `fitz` cannot be imported and OCR processing is requested. |
| **Current status** | PyMuPDF is optional. Scanned PDF OCR silently returns empty text if not installed. |
| **Dependencies** | Add `PyMuPDF` to `pyproject.toml` dependencies |
| **Priority** | Critical |
| **Difficulty** | Trivial |
| **Effort** | 1 hour |
| **Expected impact** | Users get a clear error message instead of silently losing OCR content. |
| **Success criteria** | Without PyMuPDF, processing a scanned PDF raises `ImportError` with instructions to install. With PyMuPDF, OCR works as before. |

---

## Phase 2: Document Processing

**Theme:** Expand and harden document ingestion and processing.

### 2.1 MIME-Type Based Detection (Beyond Extension)

| Field | Value |
|---|---|
| **Description** | Add content-based MIME detection using `python-magic` (libmagic bindings). When extension is missing, ambiguous, or wrong, detect the real file type from content header bytes. Replace `mimetypes.guess_type()` in `classifier.py`. |
| **Current status** | Extension-only detection via `Path.suffix`. `mimetypes.guess_type()` provides a secondary signal but uses extension too. |
| **Dependencies** | `python-magic` pip package |
| **Priority** | High |
| **Difficulty** | Low |
| **Effort** | 3 days |
| **Expected impact** | Extensionless files, misnamed files (e.g., `.pdf` renamed to `.txt`), and unknown extensions are correctly classified. |
| **Success criteria** | A `.txt` file renamed to `.data` is still classified as text. Detection accuracy on 50 test files matches or exceeds extension-only. |

### 2.2 Language Detection for Source Documents

| Field | Value |
|---|---|
| **Description** | Add language detection to `DocumentIngestionService` using `fast-langdetect` or `lingua`. Store detected language in `DocumentMetadata.language`. Use in prompt building to instruct the LLM in the correct language. |
| **Current status** | `DocumentMetadata.language` exists as a field but is never populated. Prompt is always in English. |
| **Dependencies** | `fast-langdetect` or `lingua` |
| **Priority** | High |
| **Difficulty** | Low |
| **Effort** | 2 days |
| **Expected impact** | Non-English documents are analyzed in their source language instead of being forced through English prompts. |
| **Success criteria** | French text detected as French. LLM analysis prompt includes "answer in French". Language field populated in metadata. |

### 2.3 Intelligent Ingestion Hooks

| Field | Value |
|---|---|
| **Description** | Add pre/post processing hooks to `DocumentIngestionService`. Pre-hooks run before ingestion (validation, decryption). Post-hooks run after (normalization, enrichment). Hook registry allows plugins. |
| **Current status** | No hook system. All ingestors are standalone with no chaining. |
| **Dependencies** | Phase 1 complete |
| **Priority** | Medium |
| **Difficulty** | Medium |
| **Effort** | 1 week |
| **Expected impact** | Enables custom transformations without modifying core code. E.g., auto-decrypt `.gpg` files before ingestion, or auto-translate before analysis. |
| **Success criteria** | Pre-hook can reject a file (e.g., too large). Post-hook can modify text before analysis. Hook registry accepts plugin-style registration. |

### 2.4 Email Attachment Parsing

| Field | Value |
|---|---|
| **Description** | Extend `EmailIngestor` to extract and recursively process email attachments. Each attachment is routed through `DocumentIngestionService` as a sub-ingestion. |
| **Current status** | `.eml`/`.msg` files are read as plain text. Attachments are ignored. |
| **Dependencies** | Phase 1 complete |
| **Priority** | Medium |
| **Difficulty** | Medium |
| **Effort** | 1 week |
| **Expected impact** | Emails with PDF/CSV/image attachments are fully ingested instead of losing the attachments. |
| **Success criteria** | Email with 3 PDF attachments produces 1 note for the email body + 3 notes for the PDFs. Attachments are linked back to the parent email. |

---

## Phase 3: Chunking

**Theme:** Replace regex-based chunking with semantic, hierarchical, token-aware chunking.

### 3.1 NLP Sentence Segmentation

| Field | Value |
|---|---|
| **Description** | Replace regex sentence splitting (`(?<=[.!?])\s+(?=[A-Z\d])`) with spaCy or `nltk.tokenize.sent_tokenize()` for language-aware sentence boundaries. Handles abbreviations (Mr., Dr., U.S.A.), quotes, and non-period sentence terminators. |
| **Current status** | Simple regex in `semantic_chunking.py:14`. Breaks on abbreviations, ellipses, decimal numbers. |
| **Dependencies** | `spaCy` or `nltk` (spaCy recommended for quality) |
| **Priority** | High |
| **Difficulty** | Low |
| **Effort** | 3 days |
| **Expected impact** | Chunk boundaries align with actual sentence boundaries. No more broken chunks mid-abbreviation. |
| **Success criteria** | Text "Dr. Smith went to Washington. He arrived at 9:00 a.m." splits into 2 sentences (not 6). All existing chunking tests pass with new tokenizer. |

### 3.2 Hierarchical Chunk Structure

| Field | Value |
|---|---|
| **Description** | Store parent-child relationships: Document → Section → Chunk. Each chunk stores its parent section ID. Retrieval returns the parent section text alongside the matched chunk for context. |
| **Current status** | Flat chunk list. No hierarchy. No way to get the section context for a matched chunk. |
| **Dependencies** | Phase 3.1 (sentence segmentation) |
| **Priority** | High |
| **Difficulty** | Medium |
| **Effort** | 1 week |
| **Expected impact** | LLM gets full section context when answering from a chunk, significantly improving answer quality. |
| **Success criteria** | Each chunk has `parent_section_id`. `retrieve_with_context(chunk_id)` returns the chunk + its entire parent section text. API returns `section: "Attention Mechanisms"` alongside the matching text. |

### 3.3 Token-Aware Chunk Sizing

| Field | Value |
|---|---|
| **Description** | Replace character-based `max_chunk_chars` with token-based `max_chunk_tokens`. Use `tiktoken` or Ollama's tokenizer to count tokens. Target 512–1024 tokens per chunk. Chunk at sentence boundaries to stay within token budget. |
| **Current status** | Character-based (2000 chars ≈ 500 tokens for English). No token counting. |
| **Dependencies** | `tiktoken` or Ollama tokenizer endpoint |
| **Priority** | High |
| **Difficulty** | Low |
| **Effort** | 3 days |
| **Expected impact** | Chunks stay within model context window regardless of language (CJK languages need fewer chars per token). Consistent chunk sizes across documents. |
| **Success criteria** | Document in CJK language produces chunks of similar token count (512±128) despite having many more characters than an English doc. Token-aware chunking uses `tiktoken` `cl100k_base` encoding. |

### 3.4 Semantic Topic Segmentation

| Field | Value |
|---|---|
| **Description** | Add ML-based topic segmentation: embed sentence windows (3–5 sentences), compute cosine distance between adjacent windows, split at peaks. Merge small adjacent chunks of the same topic. |
| **Current status** | Heuristic-only (headings → paragraphs → sentences). No topic-awareness. |
| **Dependencies** | Phase 3.1 (sentence), Phase 3.3 (token), Embedding service |
| **Priority** | Medium |
| **Difficulty** | High |
| **Effort** | 2 weeks |
| **Expected impact** | Topic-coherent chunks even in documents without headings. Prevents topically unrelated content from being combined into one chunk. |
| **Success criteria** | A document without headings (e.g., a blog post) is split at topic shifts, not at arbitrary paragraph breaks. Within-chunk embedding cosine similarity ≥ 0.8. Between-chunk similarity ≤ 0.6. |

---

## Phase 4: Retrieval

**Theme:** Build a production-quality hybrid search system.

### 4.1 BM25 Sparse Retrieval

| Field | Value |
|---|---|
| **Description** | Add BM25 (Okapi BM25) sparse retrieval alongside dense vector search. Tokenize queries and documents, build inverted index with term frequencies + document frequencies. BM25 ranking formula. |
| **Current status** | Simple keyword overlap (`sum(1 for w in query_words if w in text)`) in `HybridSearch`. No IDF weighting. No tokenization. |
| **Dependencies** | None (pure Python implementation or `rank_bm25` package) |
| **Priority** | High |
| **Difficulty** | Low |
| **Effort** | 1 week |
| **Expected impact** | Keyword-exact matches are ranked correctly even when the embedding model lacks the term. Particularly important for technical terms, code, and proper nouns. |
| **Success criteria** | Search "Python async" ranks documents containing "Python" + "async" higher than documents about "threading" with 0.9 semantic similarity. BM25 hits are fused with dense hits via RRF. |

### 4.2 Reciprocal Rank Fusion (RRF)

| Field | Value |
|---|---|
| **Description** | Implement RRF to merge BM25 + Dense + (optional ColBERT) results. RRF score = Σ 1/(k + rank_i) for each result set. Default k=60. Returns top-k fused results. |
| **Current status** | No fusion. `HybridSearch` does a weighted sum of semantic + keyword scores. |
| **Dependencies** | Phase 4.1 (BM25) |
| **Priority** | High |
| **Difficulty** | Low |
| **Effort** | 2 days |
| **Expected impact** | Simple but effective fusion that doesn't require score normalization (RRF works on ranks, not scores). Typically outperforms weighted sum. |
| **Success criteria** | RRF with k=60 produces higher Recall@10 than either BM25 or dense alone. Fused results contain documents from both sources even if one source had low scores. |

### 4.3 Cross-Encoder Re-Ranking

| Field | Value |
|---|---|
| **Description** | Add a cross-encoder re-ranker (BGE-reranker-v2-m3 or Cohere rerank) after hybrid retrieval. First-stage retrieval returns top-100 candidates via BM25+dense. Cross-encoder scores top-50 by [CLS] query + candidate → relevance score. Final top-k by cross-encoder score. |
| **Current status** | Single-stage retrieval. No re-ranking. |
| **Dependencies** | Phase 4.2 (RRF) |
| **Priority** | Medium |
| **Difficulty** | Medium |
| **Effort** | 2 weeks |
| **Expected impact** | +10–20% relevance improvement over hybrid retrieval alone. Cross-encoders are the SOTA method for re-ranking. |
| **Success criteria** | NDCG@10 improves by ≥0.05 over hybrid retrieval without re-ranking. Cross-encoder scores 100 query-doc pairs in <5s on CPU. Re-ranker model is a local ONNX model (no API dependency). |

### 4.4 Query Rewriting

| Field | Value |
|---|---|
| **Description** | Before searching, send the user query to a small LLM (e.g., `qwen3:8b` or even a 1.5B model) with a prompt: "Generate 3 search variants for this query that would help find relevant information." Search all 3 variants in parallel, fuse results via RRF. |
| **Current status** | Not implemented. Raw user query searched directly. |
| **Dependencies** | Phase 1.2 (token counting, to budget the rewriting call) |
| **Priority** | High |
| **Difficulty** | Low |
| **Effort** | 1 week |
| **Expected impact** | Query "transformers" would also search "transformer architecture", "attention mechanism", "neural network transformers" — capturing documents that use different terminology. |
| **Success criteria** | Query "python async" also searches "asyncio", "async/await", "concurrent python". All 3 queries return results. Fused results rank higher than raw query alone. |

### 4.5 Metadata Filtering

| Field | Value |
|---|---|
| **Description** | Add structured filter support to search: filter by `source_type`, `date_range`, `tags`, `categories`, `difficulty`. Filters can be pre-filter (before vector search) or post-filter (after). Implement filter query syntax: `search("query", filter={"source_type": {"$in": ["pdf", "markdown"]}})`. |
| **Current status** | No filtering. `VectorStore.search()` scans all entries. |
| **Dependencies** | Phase 1.1 (FAISS, which supports ID-based filtering) |
| **Priority** | High |
| **Difficulty** | Medium |
| **Effort** | 1 week |
| **Expected impact** | Users can scope searches to specific sources, date ranges, or difficulty levels. Precision improves dramatically when filtering is applied. |
| **Success criteria** | `search("attention", filter={"source_type": "pdf"})` returns only PDF results. Filter + search completes in <50ms at 10K entries. |

### 4.6 Parent-Child Retrieval

| Field | Value |
|---|---|
| **Description** | When a chunk matches a query, return the parent section text as expanded context. Chunk is the "answer snippet", parent section is the "context window". LLM receives both. |
| **Current status** | Chunk only. No parent context. |
| **Dependencies** | Phase 3.2 (hierarchical chunk structure) |
| **Priority** | High |
| **Difficulty** | Low |
| **Effort** | 3 days |
| **Expected impact** | LLM answers are more accurate with section context. A chunk saying "it uses 8 heads" is meaningless alone — with the parent "Multi-Head Attention" section, it's clear. |
| **Success criteria** | Search result includes `matched_chunk.text`, `parent_section.heading`, `parent_section.text`. LLM query uses parent section as context window. |

### 4.7 Wire Search into CLI

| Field | Value |
|---|---|
| **Description** | Add `pam search <query>` CLI command. Accepts: `--top-k`, `--filter`, `--source-type`, `--min-score`. Uses `SemanticSearch` or `HybridSearch`. Displays results as a rich table with score, source, and snippet. |
| **Current status** | `SemanticSearch` and `HybridSearch` exist as library classes only. No CLI binding, no API, no way to search from the command line. |
| **Dependencies** | Phase 1.1 (FAISS for speed) |
| **Priority** | High |
| **Difficulty** | Low |
| **Effort** | 3 days |
| **Expected impact** | This is the core user-facing feature: semantic search over the user's wiki. Without it, the vector store is invisible to the user. |
| **Success criteria** | `pam search "attention mechanism"` returns top-5 results with source, score, and 200-char snippet. `pam search "python" --source-type pdf --top-k 3` returns 3 filtered PDF results. |

---

## Phase 5: Knowledge Graph

**Theme:** Make the knowledge graph persistent, queryable, and useful.

### 5.1 Graph Persistence + Cross-Document Merging

| Field | Value |
|---|---|
| **Description** | After Phase 1.3 (basic save), add proper merge-on-write: load existing graph, de-duplicate nodes by ID, add new edges, save. Handle conflict resolution (same node from different sources — merge metadata). |
| **Current status** | Phase 1.3 adds basic save. No merge strategy for conflicting node metadata. |
| **Dependencies** | Phase 1.3 |
| **Priority** | High |
| **Difficulty** | Medium |
| **Effort** | 1 week |
| **Expected impact** | Graph accumulates knowledge correctly across documents. Same concept mentioned in 5 documents has 1 node (with merged metadata from all 5). |
| **Success criteria** | Node with same ID from 2 documents has metadata merged (not overwritten). Edge count = sum of unique edges (no duplicates). Graph file is valid JSON after every write. |

### 5.2 Graph Query (Cypher-like)

| Field | Value |
|---|---|
| **Description** | Add a simple graph query API: `graph.query("MATCH (n:concept)-[:mentioned_in]->(m:note) WHERE n.label = 'Attention' RETURN m")`. Implement as method chaining or simple pattern matching over the in-memory graph. Not a full Cypher engine — a Python API. |
| **Current status** | Only `neighbors()` and `subgraph()` methods. No declarative query interface. |
| **Dependencies** | Phase 5.1 |
| **Priority** | Medium |
| **Difficulty** | Medium |
| **Effort** | 2 weeks |
| **Expected impact** | Enables cross-document discovery: "find all notes related to concept X", "what entities appear in the same documents as concept Y". |
| **Success criteria** | `graph.query(start_node="concept::attention", edge_type="mentioned_in", target_type="note")` returns all note nodes connected via `mentioned_in` edges. Query with no matches returns empty result (not an error). |

### 5.3 Entity Resolution

| Field | Value |
|---|---|
| **Description** | Add entity resolution when merging graphs. Detect when two nodes refer to the same real-world entity despite different labels. Use: (1) exact label match, (2) fuzzy label match (Levenshtein), (3) embedding similarity of node descriptions. Merge nodes that pass confidence threshold. |
| **Current status** | No resolution. "Apple" (company) and "apple" (fruit) create separate nodes with no distinction. Typos create duplicate nodes. |
| **Dependencies** | Phase 5.1 |
| **Priority** | Medium |
| **Difficulty** | High |
| **Effort** | 3 weeks |
| **Expected impact** | No duplicate concepts. "supply-side economics" and "supply side economics" resolve to the same node. "Transformer" in electronics vs ML disambiguated by context. |
| **Success criteria** | "Supply-side" and "supply side" detected as same entity (>=0.9 similarity). Disambiguation: "transformer" in an electronics document vs ML document stays as separate nodes (human review flag). Fuzzy match precision >= 0.95 at threshold 0.9. |

### 5.4 Graph-Augmented Retrieval

| Field | Value |
|---|---|
| **Description** | Before LLM answer generation, traverse the knowledge graph from relevant nodes to find related concepts and notes. Include the subgraph in the LLM context. Example: query "attention" → vector search finds chunk → graph traversal finds related notes on "self-attention", "transformer", "BERT" → all included in context. |
| **Current status** | Not implemented. No graph awareness in the query/answer pipeline. |
| **Dependencies** | Phase 5.2 (graph query), Phase 4 (retrieval) |
| **Priority** | Low |
| **Difficulty** | High |
| **Effort** | 3 weeks |
| **Expected impact** | LLM answers incorporate knowledge from related notes that the query didn't explicitly mention. Catches relationships that vector similarity alone misses. |
| **Success criteria** | Query "explain attention" returns an answer that references "transformer" even though no retrieved chunk mentions it (because the graph connects "attention" → "transformer"). Answer quality (human-rated) improves >= 1 point on 5-point scale. |

---

## Phase 6: Image Intelligence

**Theme:** Move from basic vision-model OCR to comprehensive image understanding.

### 6.1 Image Preprocessing Pipeline

| Field | Value |
|---|---|
| **Description** | Add preprocessing before sending images to vision model: deskew (correct rotation), denoise (Gaussian/median filter), binarize (Otsu threshold for document images), contrast enhancement (CLAHE). Configurable pipeline stages. |
| **Current status** | Raw image bytes sent to vision model. No preprocessing. Noisy/dark/rotated images produce poor OCR. |
| **Dependencies** | `opencv-python` or `pillow` + `scikit-image` |
| **Priority** | Medium |
| **Difficulty** | Medium |
| **Effort** | 2 weeks |
| **Expected impact** | OCR accuracy on real-world photos of documents (which are often rotated, shadowed, noisy) improves significantly. |
| **Success criteria** | Rotated image (5°) deskewed before OCR. Dark image (underexposed) enhanced via CLAHE. Before/after character error rate measured on 20 test images — preprocessing reduces CER by >= 25%. |

### 6.2 Full-Page OCR via Tesseract

| Field | Value |
|---|---|
| **Description** | Add Tesseract OCR as a local alternative (or complement) to vision-model OCR. Tesseract is faster, lighter, and runs without GPU. Use `pytesseract` wrapper. Fall back to vision model for handwritten or unusual fonts. |
| **Current status** | Vision-model-only OCR. PyMuPDF renders pages at 2x zoom, sends to vision model. 5-page limit. |
| **Dependencies** | Tesseract OCR engine + `pytesseract` |
| **Priority** | Medium |
| **Difficulty** | Medium |
| **Effort** | 2 weeks |
| **Expected impact** | Printed document OCR drops from ~15s/page (vision model) to ~1s/page (Tesseract). No GPU required. No page limit. |
| **Success criteria** | Tesseract OCR completes 50-page PDF in <60s. Character error rate on printed documents <= 5%. Vision model used as fallback when Tesseract confidence < 80% per page. |

### 6.3 Layout Preservation (OCR Output)

| Field | Value |
|---|---|
| **Description** | Add document layout analysis: detect columns, headers, footers, page numbers, footnotes. Preserve reading order (left-to-right, top-to-bottom across columns). Output structured text with column breaks, page breaks, and section markers. Use PyMuPDF layout analysis or layoutparser. |
| **Current status** | Flat text extraction. No column detection. Multi-column PDFs produce interleaved text (left column line 1, right column line 1 = adjacent in output). |
| **Dependencies** | Phase 6.2 (Tesseract) or layoutparser |
| **Priority** | Medium |
| **Difficulty** | High |
| **Effort** | 3 weeks |
| **Expected impact** | Multi-column documents are readable after OCR. Headers/footers are identified and can be stripped or preserved as metadata. |
| **Success criteria** | Two-column academic paper produces left column text first, then right column text. Headers and page numbers detected and optionally removed. Footnotes preserved adjacent to their reference. |

### 6.4 Diagram-to-Mermaid Conversion

| Field | Value |
|---|---|
| **Description** | For diagram files (.drawio, .vsdx), parse the XML/vector format to extract shapes, connectors, and labels. Convert to Mermaid.js text representation for inclusion in the Obsidian note. |
| **Current status** | DiagramIngestor reads .drawio XML and .vsdx as raw text. No structure parsing. Diagram content is unreadable in generated notes. |
| **Dependencies** | XML parsing (stdlib) |
| **Priority** | Low |
| **Difficulty** | High |
| **Effort** | 3 weeks |
| **Expected impact** | Architecture diagrams become readable Mermaid flowcharts in generated notes instead of raw XML. |
| **Success criteria** | Simple .drawio with 3 boxes and 2 arrows produces valid Mermaid flowchart. Complex .vsdx with swimlanes produces structured diagram text. Conversion preserves labels and connector direction. |

---

## Phase 7: Table Intelligence

**Theme:** Extract, preserve, and query table data.

### 7.1 Table Detection in PDFs

| Field | Value |
|---|---|
| **Description** | Add table detection to PDF processing using Camelot or Tabula-py. Detect table regions in PDF pages, extract cell boundaries, handle merged cells, multi-page tables. |
| **Current status** | PDFs extracted as flat text via pypdf. Tables appear as jumbled text with no structure. |
| **Dependencies** | `camelot-py` or `tabula-py` (requires Java for Tabula) |
| **Priority** | High |
| **Difficulty** | Medium |
| **Effort** | 2 weeks |
| **Expected impact** | Tables in PDFs are extracted as structured data instead of unreadable text. Critical for academic papers, financial reports, and data sheets. |
| **Success criteria** | PDF with a 10-row × 4-column table produces a parsed table with 10 rows and 4 columns. Multi-page table (continues across 2 pages) detected as one table. Merged cells are preserved. Table confidence reported per extraction. |

### 7.2 Table-to-Markdown Formatting

| Field | Value |
|---|---|
| **Description** | Convert extracted table data to Markdown table format for Obsidian notes. Table becomes a readable Markdown table with aligned columns, header row, and separator line. |
| **Current status** | Tables are flat text in notes — unreadable. |
| **Dependencies** | Phase 7.1 (table detection) |
| **Priority** | High |
| **Difficulty** | Low |
| **Effort** | 2 days |
| **Expected impact** | Table data is readable in the generated Obsidian note. Users can copy-paste into spreadsheets. |
| **Success criteria** | `[[Model, Accuracy, Speed], [BERT, 92%, 10ms]]` becomes `\| Model \| Accuracy \| Speed \|\n\|-------\|----------\|-------\|\n\| BERT  \| 92%      \| 10ms  \|`. Table is visually correct in Obsidian preview. |

### 7.3 Table-as-Vector Embedding

| Field | Value |
|---|---|
| **Description** | Encode parsed tables as structured text representations for embedding: serialize as `{columns: [col1, col2], rows: [[v1, v2], [v3, v4]]}`, then embed via text encoder. Enable "find all tables where column X > Y" via metadata filtering combined with vector search. |
| **Current status** | Tables have no special embedding strategy. They are chunked like regular text, losing all structure. |
| **Dependencies** | Phase 7.1, Phase 4.5 (metadata filtering) |
| **Priority** | Low |
| **Difficulty** | Medium |
| **Effort** | 2 weeks |
| **Expected impact** | Users can search for tables by content: "benchmark table with BERT accuracy" finds the right table even when the surrounding text doesn't mention it. |
| **Success criteria** | Table query returns the table chunk as the top result. Table embedding captures column semantics (a table about "model accuracy" and one about "model latency" have different embeddings even with identical row formats). |

---

## Phase 8: Evaluation

**Theme:** Measure quality objectively. Catch regressions automatically.

### 8.1 Retrieval Evaluation Framework

| Field | Value |
|---|---|
| **Description** | Implement `RetrievalEvaluator` class with precision@k, recall@k, MRR, NDCG@k. Create labeled query-document evaluation dataset (20+ queries with known relevant results). Wire into `pam eval` CLI and CI. |
| **Current status** | No retrieval evaluation exists. No way to measure whether search is improving or regressing. |
| **Dependencies** | Phase 4 (retrieval) |
| **Priority** | High |
| **Difficulty** | Medium |
| **Effort** | 3 weeks |
| **Expected impact** | Every change to chunking, embeddings, or search can be evaluated numerically. Data-driven decisions replace guesswork. |
| **Success criteria** | `pam eval retrieval` runs evaluation and reports precision@5, recall@10, MRR, NDCG@10. Same query set produces comparable results across runs. CI blocks PR if any metric drops >5%. |

### 8.2 LLM Analysis Quality Evaluation

| Field | Value |
|---|---|
| **Description** | Create evaluation dataset of 10–20 documents with known expected analysis fields. Run pipeline, compare actual vs expected: field completion rate (what % of fields were filled), field correctness (validated against known answers), reading time accuracy. |
| **Current status** | LLM analysis quality is only informally evaluated via `intelligence_test.py` — it checks section presence, not correctness. |
| **Dependencies** | None (uses existing pipeline) |
| **Priority** | High |
| **Difficulty** | Medium |
| **Effort** | 2 weeks |
| **Expected impact** | Prompt changes, model changes, or chunking changes can be evaluated for their effect on analysis quality. |
| **Success criteria** | Evaluation dataset of 15 documents with known analysis values. `pam eval analysis` reports field completion rate, correctness rate, and reading time error. CI gates on >= 80% completion rate. |

### 8.3 Chunking Quality Metric

| Field | Value |
|---|---|
| **Description** | Implement chunk quality metrics: (1) within-chunk coherence — mean cosine similarity between sentences in the same chunk, (2) between-chunk distinction — mean cosine distance between adjacent chunks, (3) chunk size distribution — stddev of token counts across chunks. |
| **Current status** | No chunking quality metrics. Only existence tests ("chunks were created"). |
| **Dependencies** | Phase 3 (chunking) |
| **Priority** | Medium |
| **Difficulty** | Low |
| **Effort** | 3 days |
| **Expected impact** | Chunking strategy changes can be evaluated objectively. "Is this chunking better?" becomes a data question. |
| **Success criteria** | Coherence score reported per document. High-quality chunking (headings present) scores >0.8 coherence. Low-quality (no headings, random splits) scores <0.5. |

### 8.4 Hallucination Rate Detection

| Field | Value |
|---|---|
| **Description** | Compare LLM analysis claims against source text. Use NLP techniques: extract factual claims from analysis, search for supporting evidence in source, flag unsupported claims. Start simple (keyword matching) and layer in NLI models (cross-encoder NLI). |
| **Current status** | No hallucination detection. LLM output is accepted as-is. |
| **Dependencies** | Phase 8.2 (analysis quality framework) |
| **Priority** | Medium |
| **Difficulty** | High |
| **Effort** | 4 weeks |
| **Expected impact** | Catches when the LLM invents facts or entities not present in the source. Critical for trust in the system. |
| **Success criteria** | Hallucination detection flags >80% of injected false claims in test data. False positive rate < 10%. Flagged hallucinations are surfaced in the CLI output and in a "confidence" section of the generated note. |

---

## Phase 9: Production Readiness

**Theme:** Docker, security, monitoring, deployment.

### 9.1 Docker Compose Setup

| Field | Value |
|---|---|
| **Description** | Create `Dockerfile` for PAM app + `docker-compose.yml` with Ollama service. One-command startup: `docker compose up`. Mount volumes for vault and config. Health checks between services. |
| **Current status** | Manual `uv run` only. Python environment must be set up manually. Ollama must be installed separately. |
| **Dependencies** | None |
| **Priority** | High |
| **Difficulty** | Low |
| **Effort** | 1 week |
| **Expected impact** | New users can start the entire system (app + Ollama) with one command. Eliminates "works on my machine" problems. |
| **Success criteria** | `docker compose up -d` starts PAM + Ollama. `docker compose exec pam pam status` shows connected Ollama. Vault directory is mounted and persists across restarts. |

### 9.2 FastAPI Web App + REST API

| Field | Value |
|---|---|
| **Description** | Add FastAPI application with REST endpoints: `POST /ingest`, `GET /search`, `GET /notes`, `GET /status`, `GET /health`. Same business logic as CLI, exposed via HTTP. Auto-generated OpenAPI docs. |
| **Current status** | CLI-only. No HTTP interface, no web access. |
| **Dependencies** | Phase 9.1 (Docker) |
| **Priority** | Medium |
| **Difficulty** | Medium |
| **Effort** | 3 weeks |
| **Expected impact** | Enables web UI, remote access, Obsidian plugin integration. API consumers can use the system programmatically. |
| **Success criteria** | `POST /ingest` with file upload returns note URL. `GET /search?q=attention` returns JSON results with scores. `GET /health` returns 200 when Ollama is connected. OpenAPI docs at `/docs`. |

### 9.3 Basic Web UI

| Field | Value |
|---|---|
| **Description** | Minimal web UI (React or plain HTML/JS): search bar, file upload, note browser. User can search the wiki, upload a new document, and navigate generated notes. |
| **Current status** | No web UI. Terminal-only. |
| **Dependencies** | Phase 9.2 (REST API) |
| **Priority** | Medium |
| **Difficulty** | Medium |
| **Effort** | 4 weeks |
| **Expected impact** | The system becomes accessible to non-technical users. File upload via drag-and-drop instead of CLI commands. |
| **Success criteria** | User can drag a PDF onto the browser → note appears in vault. Search box returns results with clickable links. Note browser shows all generated notes with search/filter. |

### 9.4 Authentication + Rate Limiting

| Field | Value |
|---|---|
| **Description** | Add JWT-based authentication to the REST API. Registration/login endpoints. Rate limiting per user (50 req/min for search, 10 req/min for ingest). API key support for programmatic access. |
| **Current status** | No authentication. Any process on localhost can use the system. No access control. |
| **Dependencies** | Phase 9.2 (REST API) |
| **Priority** | Medium |
| **Difficulty** | Medium |
| **Effort** | 2 weeks |
| **Expected impact** | Safe to expose the API to a network. Multi-user isolation (each user sees their own vault). |
| **Success criteria** | Unauthenticated request returns 401. Authenticated request with expired token returns 401. Rate-limited client receives 429 after exceeding limit. Token refresh works. |

### 9.5 Monitoring + Observability

| Field | Value |
|---|---|
| **Description** | Add OpenTelemetry instrumentation: traces for pipeline steps, metrics for ingestion duration / LLM latency / search latency / error rates. Prometheus metrics endpoint. Structured JSON logging with correlation IDs. |
| **Current status** | Basic Python logging. No metrics, no tracing, no correlation IDs. |
| **Dependencies** | None (log format change is independent) |
| **Priority** | Low |
| **Difficulty** | Medium |
| **Effort** | 2 weeks |
| **Expected impact** | Pipeline failures can be traced to the exact step. Performance regressions visible in dashboards. Error rate trends visible over time. |
| **Success criteria** | Each pipeline run has a trace ID logged at every step. Prometheus endpoint at `/metrics`. Ingestion duration histogram with p50/p95/p99 labels. Error counter incremented on every failure with error type label. |

### 9.6 Cloud LLM Provider Support

| Field | Value |
|---|---|
| **Description** | Add OpenAI, Anthropic, and Google Gemini provider adapters behind a common `LLMProvider` interface. Configurable at settings level: `llm.provider = "ollama"` or `"openai"`. API keys via environment variables. |
| **Current status** | Ollama-only. No alternative LLM backends. |
| **Dependencies** | Phase 9.2 (for API key management) |
| **Priority** | Low |
| **Difficulty** | Medium |
| **Effort** | 3 weeks |
| **Expected impact** | Users can use GPT-4o or Claude for analysis if they prefer cloud models. Fallback if local Ollama is unavailable. |
| **Success criteria** | `PAM_LLM__PROVIDER=openai` switches to GPT-4o for analysis. Same `DocumentAnalysis` output schema regardless of provider. Token usage and cost reported per analysis. |

---

## Milestone Table

| Task | Priority | Difficulty | Est. Time | Phase | Status |
|---|---|---|---|---|---|
| FAISS IVF vector index | Critical | Low | 2 weeks | 1 | Pending |
| Token counting + truncation | Critical | Low | 1 week | 1 | Pending |
| KG persistence in pipeline | Critical | Trivial | 1 day | 1 | Pending |
| Chunk overlap implementation | Critical | Low | 1 day | 1 | Pending |
| Atomic vector store writes | Critical | Trivial | 1 day | 1 | Pending |
| PyMuPDF as required dependency | Critical | Trivial | 1 hour | 1 | Pending |
| MIME-type detection | High | Low | 3 days | 2 | Pending |
| Language detection | High | Low | 2 days | 2 | Pending |
| Ingestion hooks | Medium | Medium | 1 week | 2 | Pending |
| Email attachment parsing | Medium | Medium | 1 week | 2 | Pending |
| NLP sentence segmentation | High | Low | 3 days | 3 | Pending |
| Hierarchical chunk structure | High | Medium | 1 week | 3 | Pending |
| Token-aware chunk sizing | High | Low | 3 days | 3 | Pending |
| Semantic topic segmentation | Medium | High | 2 weeks | 3 | Pending |
| BM25 sparse retrieval | High | Low | 1 week | 4 | Pending |
| Reciprocal Rank Fusion | High | Low | 2 days | 4 | Pending |
| Cross-encoder re-ranking | Medium | Medium | 2 weeks | 4 | Pending |
| Query rewriting | High | Low | 1 week | 4 | Pending |
| Metadata filtering | High | Medium | 1 week | 4 | Pending |
| Parent-child retrieval | High | Low | 3 days | 4 | Pending |
| Wire search into CLI | High | Low | 3 days | 4 | Pending |
| Graph persistence + merge | High | Medium | 1 week | 5 | Pending |
| Graph query API | Medium | Medium | 2 weeks | 5 | Pending |
| Entity resolution | Medium | High | 3 weeks | 5 | Pending |
| Graph-augmented retrieval | Low | High | 3 weeks | 5 | Pending |
| Image preprocessing | Medium | Medium | 2 weeks | 6 | Pending |
| Tesseract full-page OCR | Medium | Medium | 2 weeks | 6 | Pending |
| Layout preservation | Medium | High | 3 weeks | 6 | Pending |
| Diagram-to-Mermaid | Low | High | 3 weeks | 6 | Pending |
| Table detection in PDFs | High | Medium | 2 weeks | 7 | Pending |
| Table-to-Markdown | High | Low | 2 days | 7 | Pending |
| Table-as-vector embedding | Low | Medium | 2 weeks | 7 | Pending |
| Retrieval evaluation framework | High | Medium | 3 weeks | 8 | Pending |
| LLM analysis quality eval | High | Medium | 2 weeks | 8 | Pending |
| Chunking quality metric | Medium | Low | 3 days | 8 | Pending |
| Hallucination detection | Medium | High | 4 weeks | 8 | Pending |
| Docker Compose setup | High | Low | 1 week | 9 | Pending |
| FastAPI + REST API | Medium | Medium | 3 weeks | 9 | Pending |
| Basic web UI | Medium | Medium | 4 weeks | 9 | Pending |
| Auth + rate limiting | Medium | Medium | 2 weeks | 9 | Pending |
| Monitoring + observability | Low | Medium | 2 weeks | 9 | Pending |
| Cloud LLM providers | Low | Medium | 3 weeks | 9 | Pending |

---

## Recommended Implementation Order

```
Week  1-2  ██  Phase 1: Critical Fixes
                 1.6 PyMuPDF required      (1hr)
                 1.5 Atomic vector writes   (1 day)
                 1.3 KG persistence         (1 day)
                 1.4 Chunk overlap          (1 day)
                 1.2 Token counting         (1 week)
                 1.1 FAISS index            (2 weeks)
                 └─ Then: Wire search into CLI

Week  3-4  ██  Phase 2: Document Processing
                 2.1 MIME detection        (3 days)
                 2.2 Language detection    (2 days)
                 2.3 Ingestion hooks       (1 week)
                 2.4 Email attachments     (1 week)

Week  5-7  ███  Phase 3: Chunking
                 3.1 NLP sentence seg     (3 days)
                 3.3 Token-aware sizing   (3 days)
                 3.2 Hierarchical chunks  (1 week)
                 3.4 Semantic topics      (2 weeks)

Week  8-11 ████ Phase 4: Retrieval
                 4.1 BM25                (1 week)
                 4.2 RRF                 (2 days)
                 4.4 Query rewriting     (1 week)
                 4.5 Metadata filtering  (1 week)
                 4.6 Parent-child ret.   (3 days)
                 4.3 Cross-encoder       (2 weeks)

Week 12-13 ██   Phase 5: Knowledge Graph
                 5.1 Graph merge         (1 week)
                 5.2 Graph query         (2 weeks)
                 5.3 Entity resolution   (3 weeks)
                 5.4 Graph-augmented ret.(3 weeks)

Week 14-16 ███  Phase 6: Image Intelligence
                 6.1 Image preprocessing (2 weeks)
                 6.2 Tesseract OCR       (2 weeks)
                 6.3 Layout preservation (3 weeks)
                 6.4 Diagram conversion  (3 weeks)

Week 16    █    Phase 7: Table Intelligence
                 7.2 Table-to-Markdown   (2 days)
                 7.1 Table detection     (2 weeks)
                 7.3 Table embedding     (2 weeks)

Week 17-19 ███  Phase 8: Evaluation
                 8.3 Chunking metric     (3 days)
                 8.2 LLM quality eval    (2 weeks)
                 8.1 Retrieval eval      (3 weeks)
                 8.4 Hallucination       (4 weeks)

Week 20-24 █████ Phase 9: Production Readiness
                 9.1 Docker             (1 week)
                 9.2 FastAPI + REST     (3 weeks)
                 9.3 Web UI             (4 weeks)
                 9.4 Auth + rate limit  (2 weeks)
                 9.5 Monitoring         (2 weeks)
                 9.6 Cloud LLMs         (3 weeks)
```

### Priority rationale for early phases:

1. **Phase 1 first** — Every task here fixes a correctness or data-loss bug. Without these, adding features on top is building on sand.
2. **Phase 4 (search CLI) immediately after Phase 1.1** — FAISS index + search CLI is the first user-visible feature. This is the core value proposition.
3. **Phase 3 before Phase 4.6** — Parent-child retrieval depends on hierarchical chunks.
4. **Phase 8 after Phase 4** — Cannot evaluate what doesn't exist. Retrieval evaluation must come after retrieval is built.
5. **Phase 9 (Docker + API) in parallel with Phase 8** — Docker setup is independent. Web UI depends on API.
6. **Phases 5–7 (KG, Images, Tables) can proceed in parallel** — No cross-dependencies between graph, image, and table work. Each can be done concurrently by different people.

### Milestone releases:

| Release | Phases | Timeline | What ships |
|---|---|---|---|
| **v1.1** | Phase 1 | Week 2 | Critical bug fixes. No new features. |
| **v1.2** | Phase 1.1 + 4.7 | Week 3 | Search CLI — first user-facing search. |
| **v2.0** | Phase 2–4 | Week 11 | Intelligent chunking + hybrid search + better ingestion. |
| **v2.1** | Phase 5 | Week 13 | Persistent, queryable knowledge graph. |
| **v3.0** | Phase 6–7 | Week 16 | Image and table intelligence. |
| **v3.1** | Phase 8 | Week 19 | Evaluation framework + quality gates. |
| **v4.0** | Phase 9 | Week 24 | Docker, REST API, Web UI, auth, monitoring. |
