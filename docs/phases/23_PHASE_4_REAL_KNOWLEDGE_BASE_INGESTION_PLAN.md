# Phase 4: Real Knowledge Base Ingestion — Inspection Report

**Date:** 2026-08-24
**Frozen HEAD:** `9f282b41b6c558b0dbea857c95e24beb3ff63f9a`
**Status:** INSPECTION COMPLETE. No code changes. No commits. No pushes.

---

## 1. Objective

Inspect PAM V1's ingestion pipeline to determine how to ingest the user's real knowledge base (beyond the current 12-source, 101-chunk intentional corpus). This report documents the full architecture, current corpus health, re-ingestion behavior, supported file types, and what the user needs to do next.

---

## 2. Current Corpus State

### 2.1 Vector Store (`data/manifests/vector_store.json`)

| Metric | Value |
|--------|-------|
| Total chunks | 101 |
| Unique source files | 12 |
| Embedding model | nomic-embed-text (768-dim) |
| File size | 1.1 MB |

### 2.2 Source Breakdown

| Source | Chunks | Dim | Type | Status |
|--------|--------|-----|------|--------|
| PCB Board Design (Beginners) | 25 | 768 | markdown | ✅ Valid |
| Neural Networks (Deep Learning Ch.1) | 18 | 768 | markdown | ✅ Valid |
| What I Learned From LeetCode | 13 | 768 | markdown | ✅ Valid |
| Our Organization (Utthunga) | 11 | 768 | markdown | ✅ Valid |
| Meet GPT-5.6 | 7 | 768 | markdown | ✅ Valid |
| DAA Assignment-4 | 7 | 768 | scanned_pdf | ✅ Valid |
| OpenHands Platform | 6 | 768 | markdown | ✅ Valid |
| b.md (test artifact) | 6 | **384** | markdown | ❌ **Dimension mismatch** |
| Jharkhand Protest | 5 | 768 | markdown | ✅ Valid |
| TiHAN-IIT Hyderabad (WhatsApp Image) | 1 | 768 | image | ✅ Valid |
| sigmamusicart song | 1 | 768 | audio | ✅ Valid |
| pam_smoke_test | 1 | 768 | text | ⚠️ Smoke test artifact |

### 2.3 Processed Files Manifest (`data/manifests/processed_files.json`)

- **23 entries** total (13 from July batch, 10 from Aug 10–14 batch)
- **July batch (entries 1–13):** Processed but NOT in vector store — the store was rebuilt around Aug 10
- **Aug batch (entries 14–23):** Currently in vector store
- **`b.md`:** In vector store but NOT in processed_files.json — a ghost entry from a different embedder

### 2.4 Corpus Health Issues

| Issue | Severity | Description |
|-------|----------|-------------|
| **384-dim contamination** | 🔴 Critical | 6 `b.md` chunks use 384-dim embeddings (different model). Incompatible with 768-dim queries. Must purge. |
| **Foreign absolute paths** | 🟡 Medium | 11 sources point at `D:\LLM-Wiki\LLM-Wiki\data\inbox\...` — dead paths in this checkout. Chunks are searchable but source paths won't resolve to files. |
| **Manifest/store drift** | 🟡 Medium | processed_files.json has 23 entries, vector store has 11 real sources. 12 July entries are ghosts in the manifest. |
| **Test artifact leakage** | 🟡 Medium | `b.md` (synthetic filler) and `pam_smoke_test.txt` are in the live corpus. Not harmful but pollute retrieval. |

---

## 3. Ingestion Architecture

### 3.1 End-to-End Flow

```
File dropped in data/inbox/
  → Watcher (watchdog Observer, 1s poll)
    → Size stability check (2 polls)
    → QueueItem enqueued
      → QueueWorker.process_next()
        → SHA-256 dedup check (manifest.contains_hash)
          → Duplicate? Skip.
          → New? Continue.
        → IngestionWorkflow.run(source)
          → DocumentIngestionService.ingest(source)
            → Select ingestor by extension/URL pattern
            → Ingestor produces SourceDocument (text + metadata)
            → DocumentMetadataService enrichment (EXIF, entities, etc.)
          → ProcessorRouter → RoutedDocumentProcessor
            → OCR/vision/audio extraction
            → Structure analysis, entity extraction, relationship detection
            → Knowledge graph update
          → SemanticChunker.chunk(document)
            → Heading-based section splitting
            → Block-level packing (code, tables, callouts atomic)
            → Sentence splitting as last resort
            → 2000-char max, 200-char overlap
          → EmbeddingService.embed_batch(texts)
            → nomic-embed-text via Ollama (768-dim)
          → VectorStore.add_batch(entries)
            → Dedup by chunk ID (overwrite last-write-wins)
            → Atomic JSON save
          → Knowledge graph merge (cross-doc links ≥0.7 cosine)
          → Obsidian note generated + written to vault/
        → File moved to data/processed/
        → Manifest entry added
```

### 3.2 Supported File Types

**Active in watcher (55 extensions):**

| Category | Extensions |
|----------|------------|
| Documents | `.md`, `.txt`, `.pdf`, `.csv`, `.xlsx` |
| Programming | `.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.java`, `.go`, `.rs`, `.c`, `.cpp`, `.h`, `.cs`, `.rb`, `.php`, `.swift`, `.kt`, `.scala`, `.r`, `.m`, `.sh`, `.bat`, `.ps1`, `.sql`, `.html`, `.css`, `.scss`, `.less`, `.vue`, `.svelte` |
| Images | `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.webp`, `.tiff`, `.svg`, `.heic` |
| Audio | `.mp3`, `.wav`, `.ogg`, `.flac`, `.aac`, `.m4a` |
| Video | `.mp4`, `.avi`, `.mov`, `.mkv`, `.webm` |

**Ingestor code exists but watcher does NOT pick up:**
`.docx`, `.pptx`, `.epub`, `.ipynb`, `.diagram`, `.archive`, `.email`, `.db`, `.json`, `.yaml`, `.toml`, `.xml`

### 3.3 Ingestion Input Directory

- **`data/inbox/`** — the canonical input directory (currently empty, only `.gitkeep`)
- Watcher watches this directory recursively
- Files are moved to `data/processed/` after successful ingestion
- Failed files go to `data/failed/`

### 3.4 Ingestor Registry

20 ingestors registered in `DocumentIngestionService`:

| Ingestor | Handles | Source Type |
|----------|---------|-------------|
| YouTubeTranscriptIngestor | YouTube URLs | youtube |
| GitHubReadmeIngestor | GitHub repo URLs | github_readme |
| PdfIngestor | `.pdf` files | scanned_pdf |
| NotebookIngestor | `.ipynb` files | notebook |
| EpubIngestor | `.epub` files | epub |
| MarkdownIngestor | `.md` files | markdown |
| CodeIngestor | Code files (31 extensions) | code |
| ConfigIngestor | Config files | config |
| TextIngestor | `.txt` files | text |
| CSVIngestor | `.csv` files | csv |
| SpreadsheetIngestor | `.xlsx` files | spreadsheet |
| ImageIngestor | Image files (9 extensions) | image |
| DocxIngestor | `.docx` files | docx |
| PptxIngestor | `.pptx` files | pptx |
| AudioIngestor | Audio files (6 extensions) | audio |
| VideoIngestor | Video files (5 extensions) | video |
| DiagramIngestor | `.diagram` files | diagram |
| ArchiveIngestor | `.archive` files | archive |
| EmailIngestor | `.email` files | email |
| DatabaseIngestor | `.db` files | database |
| ResearchIngestor | Research URLs | research |

---

## 4. Re-Ingestion Behavior

### 4.1 Dedup Mechanism

**Two regimes coexist:**

| Path | Dedup | Behavior |
|------|-------|----------|
| **Watcher** | SHA-256 hash check | `manifest.contains_hash(digest)` — skips if hash matches |
| **CLI** | **None** | Bypasses queue worker entirely, re-runs full pipeline |

### 4.2 Same File Ingested Twice

**Watcher path:**
- If byte-identical → skipped (hash match)
- If edited → re-ingested, but **no remove-before-add** in vector store

**CLI path:**
- Always re-runs full pipeline (LLM analysis + embeddings)
- Vector store `add_batch` overwrites by chunk ID (deterministic: `{source}::chunk_{index}`)
- **If new version produces fewer chunks → old trailing chunks become orphans** (searchable forever)

### 4.3 Orphan Chunk Problem

```
File v1: 10 chunks → chunk_0 through chunk_9
File v2: 7 chunks  → chunk_0 through chunk_6 (overwrite clean)
                         chunk_7 through chunk_9 survive as orphans!
```

**No `remove_by_source` exists.** The only removal method is `VectorStore.remove(entry_id)` which requires exact chunk IDs. No CLI command, no workflow, no automated cleanup.

### 4.4 Knowledge-Engine Failure Silently Loses Chunks

`IngestionWorkflow.run()` lines 956-961: if the knowledge engine step (embedding + vector store write) fails, the error is **logged as warning but ingestion still succeeds**. The Obsidian note is written, the manifest records the file as processed, but **zero or partial chunks are in the vector store**. The file can never be retried via the watcher (hash already recorded).

---

## 5. Chunking Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_chunk_chars` | 2000 | Maximum chunk size |
| `overlap_chars` | 200 | Overlap between consecutive chunks |
| `min_chunk_chars` | 200 | Floor for dynamic heading-depth budget |
| `heading_size_step` | 0 | Per-level budget reduction (0 = disabled) |
| `snap_overlap` | False | Snap overlap to paragraph boundary |
| `heading_overlap_boundary` | False | Heading-start chunks get no overlap tail |

**Chunking algorithm:** Hierarchical heading-based splitting → block-level packing (code/tables/atomic) → sentence splitting as fallback.

**Chunk metadata:** heading, heading_level, heading_path, parent_heading, language (code), structure_type (table/blockquote/callout).

---

## 6. Embedding Configuration

| Parameter | Value |
|-----------|-------|
| Model | `nomic-embed-text` |
| Dimensions | 768 (determined by Ollama, not pinned in code) |
| Endpoint | Ollama local (`http://localhost:11434`) |
| Batching | Single `embed()` call for entire batch |
| Retries | 2 retries, exponential backoff (1s, 2s) |
| Mismatch guard | `EmbeddingCountMismatchError` (non-retryable) |

---

## 7. Search Configuration

| Parameter | Value |
|-----------|-------|
| Hybrid search | BM25 + dense (cosine) with RRF fusion |
| BM25 | Okapi BM25 (k1=1.5, b=0.75), lowercase alpha-numeric tokenization |
| RRF k | 60 |
| BM25 rebuild | Lazy, triggered by vector store version change |
| Min cosine threshold | 0.45 (production) |
| Reranker | Disabled (ms-marco-MiniLM, min_score 0.125) |
| HyDE | Disabled |

---

## 8. Ingestion Plan for Real Knowledge Base

### 8.1 Pre-Ingestion Cleanup (Recommended)

Before ingesting real data, the user should clean the current corpus:

1. **Purge `b.md` (384-dim contamination):** Remove 6 chunks from vector store. No automated tool exists — requires manual `VectorStore.remove()` calls or a script.
2. **Purge `pam_smoke_test.txt`:** Optional, 1 chunk, not harmful.
3. **Reset processed_files.json:** Remove ghost entries for July batch (entries 1–13) and `b.md` if present.

### 8.2 Ingestion Workflow

**Step 1: Place files in `data/inbox/`**
```
data/inbox/
├── knowledge-base/
│   ├── topic-a/
│   │   ├── file1.md
│   │   └── file2.pdf
│   └── topic-b/
│       └── file3.txt
```

**Step 2: Start the watcher**
```bash
pam watch
```

**Step 3: Files are automatically:**
- Detected by watchdog
- Size-stability checked
- Ingested (routed to appropriate ingestor)
- AI-analyzed (Ollama qwen3:8b)
- Chunked (semantic chunker, 2000-char max)
- Embedded (nomic-embed-text, 768-dim)
- Stored in vector store
- Note written to vault/
- Moved to `data/processed/`
- Recorded in manifest

**Step 4: Verify ingestion**
```bash
pam status
pam search "test query"
```

### 8.3 Alternative: CLI Bulk Ingestion

```bash
# One file at a time (no batch mode exists)
pam ingest markdown path/to/file.md
pam ingest pdf path/to/file.pdf
```

⚠️ **CLI bypasses dedup** — every invocation re-runs the full pipeline even for byte-identical files.

### 8.4 Expected Behavior for Real Data

| Scenario | Behavior |
|----------|----------|
| New file added to inbox | Watcher detects → ingests → chunks → embeds → stores |
| Same file re-added (byte-identical) | Watcher deduplicates by SHA-256 → skips |
| File edited and re-added | Watcher re-ingests (new hash) → overwrites chunks by ID → **orphan chunks if fewer chunks** |
| Large file (>metadata.max_file_size_mb) | IngestionError raised, file moved to failed/ |
| Unsupported extension | IngestionError raised, file moved to failed/ |
| Ollama down | Embedding failure → knowledge engine warning → note written without chunks |

---

## 9. Quality Checks

### 9.1 Pre-Ingestion Checklist

- [ ] Ollama running with `nomic-embed-text` and `qwen3:8b` models
- [ ] `data/inbox/` directory exists and is writable
- [ ] No 384-dim chunks in vector store (purge `b.md`)
- [ ] `config/default.yaml` has correct paths

### 9.2 Post-Ingestion Verification

```bash
# Check vector store size
pam status

# Test retrieval quality
pam search "your expected query topic"
pam ask "your expected question"

# Run eval harness against new corpus
python eval/run_eval.py --top-k 10 --min-cosine 0.45
```

### 9.3 Red Flags

| Symptom | Likely Cause |
|---------|--------------|
| Chunks = 0 after ingestion | Knowledge engine failed silently (check logs) |
| Retrieval returns wrong sources | Foreign absolute paths in vector store |
| Retrieval quality degraded | Too many chunks from similar documents (diversity issue) |
| Latency >500ms | Vector store too large, BM25 rebuild cost |
| FNR >0.033 on eval | Chunking split important content across chunks |

---

## 10. Eval Strategy for Real Data

### 10.1 Dataset Requirements

The current eval dataset (`eval/dataset.json`) is FROZEN at 160 queries against the 12-source corpus. For real data:

1. **Create new eval dataset** with queries covering the real knowledge base
2. **Target 200-500 queries** for statistical significance
3. **Include negative queries** (20-30%) to measure FPR
4. **Label expected sources** for Hit@k measurement

### 10.2 Eval Metrics to Track

| Metric | Current Baseline | Target |
|--------|------------------|--------|
| Hit@1 | 0.902 | ≥ 0.88 |
| Hit@5 | 0.967 | ≥ 0.93 |
| MRR | 0.934 | ≥ 0.88 |
| FPR | 0.811 | < 0.50 |
| FNR | 0.008 | ≤ 0.033 |
| Latency p50 | ~14.6ms | < 50ms |
| Latency p95 | ~20ms | < 100ms |

### 10.3 Corpus Scaling Expectations

| Current | Expected | Impact |
|---------|----------|--------|
| 101 chunks | 1,000-10,000 chunks | BM25 rebuild cost increases linearly |
| 12 sources | 50-200 sources | Retrieval diversity improves |
| 1.1 MB store | 10-100 MB store | Load time increases, query time stable |

---

## 11. Dataset Analysis: Current Corpus Topics

The 12-source corpus covers:

| Domain | Sources | Coverage |
|--------|---------|----------|
| Electronics/Hardware | PCB Board Design | Component selection, layout, routing |
| AI/ML | Neural Networks, OpenHands, GPT-5.6 | Deep learning, AI agents, LLMs |
| Programming | LeetCode, DAA Assignment | Algorithms, problem-solving |
| Organization | Our Organization (Utthunga) | Company info, services |
| News | Jharkhand Protest | Current events |
| Media | sigmamusicart song | Music analysis |
| Meta | pam_smoke_test | System self-description |
| Test | b.md | Synthetic filler (should be purged) |

**Gap:** No documents about PAM itself (architecture, design decisions, roadmaps). The user's real knowledge base should include these.

---

## 12. Answerability Experiment Status

Phase 3G-B answerability gate experiment is complete but NOT production-ready:

| Metric | Result | Guardrail |
|--------|--------|-----------|
| FPR | 0.243 (−70%) | — ✅ |
| FNR | 0.098 | ≤ 0.033 ❌ |
| Latency | ~3s/query | < 500ms ❌ |
| Gate behavior | 0/32 SUPPORTED (too conservative) | — |

**Status:** Feature-flagged off (`answerability.enabled=false`). Prompt tuning needed before production use. Architecture is clean and non-disruptive.

**Recommendation:** Complete real-data ingestion first, then revisit answerability gate with tuned prompt on the larger corpus.

---

## 13. Summary of Findings

### What Works
- Ingestion pipeline is complete and functional (20 ingestors, multi-modal)
- Watcher auto-detection with SHA-256 dedup
- Semantic chunking with heading-aware splitting
- Hybrid search (BM25 + dense) with RRF fusion
- Atomic vector store persistence
- Obsidian note generation

### What Needs Attention
1. **384-dim `b.md` contamination** must be purged before any similarity operations
2. **No remove-by-source** in vector store — orphan chunks accumulate on re-ingestion
3. **CLI bypasses dedup** — every invocation re-runs full pipeline
4. **Knowledge-engine failures are silent** — chunks can be lost while manifest says "processed"
5. **Foreign absolute paths** — 11 sources point at a different repo checkout

### What the User Should Do Next
1. Purge `b.md` chunks from vector store (manual script or direct JSON edit)
2. Place real knowledge base files in `data/inbox/`
3. Run `pam watch` to trigger automatic ingestion
4. Verify with `pam status` and `pam search "test query"`
5. Create new eval dataset covering the real knowledge base
6. Run eval to establish new baseline metrics

---

*This report is inspection-only. No code changes, no commits, no pushes.*
