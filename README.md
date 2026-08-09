<div align="center">

# 🧠 AI Memory

**Build your own offline AI-powered second brain using Python, Ollama, and Obsidian.**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-000000?style=for-the-badge)
![Obsidian](https://img.shields.io/badge/Obsidian-Knowledge%20Base-7C3AED?style=for-the-badge&logo=obsidian&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)
![Version](https://img.shields.io/badge/Version-v2.0.0-blue?style=for-the-badge)
![Tests](https://img.shields.io/badge/Tests-1398%20Passing-success?style=for-the-badge)

[Overview](#-overview) •
[Features](#-features) •
[Installation](#-installation) •
[Usage](#-cli-usage) •
[Watching Mode](#-watching-mode) •
[Architecture](#%EF%B8%8F-project-architecture) •
[Configuration](#%EF%B8%8F-configuration) •
[Troubleshooting](#-troubleshooting) •
[License](#-license)

</div>

---

## 📖 Overview

**AI Memory** is an automated, local-first personal AI memory system that continuously transforms documents, research papers, GitHub repositories, YouTube transcripts, and personal notes into an interconnected Obsidian knowledge base.

With Version 2, AI Memory can now **watch folders automatically** — drop a file into the inbox and it's detected, queued, and processed without running a single command. A background watcher service, processing queue, and duplicate detection work together to keep your vault continuously up to date.

Unlike traditional note-taking apps, AI Memory doesn't just store information — it **analyzes, organizes, summarizes, links, and enriches** your knowledge while keeping everything completely offline.

- Your data never leaves your machine
- No cloud APIs
- No subscriptions
- No vendor lock-in
- All processing — watching, queuing, and AI inference — runs entirely locally through Ollama

---

## ✨ Features

### 🤖 AI Powered
- Local inference using Ollama
- Qwen3:8B integration
- Structured JSON generation with automatic retries and validation
- Modular, swappable prompt system

### 📄 Document Ingestion
Supports 100+ file types across 15 categories:
- **Documents:** PDF, DOCX, ODT, RTF, EPUB, TeX
- **Code:** Python, JavaScript, TypeScript, Java, C/C++, Go, Rust, Ruby, PHP, Swift, Kotlin, and 20+ more
- **Notebooks:** Jupyter (.ipynb)
- **Spreadsheets:** CSV, TSV, XLS, XLSX, ODS
- **Presentations:** PPTX, PPT, ODP
- **Images:** PNG, JPG, GIF, WebP, BMP, TIFF, HEIC, SVG
- **Diagrams:** DrawIO, Visio, Mermaid (.mmd)
- **Audio:** MP3, WAV, M4A, FLAC, OGG, AAC
- **Video:** MP4, MKV, MOV, AVI, WebM
- **Archives:** ZIP, TAR, GZ, 7Z, RAR
- **Emails:** EML
- **Databases:** SQLite, DB
- **Research:** BibTeX (.bib), RIS
- **Web:** HTML, XML, JSON, RSS
- **Config:** TOML, INI, CFG, YAML, ENV
- **Text:** TXT, Markdown, Log files
- **URLs:** GitHub READMEs, YouTube transcripts

### 🧠 Knowledge Extraction
Automatically extracts 21 fields:
- Summaries (short + detailed)
- Key concepts & definitions
- Important entities
- Related topics & references
- Tags, categories, and suggested titles
- Reading time & difficulty level
- Q&A pairs, flashcards, and MCQs
- Short answer and long answer questions
- Revision notes
- Metadata (word count, page count, language)
- Suggested related notes & backlinks

### 🔗 Knowledge Engine
- **Semantic chunking** — splits by headings, paragraphs, then sentences
- **Embedding generation** — Ollama `nomic-embed-text` for vector representations
- **Vector store** — in-memory with JSON persistence for similarity search
- **Knowledge graph** — builds entity/concept/definition/topic graphs with JSON persistence
- **Cross-document linking** — finds related content via vector similarity
- **Placeholder notes** — auto-creates stub notes for unresolved wiki-links
- **Semantic search** — cosine similarity over embedded chunks
- **Hybrid search** — reciprocal rank fusion (RRF, k=60) of semantic (dense) and BM25 (keyword) scores

### 📚 Obsidian Integration
- Markdown generation with YAML frontmatter
- Automatic wiki links (`[[...]]`)
- Automatic index generation & vault updates
- Duplicate protection
- Preserves your own edits — never overwrites user content

### 🖥️ Developer Friendly
- Typer-based CLI with a Rich terminal UI
- YAML-driven configuration
- Rotating logs
- Comprehensive test suite
- Type-safe, clean architecture built on SOLID principles

### ⚙️ Automation & Reliability (New in v2)
- **Automatic folder watching** — drop files into `data/inbox` and they're picked up automatically
- **Background watcher service** — runs continuously via `pam watch`
- **Processing queue** — incoming files are queued and processed in order
- **Duplicate detection (SHA-256)** — identical files are recognized and skipped
- **Automatic inbox processing** — no manual `pam ingest` calls required for watched files
- **Automatic processed & failed folders** — successful and failed files are sorted automatically
- **Queue recovery** — pending items survive restarts and interruptions
- **Graceful shutdown** — `Ctrl+C` finishes current work and exits cleanly
- **Rich CLI progress** — live progress bars for every processing stage
- **Improved logging** — dedicated log streams for the watcher, queue, and application
- **Runtime statistics** — visibility into processed, failed, and pending counts
- **Configuration for watcher and queue** — fully configurable via YAML and environment variables

---

## 🚀 Current Status

**Version:** `v2.0.0`  **Status:** 🟢 Stable · Actively Developed

| Completed | Future |
|---|---|
| Local-first architecture | RAG-based context retrieval |
| Ollama integration | External vector DB (Chroma/Qdrant) |
| PDF / Markdown / TXT ingestion | REST API for search |
| 100+ file type support | Web UI |
| GitHub README ingestion | Multi-user support |
| YouTube transcript ingestion | |
| Markdown generation & vault management | |
| CLI interface, logging, config management | |
| Automatic folder watching (`pam watch`) | |
| Background watcher service | |
| Processing queue with recovery | |
| SHA-256 duplicate detection | |
| Automatic processed / failed folders | |
| Graceful shutdown & queue persistence | |
| Rich CLI progress reporting | |
| 21-field document intelligence | |
| Semantic chunking & embeddings | |
| Vector store with similarity search | |
| Knowledge graph with persistence | |
| Cross-document linking | |
| Placeholder note creation | |
| Semantic & hybrid search | |
| Comprehensive testing (1398 tests) | |

---

## 🛠️ Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python 3.11+ |
| Local LLM | Ollama |
| Default Model | qwen3:8b / llama3.1:8b |
| Embeddings | nomic-embed-text (Ollama) |
| CLI | Typer |
| Terminal UI | Rich |
| Configuration | YAML |
| Validation | Pydantic |
| Folder Watching | Watchdog |
| Duplicate Detection | SHA-256 Hashing |
| Vector Store | In-memory + JSON persistence |
| Knowledge Graph | Custom (JSON persistence) |
| Progress Reporting | Rich Progress |
| Testing | Pytest |
| Linting | Ruff |
| Type Checking | MyPy |
| Knowledge Base | Obsidian |
| Version Control | Git |

---

## 📂 Repository

**GitHub:** [github.com/GiridharBM/AI-Memory](https://github.com/GiridharBM/AI-Memory)

```bash
git clone https://github.com/GiridharBM/AI-Memory.git
cd AI-Memory
```

---

## ⚡ Installation

### Requirements
- Python 3.11+
- Git
- Ollama
- Obsidian
- Windows, macOS, or Linux

> **Optional — offline OCR fallback (scanned documents):** scanned PDFs/images are OCR'd by the local vision model by default. To enable the CPU-only Tesseract fallback, install [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) (add `tesseract` to PATH or set `intelligence.ocr.tesseract_cmd` in `config/default.yaml`) and run `uv pip install pytesseract pillow`. `pam doctor` reports whether the fallback is available.

> **Image intelligence (optional):** photos and screenshots gain EXIF/metadata enrichment and `.drawio` files render as Mermaid when the `intelligence` extra is installed (`uv pip install -e ".[intelligence]"`). Set `intelligence.images.preprocess: true` to enable the shared deskew → denoise → CLAHE preprocessing before vision OCR (dimension/size guards default to `[8192, 8192]` / 20 MB per `intelligence.images.max_dimensions` / `max_bytes`). Toggles `intelligence.images.exif_enabled` / `diagram_enabled` restore plain passthrough behavior.

### 1. Clone the repository
```bash
git clone https://github.com/GiridharBM/AI-Memory.git
cd AI-Memory
```

### 2. Create a virtual environment

**Windows (PowerShell)**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS/Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e ".[dev]"
```

> Version 2 adds **Watchdog** for folder watching. It's included in `requirements.txt`, so no separate install step is needed — the standard install above covers it.

### 4. Verify installation
```bash
python -m pytest
pam doctor
```

Expected output:
```text
1398 passed

✔ Configuration loaded
✔ Ollama available
✔ Vault available
✔ Inbox available
```

---

## 🤖 Ollama Setup

1. Install Ollama from [ollama.com](https://ollama.com)
2. Pull the required models:
   ```bash
   ollama pull qwen3:8b
   ollama pull llama3.1:8b
   ollama pull nomic-embed-text
   ```
3. Verify installation:
   ```bash
   ollama list
   ```
   Expected:
   ```text
   qwen3:8b
   llama3.1:8b
   nomic-embed-text
   ```
4. Start Ollama (if not already running):
   ```bash
   ollama serve
   ```

**Defaults**

| Setting | Value |
|---|---|
| Endpoint | `http://localhost:11434` |
| LLM Model | `qwen3:8b` or `llama3.1:8b` |
| Embedding Model | `nomic-embed-text` |

Override with environment variables:
```bash
PAM_OLLAMA__HOST=http://localhost:11434
PAM_OLLAMA__MODEL=qwen3:8b
```

---

## 📚 Obsidian Setup

AI Memory generates Markdown files directly into an Obsidian vault. By default, the vault lives at `./vault`.

**Option 1 — Recommended:** Open the project's `vault/` folder directly as an Obsidian vault via `File → Open Folder as Vault`, and select `AI-Memory/vault`.

**Option 2:** Point AI Memory at your existing vault using an environment variable:
```bash
PAM_PATHS__VAULT_ROOT=D:\Obsidian\PersonalAIWiki
```
or edit `config/default.yaml`:
```yaml
paths:
  vault_root: D:/Obsidian/PersonalAIWiki
```

### Generated wiki structure
```text
vault/
├── Notes/
├── index.md
├── overview.md
└── log.md
```

### Managed sections

AI-generated content is wrapped in managed markers:
```markdown
<!-- PAM:BEGIN MANAGED -->
Generated AI content
<!-- PAM:END MANAGED -->
```
Everything outside these markers is preserved, so you can freely edit your notes without AI overwriting your work.

---

## 💻 CLI Usage

```bash
pam --help           # General help
pam status            # Configuration, vault, watcher, queue, and Ollama status
pam doctor            # Full health check
pam config             # View current configuration
pam config --json     # View configuration as JSON
pam watch              # Start automatic folder watching and processing
```

### 📥 Ingest Documents

| Type | Command |
|---|---|
| Markdown | `pam ingest markdown path/to/file.md` |
| PDF | `pam ingest pdf path/to/file.pdf` |
| TXT | `pam ingest txt path/to/file.txt` |
| GitHub repo | `pam ingest github https://github.com/owner/repository` |
| YouTube | `pam ingest youtube https://www.youtube.com/watch?v=VIDEO_ID` |

Examples:
```bash
pam ingest markdown data/inbox/notes.md
pam ingest pdf data/inbox/ai-paper.pdf
pam ingest github https://github.com/ollama/ollama
pam ingest youtube https://www.youtube.com/watch?v=VIDEO_ID
```

> If a YouTube transcript is unavailable, AI Memory exits gracefully with an informative message.

`pam status` shows watcher, queue, manifest, Ollama, and vault health. `pam config` prints the resolved watcher, queue, manifest, and processing settings.

---

## 🔍 Watching Mode

Version 2 introduces fully automatic processing. Run:

```bash
pam watch
```

This starts a background watcher that continuously monitors `data/inbox` for supported files (Markdown, TXT, and PDF). No manual `pam ingest` command is required — the watcher, queue, and pipeline handle everything.

```text
data/inbox -> watcher -> queue -> duplicate check -> ingestion -> vault -> manifest
```

New files are detected, queued, checked against previously processed files via SHA-256 hashing, processed one at a time, written into the Obsidian vault, recorded in `data/manifests/processed_files.json`, and moved to `data/processed`. Failed or unsupported files are moved to `data/failed`.

Stop watching with `Ctrl+C`. The watcher stops accepting new events, lets the current item finish, saves pending queue items to `data/manifests/queue_state.json`, flushes logs, and exits cleanly.

### Example workflow

```bash
# Start the watcher
pam watch
```
```text
✔ Watcher started — monitoring data/inbox
```

```bash
# In another terminal, drop a file into the inbox
cp ~/Downloads/research-notes.md data/inbox/
```
```text
✔ Detected: research-notes.md
✔ Queued (1 pending)
✔ Duplicate check passed
✔ Processing... [██████████] 100%
✔ Vault updated: vault/Notes/Research-Notes.md
✔ Moved to data/processed/research-notes.md
```

### Progress Display

Automatic processing uses Rich progress bars with the current step, percentage, elapsed time, and estimated remaining time. The CLI reports each major stage: reading the document, cleaning text, sending content to Ollama, generating knowledge, writing Markdown, updating the vault, and completion time.

### Recovery

AI Memory recreates missing runtime directories on startup, including inbox, processed, failed, logs, vault, cache, and manifests. Pending queue items are stored in `data/manifests/queue_state.json` and restored on the next `pam watch` run if the application was interrupted.

### Logs

Logs are written under `data/logs/`:

| Log | Purpose |
|---|---|
| `application.log` | Startup, configuration, and general application events |
| `watcher.log` | Folder watcher startup, shutdown, and file detection |
| `processing.log` | Queue and ingestion processing events |
| `errors.log` | Errors from any application component |

Log files rotate automatically at 10 MB and keep 5 backups.

### Retry Behaviour

Recoverable Ollama failures are retried with exponential backoff. With the default retry settings, failures wait 1 second, then 2 seconds, then 4 seconds before the file is marked failed and moved to the failed directory.

### Graceful Shutdown

On `Ctrl+C`, `pam watch` stops accepting new file events, waits for the current file and any queued work to finish, saves queue state, flushes logs, stops the watcher, and exits with a clean goodbye message.

### Watcher, Queue & Manifest Configuration

The watcher, queue, manifest, and processing behavior are configured in `config/default.yaml`:

```yaml
watcher:
  enabled: true
  inbox_path: ./data/inbox
  processed_path: ./data/processed
  failed_path: ./data/failed
  recursive: true
  interval_seconds: 1
  supported_extensions:
    - .md
    - .txt
    - .pdf

queue:
  enabled: true
  workers: 1
  max_size: 1000

manifest:
  enabled: true
  path: ./data/manifests/processed_files.json

processing:
  move_processed: true
  move_failed: true
```

Environment variables use double underscores:

```bash
PAM_WATCHER__ENABLED=false
PAM_WATCHER__INTERVAL_SECONDS=2
PAM_WATCHER__RECURSIVE=false
```

---

## 🔄 Processing Workflow

Every document — whether ingested manually or picked up automatically by the watcher — follows the same pipeline:

```text
User saves document
        │
        ▼
     Watcher
        │
        ▼
      Queue
        │
        ▼
Duplicate Detection
        │
        ▼
  AI Processing
        │
        ▼
Markdown Generation
        │
        ▼
   Vault Update
        │
        ▼
 Move to Processed
```

**Example — Watching Mode:**
```bash
pam watch
```
Detects `notes.md` in `data/inbox`, checks its SHA-256 hash against `data/manifests/processed_files.json`, processes it automatically, writes `vault/Notes/Notes.md`, and moves the source file to `data/processed/notes.md`.

**Example — Markdown (manual):**
```bash
pam ingest markdown data/inbox/python.md
```
produces `vault/Notes/Python.md` and updates `index.md`, `overview.md`, and `log.md`.

**Example — GitHub Repository:**
```bash
pam ingest github https://github.com/ollama/ollama
```
downloads and analyzes the repository README, then generates linked notes in the vault.

**Example — YouTube:**
```bash
pam ingest youtube https://www.youtube.com/watch?v=VIDEO_ID
```
pulls the transcript, extracts knowledge, and generates vault notes.

---

## 🏗️ Project Architecture

```text
Source Document
      │
      ▼
  Watcher / CLI
      │
      ▼
     Queue
      │
      ▼
Duplicate Detection
      │
      ▼
  Classifier (24 kinds)
      │
      ▼
  Router (20 processors)
      │
      ▼
  Routed Processor (OCR/Vision/Audio/...)
      │
      ▼
  AI Analysis (21 fields)
      │
      ├─→ Semantic Chunking → Embeddings → Vector Store
      ├─→ Knowledge Graph Builder → Graph Persistence
      ├─→ Cross-Document Linking (similarity search)
      │
      ▼
Markdown Generation
      │
      ▼
 Wiki Manager + Placeholder Notes
      │
      ▼
 Obsidian Vault
```

---

## 📁 Folder Structure

```text
AI-Memory/
├── app/
│   ├── application/
│   ├── cli/
│   ├── core/
│   ├── domain/
│   ├── infrastructure/
│   │   ├── ingestion/
│   │   ├── llm/
│   │   ├── logging/
│   │   ├── state/
│   │   ├── watcher/
│   │   ├── queue/
│   │   └── vault/
│   ├── pipelines/
│   ├── prompts/
│   └── templates/
├── config/
│   ├── default.yaml
│   ├── development.yaml
│   └── production.yaml
├── data/
│   ├── inbox/
│   ├── processed/
│   ├── failed/
│   ├── cache/
│   ├── manifests/
│   └── logs/
├── docs/
├── scripts/
├── tests/
│   ├── integration/
│   └── unit/
├── vault/
├── README.md
├── requirements.txt
└── pyproject.toml
```

| Directory | Purpose |
|---|---|
| `app/` | Main application source code |
| `app/infrastructure/watcher/` | Background folder watching service |
| `app/infrastructure/queue/` | Processing queue implementation |
| `config/` | YAML configuration files |
| `data/inbox/` | Input files awaiting processing |
| `data/processed/` | Files successfully processed and archived |
| `data/failed/` | Files that failed processing, for review |
| `data/cache/` | Temporary cached data |
| `data/manifests/` | Persistent processing state — `processed_files.json` and `queue_state.json` |
| `data/logs/` | Application, watcher, processing, and error logs |
| `tests/` | Unit and integration tests |
| `vault/` | Generated Obsidian vault |
| `docs/` | Project documentation |

### Design Principles
Clean Architecture · SOLID Principles · Modular Components · Type Safety · Local-first Design · Offline AI · Extensibility · Production-ready Code · Comprehensive Testing

---

## ⚙️ Configuration

Configuration is loaded in layers, in this order:
1. `config/default.yaml`
2. `config/<environment>.yaml`
3. Environment variables (`PAM_*`)

Default environment: `development`. Switch with:
```bash
PAM_ENVIRONMENT=production
```

Nested config values use double underscores:
```bash
PAM_OLLAMA__HOST=http://localhost:11434
PAM_OLLAMA__MODEL=qwen3:8b
PAM_PATHS__VAULT_ROOT=D:\Obsidian\PersonalAIWiki
PAM_WATCHER__ENABLED=false
```

Default configuration:
```yaml
app:
  name: personal-ai-memory
  environment: development

paths:
  vault_root: ./vault
  inbox_root: ./data/inbox
  staging_root: ./data/staging
  manifest_root: ./data/manifests
  cache_root: ./data/cache
  log_root: ./data/logs

ollama:
  host: http://localhost:11434
  model: qwen3:8b
  timeout_seconds: 1800
  request_retries: 3
  retry_backoff_seconds: 1.0

logging:
  level: INFO
  format: console
  console_enabled: true
  file_enabled: true
  use_colors: true
  filename: application.log
  max_bytes: 10485760
  backup_count: 5

watcher:
  enabled: true
  inbox_path: ./data/inbox
  processed_path: ./data/processed
  failed_path: ./data/failed
  recursive: true
  interval_seconds: 1
  supported_extensions:
    - .txt
    - .md
    - .pdf
    - .csv
    - .xlsx
    # ... code, image, audio, video extensions (100+ total)

queue:
  enabled: true
  workers: 1
  max_size: 1000
  state_path: ./data/manifests/queue_state.json

manifest:
  enabled: true
  path: ./data/manifests/processed_files.json

processing:
  move_processed: true
  move_failed: true
  processed_path: ./data/processed
  failed_path: ./data/failed

models:
  general_text: qwen3:8b
  programming: qwen2.5-coder:7b
  vision: qwen2.5vl:latest
  audio: faster-whisper
  embeddings: nomic-embed-text

intelligence:
  ocr: { enabled: true, engine: "auto", page_limit: 5, max_pages: 200 }
  metadata: { enabled: true, mime_enabled: true, language_detection_enabled: true, max_file_size_mb: 50, email_attachments: true }
  structure: { enabled: true }
  entities: { enabled: true }
  relationships: { enabled: true }
  graph: { enabled: true }
  tables: { enabled: true, pdf_engine: "pdfplumber" }
  images: { preprocess: false, exif_enabled: true, diagram_enabled: true }
  code: { enabled: true }

chunking:
  sentence_tokenizer: "auto"
  heading_size_step: 0
  min_chunk_chars: 200
  snap_overlap: false
  heading_overlap_boundary: false
```

View current configuration with `pam config`.

### Generated Note Format

Each generated note includes:
- YAML frontmatter, title, and summary
- Key concepts, definitions, and important entities
- Related topics, tags, and references
- Generated date and source
- Obsidian wiki links where useful

Concepts, definitions, entities, and related topics are rendered as `[[wiki links]]` so the vault grows into a connected knowledge base over time.

---

## 📘 Core Concepts

### Watcher
A background service (`pam watch`) built on **Watchdog** that monitors `data/inbox` for file system events. When a supported file is created or modified, it's handed off to the queue. The watcher runs on a configurable polling interval and can watch subdirectories recursively.

### Queue
An internal processing queue that receives files from the watcher and processes them sequentially. The queue has a configurable size limit (`max_size`) and worker count, and persists its state to disk so pending work is not lost if the application stops unexpectedly.

### Manifest
A JSON record — `data/manifests/processed_files.json` — that tracks every file AI Memory has processed, keyed by its SHA-256 hash. A second manifest, `data/manifests/queue_state.json`, stores pending queue items for recovery after a restart.

### Duplicate Detection
Before processing, every file is hashed with **SHA-256**. If the hash already exists in the manifest, the file is recognized as a duplicate and skipped, preventing redundant AI processing and duplicate vault notes.

### Processed Folder
`data/processed/` holds the original source files that were successfully ingested. Files are moved here automatically once their vault notes are generated.

### Failed Folder
`data/failed/` holds files that could not be processed — due to an unsupported format, a parsing error, or a non-recoverable Ollama failure. Check `data/logs/errors.log` for the reason before retrying.

---

## 🧑‍💻 Development Guide

```bash
# Install development dependencies
python -m pip install -e ".[dev]"

# Run the full test suite
python -m pytest

# Run unit tests only
python -m pytest tests/unit/

# Run a specific test file
python -m pytest tests/unit/test_knowledge_engine.py

# Run tests with coverage
python -m pytest --cov=app --cov-report=term-missing

# Lint
ruff check .

# Type check
mypy app
```

### Test Suite

- **1398 passing tests** (59 deselected — integration/live tests requiring Ollama, Tesseract, or network)
- Tests cover: ingestion, classification, routing, processing, AI analysis, markdown generation, knowledge engine, vector store, knowledge graph, semantic chunking, hybrid search, watcher, queue, CLI, configuration, security, and more
- External model behavior is mocked for deterministic tests
- Run `python -m pytest` to execute the full suite

### Development Principles
- Keep the project runnable after every change
- Prefer typed models for cross-module communication
- Keep Ollama access behind `app.infrastructure.llm`
- Keep vault writes behind `app.infrastructure.vault`
- Keep watcher and queue logic behind `app.infrastructure.watcher` and `app.infrastructure.queue`
- Do not overwrite user-written Obsidian content
- Add tests when changing shared behavior

---

## 🩺 Troubleshooting

### Watcher isn't detecting new files
- Confirm `pam watch` is running and `watcher.enabled` is `true` in your config
- Check that the file extension is supported (`.md`, `.txt`, `.pdf`)
- Verify `inbox_path` points to the correct directory (`pam config` shows the resolved path)
- Check `data/logs/watcher.log` for startup or permission errors

### Files stay in the queue and never process
- Confirm Ollama is running (`ollama list`) and reachable at the configured host
- Check `data/logs/processing.log` for stuck or errored jobs
- Restart with `pam watch` — pending items are restored from `data/manifests/queue_state.json`

### A file isn't being reprocessed
- This is expected behavior: AI Memory uses SHA-256 hashing to detect duplicates and skips files it has already processed
- To force reprocessing, remove the corresponding entry from `data/manifests/processed_files.json` or modify the file so its hash changes

### Files are ending up in `data/failed`
- Check `data/logs/errors.log` for the specific failure reason
- Common causes: Ollama unavailable, a malformed or password-protected PDF, or an unsupported file type
- Fix the underlying issue and move the file back into `data/inbox` to retry

### Manifest looks out of sync with the vault
- Manifests only track *source files*, not vault edits — manually edited notes in `vault/` are never touched
- If a manifest file becomes corrupted, back it up and delete it; AI Memory will recreate it and treat all inbox files as new on the next run

---

## 🔭 Vision

AI Memory has evolved from a manual document processor into an automated, local-first AI Memory System — one where knowledge capture happens continuously in the background instead of through one-off commands.

Version 3 and 4 foundations are already in place: **semantic memory** (local embeddings, semantic + hybrid search over the in-memory vector store), and a **knowledge graph** (entity/relationship extraction with JSON persistence and graph queries). Future versions build on this with external vector databases, **retrieval-augmented generation (RAG)**, and an agent layer — all while staying local-first and offline by design.

---

## 🗺️ Roadmap

### ✅ Completed (v1 – v3.2)
Local-first architecture · Ollama integration · PDF / Markdown / TXT ingestion · GitHub README ingestion · YouTube transcript ingestion · Markdown generation & vault management · CLI, logging, and config management · Automatic folder watching (`pam watch`) · Background watcher service · Processing queue with recovery · SHA-256 duplicate detection · Automatic processed / failed folders · Graceful shutdown · Rich CLI progress · Runtime statistics · 21-field document intelligence · Semantic chunking & embeddings · Vector store with similarity search · Knowledge graph with persistence · Cross-document linking · Placeholder note creation · Semantic & hybrid search · Entity/relationship extraction

### 🔜 v3 — Semantic Memory (partially shipped)
- ✅ Local embeddings & vector store — in-memory with JSON persistence
- ✅ Semantic search — cosine similarity over embedded chunks
- ✅ Hybrid search — RRF (dense + BM25)
- ✅ `pam search` CLI — query, top-k, metadata filters, min-score
- 🔜 External vector DB — ChromaDB / FAISS / Qdrant
- 🔜 RAG & context retrieval over retrieved chunks

### 🔮 v4 — Knowledge Graph (partially shipped)
- ✅ In-memory entity/relationship graph with JSON persistence and graph queries
- 🔜 Neo4j / NetworkX for large-scale graph storage

### 🚀 v5 — Autonomous AI Agent
- Personal Tutor
- Research Assistant
- Daily Knowledge Summaries

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome. Feel free to check the [issues page](https://github.com/GiridharBM/AI-Memory/issues) or open a pull request.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](./LICENSE) file for details.

---

<div align="center">

Made with 🧠 by [GiridharBM](https://github.com/GiridharBM)

</div>
