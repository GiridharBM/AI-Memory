# PAM — Embeddings, Vectors, Similarity & Storage

> **Personal reference document.** Reverse-engineered from source code, configuration, and documentation on 2026-08-18. No source code was modified.

---

# 1. What Is an Embedding?

### Beginner Explanation

An **embedding** is a list of numbers that represents the *meaning* of a piece of text. Instead of storing words as strings, you convert them into a long list of decimal numbers — a **vector** — where similar meanings end up with similar numbers.

**Why does RAG need embeddings?**

RAG (Retrieval-Augmented Generation) works by finding relevant chunks of your documents to answer a question. But you can't search for "meaning" using string matching — the question "How do I train a model?" won't match a document that says "Steps to teach a neural network." Embeddings solve this: they turn both the question and the documents into vectors, and you can then compare the vectors to find the ones with the closest meaning.

**How does text become numbers?**

An embedding model reads the text and produces a fixed-length list of numbers (e.g., 768 numbers). Each number captures some aspect of the text's meaning — topic, tone, specificity, relationships to other concepts. The exact meaning of individual numbers is opaque; what matters is the *pattern* across all 768 numbers.

**What does "semantic meaning" mean?**

It means the *concept* behind the text, not the exact words. "The cat sat on the mat" and "A feline rested on the rug" have different words but nearly identical semantic meanings — so their embeddings would be very close in vector space.

**Why are similar meanings represented by similar vectors?**

The embedding model was trained on millions of text pairs. It learned that texts discussing the same topic should be close together in vector space. The training process adjusts the model's internal parameters so that synonymous or topically related texts produce similar vector patterns.

### Simple Example

```text
Text:    "Python is a programming language."

Embedding (conceptual, not actual values):
[0.021, -0.438, 0.912, 0.115, -0.330, 0.761, ...]   ← 768 numbers total
```

### How My Project Creates Embeddings

PAM sends each chunk of text to a local Ollama server running the `nomic-embed-text` model. The model returns a 768-dimensional vector. This happens in `app/infrastructure/embeddings.py` via `EmbeddingService.embed()` (single text) or `embed_batch()` (multiple texts in one call).

---

# 2. My Actual Embedding Model

| Property | Actual Value |
|---|---|
| Embedding model | `nomic-embed-text` |
| Provider | Ollama (local server) |
| Version | nomic-embed-text v1 (274 MB) |
| Local/Cloud | **Local** — runs on `localhost:11434` |
| Document embeddings | Same model for all documents |
| Query embeddings | Same model used for queries (via `SearchService`) |
| Dimensions | **768** |
| Normalization | Not explicitly performed by PAM; vectors are used as returned by Ollama |
| Batch processing | Yes — `embed_batch()` sends all texts in one Ollama call |
| Fallback | If Ollama fails: retries 2× with exponential backoff; if still fails, propagates exception. In `SearchService`, embedder failure degrades to lexical-only (BM25). |

**Source evidence:**
- Model configured in `config/default.yaml` line 120: `embeddings: nomic-embed-text`
- Model routing in `app/core/config.py` line 200: `embeddings: str = "nomic-embed-text"`
- Instantiated in `app/pipelines/ingest_workflow.py` line 259-261
- Retry logic in `app/infrastructure/embeddings.py` lines 17-18, 63-73
- Count-mismatch guard in `app/infrastructure/embeddings.py` lines 21-27, 86-100
- Query embedding in `app/infrastructure/search.py` lines 244-249

---

# 3. Vector Dimensions

### What Is a Vector Dimension?

**Simply:** A vector dimension is one number in the list. If your embedding has 768 dimensions, it's a list of 768 numbers. Each number is one "dimension."

**Technically:** A dimension is an axis in the high-dimensional space where the embedding lives. Each text gets a point in this 768-dimensional space. The position along each axis captures some semantic feature of the text.

### Why Dimensions Matter

- **Every vector in the same store must have the same number of dimensions.** You can't compare a 768-dimensional vector with a 512-dimensional vector.
- **Different embedding models produce different dimensions.** `nomic-embed-text` produces 768; `text-embedding-ada-002` produces 1536; `all-MiniLM-L6-v2` produces 384.
- **If dimensions don't match**, the cosine similarity returns `0.0` (see `app/infrastructure/vector_store.py` line 19-20).

### Does My Project Enforce Dimensions?

**No explicit enforcement.** The `VectorStore` does not validate that all stored vectors have the same dimension. However, if a query vector has a different dimension than a stored vector, `_cosine_similarity` returns `0.0` (dimension mismatch guard at `vector_store.py` line 115):

```python
if query_dim == len(entry.embedding) and query_norm and entry_norm:
    score = dot / (query_norm * entry_norm)
```

In practice, since the same model (`nomic-embed-text`) is used for both document and query embeddings, dimensions always match (768).

---

# 4. What an Embedding Looks Like

```text
Text:
"Python is a programming language."

Embedding (768 numbers, nomic-embed-text):
[0.021, -0.438, 0.912, 0.115, -0.330, 0.761, -0.089, 0.244, ...]
 ↑                                                              ↑
 first dimension                                          768th dimension
```

**Important:** The values above are *illustrative*. Actual `nomic-embed-text` values are not printed by the project. Each number is a vector component; the complete vector has 768 dimensions; the vector represents semantic information about the input text.

Two similar texts would produce vectors that are close together in this 768-dimensional space. The actual numerical values are meaningless in isolation — what matters is the *distance* between vectors.

---

# 5. How My Project Creates Vectors

```text
Document (SourceDocument)
    │
    ▼
Extracted Text (string)
    │  ← RoutedProcessor / OCR / VisionProcessor fills document.text
    │
    ▼
SemanticChunker.chunk(text, source, source_type)
    │  ← app/infrastructure/semantic_chunking.py
    │  ← Splits by headings, blocks, sentences
    │  ← Returns list[DocumentChunk]
    │
    ▼
EmbeddingService.embed_batch(texts)
    │  ← app/infrastructure/embeddings.py
    │  ← Calls Ollama nomic-embed-text
    │  ← Returns list[EmbeddingResult] (each has embedding: list[float])
    │
    ▼
VectorEntry creation
    │  ← app/pipelines/ingest_workflow.py lines 911-925
    │  ← Maps chunk → VectorEntry(chunk_id, text, embedding, source, ...)
    │
    ▼
VectorStore.add_batch(entries)
    │  ← app/infrastructure/vector_store.py
    │  ← Stores in _entries dict, pre-computes norms
    │
    ▼
VectorStore.save()
    │  ← Atomic write to data/manifests/vector_store.json
```

### Key Classes/Functions

| Stage | Class/Function | File |
|---|---|---|
| Chunking | `SemanticChunker.chunk()` | `app/infrastructure/semantic_chunking.py:241` |
| Embedding | `EmbeddingService.embed_batch()` | `app/infrastructure/embeddings.py:58` |
| Entry creation | (inline in `IngestionWorkflow._run_knowledge_engine`) | `app/pipelines/ingest_workflow.py:911` |
| Storage | `VectorStore.add_batch()` | `app/infrastructure/vector_store.py:73` |
| Persistence | `VectorStore.save()` | `app/infrastructure/vector_store.py:126` |

---

# 6. What Is a Vector Database?

### Beginner Explanation

A **vector database** is a specialized database designed to store and search vectors (lists of numbers) efficiently. Unlike a regular database that stores rows and columns, a vector database stores embeddings and can quickly find which ones are most similar to a query vector.

**Why do we need one?**

When you have thousands of document chunks, each represented as a 768-dimensional vector, you need a fast way to find the closest matches to a query vector. Checking every vector one by one is slow for large collections.

**What does it store?**

Vectors (embeddings) along with metadata: the original text, source file, position in the document, and any other information you want to attach.

**How does it find similar vectors?**

It uses approximate nearest neighbor (ANN) algorithms like HNSW, IVF, or brute-force cosine similarity to find vectors that are geometrically close to the query vector.

### What My Project Actually Uses

PAM does **NOT** use a vector database. It uses a **custom in-memory vector store with JSON persistence**.

| Aspect | Vector Database | PAM's Vector Store |
|---|---|---|
| Storage | Disk-native, indexed | In-memory dict (`_entries`) |
| Persistence | Native (WAL, SSTable, etc.) | JSON file via `os.replace()` |
| Search | ANN indexes (HNSW, IVF) | Brute-force linear scan |
| Scalability | Millions+ vectors | Practical for ~10k vectors |
| Dependencies | External (ChromaDB, FAISS, Qdrant) | None — pure Python |

This is a deliberate choice for a local-first, dependency-free system. It works well for personal knowledge bases (hundreds to low thousands of documents). For larger corpora, the project's V2 roadmap lists switching to ChromaDB/FAISS/Qdrant.

---

# 7. My Actual Vector Storage

### Storage Class

`VectorStore` in `app/infrastructure/vector_store.py`

### Data Structure

```python
class VectorStore:
    _entries: dict[str, VectorEntry]    # id → entry
    _norms: dict[str, float]            # id → pre-computed L2 norm
    _version: int                       # mutation counter (for BM25 cache)
    _persistence_path: Path | None      # data/manifests/vector_store.json
```

### VectorEntry Schema (domain model)

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Chunk ID, e.g. `"/path/to/file.md::chunk_0"` |
| `text` | `str` | The chunk text |
| `embedding` | `list[float]` | 768-dimensional vector |
| `source` | `str` | Original file path |
| `source_type` | `str` | Document kind (markdown, pdf, code, etc.) |
| `chunk_index` | `int` | Position in document (0-based) |
| `start_char` | `int \| None` | Start character offset in original text |
| `end_char` | `int \| None` | End character offset in original text |
| `metadata` | `dict[str, str]` | Heading info, structure type, language, etc. |

### JSON Persistence Schema

```json
{
  "entries": [
    {
      "id": "/path/to/file.md::chunk_0",
      "text": "The chunk text content...",
      "embedding": [0.021, -0.438, ...],
      "source": "/path/to/file.md",
      "source_type": "markdown",
      "chunk_index": 0,
      "start_char": 0,
      "end_char": 1950,
      "metadata": {"heading": "Introduction", "heading_level": "1"}
    }
  ]
}
```

**Source:** `vector_store.py` lines 130-143 (serialization), lines 172-193 (deserialization).

### Persistence Details

- **File:** `data/manifests/vector_store.json`
- **Write:** Atomic — writes to `.tmp` file first, then `os.replace()` (lines 146-157)
- **Read:** On `VectorStore.__init__()` if file exists (line 56-57)
- **Format:** Compact JSON with `separators=(",", ":")` for ~32% smaller files (line 151)
- **Corruption handling:** Malformed entries are skipped with a warning (line 192-193)

### Update Behavior

- `add()` / `add_batch()`: Overwrites if same ID exists (dict key collision = last-write-wins)
- `remove()`: Deletes by ID
- `save()`: Writes all current entries atomically
- **No merge/diff** — full overwrite on every save

### Deletion Behavior

- `remove(entry_id)`: Removes from `_entries` and `_norms`, bumps version
- **No orphan cleanup:** If a document is deleted from the filesystem, its vectors remain in the store forever until manually cleaned

---

# 8. Vector Storage Lifecycle

```text
Chunk (DocumentChunk)
    │
    ▼
EmbeddingService.embed_batch([chunk.text, ...])
    │  Returns EmbeddingResult with embedding: list[float]
    │
    ▼
VectorEntry(id=chunk.chunk_id, text=chunk.text, embedding=..., ...)
    │
    ▼
VectorStore.add_batch([entry, ...])
    │  Stores in _entries dict
    │  Pre-computes L2 norm in _norms dict
    │  Bumps _version counter
    │
    ▼
VectorStore.save()
    │  Atomic write to vector_store.json
    │
    ▼
VectorStore.search(query_embedding, top_k=5, min_score=0.0)
    │  Linear scan over all entries
    │  Cosine similarity for each
    │  Filter by min_score
    │  Sort by score (desc) then id (for stability)
    │  Return top_k results
```

### What Happens When a Document Is Re-Ingested

1. SHA-256 check: if unchanged, skip (manifest dedup)
2. If changed, a new document is processed with new chunks
3. New chunks get new IDs (`"{source}::chunk_0"`, `"{source}::chunk_1"`, etc.)
4. Same source path → same chunk ID prefix → **new entries overwrite old entries** (dict key collision)
5. Old vectors for the same source are replaced, not accumulated

### What Happens When a Document Changes

- SHA-256 changes → treated as new ingestion
- New chunks replace old chunks (same ID prefix, last-write-wins)
- No partial update — all chunks are replaced

### What Happens When a Document Is Deleted

- **Nothing.** Vectors remain in the store
- No filesystem watcher for deletions
- No garbage collection
- Vectors become orphaned (searchable but with no corresponding source file)

### What Happens on Duplicate Data

- Same chunk ID → `add()` overwrites (dict key collision)
- Same source file → same chunk IDs → old entries replaced

---

# 9. What Is Vector Similarity?

**What does it mean for two vectors to be similar?**

Two vectors are similar when they point in roughly the same direction in vector space. For text embeddings, this means the texts have similar meaning.

### Conceptual Example

```text
Vector A: [0.8, 0.6, 0.0]    ← "How to train a neural network"
Vector B: [0.7, 0.7, 0.1]    ← "Steps to teach a deep learning model"
Vector C: [0.0, 0.0, 1.0]    ← "Best pizza restaurants in Rome"

A and B are similar (close in vector space) → high cosine similarity
A and C are dissimilar (far apart) → low cosine similarity
```

### Key Terms

- **Semantic similarity:** How close the *meanings* are, regardless of exact words
- **Vector distance:** Geometric distance between two points in vector space
- **Similarity score:** A number (typically -1 to 1 for cosine) indicating how similar two vectors are
- **High score:** Vectors are close → meanings are similar
- **Low score:** Vectors are far apart → meanings are different

### How My Project Performs Similarity Search

The `VectorStore.search()` method (`vector_store.py:94-124`):
1. Computes the query vector's L2 norm (pre-computed once)
2. For each stored entry, computes cosine similarity via dot product / (query_norm × entry_norm)
3. Filters out results below `min_score`
4. Sorts by score descending, then by ID for deterministic ties
5. Returns top `top_k` results

---

# 10. Cosine Similarity

### Intuitive Explanation

Cosine similarity measures the **angle** between two vectors, not their length. Two vectors pointing in the same direction have a similarity of 1.0. Two vectors pointing in opposite directions have -1.0. Perpendicular vectors have 0.0.

Why angle and not length? Because in embedding space, the *direction* encodes meaning, and the *magnitude* is less important. A longer version of the same vector should still be "similar."

### Formula

```text
cosine_similarity(A, B) = (A · B) / (||A|| × ||B||)

Where:
  A · B     = dot product (sum of element-wise products)
  ||A||     = L2 norm (sqrt of sum of squares)
  ||B||     = L2 norm
```

### Score Range

| Score | Meaning |
|---|---|
| 1.0 | Identical direction (same meaning) |
| 0.8 - 0.99 | Very similar meaning |
| 0.5 - 0.79 | Somewhat similar |
| 0.0 - 0.49 | Weak or no similarity |
| -1.0 | Opposite meaning (rare for text embeddings) |

### Why Cosine Similarity Is Commonly Used

- **Length-invariant:** A short and long version of the same text get similar scores
- **Bounded range:** Always between -1 and 1, making thresholds easy to set
- **Computationally simple:** Just a dot product and two norms
- **Works well with normalized embeddings:** Most embedding models produce near-unit vectors

### Does My Project Use Cosine Similarity?

**Yes.** VERIFIED IMPLEMENTED.

The `_cosine_similarity()` function in `app/infrastructure/vector_store.py:18-26`:

```python
def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
```

The same computation is used inline in `VectorStore.search()` (lines 105-119) with pre-computed norms for performance.

---

# 11. Other Similarity Metrics

| Metric | Implemented? | Where Used | Higher/Lower Is Better? |
|---|---|---|---|
| Cosine similarity | **Yes** | `VectorStore.search()`, `_cosine_similarity()` | Higher is better |
| BM25 (Okapi) | **Yes** | `BM25Index.search()` — lexical/keyword matching | Higher is better |
| Reciprocal Rank Fusion | **Yes** | `_rrf_fuse()` in `app/infrastructure/search.py` — merges dense + BM25 results | Higher is better |
| Dot product | **No** | Not implemented as a separate metric | — |
| Euclidean distance (L2) | **No** | Not implemented | — |
| Inner product | **No** | Not implemented as a separate metric | — |
| Manhattan distance (L1) | **No** | Not implemented | — |

**Source:** Searched entire codebase for `euclidean`, `l2`, `manhattan`, `inner_product`, `dot_product`. No matches found beyond the cosine implementation.

---

# 12. Vector Normalization

### What Normalization Means

Normalization means scaling a vector so its length (L2 norm) equals 1.0. A normalized vector lies on the unit sphere. This makes cosine similarity equivalent to a simple dot product (since `||A|| = 1`).

### Does My Project Normalize Vectors?

**Not explicitly.** The `EmbeddingService` does not normalize vectors after receiving them from Ollama. Ollama's `nomic-embed-text` may return near-unit vectors (this is common for embedding models), but PAM does not enforce or verify this.

### Where Normalization Matters in PAM

- `VectorStore.search()` computes `query_norm` and `entry_norm` for each comparison (lines 105-119)
- Pre-computed norms are stored in `VectorStore._norms` dict (line 70, 76)
- If a vector has norm 0 (zero vector), cosine similarity returns 0.0 (line 24-25)

### Impact

Since cosine similarity divides by the norms, un-normalized vectors still produce correct similarity scores. Normalization would only matter if the project switched to dot-product similarity (which it doesn't).

---

# 13. Query Embedding

### What Happens When You Ask a Question

```text
User asks:
"How are handwritten PDFs processed?"
    │
    ▼
SearchService.search(query="How are handwritten PDFs processed?", top_k=5)
    │  ← app/infrastructure/search.py:252
    │
    ▼
SearchService._embed_query(query)
    │  ← app/infrastructure/search.py:268
    │  ← Calls self._embed(query)
    │  ← self._embed is the callable passed at construction
    │
    ▼
EmbeddingService.embed(query)
    │  ← app/infrastructure/embeddings.py:53
    │  ← Calls Ollama nomic-embed-text
    │  ← Returns EmbeddingResult with embedding: list[float]
    │
    ▼
query_embedding: list[float]   (768 dimensions)
    │
    ▼
HybridSearch.search(query, query_embedding, top_k=5)
    │  ← Combines dense search + BM25 + RRF fusion
```

### Key Details

| Detail | Value |
|---|---|
| Model for query embedding | Same as documents: `nomic-embed-text` |
| Same model for docs and queries? | **Yes** — VERIFIED |
| Query preprocessing | None (raw query text sent to model) |
| Query embedding location | Created in `SearchService._embed_query()`, used in `HybridSearch.search()` |

**Source:** `search.py` lines 244-249 show the default embedder setup; line 262 shows query embedding in the search method.

---

# 14. Vector Search

### How Vector Search Works in My Implementation

```text
Query vector (768-dim)
    │
    ▼
VectorStore.search(query_embedding, top_k, min_score)
    │  ← app/infrastructure/vector_store.py:94
    │
    ├── For each stored entry:
    │     ├── Check dimension match (query_dim == entry.embedding length)
    │     ├── Compute cosine similarity: dot / (query_norm × entry_norm)
    │     ├── If score >= min_score: include in results
    │
    ├── Sort by (-score, entry.id)
    │
    └── Return top_k results
```

### Details

| Aspect | Implementation |
|---|---|
| Query vector | 768-dim from `nomic-embed-text` |
| Stored vectors | In-memory dict (`_entries`) |
| Similarity calculation | Cosine similarity (brute-force linear scan) |
| Ranking | Score descending, then ID ascending (deterministic) |
| Score | Cosine similarity value (-1.0 to 1.0) |
| Top-K | Configurable, default 5 |
| Threshold | `min_score` parameter, default 0.0 |
| Metadata filtering | Exact-match on `VectorEntry` fields, then `metadata` keys |
| Result ordering | Score descending, then ID ascending |

**Note:** BM25/hybrid/RRF fusion is documented separately. This section covers only the dense vector search leg.

---

# 15. Top-K

### What Top-K Means

Top-K means "return the K most similar results." K is the maximum number of results to return.

### Actual K Values in My Project

| Context | Default K | Configurable? | Evidence |
|---|---|---|---|
| `VectorStore.search()` | 5 | Yes (parameter) | `vector_store.py:98` |
| `SemanticSearch.search()` | 5 | Yes (parameter) | `search.py:93` |
| `HybridSearch.search()` | 5 | Yes (parameter) | `search.py:155` |
| `SearchService.search()` | 5 | Yes (parameter) | `search.py:256` |
| `pam search` CLI | 5 | Yes (`--top-k` flag) | `app/cli/entry.py` |
| `pam ask` (QA) | 8 | Hardcoded in `QAWorkflow` | `app/application/qa_workflow.py` |
| Cross-document linking | 3 | Hardcoded | `ingest_workflow.py:988,991` |

### Pool Size

For hybrid search, the candidate pool per leg is `max(top_k * 5, 50)` (line 158 of `search.py`). So for `top_k=5`, each leg (dense + BM25) considers up to 50 candidates before RRF fusion.

### Minimum K

K must be > 0 for results. `HybridSearch.search()` returns `[]` if `top_k <= 0` (line 157).

### Maximum K

No hard maximum. The only practical limit is the total number of entries in the store.

---

# 16. Score Thresholds

### Default Threshold

**`min_score = 0.0`** — no filtering by default. All results with score >= 0.0 are returned.

Since cosine similarity ranges from -1.0 to 1.0, and `min_score=0.0` excludes negative scores, effectively only vectors with positive similarity are returned.

### Where Thresholds Are Used

| Location | Default | Evidence |
|---|---|---|
| `VectorStore.search()` | 0.0 | `vector_store.py:99` |
| `SemanticSearch.search()` | 0.0 | `search.py:95` |
| `HybridSearch.search()` | 0.0 | `search.py:155` |
| `SearchService.search()` | 0.0 | `search.py:257` |
| Cross-document linking | **0.7** | `ingest_workflow.py:991` |

### What Happens Below Threshold

Results with `score < min_score` are excluded from the results list.

### What Happens If No Result Passes

An empty list is returned. No error is raised.

### Is Threshold Configurable?

**Yes** — via the `min_score` parameter on all search methods. Not exposed as a CLI flag for `pam search` (only `--top-k` is available).

---

# 17. Embedding Limits

### Embedding Input Limit

The `nomic-embed-text` model supports up to **8192 tokens** input. This is the embedding model's context window — the maximum number of tokens it can process in a single embedding call.

### LLM Context Window

The LLM (e.g., `qwen3:8b`) has a separate context window for text generation. This is **not** the same as the embedding input limit.

| Component | Limit | Purpose |
|---|---|---|
| `nomic-embed-text` (embedding) | 8192 tokens | Maximum input for creating an embedding |
| `qwen3:8b` (LLM) | Separate context window | Maximum input for text generation/analysis |

### Chunk Size Relationship

Default chunk size is **2000 characters** (`SemanticChunker.max_chunk_chars`). At ~4 tokens per character (rough average), this is ~5000 tokens — well within the 8192-token embedding limit.

### Batch Limits

`embed_batch()` sends all texts in a single Ollama API call. Ollama handles batching internally. No explicit batch size limit is enforced by PAM.

### What Happens When Text Is Too Large

If a single chunk exceeds the model's token limit, Ollama will truncate or error. PAM does not pre-check token count. In practice, the 2000-char default chunk size keeps chunks well within limits.

---

# 18. Storage Schema

### Complete Storage Structure

```text
data/manifests/
├── processed_files.json     ← Manifest (SHA-256 dedup)
├── vector_store.json        ← Vector embeddings
├── knowledge_graph.json     ← Entity/relationship graph
└── queue_state.json         ← Queue persistence

vector_store.json:
{
  "entries": [
    {
      "id": "{source}::chunk_{index}",        ← string, unique per chunk
      "text": "chunk text content...",          ← string, the actual text
      "embedding": [0.021, -0.438, ...],       ← list[float], 768 dimensions
      "source": "/path/to/original/file.md",   ← string, source file path
      "source_type": "markdown",                ← string, document kind
      "chunk_index": 0,                         ← int, position in document
      "start_char": 0,                          ← int, start offset in text
      "end_char": 1950,                         ← int, end offset in text
      "metadata": {                             ← dict[str, str], chunk context
        "heading": "Introduction",
        "heading_level": "1",
        "heading_path": "Introduction",
        "parent_heading": ""
      }
    }
  ]
}
```

### In-Memory Structure

```text
VectorStore
├── _entries: dict[str, VectorEntry]    ← id → entry (O(1) lookup)
├── _norms: dict[str, float]            ← id → L2 norm (pre-computed)
├── _version: int                       ← mutation counter (for BM25 cache)
└── _persistence_path: Path             ← vector_store.json path
```

---

# 19. Embedding Caching

**Embedding caching is not currently implemented.**

Every embedding call goes to Ollama, even for previously embedded text. There is no:
- Disk cache for embeddings
- In-memory LRU cache
- Hash-based cache key
- Invalidation logic

The only "caching" is the vector store itself — once a chunk is embedded and stored, re-ingesting the same file (with the same SHA-256) skips the entire pipeline via manifest dedup, so embeddings are not re-computed.

---

# 20. Complete Storage Architecture

### Ingestion Path

```text
Document (SourceDocument)
    │
    ▼
RoutedProcessor → extracted text
    │
    ▼
SemanticChunker.chunk()
    │  ← Splits by headings, blocks, sentences
    │  ← Overlap: 200 chars tail prepend
    │  ← Returns list[DocumentChunk]
    │
    ▼
EmbeddingService.embed_batch()
    │  ← Ollama nomic-embed-text
    │  ← Returns list[EmbeddingResult]
    │
    ▼
VectorStore.add_batch()
    │  ← Stores entries in _entries dict
    │  ← Pre-computes norms in _norms dict
    │  ← Bumps _version
    │
    ▼
VectorStore.save()
    │  ← Atomic write: .tmp → os.replace()
    │  ← File: data/manifests/vector_store.json
```

### Query Path

```text
User Query
    │
    ▼
SearchService.search(query, top_k=5)
    │
    ├── _embed_query(query)
    │     └── EmbeddingService.embed(query) → query_embedding
    │
    ├── HybridSearch.search(query, query_embedding, top_k)
    │     │
    │     ├── Dense leg: VectorStore.search(query_embedding, pool_size)
    │     │     └── Cosine similarity over all entries
    │     │
    │     ├── Lexical leg: BM25Index.search(query, pool_size)
    │     │     └── Okapi BM25 over tokenized text
    │     │
    │     └── RRF fusion: _rrf_fuse(dense_ids, bm25_ids, k=60)
    │           └── Merges ranked lists by reciprocal rank
    │
    └── Return list[SearchHit] (top_k results)
```

### Mermaid Diagram

```mermaid
flowchart TD
    A[Document] --> B[SemanticChunker]
    B --> C["Chunks (list[DocumentChunk])"]
    C --> D[EmbeddingService.embed_batch]
    D --> E["Embeddings (list[EmbeddingResult])"]
    C --> F[Create VectorEntry per chunk]
    E --> F
    F --> G[VectorStore.add_batch]
    G --> H["_entries dict + _norms dict"]
    H --> I[VectorStore.save]
    I --> J["vector_store.json (atomic write)"]

    K[User Query] --> L[SearchService.search]
    L --> M["_embed_query → Ollama nomic-embed-text"]
    M --> N[query_embedding: list[float]]
    L --> O[HybridSearch.search]
    N --> O
    J --> O
    O --> P["Dense: VectorStore.search (cosine)"]
    O --> Q["Lexical: BM25Index.search"]
    P --> R["RRF Fusion (k=60)"]
    Q --> R
    R --> S["Top-K SearchHits"]
```

---

# 21. Beginner Summary

## Explain This Like I Know Nothing About RAG

**Embedding:** Converting text into a list of numbers (a vector) so a computer can understand meaning, not just words. Your document gets chopped into chunks, and each chunk becomes a vector of 768 numbers.

**Vector:** A list of numbers representing text. Think of it as a GPS coordinate, but in 768-dimensional space instead of 2 dimensions. Each number tells you where the text "sits" in meaning-space.

**Dimensions:** How many numbers are in the vector. `nomic-embed-text` uses 768 dimensions. More dimensions = more nuanced meaning capture. All vectors in the same store must have the same number of dimensions.

**Vector Database:** A place to store vectors so you can quickly find similar ones. PAM uses a simple in-memory dictionary with JSON file backup — not a fancy database, but it works for personal use.

**Similarity:** How close two vectors are in meaning-space. If two vectors point in the same direction, the texts have similar meaning.

**Cosine Similarity:** The specific math PAM uses to measure similarity. It measures the angle between two vectors. Score of 1.0 = same meaning. Score of 0.0 = unrelated. Score of -1.0 = opposite.

**Query Embedding:** When you ask a question, PAM converts your question into a vector using the same model that created the document vectors. Then it finds which document vectors are closest.

**Top-K:** "Give me the K most similar results." If K=5, you get up to 5 matching chunks. PAM defaults to K=5 for search and K=8 for Q&A.

**Threshold:** A minimum similarity score. Results below this score are thrown away. PAM's default threshold is 0.0 (no filtering), but cross-document linking uses 0.7.

**All connected:** Your documents get chunked → each chunk gets embedded → embeddings get stored → you ask a question → your question gets embedded → PAM finds the most similar stored embeddings → those chunks get sent to an LLM → the LLM answers using those chunks as context.

---

# 22. Actual Implementation Summary

## What My Project Actually Uses

| Component | Actual Value |
|---|---|
| Embedding model | `nomic-embed-text` via Ollama |
| Vector dimension | 768 |
| Vector storage | In-memory dict + JSON persistence (`vector_store.json`) |
| Similarity metric | Cosine similarity (custom implementation) |
| Top-K (search) | 5 (default), configurable |
| Top-K (QA) | 8 (hardcoded in QAWorkflow) |
| Score threshold | 0.0 (default), 0.7 for cross-doc linking |
| Query embedding | Same model as documents (`nomic-embed-text`) |
| Persistence | Atomic JSON write (`data/manifests/vector_store.json`) |
| BM25 | Pure-Python Okapi BM25, k1=1.5, b=0.75 |
| Hybrid fusion | Reciprocal Rank Fusion, k=60 |
| Normalization | Not explicit (relies on Ollama output) |
| Embedding caching | Not implemented |
| Chunk size | 2000 chars default, 200 char overlap |
| Embedding input limit | 8192 tokens (model capacity) |

---

# 23. Important Discoveries

1. **No vector dimension enforcement.** The store accepts any dimension. Mismatched query/store dimensions silently return 0.0 score. In practice this never happens because the same model is always used.

2. **No embedding caching.** Every search query re-embeds the query text via Ollama. For repeated queries, this is wasteful. The vector store itself is the only "cache" — re-ingesting the same file skips via SHA-256 dedup.

3. **No delete/GC for vectors.** Deleted or modified files leave orphaned vectors. Over time, the store accumulates stale entries.

4. **Brute-force search.** No ANN index. Linear scan over all entries. Practical for <10k vectors; would be slow for 100k+.

5. **Batch embedding count mismatch is fatal.** If Ollama returns fewer/more vectors than requested texts, `EmbeddingCountMismatchError` is raised immediately without retry (unlike transient errors which retry 2×). This prevents silent chunk-vector misalignment.

6. **BM25 index is rebuilt lazily.** Only when `VectorStore.version` changes (i.e., when the corpus is mutated). Not rebuilt on every query. This was a measured optimization (noted in `search.py:117-118`).

7. **RRF k=60 is hardcoded.** Not configurable via settings or CLI. The `HybridSearch` constructor accepts `rrf_k` but it's not exposed to the user.

8. **Cross-document linking threshold is hardcoded.** `min_score=0.7` in `ingest_workflow.py:991` — not configurable.

9. **Ollama `nomic-embed-text` context window is 8192 tokens** (confirmed from Ollama docs), but PAM's default chunk size is 2000 chars (~5000 tokens), leaving headroom.

10. **The `vector_store.json` path is always `{manifest_root}/vector_store.json`.** Hardcoded in both `ingest_workflow.py:264` and `search.py:239`. Not configurable separately.

---

# 24. Final Verification

| Item | Verified? | Value |
|---|---|---|
| Embedding model | **Yes** | `nomic-embed-text` via Ollama |
| Vector dimension | **Yes** | 768 (confirmed from nomic-embed-text documentation) |
| Storage implementation | **Yes** | In-memory dict + atomic JSON persistence |
| Similarity metric | **Yes** | Cosine similarity (custom `_cosine_similarity()`) |
| Cosine similarity usage | **Yes** | `vector_store.py:18-26` and inline at `vector_store.py:115-119` |
| Normalization | **No** | Not explicit; relies on Ollama output |
| Query embedding | **Yes** | Same model (`nomic-embed-text`) via `SearchService._embed_query()` |
| Top-K | **Yes** | Default 5 (search), 8 (QA), configurable via parameter |
| Score threshold | **Yes** | Default 0.0, 0.7 for cross-doc linking |
| Embedding limits | **Yes** | 8192 tokens (model capacity); 2000 chars default chunk |
| Embedding caching | **No** | Not implemented |
| Delete/GC | **No** | Not implemented |

---

*Document created 2026-08-18. Source code was inspected but not modified. No git changes were made.*
