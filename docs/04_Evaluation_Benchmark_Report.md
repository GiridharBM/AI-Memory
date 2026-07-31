# LLM Wiki – Evaluation & Benchmark Report

> Generated from live codebase inspection and measured test execution.

---

## 1. Functional Testing

### 1.1 Ingestion

**Status:** ✅ Tested (26 file types)

**Coverage:**
- `test_ingestion.py` — 29 tests covering markdown, txt, pdf, github, youtube, notebook, eml, sqlite, bib, ris, zip, drawio, csv, tsv, html, json, xml, css, toml, python, typescript, kotlin, swift, sql, tex, env
- `test_routing.py` — 102 tests covering 52 extension-to-kind mappings
- `test_text_preprocessing.py` — 4 tests for `clean_text()`
- `test_hashing.py` — 4 tests for `compute_file_hash()`

**Per-ingestor coverage (measured, from pytest-cov):**

| Module | Coverage | Gap |
|---|---|---|
| `ingestion/service.py` | 92% | Raises / unsupported paths |
| `ingestion/utils.py` | 96% | Code block edge cases |
| `ingestion/base.py` | 90% | `require_path_source` error path |
| `ingestion/pdf_ingestor.py` | 85% | Error-handling branches |
| `ingestion/markdown_ingestor.py` | 77% | Alternative paths |
| `ingestion/txt_ingestor.py` | 69% | Write methods, fallbacks |
| `ingestion/csv_ingestor.py` | 87% | Error wrappers |
| `ingestion/spreadsheet_ingestor.py` | 32% | **Low** — most error/cell-extraction paths untested |
| `ingestion/docx_ingestor.py` | 45% | **Low** — minimal test coverage |
| `ingestion/pptx_ingestor.py` | 37% | **Low** — minimal test coverage |
| `ingestion/epub_ingestor.py` | 25% | **Low** — minimal test coverage |
| `ingestion/archive_ingestor.py` | 65% | Extraction recursion |
| `ingestion/audio_ingestor.py` | 65% | Metadata paths |
| `ingestion/image_ingestor.py` | 65% | Metadata paths |
| `ingestion/video_ingestor.py` | 65% | Metadata paths |
| `ingestion/code_ingestor.py` | 69% | Language detection |
| `ingestion/config_ingestor.py` | 74% | Format-specific paths |
| `ingestion/email_ingestor.py` | 68% | Attachment handling |
| `ingestion/notebook_ingestor.py` | 84% | Cell extraction |
| `ingestion/database_ingestor.py` | 88% | Query execution paths |
| `ingestion/diagram_ingestor.py` | 77% | XML parsing |
| `ingestion/research_ingestor.py` | 94% | Citation format parsing |
| `ingestion/youtube_transcript_ingestor.py` | 78% | API error fallbacks |
| `ingestion/github_readme_ingestor.py` | 64% | HTTP error paths |

**Missing tests:** No tests for:
- Rate-limiting behavior of URL-based ingestors
- Large file handling (>100MB)
- Encoding detection fallbacks
- Concurrent ingestion

### 1.2 OCR

**Status:** 🟡 Partial — tested via `test_processor_wiring.py` and `test_processors.py`

**Coverage:**
- `processor_impls.py` — 95% (OCRProcessor, HandwritingProcessor, VisionProcessor)
- `routing/classifier.py` — 83% (scanned_pdf, handwritten, image classification)
- `vision_client.py` — 43% (**Low** — only constructor tested, `describe_image`/`describe_image_bytes` untested without a running vision model)
- `whisper_transcriber.py` — 46% (**Low** — requires running Whisper)

**What's tested:**
- `OCRProcessor.process()` returns enriched document with correct confidence
- `HandwritingProcessor.process()` returns enriched document with correct confidence
- `VisionProcessor.process()` returns enriched document with correct confidence
- `DocumentClassifier` correctly sets `requires_ocr=True` for scanned_pdf, handwritten, image
- Router selection for scanned_pdf → OCRProcessor, image → VisionProcessor, handwritten → HandwritingProcessor

**What's NOT tested:**
- `OllamaVisionClient.describe_image()` — requires live vision model
- `_ocr_extract_from_pdf()` — PyMuPDF page rendering path
- `_looks_handwritten()` heuristic
- OCR confidence scoring accuracy
- PDF >5 page truncation behavior

### 1.3 Search

**Status:** ✅ Tested (unit level only)

**Coverage:**
- `test_knowledge_engine.py` — 3 tests for `SemanticSearch` and `HybridSearch`
- `search.py` — 100% line coverage

**What's tested:**
- `SemanticSearch.search()` returns hits sorted by score
- `HybridSearch.search()` combines semantic + keyword scores
- Score weighting (0.7 semantic + 0.3 keyword)

**What's NOT tested:**
- Search with empty vector store
- Search with `min_score` filtering
- Search at >1000 entry scale (performance)
- No CLI end-to-end test (`pam search` does not exist)

### 1.4 Embeddings

**Status:** ✅ Tested

**Coverage:**
- `test_knowledge_engine.py` — 10 tests for `EmbeddingService`
- `embeddings.py` — 100% line coverage

**What's tested:**
- `embed(text)` returns `EmbeddingResult` with model and embedding
- `embed_batch(texts)` returns correct number of results
- Empty input raises `ValueError`
- Ollama response normalization

**What's NOT tested:**
- Embedding dimension validation
- Large batch behavior (memory)
- Embedding service with real Ollama timeouts
- Caching (not implemented)

### 1.5 Vector Database

**Status:** ✅ Tested

**Coverage:**
- `test_knowledge_engine.py` — 10 tests (add, search, persistence, cosine similarity)
- `vector_store.py` — 94% line coverage

**What's tested:**
- `add()` / `add_batch()` / `get()` / `remove()`
- `search()` returns sorted results, respects `top_k` and `min_score`
- `save()` / `_load()` roundtrip persistence
- `_cosine_similarity()` with identical, orthogonal, and zero vectors
- Missing `__len__` bug (previously returned 0 — fixed)

**What's NOT tested:**
- Corrupted JSON loading (silent failure path)
- Empty store search
- Large store performance (1000+ entries)
- Concurrent access

### 1.6 CLI

**Status:** ✅ Tested (basic coverage)

**Coverage:**
- `test_cli.py` — 5 tests
- `cli/entry.py` — 83% line coverage

**What's tested:**
- `config` command displays settings
- `status` command displays health
- `doctor` command checks dependencies
- `ingest markdown` runs full pipeline
- `watch` starts watcher

**What's NOT tested:**
- `ingest pdf`, `ingest txt`, `ingest github`, `ingest youtube` subcommands
- `config --json` output
- Error exit codes on failures
- `_run_ingest()` with vision/audio processors
- All `_ensure_runtime_directories()` edge cases

### 1.7 Queue

**Status:** ✅ Tested

**Coverage:**
- `test_queue_manager.py` — 7 tests
- `test_queue_state.py` — 3 tests
- `test_queue_worker.py` — 3 tests
- `test_queue_worker_pipeline.py` — 6 integration tests
- `manager.py` — 97%, `state.py` — 93%, `worker.py` — 82%

**What's tested:**
- Enqueue, dequeue, FIFO order
- Duplicate rejection (pending + processing)
- Queue capacity (`max_size`)
- State persistence and recovery (valid + invalid JSON)
- Worker processes files → vault → manifest → moved
- Worker handles unsupported files → failed path
- Worker skips duplicates

**What's NOT tested:**
- `stats.py` — 74% coverage (untested: metrics recording)
- `models.py` — 100% but minimal (data classes only)
- Worker crash recovery mid-job
- Queue draining during shutdown

### 1.8 Knowledge Graph

**Status:** ✅ Tested

**Coverage:**
- `test_knowledge_engine.py` — 10 tests for building, queries, persistence
- `domain/knowledge_graph.py` — 97%
- `infrastructure/knowledge_graph.py` — 98%

**What's tested:**
- `KnowledgeGraphBuilder.build_from_analysis()` creates correct nodes/edges
- `add_node()` / `add_edge()` with endpoint validation
- `neighbors()` bidirectional traversal
- `subgraph()` BFS with depth limit
- `save()` / `load()` JSON roundtrip
- `merge_graphs()` union merge

**What's NOT tested:**
- Edge weight semantics in search/query
- Large graph performance (>1000 nodes)
- Cross-document linking (`_find_cross_document_links` in pipeline)
- Graph save path in end-to-end workflow

---

## 2. Missing Tests (28 modules with zero dedicated test imports)

### Core
| Module | Coverage | Risk |
|---|---|---|
| `app.core.extensions` | 100% | Static constants only — low risk |
| `app.prompts.document_analysis` | 100% | Static prompt strings — low risk |

### Individual Ingestors (tested indirectly through service, but files not imported directly)
| Module | Coverage | Risk |
|---|---|---|
| `archive_ingestor.py` | 65% | Medium — archive recursion edge cases |
| `audio_ingestor.py` | 65% | Medium — no audio file test fixtures |
| `base.py` | 90% | Low — abstract base, mostly interface |
| `code_ingestor.py` | 69% | Medium — no code file test fixtures |
| `config_ingestor.py` | 74% | Low — config file read is simple |
| `csv_ingestor.py` | 87% | Low — simple text read |
| `database_ingestor.py` | 88% | Medium — query execution |
| `diagram_ingestor.py` | 77% | Medium — XML parse edge cases |
| `docx_ingestor.py` | 45% | **High** — no .docx fixtures in test suite |
| `email_ingestor.py` | 68% | Medium — no .eml fixtures |
| `epub_ingestor.py` | 25% | **High** — no .epub fixtures |
| `image_ingestor.py` | 65% | Medium — no image fixtures |
| `markdown_ingestor.py` | 77% | Low — simple text read |
| `notebook_ingestor.py` | 84% | Low — cell extraction is tested via service |
| `pptx_ingestor.py` | 37% | **High** — no .pptx fixtures |
| `research_ingestor.py` | 94% | Low — well covered |
| `spreadsheet_ingestor.py` | 32% | **High** — no spreadsheet fixtures |
| `txt_ingestor.py` | 69% | Low — simple text read |
| `video_ingestor.py` | 65% | Low — metadata only |
| `youtube_transcript_ingestor.py` | 78% | Medium — API dependency |

### LLM Clients (require live Ollama)
| Module | Coverage | Risk |
|---|---|---|
| `vision_client.py` | 43% | **High** — describe_image untested without vision model |
| `whisper_transcriber.py` | 46% | **High** — requires audio model |

### Queue
| Module | Coverage | Risk |
|---|---|---|
| `queue/models.py` | 100% | Data classes only — low risk |
| `queue/stats.py` | 74% | Low — metrics collection |

### Watcher
| Module | Coverage | Risk |
|---|---|---|
| `watcher/events.py` | 100% | Simple types — low risk |
| `watcher/filters.py` | 100% | Covered via watcher service tests |

---

## 3. Performance Benchmarks

### 3.1 Measured Values

All measurements taken on the test machine. CPU: unknown, RAM: unknown, OS: Windows.

| Benchmark | Value | Methodology |
|---|---|---|
| **Python import time** | **0.32s** | `time python -c "import app"` |
| **Ollama connection time** | **1.78s** | `time ollama.Client().ps()` |
| **Unit tests (24 files)** | **5.2s** | `pytest tests/unit/ -q` |
| **Integration tests (2 files)** | **2.2s** | `pytest tests/integration/test_complete_workflow.py tests/integration/test_queue_worker_pipeline.py` |
| **Full test suite (394 tests)** | **92.9s** | `pytest --cov=app` |
| **Test coverage** | **84.77%** | `pytest --cov=app` (4247 statements, 647 missed) |

### 3.2 Estimated Values

These values are **estimates based on code analysis**, not measurements. They cannot be measured without running the full pipeline with Ollama and real files.

| Benchmark | Estimated | Basis |
|---|---|---|
| **Startup time (CLI)** | ~0.5s | Import (0.32s) + config load + Ollama check (1.78s if server reachable) |
| **Ingestion: 10KB .md file** | ~0.01s | File read + `clean_text()` — pure Python, negligible |
| **Ingestion: 1MB .pdf file** | ~0.5–2s | `pypdf` extraction, proportional to page count |
| **Ingestion: 10MB .pdf file** | ~5–20s | Full file in memory, pypdf scales linearly |
| **Ingestion: 50MB .csv file** | ~0.5–1s | File read, no complex parsing |
| **OCR: single page image** | ~10–30s | Vision model inference via Ollama (GPU-dependent) |
| **OCR: 5-page scanned PDF** | ~50–150s | 5 pages × 10–30s per page |
| **Embedding: single text** | ~0.1–0.5s | Ollama nomic-embed-text inference |
| **Embedding: batch of 50** | ~2–10s | Ollama batch endpoint, scales sub-linearly |
| **Search: 100 entries** | ~0.001s | O(n) cosine similarity, 100 entries × 384 dim |
| **Search: 10,000 entries** | ~0.1s | O(n) scan of 10K entries |
| **Search: 100,000 entries** | ~1s | O(n) scan becomes noticeable bottleneck |
| **LLM analysis: short text** | ~5–15s | `qwen3:8b` inference on CPU |
| **LLM analysis: long text (8K tokens)** | ~30–120s | Full context window processing |
| **Memory: idle** | ~80–150MB | Python process + imported modules |
| **Memory: after 10K chunks in vector store** | ~200–500MB | 10K vectors × 384 dim × 4 bytes ≈ 15MB + Python overhead |
| **Memory: after 100K chunks** | ~1–3GB | 100K vectors × 768 dim (if using larger model) |
| **CPU: idle** | ~0% | No background threads |
| **CPU: embedding batch** | ~100% (1 core) | Ollama inference |
| **CPU: LLM analysis** | ~100% (all cores) | Ollama uses all available cores |
| **GPU: N/A if CPU-only** | — | Ollama can use GPU if configured |

### 3.3 Scaling Projections

```
Search Latency vs Vector Store Size (estimated, O(n) brute-force)
  Entries    │  Latency
  ───────────┼──────────
      100    │  0.001s
    1,000    │  0.01s
   10,000    │  0.1s
  100,000    │  1.0s
1,000,000    │  10.0s  ← unusable without indexing

LLM Analysis Time vs Document Length (estimated, qwen3:8b on CPU)
  Tokens     │  Time
  ───────────┼──────────
      500    │  5s
    2,000    │  20s
    8,000    │  90s
   32,000    │  ~6min  ← may exceed context window
```

---

## 4. Retrieval Evaluation

### 4.1 Current State: Not Implemented

There is **no retrieval evaluation framework** in the project. The following metrics have no implementation, no test, and no benchmark:

| Metric | Status | Reason |
|---|---|---|
| **Precision@k** | ❌ Not implemented | No labeled query-document pairs |
| **Recall@k** | ❌ Not implemented | No ground-truth relevance judgments |
| **Mean Reciprocal Rank (MRR)** | ❌ Not implemented | No query set with known relevant docs |
| **Normalized Discounted Cumulative Gain (NDCG)** | ❌ Not implemented | No graded relevance judgments |
| **Citation quality** | ❌ Not implemented | LLM analysis does not cite sources |
| **Hallucination rate** | ❌ Not implemented | No automated fact-checking against source |

### 4.2 How Evaluation Should Be Added

#### Step 1: Create a labeled evaluation dataset

```
data/eval/
├── queries.jsonl        # {"query": "...", "relevant_chunk_ids": ["id1", "id2"]}
├── documents/
│   ├── doc1.md
│   ├── doc2.pdf
│   └── ...
└── relevance_judgments.json  # {query_id: {chunk_id: relevance_score (0-3)}}
```

Each query is a natural language search. The relevant chunk IDs are the ground-truth answers.

#### Step 2: Implement evaluation runner

```python
class RetrievalEvaluator:
    def __init__(self, vector_store, search, queries, relevance_judgments):
        ...

    def precision_at_k(self, k=10):
        """Fraction of retrieved docs that are relevant."""
        ...

    def recall_at_k(self, k=10):
        """Fraction of relevant docs that are retrieved."""
        ...

    def mrr(self):
        """Mean reciprocal rank of first relevant result."""
        ...

    def ndcg_at_k(self, k=10):
        """Normalized discounted cumulative gain."""
        ...
```

#### Step 3: Integration into CI

```yaml
# .github/workflows/eval.yml
name: Retrieval Eval
on: [push]
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: pip install -e ".[dev]"
      - run: ollama pull nomic-embed-text
      - run: python -m tests.eval.run_evaluation
```

#### Step 4: Track over time

```
Evaluations/
├── 2026-01-01.json    # baseline
├── 2026-01-15.json    # after chunking improvement
└── 2026-02-01.json    # after hybrid search
```

#### Recommended metrics to track per commit:

1. **Precision@5** — How many of the top 5 results are relevant
2. **Recall@10** — What fraction of all relevant docs appear in top 10
3. **MRR** — How early does the first relevant result appear
4. **NDCG@10** — How well are highly relevant docs ranked
5. **Latency p50/p95/p99** — Search speed distribution
6. **Index size** — Memory usage of vector store

---

## 5. Benchmark Recommendations

### 5.1 Chunking Benchmarks

Use `pytest-benchmark` to measure chunking performance and quality:

```python
# tests/benchmarks/test_chunking.py
def test_chunking_speed(benchmark):
    chunker = SemanticChunker(max_chunk_chars=2000)
    text = "..." * 10000  # 10K paragraphs
    result = benchmark(chunker.chunk, text, "benchmark", "text")
    assert len(result) > 0

def test_chunking_quality():
    """Measure semantic coherence within vs across chunks."""
    chunker = SemanticChunker(heading_split=True)
    chunks = chunker.chunk(long_markdown_doc, "test", "markdown")
    within_similarity = cosine(embed(chunks[0].text), embed(chunks[0].text))
    cross_similarity = cosine(embed(chunks[0].text), embed(chunks[1].text))
    assert within_similarity > cross_similarity
```

**Recommended benchmark datasets:**
- **BEIR** (Benchmarking Information Retrieval): 18 datasets for zero-shot retrieval eval (notebook)
- **LoCo** (Long Context): For chunking quality with long documents
- **SCIDOCS**: Scientific paper retrieval
- **Custom**: 10–20 real documents from the user's own vault

### 5.2 Ingestion Benchmarks

```python
# tests/benchmarks/test_ingestion.py
INGESTION_FILES = [
    ("data/benchmarks/small.md", "10KB", "markdown"),
    ("data/benchmarks/medium.pdf", "1MB", "pdf"),
    ("data/benchmarks/large.pdf", "50MB", "pdf"),
    ("data/benchmarks/wide.csv", "10MB 50 columns", "csv"),
]

@pytest.mark.parametrize("path,label,kind", INGESTION_FILES)
def test_ingestion_speed(benchmark, path, label, kind, service):
    result = benchmark(service.ingest, path)
    assert result.succeeded
```

### 5.3 Embedding Benchmarks

```python
# tests/benchmarks/test_embeddings.py
@pytest.mark.benchmark
def test_embedding_throughput(benchmark):
    service = EmbeddingService(settings)
    texts = ["sample text"] * 100
    result = benchmark(service.embed_batch, texts)
    assert len(result) == 100
```

### 5.4 Vector Search Benchmarks

```python
# tests/benchmarks/test_vector_search.py
def test_search_latency_vs_size(benchmark):
    """Measure O(n) scaling empirically."""
    store = VectorStore()
    for i in range(STORE_SIZE):
        store.add(VectorEntry(id=f"chunk_{i}", text="x", embedding=[0.1] * 384, ...))

    def search():
        return store.search([0.1] * 384, top_k=10)
    result = benchmark(search)
    assert len(result) == min(10, STORE_SIZE)
```

**Expected results (to validate):**

| Store Size | Expected Latency |
|---|---|
| 100 | ~0.001s |
| 1,000 | ~0.01s |
| 10,000 | ~0.1s |
| 100,000 | ~1.0s |

### 5.5 Recommended Evaluation Pipeline

```yaml
# .github/workflows/benchmark.yml
name: Benchmarks
on:
  push:
    branches: [main]
  schedule:
    - cron: '0 0 * * 0'  # weekly

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
          pip install pytest-benchmark

      - name: Start Ollama
        run: |
          docker run -d --name ollama -p 11434:11434 ollama/ollama
          sleep 10
          ollama pull nomic-embed-text

      - name: Run ingestion benchmarks
        run: python -m pytest tests/benchmarks/ -k "ingestion" --benchmark-only --benchmark-json=benchmark_results.json

      - name: Run retrieval benchmarks
        run: python -m pytest tests/benchmarks/ -k "retrieval" --benchmark-only --benchmark-json=retrieval_results.json

      - name: Compare with baseline
        run: python scripts/compare_benchmarks.py benchmark_results.json .benchmark_baseline.json

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: benchmark-results
          path: benchmark_results.json
```

### 5.6 LLM Evaluation (Quality)

```python
# tests/eval/test_llm_analysis_quality.py

ANALYSIS_TEST_CASES = [
    {
        "source": "test_short.md",
        "expected": {
            "has_summary": True,
            "min_keywords": 3,
            "max_keywords": 15,
            "min_concepts": 1,
            "reading_time_positive": True,
        },
    },
    {
        "source": "test_code.py",
        "expected": {
            "has_summary": True,
            "categories_contain": ["Programming", "Code"],
        },
    },
]

@pytest.mark.slow
@pytest.mark.parametrize("case", ANALYSIS_TEST_CASES)
def test_analysis_quality(case, settings, ollama_client):
    workflow = IngestionWorkflow.from_runtime(ollama_client=ollama_client, ...)
    result = workflow.run(f"tests/fixtures/{case['source']}")

    for key, value in case["expected"].items():
        if key == "has_summary":
            assert result.ai_result.analysis.summary.short
        elif key == "min_keywords":
            assert len(result.ai_result.analysis.keywords) >= value, \
                f"Expected ≥{value} keywords, got {len(result.ai_result.analysis.keywords)}"
```

---

## 6. Overall Quality Assessment

| Dimension | Score | Evidence |
|---|---|---|
| **Test coverage** | 84.77% | 4247 stmts, 647 missed. Above 80% threshold. |
| **Test count** | 394 passing | 26 pytest files, 0 failures in last run |
| **Test speed** | 92.9s full suite | Unit: 5.2s, Integration: 2.2s |
| **Untested modules** | 28 files | Mostly ingestors with no file fixtures |
| **Low-coverage modules** | 7 below 50% | epub (25%), spreadsheet (32%), pptx (37%), vision_client (43%), whisper (46%), docx (45%) |
| **Integration tests** | 8 tests | Two workflow files with fake AI processors |
| **E2E tests** | 3 standalone scripts | Require real Ollama, not in pytest suite |
| **Performance benchmarks** | None | No benchmark tests, no regression tracking |
| **Retrieval evaluation** | None | No precision/recall/NDCG metrics |
| **LLM quality evaluation** | None | No hallucination or citation quality checks |

### Code Quality by Module

```
              ┌────────────────────────────────────────┐
              │  Test Coverage by Module Group          │
              │                                        │
  Domain      │████████████████████████████████  99%    │
  Core        │███████████████████████████████   97%    │
  CLI         │██████████████████████████        83%    │
  Queue       │███████████████████████████       87%    │
  Watcher     │███████████████████████████████   97%    │
  Search/Emb  │███████████████████████████████   100%   │
  KG          │███████████████████████████████   97%    │
  Chunking    │██████████████████████████████    92%    │
  State/Man   │███████████████████████████       87%    │
  Ingestion   │███████████████████               64%*   │
  LLM Client  │██████████████                    54%*   │
  Pipeline    │███████████                       59%    │
              └────────────────────────────────────────┘
              * Weighted average across all source files
```

---

## 7. Testing Roadmap

### Phase 1: Close Coverage Gaps (Weeks 1–2)

| Task | Effort | Impact |
|---|---|---|
| Add test fixtures for .docx, .pptx, .xlsx, .epub, .eml | 2 days | Closes 5 low-coverage modules |
| Add unit tests for `vision_client.py` with mocked responses | 1 day | 43% → 90% |
| Add unit tests for `whisper_transcriber.py` with mocked transcription | 1 day | 46% → 85% |
| Add `spreadsheet_ingestor.py` tests with real .xlsx fixture | 1 day | 32% → 85% |
| Add `pipeline/ingest_workflow.py` coverage for edge cases | 2 days | 59% → 80% |

### Phase 2: Add Benchmark Suite (Weeks 3–4)

| Task | Effort | Impact |
|---|---|---|
| Add `pytest-benchmark` + chunking benchmarks | 1 day | Baseline for chunking speed/quality |
| Add ingestion speed benchmarks across file types | 1 day | Baseline for ingestion throughput |
| Add vector search O(n) scaling test | 1 day | Document the bottleneck numerically |
| Add embedding throughput benchmark | 1 day | Baseline for embedding performance |
| Add CI benchmark comparison script | 2 days | Regression detection in CI |

### Phase 3: Add Retrieval Evaluation (Weeks 5–6)

| Task | Effort | Impact |
|---|---|---|
| Create labeled query-doc evaluation dataset | 3 days | Ground truth for all retrieval metrics |
| Implement `RetrievalEvaluator` (precision, recall, MRR, NDCG) | 2 days | First-ever retrieval quality metric |
| Add CLI command `pam eval search <dataset>` | 1 day | On-demand evaluation |
| Add CI evaluation job | 1 day | Regression detection per commit |

### Phase 4: Add LLM Quality Evaluation (Weeks 7–8)

| Task | Effort | Impact |
|---|---|---|
| Create analysis quality test cases (10–20 documents) | 3 days | Ground truth for LLM analysis |
| Implement analysis quality metrics (field completion, correctness) | 2 days | Measure LLM output quality |
| Add hallucination detection (compare analysis claims to source text) | 3 days | Critical quality metric |
| Add CI quality gate | 1 day | Prevent LLM analysis regressions |

### Phase 5: Ongoing

| Task | Cadence |
|---|---|
| Run full benchmark suite on every `main` commit | CI |
| Compare benchmarks to baseline, alert on >10% regression | CI |
| Quarterly evaluation dataset expansion | Quarterly |
| Annual benchmark baseline reset | Yearly |
