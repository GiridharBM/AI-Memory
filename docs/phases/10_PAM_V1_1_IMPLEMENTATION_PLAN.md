# PAM V1.1 Implementation Plan

> **Document type:** Planning document only — no code changes
> **Created:** 2026-08-19
> **Primary source:** `09_V1_FINAL_AUDIT_AND_SCOPE_DECISION.md`
> **Status:** PAM V1 remains frozen

---

# 1. V1.0 BASELINE

## Exact Current State (Verified)

| Component | Value | Evidence |
|---|---|---|
| **Version** | 1.0.0 | `pyproject.toml:7` |
| **Tests** | 1377 passing, 57 deselected | `pytest --co -q` |
| **Coverage** | 89.80% line | `pytest --cov` |
| **CLI commands** | 12 | `entry.py` — verified |
| **Active models** | qwen3:8b, nomic-embed-text, qwen2.5vl | Verified invoked |
| **Dead model config** | qwen2.5-coder:7b | CodeProcessor is passthrough |
| **Ingestion types** | 24 source types, 90+ extensions | `extensions.py`, `classifier.py` |
| **Broken adapters** | RTF, ODT, XLS, ODS, PPT, ODP | Wrong parsers assigned |
| **Embedding model** | nomic-embed-text, 768-dim | `embeddings.py:45` |
| **Vector store** | In-memory dict + JSON persistence | `vector_store.py` |
| **BM25** | Okapi, k1=1.5, b=0.75, regex tokenizer | `bm25.py:13,33-34` |
| **Hybrid search** | Vector + BM25 + RRF(k=60) | `search.py:148-197` |
| **Reranking** | None | Zero matches |
| **Context limits** | 8 chunks, 12,000 chars (hardcoded) | `qa_workflow.py:16-17` |
| **Grounding** | Prompt-level only | `qa.py:5-21` |
| **Citations** | `[SOURCE N]` format | `qa.py:20` |
| **Knowledge graph** | Built, persisted, NOT used in retrieval | `ingest_workflow.py:888-943` |
| **Audio** | faster-whisper (undeclared dep), timestamps discarded | `whisper_transcriber.py:36` |
| **Video** | Empty text, no content extracted | `video_ingestor.py:30` |
| **Watcher** | on_created only, single worker | `service.py:207`, `config.py:149` |
| **Dedup** | SHA-256 content hash | `hashing.py:22-36` |
| **CI** | ruff, mypy, pytest on ubuntu (3.11/3.12/3.13) | `.github/workflows/ci.yml` |
| **Dead dependency** | structlog (zero imports) | `pyproject.toml:22` |
| **Undeclared deps** | python-docx, python-pptx, faster-whisper | Not in pyproject.toml |

---

# 2. V1.1 PRINCIPLES

Every change in V1.1 must follow these principles:

1. **Evidence before optimization** — Measure first, optimize second. No retrieval changes without a baseline.
2. **Measurement before retrieval changes** — Evaluation dataset exists and baseline metrics are recorded before any retrieval improvement.
3. **Fix correctness before adding features** — Broken adapters, undeclared dependencies, and dead config are fixed before new features.
4. **Avoid unnecessary architecture changes** — The 4-layer architecture is sound. Don't refactor what works.
5. **Preserve working V1 behavior** — Existing CLI flags, config format, vault format, and vector format must remain backward-compatible.
6. **Small incremental changes** — Each phase produces a testable, releasable increment.
7. **Every change must have tests** — Unit tests for new code, regression tests for changed behavior, evaluation for retrieval changes.

---

# 3. PHASE 1 — RETRIEVAL BASELINE

## Evaluation Dataset Design

### Source Documents

Use PAM's own documentation and source code as the corpus. This is the most accessible and verifiable dataset.

| Document | Path | Why |
|---|---|---|
| PAM architecture | `08_PAM_V1_ARCHITECTURE_AND_EXPLANATION.md` | Comprehensive feature description |
| Ingestion reference | `01_PROJECT_AND_INGESTION_REFERENCE.md` | Detailed ingestion details |
| Embeddings reference | `02_EMBEDDINGS_VECTORS_AND_STORAGE.md` | Vector store details |
| Retrieval reference | `03_RETRIEVAL_RAG_AND_KNOWLEDGE_GRAPH.md` | Search pipeline details |
| CLI reference | `04_CLI_MODELS_LIMITS_TESTING_AND_OPERATIONS.md` | Command details |
| QA workflow source | `app/application/qa_workflow.py` | Implementation details |
| Search source | `app/infrastructure/search.py` | Retrieval implementation |
| Vector store source | `app/infrastructure/vector_store.py` | Storage implementation |

### Query Design

Create 50 queries across 5 categories:

| Category | Count | Example Query | Expected Sources |
|---|---|---|---|
| **Factoid** | 15 | "What embedding model does PAM use?" | `02_*.md` — nomic-embed-text section |
| **How-to** | 10 | "How does PAM handle scanned PDFs?" | `01_*.md` — OCR section |
| **Comparison** | 10 | "What is the difference between vector search and BM25?" | `03_*.md` — hybrid search section |
| **Negative** | 10 | "What cloud providers does PAM support?" | None (PAM is local-only) |
| **Edge case** | 5 | "What happens when the knowledge base is empty?" | `03_*.md` — zero results handling |

### Ground Truth Format

```jsonl
{
  "id": "q001",
  "query": "What embedding model does PAM use?",
  "expected_sources": ["02_EMBEDDINGS_VECTORS_AND_STORAGE.md"],
  "expected_chunks_hint": "nomic-embed-text, 768 dimensions",
  "category": "factoid",
  "min_relevant_chunks": 1
}
```

### Storage

```
eval/
  dataset.jsonl          # 50 queries with ground truth
  run_eval.py            # Evaluation script
  results/
    baseline_v1.json     # V1.0 baseline metrics
    v1.1_phase3.json     # After retrieval improvements
    v1.1_final.json      # Final V1.1 metrics
```

### Evaluation Script Design

`run_eval.py` will:
1. Load `dataset.jsonl`
2. For each query:
   a. Run `SearchService.search(query, top_k=10)` — capture ranked results
   b. Check if any expected source appears in top-K
   c. Record rank of first relevant result
3. Compute metrics across all queries
4. Save results to JSON

### Metrics

| Metric | Formula | Target |
|---|---|---|
| **Recall@5** | (relevant in top 5) / (total relevant) | ≥ 0.6 |
| **Recall@10** | (relevant in top 10) / (total relevant) | ≥ 0.75 |
| **Hit Rate** | queries with ≥1 relevant in top 5 / total queries | ≥ 0.8 |
| **MRR** | mean(1 / rank of first relevant) | ≥ 0.7 |

### Per-Component Evaluation

Also measure individual component performance:

| Component | What to Measure | How |
|---|---|---|
| Vector search only | Recall@5 without BM25 | Disable BM25 leg |
| BM25 only | Recall@5 without vectors | Disable vector leg |
| Hybrid (RRF) | Recall@5 with both | Default |
| RRF vs. max-score | Compare RRF with simple max-score fusion | Alternate fusion |

---

# 4. PHASE 2 — CORRECTNESS FIXES

## 4.1 Broken Adapters

### RTF

| Aspect | Detail |
|---|---|
| Current failure | `DocxIngestor` at `docx_ingestor.py:21` lists `.rtf` in `supported_suffixes`. `_extract_text()` at line 42 imports `python-docx` which cannot parse RTF. Raises `IngestionError`. |
| Root cause | Wrong parser assigned. RTF requires a dedicated parser (e.g., `pyreadoffice` or `striprtf`). |
| Expected fix | Remove `.rtf` from `DocxIngestor.supported_suffixes`. Either create a dedicated `RTFIngestor` or remove RTF from the supported list entirely. |
| Dependency | None new if removing from list. `striprtf` (~30 lines) if implementing. |
| Tests required | Unit test: ingest sample .rtf file, verify text extraction or graceful error. Regression: existing DOCX tests unchanged. |
| Risk | LOW — removing from list prevents errors. Users who depend on RTF can re-add later. |

### ODT

| Aspect | Detail |
|---|---|
| Current failure | `DocxIngestor` at `docx_ingestor.py:21` lists `.odt`. Same failure as RTF. |
| Root cause | Wrong parser. ODT is ODF format, not OOXML. |
| Expected fix | Remove `.odt` from `DocxIngestor.supported_suffixes`. |
| Dependency | None. |
| Tests required | Same as RTF. |
| Risk | LOW. |

### XLS

| Aspect | Detail |
|---|---|
| Current failure | `SpreadsheetIngestor` at `spreadsheet_ingestor.py:21` lists `.xls`. `openpyxl` at line 42 cannot read BIFF format. |
| Root cause | openpyxl only supports XLSX (OOXML), not XLS (BIFF). |
| Expected fix | Remove `.xls` from `SpreadsheetIngestor.supported_suffixes`. |
| Dependency | None. `xlrd` could read .xls but adds a dependency for a legacy format. |
| Tests required | Unit test: ingest sample .xls, verify graceful error or skip. |
| Risk | LOW. |

### ODS

| Aspect | Detail |
|---|---|
| Current failure | `SpreadsheetIngestor` at `spreadsheet_ingestor.py:21` lists `.ods`. openpyxl cannot read ODF. |
| Root cause | Wrong parser. |
| Expected fix | Remove `.ods` from `SpreadsheetIngestor.supported_suffixes`. |
| Dependency | None. |
| Tests required | Same as XLS. |
| Risk | LOW. |

### PPT

| Aspect | Detail |
|---|---|
| Current failure | `PptxIngestor` at `pptx_ingestor.py:21` lists `.ppt`. `python-pptx` at line 42 cannot read binary PPT. |
| Root cause | python-pptx only supports PPTX (OOXML), not PPT (binary). |
| Expected fix | Remove `.ppt` from `PptxIngestor.supported_suffixes`. |
| Dependency | None. |
| Tests required | Same pattern. |
| Risk | LOW. |

### ODP

| Aspect | Detail |
|---|---|
| Current failure | `PptxIngestor` at `pptx_ingestor.py:21` lists `.odp`. python-pptx cannot read ODF. |
| Root cause | Wrong parser. |
| Expected fix | Remove `.odp` from `PptxIngestor.supported_suffixes`. |
| Dependency | None. |
| Tests required | Same pattern. |
| Risk | LOW. |

### VSDX (Bonus Finding)

| Aspect | Detail |
|---|---|
| Current failure | Routed to `PassthroughProcessor`. Reads binary as text — garbage output. |
| Expected fix | Remove from supported extensions or implement dedicated ingestor. |
| Risk | LOW. |

## 4.2 Dependency Fixes

### structlog (REMOVE)

| Aspect | Detail |
|---|---|
| Current state | Declared at `pyproject.toml:22`. Zero imports in `app/**/*.py`. |
| Fix | Remove line 22 from `pyproject.toml`. Remove from `requirements.txt` if present. |
| Risk | NONE — nothing uses it. |

### python-docx (ADD to optional)

| Aspect | Detail |
|---|---|
| Current state | Used at `docx_ingestor.py:42`. Not declared in pyproject.toml. Lazy import with ImportError. |
| Fix | Add to `[project.optional-dependencies] intelligence` list. |
| Risk | LOW — already works via lazy import, just making it explicit. |

### python-pptx (ADD to optional)

| Aspect | Detail |
|---|---|
| Current state | Used at `pptx_ingestor.py:42`. Not declared. |
| Fix | Add to `[project.optional-dependencies] intelligence` list. |
| Risk | LOW. |

### faster-whisper (ADD to optional)

| Aspect | Detail |
|---|---|
| Current state | Used at `whisper_transcriber.py:27`. Not declared. Lazy import with RuntimeError. |
| Fix | Add to `[project.optional-dependencies] intelligence` list. |
| Risk | LOW. |

### httpx (Document or declare)

| Aspect | Detail |
|---|---|
| Current state | Imported at `ollama_client.py:11`. Transitive dependency of `ollama`. |
| Fix | Either add explicit dependency or document that it comes transitively via `ollama`. No code change needed — just pyproject.toml clarity. |
| Risk | LOW. |

---

# 5. PHASE 3 — RETRIEVAL IMPROVEMENTS

**Prerequisite:** Phase 1 baseline metrics recorded.

Every proposed change must be evaluated against the baseline.

## 5.1 Top-K Tuning

| Change | Hypothesis | Baseline Metric | Target Metric | Risk |
|---|---|---|---|---|
| Test top_k=3 | Fewer results improve precision | Recall@5 baseline | Recall@3 ≥ baseline × 0.9 | LOW |
| Test top_k=8 | More results improve recall | Recall@5 baseline | Recall@8 ≥ baseline × 1.1 | LOW |
| Test top_k=10 | Maximum recall | Recall@10 baseline | Recall@10 ≥ 0.75 | LOW |

**Decision:** Make top_k configurable via settings (already configurable via CLI). Default remains 5.

## 5.2 Score Thresholds

| Change | Hypothesis | Baseline Metric | Target Metric | Risk |
|---|---|---|---|---|
| Set min_score=0.15 default | Reduces noise without losing relevant results | Recall@5 baseline | Recall@5 ≥ baseline × 0.95, Precision@5 improves | LOW |
| Test min_score=0.25 | Aggressive filtering | Recall@5 baseline | Measure recall loss | MEDIUM |

**Decision:** Add `min_score: 0.15` to `config/default.yaml`. Users can override via CLI `--min-score`.

## 5.3 BM25 Stemming

| Change | Hypothesis | Baseline Metric | Target Metric | Risk |
|---|---|---|---|---|
| Add Snowball stemmer | Morphological variants match better | BM25-only Recall@5 | BM25 Recall@5 improves | LOW |
| Add stop-word removal | Reduces noise from common words | BM25-only Recall@5 | Measure impact | LOW |

**Decision:** Add optional `stemmer` parameter to `BM25Index.__init__()`. Default: `None` (current behavior). Configurable via settings.

Implementation at `bm25.py:29-35`:
```python
def __init__(self, corpus: list[str], *, k1: float = 1.5, b: float = 0.75, stemmer: Callable[[str], str] | None = None) -> None:
```

Apply stemmer in `tokenize()` at line 16-18 if provided.

## 5.4 RRF Parameters

| Change | Hypothesis | Baseline Metric | Target Metric | Risk |
|---|---|---|---|---|
| Test k=30 | Better for small corpus | Hybrid Recall@5 | Measure | LOW |
| Test k=80 | More weight on rank position | Hybrid Recall@5 | Measure | LOW |
| Make k configurable | Users can tune | — | — | LOW |

**Decision:** Make `rrf_k` configurable via settings. Default remains 60.

## 5.5 Query Processing

| Change | Hypothesis | Baseline Metric | Target Metric | Risk |
|---|---|---|---|---|
| Simple keyword expansion | "handwriting" matches "handwritten" | Recall@5 for variant queries | Measure | LOW |
| Query lowercasing | Consistent matching | — | — | TRIVIAL |

**Decision:** Add query lowercasing before BM25 tokenization (already done in BM25 tokenize). For V1.1, add optional keyword expansion via simple dictionary.

## 5.6 Candidate Pool

| Change | Hypothesis | Baseline Metric | Target Metric | Risk |
|---|---|---|---|---|
| Test pool_size=top_k×3 | Smaller pool, faster | Recall@5 | Measure | LOW |
| Test pool_size=top_k×10 | Larger pool, better fusion | Recall@5 | Measure | LOW |

**Decision:** Make pool multiplier configurable. Default remains ×5.

## 5.7 Reranking

See Section 6.

---

# 6. RERANKING DECISION

## Should Reranking Be in V1.1?

### Arguments For
- Cross-encoders see query+document together, catching relevance that cosine similarity misses
- Documented ~10-15% MRR improvement in RAG benchmarks
- Insertion point is clear: after RRF fusion, before context building

### Arguments Against
- Adds 50-200ms latency per query (cross-encoder inference)
- Adds ~80MB model download
- Adds `sentence-transformers` dependency (large)
- Cannot be measured without baseline (Phase 1 prerequisite)
- Personal knowledge base may not benefit as much as web-scale search

### Recommendation: **V1.1 OPTIONAL, NOT MUST HAVE**

Reranking should be:
1. Implemented as an optional, config-gated feature
2. Default: disabled
3. Evaluated against baseline to measure actual benefit
4. Only promoted to "enabled by default" if measured improvement exceeds 5% MRR

### Implementation Design (If Proceeding)

| Aspect | Detail |
|---|---|
| Where | `SearchService.search()` at `search.py:265` — after filter, before return |
| Input | `list[SearchHit]` from hybrid search (already filtered) |
| Output | `list[SearchHit]` re-sorted by cross-encoder score |
| Model | `cross-encoder/ms-marco-MiniLM-L-6-v2` (~80MB) |
| Config | `reranker.enabled: false` (default), `reranker.model: "cross-encoder/ms-marco-MiniLM-L-6-v2"` |
| Latency | 50-200ms additional per query |
| Dependency | `sentence-transformers` (optional) |

### Evaluation Criteria
- MRR improvement ≥ 5% over baseline with reranking enabled
- Latency increase < 200ms
- No regression in Recall@5

---

# 7. PHASE 4 — VECTOR STORAGE RELIABILITY

## 7.1 Stale Vector Handling

**Problem:** Re-ingesting a file adds new vectors without removing old ones for the same source.

**Fix:** Add `VectorStore.remove_by_source(source: str) -> int` method.

At `vector_store.py`, add after `remove()` (line 86-92):

```python
def remove_by_source(self, source: str) -> int:
    """Remove all entries matching a source path. Returns count removed."""
    to_remove = [eid for eid, entry in self._entries.items() if entry.source == source]
    for eid in to_remove:
        del self._entries[eid]
        self._norms.pop(eid, None)
    if to_remove:
        self._version += 1
    return len(to_remove)
```

**Call site:** `ingest_workflow.py:927` — before `store.add_batch(entries)`, call `store.remove_by_source(str(source))`.

**Risk:** LOW — non-breaking addition. Existing callers unaffected.

## 7.2 Garbage Collection

**Problem:** Deleted files leave orphan vectors.

**Fix:** Add `VectorStore.find_orphans(valid_sources: set[str]) -> list[str]` method.

```python
def find_orphans(self, valid_sources: set[str]) -> list[str]:
    """Return entry IDs whose source is not in valid_sources."""
    return [eid for eid, entry in self._entries.items() if entry.source not in valid_sources]
```

**Integration:** `pam doctor` scans vector store, reports orphan count. Optional `pam doctor --fix` removes orphans.

**Risk:** LOW — read-only by default.

## 7.3 Modified Document Handling

**Current behavior:** SHA-256 detects content change, triggers re-ingestion. New vectors added, old remain.

**Fix:** The `remove_by_source()` call in the ingestion pipeline (7.1) handles this automatically. When a modified file is re-ingested, old vectors are removed before new ones are added.

**No additional code needed** beyond 7.1.

## 7.4 Migration Risks

| Risk | Mitigation |
|---|---|
| Existing vectors have no orphan issue (V1 was frozen) | No migration needed — orphans only accumulate after V1.1 |
| `remove_by_source` could remove vectors during active search | VectorStore is not thread-safe for writes during reads; queue serializes access |
| JSON save after bulk remove could be slow | Atomic write is fast for <10k entries; acceptable for personal use |

---

# 8. PHASE 5 — EMBEDDING CACHE

## Is Caching Justified?

### Without Cache
- Every search re-embeds query via Ollama (~10-50ms)
- Every re-ingestion re-embeds unchanged chunks
- Repeated identical queries hit Ollama each time

### With Cache
- Identical queries served from cache (~0.01ms)
- Cache hit rate depends on query repetition patterns
- Invalidation: LRU eviction, no disk persistence needed

### Analysis

| Scenario | Frequency | Cache Benefit |
|---|---|---|
| Repeated query (same question twice) | Common in personal use | HIGH — saves 10-50ms |
| Similar query (different wording) | Common | LOW — different embedding, cache miss |
| Re-ingestion of unchanged file | Rare (SHA-256 dedup prevents) | NONE — already skipped |
| Batch ingestion | One-time | LOW — each chunk is unique |

### Recommendation: **Implement query embedding cache only**

**Scope:** `@functools.lru_cache` on `EmbeddingService.embed()`. One line of code.

**Not implementing:**
- Disk cache (personal use doesn't need persistence across restarts)
- Chunk embedding cache (SHA-256 dedup already prevents re-embedding)
- Invalidation logic (LRU handles eviction)

**Implementation at `embeddings.py`:**

```python
from functools import lru_cache

@lru_cache(maxsize=1024)
def embed(self, text: str) -> EmbeddingResult:
    # ... existing code
```

**Risk:** TRIVIAL — one decorator addition, backward-compatible.

---

# 9. PHASE 6 — AUDIO

## Current Verified Behavior

| Aspect | Value | Evidence |
|---|---|---|
| Model | `faster-whisper`, size "base" | `whisper_transcriber.py:16` |
| Device | CPU | `whisper_transcriber.py:17` |
| File types | .mp3, .wav, .m4a, .flac, .ogg, .aac | `audio_ingestor.py:20` |
| Transcription | `model.transcribe(path, beam_size=5)` | `whisper_transcriber.py:35` |
| Timestamps | **Discarded** | `whisper_transcriber.py:36` — only `segment.text` collected |
| Output | Flat text string | `processor_impls.py:276-289` |
| Searchable | Yes (text goes through chunking) | Full pipeline verified |
| Dependency | **Undeclared** in pyproject.toml | Not in any requirements |

## V1.1 Audio Scope

### MUST HAVE
- Declare `faster-whisper` in pyproject.toml optional dependencies

### SHOULD HAVE (if time permits)
- Preserve timestamps in transcript metadata (low effort, high value for future features)
- Make model size configurable (currently hardcoded "base")

### NOT V1.1
- Speaker diarization
- Language detection
- Audio preprocessing (noise reduction)
- Chunking by audio segments

### Timestamp Preservation Design

At `whisper_transcriber.py:36`, change from:
```python
parts = [segment.text for segment in segments]
```
to:
```python
segments_data = [{"text": s.text, "start": s.start, "end": s.end} for s in segments]
parts = [s["text"] for s in segments_data]
```

Store `segments_data` in `ProcessedDocument.metadata["audio_segments"]` for future use. The flat text is still used for chunking. No breaking change.

---

# 10. PHASE 7 — VIDEO

## Current Verified Behavior

Video files (.mp4, .mkv, .mov, .avi, .webm) produce:
- `text=""` from `video_ingestor.py:30`
- `VideoProcessor` is a passthrough (`processor_impls.py:186`)
- No audio extraction, no frame extraction, no ASR
- Empty text fails at AI processing or produces empty analysis

## Recommendation: **V1.1 — Minimum Viable Video (Audio Only)**

### Why V1.1

Video is the largest content gap. Audio extraction + ASR is the minimum useful pipeline. Frame extraction is complex and should wait for V2.

### Minimum Useful Pipeline

```
Video file (.mp4 etc.)
  ↓
ffmpeg extract audio track (new)
  ↓
faster-whisper transcribe (existing)
  ↓
Flat text (existing pipeline)
  ↓
Chunking → Embedding → Storage
```

### Implementation Requirements

| Component | Difficulty | Dependency |
|---|---|---|
| ffmpeg audio extraction | Medium | `ffmpeg` binary (external) or `moviepy` (Python) |
| Audio file from video | Low | Write extracted audio to temp file |
| Route to existing ASR | Low | Reuse `WhisperTranscriber` |
| Cleanup temp file | Low | `tempfile` context manager |

### Decision Point

**Use `ffmpeg` binary (subprocess) vs. `moviepy` (Python)?**

| Approach | Pros | Cons |
|---|---|---|
| `ffmpeg` subprocess | No Python dependency, fast, well-tested | Requires ffmpeg installed on system |
| `moviepy` | Pure Python, no system dependency | Large dependency (~50MB), slow |

**Recommendation:** `ffmpeg` subprocess. PAM already depends on external tools (Tesseract). Document ffmpeg as a requirement for video support.

### Scope

- **V1.1:** Audio extraction + ASR for video files
- **V2:** Frame extraction + vision model analysis

---

# 11. PHASE 8 — KNOWLEDGE GRAPH

## Current State

- Built during ingestion (`ingest_workflow.py:888-943`)
- 5 node types, 3 edge types
- Persisted to `knowledge_graph.json`
- Rendered in Obsidian notes
- **NOT used in retrieval or QA**

## Should We Implement Graph RAG?

### Step 1: Measure Graph Quality (Before Any Implementation)

| Measurement | How | Target |
|---|---|---|
| Entity accuracy | Sample 50 documents, manually verify extracted entities | >80% accurate |
| Relationship accuracy | Sample 50 edges, verify they make sense | >70% accurate |
| Graph connectivity | Measure average degree, connected components | Meaningful connections exist |

### Step 2: Define Useful Graph Queries

| Query Type | Example | Benefit |
|---|---|---|
| Entity neighbors | "What concepts relate to 'embeddings'?" | Contextual enrichment |
| Path finding | "How does 'chunking' connect to 'retrieval'?" | Concept mapping |
| Subgraph extraction | "Show everything related to 'OCR'" | Focused context |

### Step 3: Decision Framework

| If graph quality... | Then... |
|---|---|
| >80% entity accuracy, meaningful connections | Consider graph-assisted retrieval (V1.2) |
| 60-80% accuracy | Fix extraction quality first |
| <60% accuracy | Graph retrieval is not worth implementing |

### Recommendation: **KEEP AS IS for V1.1**

- Do NOT implement graph retrieval in V1.1
- Measure graph quality as a V1.1 deliverable (manual sampling)
- Decision on graph retrieval deferred to V1.2 based on quality measurement
- The graph provides value through Obsidian integration (wiki-links, graph view)

---

# 12. PHASE 9 — OBSERVABILITY

## Current State

- Structured JSON logging (`core/logging.py`)
- Component-specific log files (`watcher.log`, `processing.log`, `errors.log`)
- Retrieval scores logged at DEBUG level only (`search.py:100-103`)
- `pam status` counters hardcoded to 0 (`entry.py:154-156`)

## V1.1 Improvements

### 12.1 Retrieval Score Logging

**At `qa_workflow.py:105-108`**, add hit scores to INFO log:

```python
# Current:
logger.info("QA request processed.", extra={"question": question, "hits": len(hits), "top_k": top_k})

# V1.1:
logger.info("QA request processed.", extra={
    "question": question,
    "hits": len(hits),
    "top_k": top_k,
    "scores": [round(h.score, 4) for h in hits[:5]],
    "sources": [h.source for h in hits[:5]],
})
```

**Risk:** TRIVIAL — log format change only.

### 12.2 RuntimeStats Persistence

**At `queue/stats.py`**, add `save()` and `load()` methods to `RuntimeStats`:

```python
def save(self, path: Path) -> None:
    path.write_text(json.dumps({...}), encoding="utf-8")

@classmethod
def load(cls, path: Path) -> "RuntimeStats":
    # ... load from JSON
```

**At `entry.py:154-156`**, load stats from disk instead of hardcoding 0.

**Risk:** LOW — additive, no breaking change.

### 12.3 Ingestion Failure Logging

**At `worker.py:258-266`**, log failure details at ERROR level with file path, error type, and traceback.

**Risk:** TRIVIAL — log enhancement only.

---

# 13. TEST PLAN

## Per-Phase Test Requirements

### Phase 1 (Evaluation)
| Test Type | What | Count |
|---|---|---|
| Unit | `run_eval.py` loads dataset, computes metrics | 5 |
| Integration | End-to-end eval: ingest docs → search → compute Recall@5 | 2 |

### Phase 2 (Correctness Fixes)
| Test Type | What | Count |
|---|---|---|
| Unit | Each removed adapter produces graceful error or skip | 6 |
| Unit | Each added dependency imports correctly | 3 |
| Regression | Existing DOCX/PPTX/XLSX tests still pass | ~20 |
| Integration | `pam ingest` with removed file types doesn't crash | 6 |

### Phase 3 (Retrieval Improvements)
| Test Type | What | Count |
|---|---|---|
| Unit | BM25 with stemmer produces different tokens | 3 |
| Unit | Configurable RRF k produces different rankings | 2 |
| Unit | Configurable context limits work | 2 |
| Integration | Search with new defaults doesn't regress | 5 |
| Evaluation | Recall@5 improvement measured | 1 |

### Phase 4 (Vector Lifecycle)
| Test Type | What | Count |
|---|---|---|
| Unit | `remove_by_source()` removes correct entries | 3 |
| Unit | `find_orphans()` identifies stale entries | 3 |
| Integration | Re-ingestion removes old vectors | 2 |
| Integration | Orphan detection works end-to-end | 1 |

### Phase 5 (Embedding Cache)
| Test Type | What | Count |
|---|---|---|
| Unit | Cache hit returns same result | 2 |
| Unit | Cache miss triggers Ollama call | 1 |
| Unit | Cache eviction works | 1 |

### Phase 6 (Audio)
| Test Type | What | Count |
|---|---|---|
| Unit | faster-whisper imports correctly | 1 |
| Integration | Audio transcription produces text | 1 |
| Unit | Timestamps preserved in metadata | 1 |

### Phase 7 (Video)
| Test Type | What | Count |
|---|---|---|
| Unit | ffmpeg extraction produces audio file | 2 |
| Integration | Video → audio → transcript → chunking pipeline | 1 |
| Unit | Temp file cleanup | 1 |

### Phase 8 (Knowledge Graph)
| Test Type | What | Count |
|---|---|---|
| Manual | Entity accuracy sampling | 1 |
| Manual | Relationship accuracy sampling | 1 |

### Coverage Target

Maintain or improve 89.80% line coverage. Estimated new tests: ~50-60.

---

# 14. BACKWARD COMPATIBILITY

## What Must Remain Unchanged

| Component | Why | Migration Risk |
|---|---|---|
| **CLI flags** | Existing scripts/aliases depend on them | NONE — adding flags is non-breaking |
| **Config format** | Existing `config/default.yaml` users | NONE — adding new fields with defaults is non-breaking |
| **Vault format** | Existing Obsidian notes depend on wiki-link format | NONE — not changing note generation |
| **Vector format** | Existing `vector_store.json` must load | NONE — adding fields is forward-compatible |
| **Manifest format** | Existing `processed_files.json` must load | NONE — not changing format |
| **Search results** | `SearchHit` fields must remain | NONE — adding fields is non-breaking |
| **QA output** | `QAAnswer` format must remain | NONE — not changing |
| **BM25 defaults** | k1=1.5, b=0.75 must remain default | NONE — adding optional stemmer is backward-compatible |
| **RRF default** | k=60 must remain default | NONE — making configurable is backward-compatible |

## Migration Requirements

| Change | Migration Needed? | Detail |
|---|---|---|
| Remove broken adapters | **NO** | Files that would have errored now produce a clear error message or are not recognized |
| Add dependencies to pyproject.toml | **NO** | Existing installations already have them (manually installed) |
| Remove structlog | **NO** | Nothing uses it |
| Add `remove_by_source()` | **NO** | New method, no existing callers |
| Add embedding cache | **NO** | Transparent, same results |
| Add BM25 stemmer | **NO** | Default `None` preserves current behavior |
| Make RRF k configurable | **NO** | Default 60 preserves current behavior |
| Make context limits configurable | **NO** | Defaults 8/12000 preserve current behavior |
| Add video audio extraction | **NO** | New capability, no existing video content to migrate |

---

# 15. IMPLEMENTATION ORDER

| # | Phase | Goal | Estimated Effort |
|---|---|---|---|
| 1 | **Retrieval evaluation** | Create dataset, measure baseline | 1-2 days |
| 2 | **Correctness fixes** | Remove broken adapters, fix dependencies | 1 day |
| 3 | **Dependency cleanup** | Remove structlog, declare missing deps | 0.5 day |
| 4 | **Retrieval improvements** | Stemming, configurable limits, score defaults | 2-3 days |
| 5 | **Vector lifecycle** | remove_by_source, orphan detection | 1-2 days |
| 6 | **Embedding cache** | LRU cache on embed() | 0.5 day |
| 7 | **Observability** | Logging improvements, stats persistence | 1 day |
| 8 | **Audio improvements** | Declare dependency, preserve timestamps | 0.5 day |
| 9 | **Video audio extraction** | ffmpeg + ASR pipeline | 2-3 days |
| 10 | **Knowledge graph evaluation** | Manual quality sampling | 0.5 day |
| 11 | **Reranking (optional)** | Cross-encoder, config-gated | 2-3 days |
| 12 | **Final verification** | Full test suite, evaluation, documentation | 1-2 days |

**Total estimated effort:** 12-18 days for a single developer.

---

# 16. V1.1 SCOPE

### MUST HAVE (8 items)

1. Retrieval evaluation dataset (50 queries, ground truth)
2. Baseline metrics (Recall@5, MRR, Hit Rate)
3. Remove 6 broken adapters (RTF, ODT, XLS, ODS, PPT, ODP)
4. Fix 4 dependency issues (remove structlog, add python-docx/python-pptx/faster-whisper)
5. `VectorStore.remove_by_source()` + stale vector cleanup on re-ingestion
6. Configurable `MAX_CONTEXT_CHUNKS` and `MAX_CONTEXT_CHARS`
7. BM25 stemming (optional, default off)
8. `pam status` shows real runtime counters

### SHOULD HAVE (6 items)

9. Embedding LRU cache (query-level)
10. Score threshold default (min_score: 0.15)
11. RRF k configurable via settings
12. Retrieval score logging at INFO level
13. Preserve audio timestamps in metadata
14. Video audio extraction (ffmpeg + ASR)

### OPTIONAL (4 items)

15. Cross-encoder reranking (config-gated, default off)
16. Orphan vector detection in `pam doctor`
17. Query keyword expansion
18. Candidate pool multiplier configurable

### V2 (7 items)

19. External vector database (FAISS/ChromaDB)
20. Graph RAG (after graph quality measurement)
21. LLM streaming
22. Parallel ingestion
23. Docker support
24. Video frame extraction + vision analysis
25. macOS CI

---

# 17. WHAT NOT TO IMPLEMENT

| Feature | Why |
|---|---|
| Microservices architecture | PAM is a personal CLI tool, not a distributed system |
| Kubernetes deployment | Single-user local tool doesn't need orchestration |
| Authentication server | CLI-only with filesystem ACLs is sufficient |
| Cloud infrastructure | Local-first is a core design principle |
| Graph RAG without evidence | Would add complexity without knowing if graph quality is good |
| Complex agent systems | RAG with grounding is sufficient for personal QA |
| Unnecessary databases | JSON files work for personal scale |
| GraphQL API | No consumers need it |
| WebSocket streaming | CLI doesn't need it |
| Multi-tenant architecture | Single-user tool |
| Unnecessary abstractions | Interface with one implementation, factory for one product |
| Speculative config | Config for values that never change |

---

# 18. DEFINITION OF DONE

## V1.1 Is Complete When:

### Tests
- [ ] All existing 1377 tests pass (no regressions)
- [ ] 50+ new tests added (estimated total: 1430+)
- [ ] Line coverage ≥ 89.80% (maintain or improve)

### Evaluation
- [ ] 50-query evaluation dataset created (`eval/dataset.jsonl`)
- [ ] Baseline metrics recorded (`eval/results/baseline_v1.json`)
- [ ] V1.1 metrics recorded (`eval/results/v1.1_final.json`)
- [ ] Recall@5 ≥ 0.6
- [ ] MRR ≥ 0.7
- [ ] Hit Rate ≥ 0.8

### Correctness
- [ ] 6 broken adapters removed from supported list
- [ ] structlog removed from pyproject.toml
- [ ] python-docx, python-pptx, faster-whisper declared in pyproject.toml
- [ ] `pam ingest` with removed file types produces clear error (not crash)

### Features
- [ ] `VectorStore.remove_by_source()` implemented and tested
- [ ] Re-ingestion removes old vectors
- [ ] `MAX_CONTEXT_CHUNKS` and `MAX_CONTEXT_CHARS` configurable
- [ ] BM25 stemmer optional parameter works
- [ ] Embedding cache active (LRU, 1024 entries)
- [ ] `pam status` shows real counters
- [ ] Retrieval scores logged at INFO level
- [ ] Audio timestamps preserved in metadata
- [ ] Video audio extraction works (if ffmpeg available)

### Documentation
- [ ] README updated with new features
- [ ] Config documentation updated
- [ ] V1.1 changelog created
- [ ] Architecture diagram updated (if changed)

### CI
- [ ] All CI checks pass (ruff, mypy, pytest)
- [ ] No new warnings

---

# 19. FINAL V1.1 ROADMAP

## Phase 1: Evaluation Foundation (Days 1-2)

**Goal:** Establish measurable baseline.

| Change | Tests | Measurement |
|---|---|---|
| Create `eval/dataset.jsonl` (50 queries) | Unit: dataset loading | — |
| Create `eval/run_eval.py` | Unit: metric computation | — |
| Run baseline evaluation | Integration: full pipeline | Recall@5, MRR, Hit Rate |
| Record in `eval/results/baseline_v1.json` | — | Baseline established |

**Completion criteria:** Baseline metrics recorded. All existing tests pass.

## Phase 2: Correctness (Days 3-4)

**Goal:** Fix broken adapters and dependency issues.

| Change | Tests | Measurement |
|---|---|---|
| Remove RTF/ODT from DocxIngestor | 2 unit + 1 regression | No crash on .rtf/.odt |
| Remove XLS/ODS from SpreadsheetIngestor | 2 unit + 1 regression | No crash on .xls/.ods |
| Remove PPT/ODP from PptxIngestor | 2 unit + 1 regression | No crash on .ppt/.odp |
| Remove structlog from pyproject.toml | 1 unit (import check) | `pip install` works |
| Add python-docx to optional deps | 1 unit | Import works |
| Add python-pptx to optional deps | 1 unit | Import works |
| Add faster-whisper to optional deps | 1 unit | Import works |

**Completion criteria:** All broken adapters removed. Dependencies declared. Tests pass.

## Phase 3: Retrieval Improvements (Days 5-7)

**Goal:** Improve retrieval quality with measurable gains.

| Change | Tests | Measurement |
|---|---|---|
| Configurable `MAX_CONTEXT_CHUNKS`/`MAX_CONTEXT_CHARS` | 2 unit | Defaults unchanged |
| BM25 optional stemming | 3 unit | Stemmed vs. unstemmed comparison |
| Configurable RRF k | 2 unit | k=60 default preserved |
| Score threshold default (min_score: 0.15) | 1 unit + eval | Recall@5 ≥ baseline × 0.95 |
| Re-run evaluation | Integration | Compare against baseline |

**Completion criteria:** Retrieval metrics improve or stay same. No regressions.

## Phase 4: Vector Lifecycle (Days 8-9)

**Goal:** Fix storage monotonicity.

| Change | Tests | Measurement |
|---|---|---|
| `VectorStore.remove_by_source()` | 3 unit | Removes correct entries |
| Call `remove_by_source` in ingestion | 2 integration | Re-ingestion replaces vectors |
| Orphan detection (read-only) | 2 unit | Identifies stale entries |

**Completion criteria:** Re-ingestion doesn't accumulate vectors. Orphans detectable.

## Phase 5: Small Improvements (Days 10-11)

**Goal:** Quick wins.

| Change | Tests | Measurement |
|---|---|---|
| Embedding LRU cache | 2 unit | Cache hit/miss |
| RuntimeStats persistence | 2 unit | `pam status` shows real numbers |
| Retrieval score logging | 1 unit | Log format correct |
| Audio timestamp preservation | 1 unit | Metadata contains segments |
| Declare faster-whisper dependency | Already done in Phase 2 | — |

**Completion criteria:** All small improvements working. Tests pass.

## Phase 6: Video (Days 12-14)

**Goal:** Minimum viable video support.

| Change | Tests | Measurement |
|---|---|---|
| ffmpeg audio extraction | 2 unit | Audio file produced |
| Video → audio → ASR pipeline | 1 integration | Video produces searchable text |
| Cleanup temp files | 1 unit | No temp file leaks |

**Completion criteria:** Video files produce searchable content (audio track only).

## Phase 7: Verification (Days 15-16)

**Goal:** Final validation.

| Change | Tests | Measurement |
|---|---|---|
| Full test suite | All 1430+ tests pass | No regressions |
| Final evaluation | Recall@5, MRR, Hit Rate | Meets targets |
| Documentation update | — | README, config docs |
| Version bump | — | pyproject.toml → 1.1.0 |

**Completion criteria:** All V1.1 scope complete. All tests pass. Metrics meet targets.

---

# 20. FINAL RECOMMENDATION

## What Should I Implement FIRST?

**Create the retrieval evaluation dataset.**

Before any code change, before any fix, before any improvement — measure what you have.

### First Implementation Task

```
1. Create eval/ directory
2. Create eval/dataset.jsonl with 50 queries
3. Create eval/run_eval.py that:
   a. Loads the dataset
   b. Runs SearchService.search() for each query
   c. Computes Recall@5, MRR, Hit Rate
   d. Saves results to eval/results/baseline_v1.json
4. Run the evaluation
5. Record the baseline numbers
```

**Why this first?**
- Without baseline metrics, every subsequent change is a guess
- The evaluation dataset becomes the regression test for all retrieval improvements
- It takes 1-2 days and produces the foundation for all V1.1 work
- It reveals the actual strengths and weaknesses of the current system

**What NOT to do first?**
- Don't fix broken adapters first — they're annoying but not blocking retrieval quality
- Don't add features first — you can't measure if they help without a baseline
- Don't refactor first — the architecture is sound, leave it alone

**The evaluation dataset is the single most important V1.1 deliverable.** Everything else builds on it.

---

> **Document ends here. No source code, configuration, README, or .gitignore was modified.**
