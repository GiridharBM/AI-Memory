# PAM V1 → V1.1 Improvement Roadmap

> **Document type:** Planning Document Only
> **Created:** 2026-08-18
> **Source basis:** `01_PROJECT_AND_INGESTION_REFERENCE.md`, `02_EMBEDDINGS_VECTORS_AND_STORAGE.md`, `03_RETRIEVAL_RAG_AND_KNOWLEDGE_GRAPH.md`, `04_CLI_MODELS_LIMITS_TESTING_AND_OPERATIONS.md`, `VERSION_1_COMPLETE_FINAL_REPORT.md`, `06_PAM_V1_BEGINNER_TO_TECHNICAL_GUIDE.md`
> **Verification:** Every recommendation verified against actual source code.

---

# 1. CURRENT V1 BASELINE

## What Already Works

PAM V1.0.0 is a **frozen local MVP** with 1375 tests, 89.80% line coverage, and a clean CLI interface. The following is verified working:

### Ingestion Pipeline (12-step)
- File detection, classification (24 source types, 90+ extensions), routing to 20 specialized processors
- Text extraction from PDF, Markdown, TXT, HTML, DOCX, PPTX, EPUB, IPYNB, EML, LaTeX, BibTeX, RIS
- AI enrichment via Ollama `qwen3:8b` producing `DocumentAnalysis` with 21 fields
- Semantic chunking (heading-aware, block-aware, sentence-aware) with 200-char tail overlap
- SHA-256 content hashing for deduplication at manifest level

### Embeddings & Vector Storage
- `nomic-embed-text` 768-dimensional embeddings via local Ollama
- In-memory vector store with cosine similarity search
- Atomic JSON persistence (`vector_store.json`) with corruption recovery

### Retrieval & QA
- Hybrid search: dense vector + BM25 lexical + Reciprocal Rank Fusion (k=60)
- BM25 with Okapi scoring (k1=1.5, b=0.75)
- Context window: 8 chunks max, 12,000 chars max
- QA via `qwen3:8b` with system-prompt grounding and `[SOURCE N]` citation format
- CLI-accessible: `pam search` and `pam ask` with `--top-k`, `--min-score`, `--filter`, `--source-type`

### Multimodal
- Vision model (`qwen2.5vl`) for image understanding and OCR
- Tesseract fallback for text extraction
- Code analysis with AST (Python) and heuristic regex (others)
- Audio transcription via `faster-whisper` (runtime dependency)

### Watcher & Queue
- Filesystem watcher (`watchdog`) on configurable inbox directory
- Thread-safe queue with persistence, single worker, failure handling
- Files moved to `data/processed/` or `data/failed/` on completion/failure

### Obsidian Integration
- Auto-generated wiki-linked Markdown notes with graph summary sections
- Vault writer with upsert behavior (preserves user edits)

### Operations
- `pam status`, `pam doctor`, `pam config`, `pam config-show`
- Structured JSON logging with component-specific log files and rotation
- Rich CLI tables and error messages

### Quality
- 1375 tests, 89.80% line coverage
- CI on GitHub Actions: ruff lint, mypy type check, pytest+coverage (Python 3.11/3.12/3.13)

---

# 2. CURRENT WEAKNESSES

## Critical

| # | Weakness | Evidence | Impact |
|---|----------|----------|--------|
| C1 | **Knowledge graph built but never used in retrieval** | `search.py` (276 lines) and `qa_workflow.py` (127 lines) have zero references to `KnowledgeGraph`. Graph is dead weight during QA. | Ingestion wastes time building a graph that provides zero retrieval value. |
| C2 | **No vector deletion or GC** | `VectorStore.remove(entry_id)` exists (`vector_store.py:86-92`) but no `remove_by_source()`. No orphan cleanup. Deleted/modified files leave vectors forever. | Storage grows monotonically. Stale vectors pollute search results. |
| C3 | **Video files produce no searchable content** | Video ingestion enters AI processing with empty text, which fails. No audio extraction, no frame extraction, no caption extraction. | Users who drop video files get silent failures or empty results. |

## High

| # | Weakness | Evidence | Impact |
|---|----------|----------|--------|
| H1 | **No reranking** | Searched for `rerank`, `cross.?encoder`, `colbert`, `cohere` across all `app/**/*.py` — zero results. Pipeline: dense+BM25→RRF→return. | Retrieval quality capped at RRF fusion accuracy. |
| H2 | **No query rewriting or expansion** | Searched for `query.?rewrite`, `query.?expand`, `HyDE`, `hypothetical` — zero results. Raw query embedded as-is (`search.py:262`). | "handwriting" won't match "handwritten"; morphological variants missed. |
| H3 | **No retrieval quality evaluation** | No Recall@K, Precision@K, MRR, NDCG, faithfulness, groundedness, or hallucination measurement anywhere. | Cannot measure if improvements help or hurt. Flying blind. |
| H4 | **`MAX_CONTEXT_CHUNKS=8` and `MAX_CONTEXT_CHARS=12_000` hardcoded** | `qa_workflow.py:16-17` — module-level constants, not in config, not overridable. | Cannot tune context window for different query complexity or model sizes. |
| H5 | **Embedding cache absent** | `embeddings.py` (101 lines) — zero caching. Every search re-embeds query via Ollama. Cross-doc link detection re-embeds already-embedded chunks (`ingest_workflow.py:973-996`). | Unnecessary latency and compute on repeated queries. |
| H6 | **BM25 uses hardcoded regex tokenizer, no stemming** | `bm25.py:13` — `_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")`. No stemming, no stop-word removal, no language awareness. | Morphological variants (running/run/ran) not matched. |
| H7 | **`pam status` counters always show 0** | `entry.py:154-156` — "Processed today", "Skipped duplicates", "Failed today" are runtime-only (`RuntimeStats` in `stats.py`), not persisted, always hardcoded to "0". | Users cannot see processing stats without checking logs. |

## Medium

| # | Weakness | Evidence | Impact |
|---|----------|----------|--------|
| M1 | **RRF k=60 not configurable** | `search.py:187` — constructor parameter exists but not exposed to config or CLI. | Cannot tune fusion behavior for different corpus sizes. |
| M2 | **BM25 k1=1.5, b=0.75 not configurable** | `bm25.py` — hardcoded in tokenizer/index. | Cannot tune lexical matching for different document types. |
| M3 | **No dimension enforcement** | `vector_store.py:68-77` — `add()`/`add_batch()` store whatever vector is provided. `vector_store.py:115` — dimension mismatch silently returns score 0.0. | Switching embedding models silently breaks all queries against old vectors. |
| M4 | **Metadata filtering is exact-match only** | `search.py:69-80` — `_hit_matches_filter()` does exact string match. Comments note "$in/range syntax is roadmap 4.5" (`search.py:72`). | Cannot filter by date range, numeric thresholds, or partial matches. |
| M5 | **No LLM response cache** | Every `pam ask` call hits Ollama even for identical questions. | Redundant compute for repeated queries. |
| M6 | **No streaming for LLM responses** | Full response buffered before display. | Long answers appear to hang with no feedback. |
| M7 | **Undeclared dependencies** | `faster-whisper`, `python-docx`, `python-pptx` not in `requirements.txt` / `pyproject.toml`. | Silent failures when these are not installed. |
| M8 | **Watcher monitors 53 of 90+ classified extensions** | `config/default.yaml:37-95` — watcher `supported_extensions` is subset of `PROCESSABLE_EXTENSIONS`. `.docx`, `.ipynb`, `.eml`, `.bib`, `.ris`, `.tex`, `.html` are ingestible but watcher-inaccessible. | Users must manually extend config to watch all ingestible types. |
| M9 | **PDF-embedded images extracted but never understood** | Images stored as metadata but not processed by vision model. | Images in PDFs contribute nothing to search or QA. |

## Low

| # | Weakness | Evidence | Impact |
|---|----------|----------|--------|
| L1 | **No Docker support** | No `Dockerfile` or `docker-compose.yml` anywhere in workspace. | Cannot containerize for reproducible deployment. |
| L2 | **macOS untested** | CI runs on ubuntu-latest only. No macOS testing evidence. | Platform-specific bugs may exist undetected. |
| L3 | **`os.replace()` may not be atomic on Windows** | `vector_store.py:155` — noted as platform concern in docs. | Potential data corruption on power failure during save. |
| L4 | **No `pam version` command** | Version only in `pyproject.toml:7`. No `__version__` in `app/`. | Users cannot check version from CLI. |
| L5 | **No `pam reprocess` command** | No way to bulk reprocess failed files without manual file moving. | Failed items require manual intervention. |
| L6 | **No encryption of stored data** | `vector_store.json`, `knowledge_graph.json`, vault notes, logs all plaintext. | Sensitive content stored unencrypted on disk. |
| L7 | **Watcher only monitors `on_created`** | No `on_modified` or `on_deleted` handlers. | File changes after initial drop are not detected. |

---

# 3. RETRIEVAL IMPROVEMENTS

## 3.1 Retrieval Quality Evaluation

**Current state:** None. Zero measurement of retrieval quality.

**What to build:** A ground-truth evaluation dataset and automated metrics.

**Priority: CRITICAL.** Without evaluation, every other retrieval improvement is guesswork.

**Approach:**
- Create `eval/` directory with a JSONL dataset of `{query, expected_chunks[], expected_sources[]}`
- Run retrieval against dataset and compute Recall@K, Precision@K, MRR, NDCG
- Run as part of CI (optional, can be manual for V1.1)
- See Section 7 for full evaluation design.

**Evidence this is needed:** Without metrics, the team cannot know if adding reranking, query rewriting, or BM25 improvements actually improves results.

## 3.2 Reranking

**Current state:** No reranking. Pipeline: dense+BM25→RRF→return.

**What to add:** A cross-encoder reranker as an optional second stage.

**Priority: HIGH.**

**Approach:**
- Add optional `cross-encoder/ms-marco-MiniLM-L-6-v2` (or similar) via `sentence-transformers`
- `CrossEncoderReranker.rerank(query, hits, top_k)` — takes RRF results, returns reranked top_k
- Gate behind config: `reranker.enabled: false` (default off for V1.1, opt-in)
- Reranker runs after RRF fusion, before context building

**Why it helps:** Cross-encoders see query and document together, catching relevance that cosine similarity + BM25 miss. Documented ~10-15% MRR improvement in RAG benchmarks.

**Risk:** Adds ~50-200ms per query. CPU-only inference. Model download ~80MB.

**Evidence this is needed:** Current pipeline relies on `k=60` RRF which is a reasonable default but has no second-stage precision signal.

## 3.3 BM25 Improvements

**Current state:** Regex tokenizer `[a-z0-9_]+`, no stemming, no stop words, no language awareness. `bm25.py:13-18`.

**Improvements:**

| Improvement | Difficulty | Benefit |
|---|---|---|
| Add optional stemming (Snowball via `PyStemmer`) | Low | Matches running/run/ran |
| Add optional stop-word removal | Low | Reduces noise from common words |
| Make tokenizer injectable (configurable) | Medium | Allows language-specific tokenizers |
| Persist BM25 index to disk | Medium | Avoids rebuild on every corpus change |

**Priority: MEDIUM.** Stemming provides the highest value-to-effort ratio.

**Evidence this is needed:** The regex tokenizer at `bm25.py:13` treats "running" and "run" as completely different tokens.

## 3.4 RRF Improvements

**Current state:** `_rrf_fuse()` in `search.py:187` with hardcoded k=60.

**Improvements:**

| Improvement | Difficulty | Benefit |
|---|---|---|
| Make k configurable via settings | Low | Tune fusion for corpus size |
| Add weighted RRF (dense weight vs. BM25 weight) | Medium | Allow biasing toward semantic or lexical |
| Handle tie-breaking deterministically | Low | Currently sorted by ID for stability — this is fine |

**Priority: LOW-MEDIUM.** Making k configurable is trivial and useful.

**Evidence this is needed:** k=60 is the standard default, but optimal k varies with corpus size. For a small personal knowledge base (<1000 docs), k=20-30 may be better.

## 3.5 Top-K Tuning

**Current state:** Default top_k=5 for search and QA. Configurable via CLI `--top-k`.

**Improvements:** No change needed. The CLI flags work. The defaults are reasonable.

**Priority: LOW.** Already well-implemented.

## 3.6 Score Thresholds

**Current state:** Default min_score=0.0. Configurable via CLI `--min-score`.

**What to improve:** Add a recommended default or auto-threshold.

| Approach | Difficulty | Benefit |
|---|---|---|
| Add `min_score` to `config/default.yaml` (e.g., 0.15) | Low | Reduces noise without CLI flags |
| Auto-threshold: reject scores below mean+1σ of results | Medium | Adaptive to corpus |
| Document score ranges and thresholds | Low | Users know what 0.3 vs 0.7 means |

**Priority: MEDIUM.** A config default of 0.15-0.25 would eliminate most noise.

**Evidence this is needed:** Default 0.0 means every query returns all indexed chunks regardless of relevance.

## 3.7 Query Rewriting

**Current state:** No query rewriting. Raw query sent to embedder (`search.py:262`).

**What to add:**

| Approach | Difficulty | Benefit |
|---|---|---|
| Simple keyword extraction + expansion | Low | Handles morphological variants |
| LLM-based query rewriting (1-shot) | Medium | Handles ambiguous queries |
| HyDE (Hypothetical Document Embedding) | Medium | Improves recall for complex queries |

**Priority: MEDIUM.** Start with simple keyword expansion. LLM-based rewriting adds latency and Ollama dependency.

**Evidence this is needed:** Search for "handwritten notes" won't match a document about "handwriting processing" due to embedding sensitivity to word forms.

## 3.8 Metadata Filtering

**Current state:** Exact-match filtering on `source_type` and arbitrary metadata keys. `search.py:69-80`. CLI: `--source-type` and `--filter` (JSON object).

**What to add:**

| Feature | Difficulty | Benefit |
|---|---|---|
| `$in` operator for multi-value match | Low | Filter by multiple source types |
| Date range filtering | Medium | "Show me files from last week" |
| Numeric range filtering | Medium | Filter by chunk index, heading level |

**Priority: LOW-MEDIUM.** The existing exact-match is sufficient for V1.1. Date filtering is the most requested.

**Evidence this is needed:** Comment at `search.py:72` explicitly notes "$in/range syntax is roadmap 4.5."

## 3.9 Duplicate Retrieval

**Current state:** No deduplication in context. Duplicate chunks from different sources consume the 12k char budget.

**What to add:**

| Approach | Difficulty | Benefit |
|---|---|---|
| Exact text dedup in `build_context()` | Low | Prevents same text appearing twice |
| Source-level dedup (max 1 chunk per source) | Low | Diversifies context |

**Priority: MEDIUM.** Simple text dedup is trivial and valuable.

**Evidence this is needed:** `qa_workflow.py:33-58` — `build_context()` has no dedup logic. Chunks are appended until budget exhausted.

## 3.10 Context Selection

**Current state:** `MAX_CONTEXT_CHUNKS=8`, `MAX_CONTEXT_CHARS=12_000` at `qa_workflow.py:16-17`. Character-level truncation per chunk.

**What to improve:**

| Improvement | Difficulty | Benefit |
|---|---|---|
| Make constants configurable via settings | Low | Users tune for their model's context window |
| Add chunk overlap detection | Medium | Avoids sending overlapping context |
| Score-weighted ordering (already done) | Done | — |

**Priority: HIGH.** Making these configurable is trivial and high-impact.

**Evidence this is needed:** These constants assume a specific model context window. Different Ollama models have different limits.

---

# 4. STORAGE IMPROVEMENTS

## 4.1 Vector Delete/GC

**Current state:** `VectorStore.remove(entry_id)` exists but no orphan cleanup. No `remove_by_source()`. Deleted files leave vectors forever.

**What to add:**

| Feature | Difficulty | Benefit |
|---|---|---|
| `VectorStore.remove_by_source(source)` | Low | Clean vectors when source file is deleted |
| GC scan: find vectors with no matching source file | Medium | Reclaim space from deleted files |
| Integrate GC into `pam status` or `pam doctor` | Low | Users can see orphan count |

**Priority: HIGH.** Without this, storage grows monotonically and stale vectors pollute results.

**Evidence this is needed:** `vector_store.py` has no `remove_by_source()`. `ingest_workflow.py:927-929` adds new vectors without removing old ones for the same source.

## 4.2 Stale Vectors

**Current state:** Re-ingesting a file with same path creates new chunks that overwrite old chunks (dict key collision). But chunks from files that changed content get NEW chunk IDs, so old vectors are NOT replaced — they accumulate.

**What to add:**

| Feature | Difficulty | Benefit |
|---|---|---|
| On ingest, remove all vectors for the source path before adding new ones | Low | Prevents vector accumulation |
| Add `VectorStore.remove_by_prefix(source_path)` | Low | Bulk removal by source prefix |

**Priority: HIGH.** Stale vectors directly degrade retrieval quality.

**Evidence this is needed:** `ingest_workflow.py:927-929` — `store.add_batch(entries)` does not first remove existing entries for the same source.

## 4.3 JSON Persistence Scalability

**Current state:** Whole-store rewrite on every save. `vector_store.json` written atomically via `os.replace()`.

**What to improve:**

| Approach | Difficulty | Benefit |
|---|---|---|
| Incremental save (append new entries, lazy full rewrite) | Medium | Faster saves for large stores |
| Periodic save instead of save-on-every-add | Low | Reduces I/O during batch ingest |
| Compressed JSON (gzip) | Low | Smaller files |

**Priority: LOW.** JSON persistence is fine for <10k vectors. The atomic write is correct.

**Evidence this is needed:** `vector_store.py:146-157` — every `save()` rewrites the entire store. For 5000 vectors this is fast; for 50k+ it becomes noticeable.

## 4.4 Vector Dimension Enforcement

**Current state:** No dimension check at storage time. `vector_store.py:68-77`. Mismatched dimensions silently return 0.0 at search time (`vector_store.py:115`).

**What to add:**

| Feature | Difficulty | Benefit |
|---|---|---|
| Validate embedding dimension on `add()`/`add_batch()` | Low | Fail fast on model mismatch |
| Store expected dimension in vector store metadata | Low | Detect model changes |

**Priority: MEDIUM.** This is a safety guard for when users change their embedding model.

**Evidence this is needed:** Switching from `nomic-embed-text` (768-dim) to another model would silently break all queries with zero-score results.

## 4.5 Embedding Cache

**Current state:** No caching. Every search re-embeds query. Every re-ingestion re-embeds all chunks.

**What to add:**

| Feature | Difficulty | Benefit |
|---|---|---|
| LRU cache for query embeddings (key=query text, value=vector) | Low | Avoids re-embedding identical queries |
| Embedding cache for chunk text during re-ingestion | Medium | Avoids re-embedding unchanged chunks |

**Priority: MEDIUM.** Query embedding cache is trivial and helps repeated queries.

**Evidence this is needed:** `embeddings.py` has no caching. A `@functools.lru_cache` on `embed(text)` would handle the most common case.

## 4.6 BM25 Index Persistence

**Current state:** BM25 index is ephemeral. Rebuilt from vector store on every startup or corpus change.

**What to add:**

| Feature | Difficulty | Benefit |
|---|---|---|
| Persist BM25 index to disk | Medium | Faster startup, no rebuild delay |
| Incremental index update | High | Avoid full rebuild on single document add |

**Priority: LOW.** For personal knowledge bases (<5000 docs), rebuild is fast.

**Evidence this is needed:** `bm25.py` — `BM25Index.__init__()` takes a `texts` list and rebuilds from scratch. No `save()`/`load()` methods exist.

---

# 5. MULTIMODAL IMPROVEMENTS

## 5.1 Local Audio ASR

**Current state:** `faster-whisper` is a runtime dependency, not in `pyproject.toml`. Audio transcription works but depends on manual install.

**What to improve:**

| Feature | Difficulty | Benefit |
|---|---|---|
| Add `faster-whisper` to `pyproject.toml` as optional dependency | Low | Proper dependency management |
| Add audio preprocessing (noise reduction, normalization) | Medium | Better transcription quality |
| Preserve timestamps from transcript segments | Low | Enable time-based search |
| Chunk by audio segments (paragraph detection) | Medium | Better context boundaries |

**Priority: MEDIUM.** The core works; the packaging and quality improvements matter.

**Evidence this is needed:** `faster-whisper` is documented as required but not in `pyproject.toml:dependencies`.

## 5.2 Video Audio Extraction

**Current state:** Video files produce NO searchable content. Files are ingested but produce empty text that fails at AI processing.

**What to add:**

| Feature | Difficulty | Benefit |
|---|---|---|
| Extract audio track from video (via `ffmpeg` or `moviepy`) | Medium | Enables ASR on video content |
| Extract subtitle/caption tracks if available | Low | Already-available text content |
| Duration/resolution metadata extraction | Low | Useful for video file organization |

**Priority: HIGH.** Video is the largest content gap. Audio extraction + ASR unlocks video search.

**Evidence this is needed:** Video ingestion at `ingest_workflow.py` enters AI processing with empty text, producing empty or failed results.

## 5.3 Video Frame Extraction

**Current state:** No frame extraction.

**What to add:**

| Feature | Difficulty | Benefit |
|---|---|---|
| Extract keyframes at intervals (e.g., every 30s) | Medium | Visual content from video |
| Process keyframes through vision model | Medium | Image understanding of video content |

**Priority: LOW.** This is a significant feature addition. Audio extraction alone provides most of the value.

**Evidence this is needed:** Video content is entirely lost currently. Keyframe extraction is the standard approach but requires ffmpeg integration.

## 5.4 OCR Improvements

**Current state:** Vision model (`qwen2.5vl`) for OCR, Tesseract fallback. No confidence reporting. No layout preservation.

**What to improve:**

| Feature | Difficulty | Benefit |
|---|---|---|
| Report OCR confidence scores | Low | Enable confidence-based filtering |
| Auto-trigger OCR for all scanned PDFs (currently only when text layer is empty) | Low | Better coverage |
| Increase default page limit from 5 to higher | Low | Process more pages |

**Priority: MEDIUM.** Confidence reporting is trivial and useful. Page limit increase is config change.

**Evidence this is needed:** `vision_ocr.py` — OCR engine does not report confidence. Page limit default 5 at `config/default.yaml`.

## 5.5 Handwriting Recognition

**Current state:** Uses same general vision model. Must be told via `source_type="handwritten"`. No automatic detection.

**What to improve:**

| Feature | Difficulty | Benefit |
|---|---|---|
| Automatic handwriting detection (based on image features) | High | No manual source_type needed |
| Handwriting-specific prompting to vision model | Low | Better transcription accuracy |

**Priority: LOW.** The current approach (user specifies handwritten) works. Automatic detection is complex and unreliable.

## 5.6 Image Understanding

**Current state:** Vision model processes images. PDF-embedded images extracted as metadata but never understood.

**What to improve:**

| Feature | Difficulty | Benefit |
|---|---|---|
| Process PDF-embedded images through vision model | Medium | Images in PDFs become searchable |
| Image preprocessing (deskew/denoise/CLAHE) as opt-in | Low | Better OCR on poor scans |

**Priority: MEDIUM.** PDF-embedded images are a common content type that is currently wasted.

**Evidence this is needed:** PDF images are stored as metadata (`image_data`) but never passed to vision model for understanding.

---

# 6. KNOWLEDGE GRAPH IMPROVEMENTS

## Current State

The knowledge graph is built during ingestion at `ingest_workflow.py:884-971`:
- Entities extracted deterministically from `DocumentAnalysis`
- Relationships detected between entities
- Graph persisted to `knowledge_graph.json`
- Rendered as text summary in Obsidian notes

**The graph is NOT used in retrieval or QA.** Verified:
- `search.py` (276 lines) — zero imports or references to `KnowledgeGraph`
- `qa_workflow.py` (127 lines) — zero references to knowledge graph
- `KnowledgeGraph.neighbors()` and `.subgraph()` at `domain/knowledge_graph.py:66-96` — never called from any retrieval path

## Should Graph Retrieval Be Added?

### Arguments FOR:
- Entities and relationships provide structured context that embeddings miss
- "What concepts relate to X?" queries would benefit from graph traversal
- Graph context could be appended to QA context alongside vector results

### Arguments AGAINST:
- **Graph quality is unknown.** Without evaluation, we don't know if extracted entities/relationships are accurate.
- **Graph coverage is sparse.** Cross-document linking uses `min_score=0.7` and `top_k=3` (hardcoded), producing few connections.
- **Added complexity.** Graph traversal adds latency and a new retrieval path to debug.
- **Diminishing returns for small corpora.** Personal knowledge bases (<1000 docs) don't need graph-based retrieval — vector + BM25 is sufficient.

### Recommendation

**Do NOT add graph retrieval in V1.1.** The cost-benefit ratio is poor:
- The graph is built from deterministic extraction, not LLM-based, so quality is likely mediocre
- For a personal knowledge base of <1000 documents, vector + BM25 + RRF is sufficient
- Graph retrieval requires its own evaluation framework, doubling the evaluation effort

**What to do instead:**
1. **Measure graph quality first.** Sample 50 documents, manually verify extracted entities/relationships. If quality is >80%, graph retrieval becomes worth investing in.
2. **If graph quality is good:** Add graph context as an optional retrieval source in V1.2, not V1.1.
3. **If graph quality is poor:** Fix extraction quality before adding retrieval.

**V1.1 action:** Keep the graph build step as-is. Do not invest in graph retrieval until quality is measured and confirmed.

---

# 7. EVALUATION

## Why Evaluation First

Without evaluation, every improvement is a guess. Evaluation should be the FIRST phase of V1.1.

## Test Dataset Design

### Structure

```jsonl
{"id": "q001", "query": "How does PAM handle handwritten PDFs?", "expected_chunks": ["chunk_xxx", "chunk_yyy"], "expected_sources": ["/path/to/handwriting.md"], "category": "ingestion"}
{"id": "q002", "query": "What embedding model does PAM use?", "expected_chunks": ["chunk_zzz"], "expected_sources": ["/path/to/embeddings.md"], "category": "retrieval"}
```

### Dataset Requirements

| Requirement | Detail |
|---|---|
| Size | 50-100 queries minimum for meaningful metrics |
| Categories | Cover ingestion, retrieval, QA, multimodal, config |
| Expected documents | 1-5 relevant chunks per query |
| Source files | Use actual PAM documentation and source code as corpus |
| Negative examples | Queries with NO relevant results (to test precision) |

### Where to Store

```
eval/
  dataset.jsonl          # Ground truth queries
  run_eval.py            # Evaluation script
  results/               # Saved evaluation runs
```

## Metrics

### Retrieval Metrics (what matters most for PAM)

| Metric | What It Measures | Target for V1.1 |
|---|---|---|
| **Recall@5** | Of 5 returned results, how many are relevant? | >0.6 |
| **Recall@10** | Of 10 returned results, how many are relevant? | >0.75 |
| **Precision@5** | Of 5 returned results, how many are relevant? (same as Recall@5 for top-5) | >0.6 |
| **MRR** | Mean Reciprocal Rank — where is the first relevant result? | >0.7 |
| **NDCG@5** | Normalized Discounted Cumulative Gain — are relevant results ranked higher? | >0.7 |
| **Hit Rate** | What fraction of queries return at least 1 relevant result? | >0.8 |

### RAG Quality Metrics (secondary for V1.1)

| Metric | What It Measures | Priority |
|---|---|---|
| **Context Relevance** | Are the retrieved chunks actually relevant to the query? | High |
| **Faithfulness** | Does the answer only use information from the context? | Medium |
| **Answer Relevance** | Does the answer address the query? | Medium |
| **Groundedness** | Is the answer supported by the retrieved context? | Medium |

### Which Metrics Matter Most

**For PAM specifically:**
1. **Recall@5 and Hit Rate** — PAM is a personal knowledge base. Users want to find what they stored. Missing relevant content is worse than returning some noise.
2. **MRR** — Users rarely look past the first result. The first result being relevant matters a lot.
3. **Context Relevance** — Directly determines whether the LLM gets good information to work with.
4. **Faithfulness** — PAM already instructs the LLM to ground answers, but measurement is needed.

NDCG is less critical for PAM (personal use, not production ranking). Precision@5 is identical to Recall@5 when 5 results are returned.

## Evaluation Implementation

### Manual Evaluation (V1.1 minimum)

1. Create 50-query dataset with ground truth
2. Run `pam search` and `pam ask` for each query
3. Manually score: was the relevant document in the top 5? top 10?
4. Compute Recall@5, Recall@10, MRR, Hit Rate
5. Record results in `eval/results/baseline_v1.json`

### Automated Evaluation (V1.1 stretch goal)

1. Script that runs retrieval for all queries
2. Computes metrics automatically against ground truth
3. Generates report with per-category breakdown
4. Can be run as `python eval/run_eval.py`

---

# 8. RELIABILITY

## 8.1 Watcher

**Current state:** `watchdog` observer with `_InboxCreatedHandler`. File stability check (poll twice, 0.5s delay). Only `on_created` events.

**Improvements:**

| Feature | Difficulty | Benefit |
|---|---|---|
| Add `on_modified` handler | Low | Detect file changes after initial drop |
| Add `on_deleted` handler (log warning) | Low | Detect when inbox files are removed |
| Configurable stability check interval | Low |适应不同文件系统速度 |

**Priority: LOW.** The current `on_created` handler is sufficient for the "drop a file" workflow.

## 8.2 Queue & Worker

**Current state:** Single worker (max 1), thread-safe queue, persistent state via JSON, failure moves files to `data/failed/`.

**Improvements:**

| Feature | Difficulty | Benefit |
|---|---|---|
| Configurable worker count (allow >1) | High | Parallel ingestion |
| Retry failed items with backoff | Medium | Recover from transient Ollama failures |
| Max retry count before moving to failed | Low | Prevent infinite retry loops |
| Queue priority (urgent vs. background) | High | User-initiated ingest prioritized |

**Priority: MEDIUM for retry, LOW for parallel.** For personal use, single worker is fine. Retry for transient failures is valuable.

**Evidence this is needed:** Currently, a transient Ollama timeout sends the file directly to `data/failed/` with no retry.

## 8.3 Failure Recovery

**Current state:**
- Corrupt vector store: malformed entries skipped, starts partial (`vector_store.py:192-193`)
- Corrupt manifest: quarantined and recreated empty (loses all dedup history)
- Corrupt queue state: returns empty list, pending items lost

**Improvements:**

| Feature | Difficulty | Benefit |
|---|---|---|
| Backup before write (keep last 2 versions) | Low | Recover from corruption |
| Validate JSON before atomic replace | Low | Prevent writing corrupt data |
| Log corruption events with details | Low | Debug issues |

**Priority: MEDIUM.** Backup-before-write is the highest-value, lowest-effort improvement.

**Evidence this is needed:** `vector_store.py:146-157` — writes to `.tmp` then `os.replace()`. If the `.tmp` write is corrupt, it replaces the good file.

## 8.4 Atomic Writes

**Current state:** `os.replace()` used for atomicity. Noted as potentially non-atomic on Windows.

**Improvements:**

| Feature | Difficulty | Benefit |
|---|---|---|
| Use `tempfile.NamedTemporaryFile` with delete=False | Low | Better cross-platform atomicity |
| Validate file integrity after write | Low | Detect corruption |

**Priority: LOW.** The current approach works on POSIX. Windows issue is theoretical.

## 8.5 Logging & Observability

**Current state:** Structured JSON logging. Component-specific log files (`watcher.log`, `processing.log`, `errors.log`). Retrieval scores logged at DEBUG level only.

**Improvements:**

| Feature | Difficulty | Benefit |
|---|---|---|
| Log retrieval scores at INFO level | Low | Debug retrieval quality without DEBUG mode |
| Log prompt sent to LLM (opt-in) | Low | Debug QA quality |
| Persist runtime stats to disk | Low | `pam status` shows real counters |
| Add structured metrics (ingest time, query latency) | Medium | Performance monitoring |

**Priority: MEDIUM.** Persisting runtime stats and logging retrieval scores are trivial and high-value.

**Evidence this is needed:**
- `entry.py:154-156` — status counters hardcoded to "0"
- `qa_workflow.py:105-108` — does NOT log individual retrieval scores
- `search.py:100-103` — retrieval scores at DEBUG only

---

# 9. SECURITY

## 9.1 Prompt Injection

**Current state:** System prompt at `qa.py:15-18` instructs LLM to treat retrieved text as data, not instructions. No programmatic enforcement.

**Assessment:** For a local CLI tool, this is adequate. PAM is not exposed to untrusted input in a production setting. The prompt injection risk is limited to:
- User accidentally ingesting a malicious document
- That document's content appearing in retrieval context
- The LLM following instructions in the document

**Mitigation (if desired):**
- Add output filtering to detect common injection patterns
- Use a separate classifier to score output safety

**Priority: LOW.** The threat model for a personal local CLI tool is low. The existing instruction-level defense is sufficient for V1.1.

## 9.2 Secrets & Credentials

**Current state:** No secrets management. No API keys needed (local Ollama). No `.env` file loading.

**Assessment:** PAM uses only local models. No API keys or external services. This is a security advantage.

**Risk:** If a user configures an external LLM provider (planned V2), secrets handling becomes critical.

**Priority: N/A for V1.1.** No change needed.

## 9.3 Local Data

**Current state:** All data stored locally in plaintext. No encryption.

**Assessment:** For a personal tool, plaintext is acceptable. The user already has filesystem-level access control.

**Priority: N/A for V1.1.** Encryption is a V2 feature if PAM ever supports shared/multi-user scenarios.

## 9.4 Logs

**Current state:** Structured JSON logs. File paths logged. No PII redaction.

**Assessment:** File paths in logs are expected. No user content is logged at INFO level (only query text and hit counts).

**Priority: LOW.** Current logging is appropriate for a local tool.

## 9.5 Filesystem

**Current state:** 50MB file size limit. SHA-256 integrity hashing. Configurable inbox/processed/failed paths.

**Assessment:** The file size limit and integrity checks are reasonable.

**Priority: N/A for V1.1.**

## 9.6 Model Calls

**Current state:** All model calls are local via Ollama. No external API calls.

**Assessment:** This is the strongest security posture — no data leaves the machine.

**Priority: N/A for V1.1.** No change needed.

---

# 10. PLATFORM SUPPORT

## Current State

| Platform | Status | Evidence |
|---|---|---|
| **Windows** | Primary development platform | Author develops on Windows. `PurePosixPath` usage in `code/languages.py:5` is minor. `os.replace()` may not be atomic. |
| **Linux** | CI tested | `.github/workflows/ci.yml` runs on `ubuntu-latest`. Python 3.11/3.12/3.13. |
| **macOS** | Unknown/untested | No CI evidence. No macOS-specific testing. |
| **Docker** | Not supported | No `Dockerfile` or `docker-compose.yml`. |
| **WSL** | Unknown | Not tested or documented. |

## Recommendations for V1.1

| Feature | Difficulty | Benefit | Priority |
|---|---|---|---|
| Fix `PurePosixPath` → `Path` in `code/languages.py:5` | Trivial | Correct Windows path handling | HIGH |
| Add macOS to CI matrix | Low | Cross-platform confidence | MEDIUM |
| Add `Dockerfile` | Medium | Reproducible deployment | LOW |
| Document GPU/VRAM requirements | Low | User onboarding | MEDIUM |

**Priority: MEDIUM overall.** The `PurePosixPath` fix is trivial and should be done. Docker is a V2 feature.

**Evidence this is needed:** `code/languages.py:5` — `from pathlib import PurePosixPath` used for suffix extraction. Works by accident (suffix is after last `.`) but incorrect for Windows paths with backslashes.

---

# 11. TESTING

## Current State

- 1375 tests, 89.80% line coverage, 732 statements missed
- CI: ruff lint, mypy type check, pytest+coverage
- No branch coverage, no mutation testing, no performance regression tests

## Unit Tests to Add

| Test Area | What to Test | Priority |
|---|---|---|
| `VectorStore.remove_by_source()` | Bulk removal by source path | HIGH (once implemented) |
| `BM25Index` with stemming | Stemming integration | MEDIUM |
| Embedding cache hit/miss | Cache behavior | MEDIUM |
| `build_context()` dedup | Duplicate chunk removal | HIGH (once implemented) |
| Score threshold filtering | min_score > 0 behavior | LOW (already works) |
| Dimension mismatch | Invalid embedding dimensions | MEDIUM |
| Configurable MAX_CONTEXT_* | Settings override | HIGH (once implemented) |

## Integration Tests to Add

| Test Area | What to Test | Priority |
|---|---|---|
| End-to-end ingest → search → ask pipeline | Full workflow with assertions on retrieval quality | HIGH |
| Re-ingestion removes old vectors | No vector accumulation | HIGH |
| Watcher → queue → ingest pipeline | File drop to searchable content | MEDIUM |
| Corrupt file recovery | JSON corruption → graceful degradation | MEDIUM |

## E2E Tests to Add

| Test Area | What to Test | Priority |
|---|---|---|
| Real document ingestion + QA | Ingest actual PDF, ask question, verify answer references correct source | HIGH |
| Multi-document ingestion | Ingest 5+ files, verify search returns correct results | MEDIUM |
| Video ingestion | Verify video content is extractable (once implemented) | LOW |

## Retrieval Evaluation

| Test Area | What to Test | Priority |
|---|---|---|
| Recall@5 against ground truth | Automated retrieval quality measurement | HIGH |
| MRR against ground truth | First relevant result rank | HIGH |
| Faithfulness scoring | LLM answers grounded in context | MEDIUM |

---

# 12. PRIORITIZATION

| Improvement | Priority | Difficulty | Benefit | Risk | Why |
|---|---|---|---|---|---|
| **Retrieval evaluation dataset** | CRITICAL | Medium | High | Low | Without metrics, all other improvements are guesswork |
| **Vector delete/GC + stale vector cleanup** | HIGH | Low | High | Low | Storage grows monotonically; stale vectors degrade quality |
| **Configurable MAX_CONTEXT_CHUNKS/CHARS** | HIGH | Low | High | Low | Trivial change; enables model-specific tuning |
| **Embedding cache (query-level)** | HIGH | Low | Medium | Low | `@lru_cache` on `embed()` — one-line change |
| **RuntimeStats persistence** | HIGH | Low | Medium | Low | `pam status` shows real counters instead of hardcoded "0" |
| **Reranking (cross-encoder)** | HIGH | Medium | High | Medium | ~10-15% MRR improvement; adds latency and dependency |
| **Video audio extraction + ASR** | HIGH | Medium | High | Medium | Largest content gap; `ffmpeg` integration required |
| **BM25 stemming** | MEDIUM | Low | Medium | Low | `PyStemmer` integration; improves lexical matching |
| **Query embedding cache** | MEDIUM | Low | Low | Low | Already covered by embedding cache above |
| **Make RRF k configurable** | MEDIUM | Low | Low | Low | Trivial config addition |
| **Dimension enforcement** | MEDIUM | Low | Low | Low | Safety guard for model changes |
| **Score threshold default in config** | MEDIUM | Low | Low | Low | Reduces noise without CLI flags |
| **BM25 persistence** | LOW | Medium | Low | Low | Rebuild is fast for personal corpora |
| **Graph retrieval** | LOW | High | Unknown | High | First measure graph quality; premature without eval |
| **Docker support** | LOW | Medium | Low | Low | V2 feature; local use doesn't need containerization |
| **macOS CI** | LOW | Low | Low | Low | Nice-to-have, not blocking |
| **`pam version` command** | LOW | Trivial | Low | Low | Version available via `pip show pam` |
| **`pam reprocess` command** | LOW | Low | Low | Low | Manual file moving is workable |

---

# 13. RECOMMENDED V1.1

## Must Have (ship-blocking)

1. **Retrieval evaluation dataset** — 50-query ground truth set with Recall@5, MRR, Hit Rate measurement
2. **Vector delete/GC** — `remove_by_source()`, stale vector cleanup on re-ingestion, orphan detection
3. **Configurable context limits** — `MAX_CONTEXT_CHUNKS` and `MAX_CONTEXT_CHARS` in settings
4. **Embedding cache** — LRU cache for query embeddings to avoid re-embedding identical queries
5. **RuntimeStats persistence** — `pam status` shows real processing counters
6. **BM25 stemming** — Add Snowball stemming to BM25 tokenizer

## Should Have (high value, include if time permits)

7. **Cross-encoder reranking** — Optional second-stage reranker, gated behind config
8. **Video audio extraction** — ffmpeg integration for audio track extraction + ASR
9. **Score threshold default** — Add `min_score: 0.15` to `config/default.yaml`
10. **Context deduplication** — Remove duplicate chunks in `build_context()`
11. **Retrieval score logging** — Log individual hit scores at INFO level
12. **Backup before write** — Keep last 2 versions of JSON files

## Nice to Have (include only if ahead of schedule)

13. **Query rewriting** — Simple keyword expansion for morphological variants
14. **RRF k configurable** — Add to settings
15. **Dimension enforcement** — Validate embedding dimensions on store
16. **BM25 persistence** — Save/load index from disk
17. **`pam version` command** — Trivial addition
18. **macOS CI** — Add to GitHub Actions matrix
19. **`PurePosixPath` fix** — Replace with `Path` in `code/languages.py`

## Explicitly NOT in V1.1

- Graph retrieval (measure quality first)
- Docker support (V2)
- External vector database (V2)
- LLM streaming (V2)
- Parallel ingestion (V2)
- Encryption (V2)
- HyDE / LLM query rewriting (V2)
- Video frame extraction (V2)
- Automatic handwriting detection (V2)
- `pam reprocess` command (V2)

---

# 14. WHAT NOT TO CHANGE

The following parts of V1 are working well and should remain stable:

| Component | Why It Works | Risk of Change |
|---|---|---|
| **Ingestion pipeline (12-step)** | Well-tested, 20 processors, handles 90+ extensions. | High — any change risks breaking working file types. |
| **Ollama client** | Configurable retries, exponential backoff, proper error handling. | Low — only add features, don't refactor. |
| **Vector store core** | In-memory cosine search is correct and fast for personal use. | Medium — changes to persistence could corrupt data. |
| **BM25 scoring** | Okapi BM25 (k1=1.5, b=0.75) is a proven algorithm. | Low — tokenizer changes are additive. |
| **RRF fusion** | Standard algorithm, k=60 is reasonable default. | Low — making k configurable is non-breaking. |
| **Obsidian integration** | Wiki-linked notes, graph summary, upsert behavior. | Medium — changing note format breaks existing vaults. |
| **CLI interface** | Typer-based, well-structured, consistent flags. | Low — adding flags is non-breaking. |
| **Structured logging** | JSON formatter, rotating files, component-specific logs. | Low — log format changes are non-breaking. |
| **Test suite (1375 tests)** | Comprehensive unit + integration coverage. | Low — adding tests is non-breaking. |
| **CI pipeline** | ruff, mypy, pytest+coverage on Python 3.11/3.12/3.13. | Low — adding jobs is non-breaking. |

**Principle:** If it works and tests pass, don't touch it. V1.1 additions should be additive, not refactoring.

---

# 15. FINAL V1.1 ROADMAP

## Phase 1: Evaluation Foundation (Week 1-2)

**Goal:** Establish measurable baseline so all future improvements can be validated.

```
1.1  Create eval/ directory structure
     └── eval/dataset.jsonl (50 queries with ground truth)
     └── eval/run_eval.py (automated evaluation script)

1.2  Run baseline evaluation
     └── Recall@5, Recall@10, MRR, Hit Rate
     └── Record in eval/results/baseline_v1.json

1.3  Add retrieval score logging
     └── Log individual hit scores at INFO level
     └── qa_workflow.py:105-108 — add hit.score to log

1.4  Persist RuntimeStats
     └── Save stats to data/stats.json on shutdown
     └── Load stats on startup
     └── pam status shows real counters
```

**Exit criteria:** Baseline metrics recorded. `pam status` shows real counters.

## Phase 2: Storage Reliability (Week 2-3)

**Goal:** Fix the storage monotonicity problem. No more stale vectors.

```
2.1  Add VectorStore.remove_by_source(source)
     └── vector_store.py — new method

2.2  Clean stale vectors on re-ingestion
     └── ingest_workflow.py — remove old vectors before adding new

2.3  Add orphan detection
     └── Scan vector store for entries with no matching source file
     └── Report in pam doctor

2.4  Backup before write
     └── Keep vector_store.json.bak (last successful write)
     └── Keep knowledge_graph.json.bak

2.5  Add dimension enforcement
     └── Validate embedding dimension on add()/add_batch()
     └── Store expected dimension in store metadata
```

**Exit criteria:** Re-ingesting a file replaces old vectors. `pam doctor` reports orphan count.

## Phase 3: Retrieval Quality (Week 3-5)

**Goal:** Improve retrieval quality with measurable gains.

```
3.1  Configurable context limits
     └── qa.py settings — MAX_CONTEXT_CHUNKS, MAX_CONTEXT_CHARS
     └── Defaults: 8 chunks, 12_000 chars (unchanged)

3.2  BM25 stemming
     └── Add Snowball stemmer to bm25.py
     └── Make tokenizer configurable via settings
     └── Default: stemmed + lowercase

3.3  Embedding cache
     └── @lru_cache on EmbeddingService.embed()
     └── Configurable cache size

3.4  Context deduplication
     └── build_context() — skip chunks with duplicate text
     └── Max 1 chunk per source file

3.5  Score threshold default
     └── Add min_score: 0.15 to config/default.yaml
     └── Document score ranges for users

3.6  Re-run evaluation
     └── Compare against baseline_v1.json
     └── Record in eval/results/v1.1_phase3.json
```

**Exit criteria:** Recall@5 improves by ≥5% over baseline. MRR improves by ≥5%.

## Phase 4: Reranking (Week 5-6)

**Goal:** Add optional cross-encoder reranking for higher precision.

```
4.1  Add CrossEncoderReranker
     └── app/infrastructure/reranker.py
     └── Optional sentence-transformers dependency

4.2  Integrate into search pipeline
     └── HybridSearch → RRF → CrossEncoderReranker → return
     └── Gated behind reranker.enabled config

4.3  Add to QA workflow
     └── QAWorkflow.ask() — optional reranking before context build

4.4  Re-run evaluation
     └── Compare with and without reranking
     └── Record latency impact
```

**Exit criteria:** MRR improves by ≥5% with reranking enabled. Latency increase <200ms.

## Phase 5: Multimodal (Week 6-8)

**Goal:** Unlock video content and improve audio/image processing.

```
5.1  Fix faster-whisper dependency
     └── Add to pyproject.toml as optional dependency

5.2  Video audio extraction
     └── ffmpeg integration for audio track extraction
     └── Route extracted audio through faster-whisper ASR

5.3  PDF image understanding
     └── Pass extracted images through vision model
     └── Store image descriptions as searchable text

5.4  OCR confidence reporting
     └── Vision model returns confidence scores
     └── Store in metadata for filtering

5.5  Fix PurePosixPath
     └── code/languages.py:5 — replace with Path
```

**Exit criteria:** Video files produce searchable content. PDF images are searchable. OCR confidence available.

## Phase 6: Polish & Ship (Week 8-9)

**Goal:** Final quality pass, documentation, and release.

```
6.1  Add pam version command
     └── Read from pyproject.toml or __version__

6.2  Add macOS to CI matrix
     └── .github/workflows/ci.yml — add macos-latest

6.3  Update documentation
     └── README — new features, configuration options
     └── 07_PAM_V1_TO_V1_1_IMPROVEMENT_ROADMAP.md — mark completed items

6.4  Final evaluation
     └── Full Recall@5, MRR, Hit Rate on v1.1
     └── Compare against baseline
     └── Record in eval/results/v1.1_final.json

6.5  Version bump
     └── pyproject.toml: version = "1.1.0"
```

**Exit criteria:** All tests pass. Evaluation shows measurable improvement. Version bumped.

---

## Summary

| Phase | Focus | Duration | Key Deliverable |
|---|---|---|---|
| **Phase 1** | Evaluation | Week 1-2 | Baseline metrics, persistent stats |
| **Phase 2** | Storage | Week 2-3 | Vector delete/GC, backup, dimension enforcement |
| **Phase 3** | Retrieval | Week 3-5 | Stemming, caching, dedup, configurable limits |
| **Phase 4** | Reranking | Week 5-6 | Cross-encoder reranker |
| **Phase 5** | Multimodal | Week 6-8 | Video ASR, PDF images, OCR confidence |
| **Phase 6** | Polish | Week 8-9 | Documentation, CI, version bump |

**Total estimated effort:** 8-9 weeks for a single developer.

**Critical path:** Phase 1 (Evaluation) → Phase 2 (Storage) → Phase 3 (Retrieval). Phases 4-6 can partially overlap.

**V1.1 scope:** Phases 1-3 are Must Have. Phase 4 is Should Have. Phases 5-6 are Nice to Have.

---

> **Document ends here. No source code was modified.**
