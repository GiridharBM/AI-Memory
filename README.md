<div align="center">

# 🧠 AI Memory

**Build your own offline AI-powered second brain using Python, Ollama, and Obsidian.**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-000000?style=for-the-badge)
![Obsidian](https://img.shields.io/badge/Obsidian-Knowledge%20Base-7C3AED?style=for-the-badge&logo=obsidian&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)
![Version](https://img.shields.io/badge/Version-v1.0-blue?style=for-the-badge)
![Tests](https://img.shields.io/badge/Tests-36%20Passing-success?style=for-the-badge)

[Overview](#-overview) •
[Features](#-features) •
[Installation](#-installation) •
[Usage](#-cli-usage) •
[Architecture](#%EF%B8%8F-project-architecture) •
[Configuration](#%EF%B8%8F-configuration) •
[License](#-license)

</div>

---

## 📖 Overview

**AI Memory** is a local-first personal AI memory system that continuously transforms documents, research papers, GitHub repositories, YouTube transcripts, and personal notes into an interconnected Obsidian knowledge base.

Unlike traditional note-taking apps, AI Memory doesn't just store information — it **analyzes, organizes, summarizes, links, and enriches** your knowledge while keeping everything completely offline.

- Your data never leaves your machine
- No cloud APIs
- No subscriptions
- No vendor lock-in

---

## ✨ Features

### 🤖 AI Powered
- Local inference using Ollama
- Qwen3:8B integration
- Structured JSON generation with automatic retries and validation
- Modular, swappable prompt system

### 📄 Document Ingestion
Supports:
- PDF documents
- Markdown files
- Plain text files
- GitHub repository READMEs
- YouTube transcripts

### 🧠 Knowledge Extraction
Automatically extracts:
- Summaries
- Key concepts & definitions
- Important entities
- Related topics & references
- Tags and suggested titles

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

---

## 🚀 Current Status

**Version:** `v1.0.0`  **Status:** 🟢 Actively Developed

| Completed | In Progress |
|---|---|
| Local-first architecture | Folder ingestion |
| Ollama integration | Automatic vault watching |
| PDF / Markdown / TXT ingestion | Better PDF parsing |
| GitHub README ingestion | Incremental processing |
| YouTube transcript ingestion | |
| Markdown generation & vault management | |
| CLI interface, logging, config management | |
| Comprehensive testing | |

---

## 🛠️ Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python 3.11+ |
| Local LLM | Ollama |
| Default Model | Qwen3:8B |
| CLI | Typer |
| Terminal UI | Rich |
| Configuration | YAML |
| Validation | Pydantic |
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

### 4. Verify installation
```bash
python -m pytest
pam doctor
```

Expected output:
```text
36 passed

✔ Configuration loaded
✔ Ollama available
✔ Vault available
✔ Inbox available
```

---

## 🤖 Ollama Setup

1. Install Ollama from [ollama.com](https://ollama.com)
2. Pull the default model:
   ```bash
   ollama pull qwen3:8b
   ```
3. Verify installation:
   ```bash
   ollama list
   ```
   Expected:
   ```text
   qwen3:8b
   ```
4. Start Ollama (if not already running):
   ```bash
   ollama serve
   ```

**Defaults**

| Setting | Value |
|---|---|
| Endpoint | `http://localhost:11434` |
| Model | `qwen3:8b` |

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
pam --help          # General help
pam status           # Configuration, vault, and Ollama status
pam doctor           # Full health check
pam config            # View current configuration
pam config --json    # View configuration as JSON
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

---

## 🔄 Processing Workflow

Every document follows the same pipeline:

```text
Document → Ingestion → Text Cleaning → Prompt Construction
→ Ollama Processing → Structured JSON → Markdown Generation
→ Wiki Update → Obsidian Vault
```

**Example — Markdown:**
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
  Ingestion
      │
      ▼
Text Preprocessing
      │
      ▼
 Prompt Builder
      │
      ▼
 Ollama (Qwen3)
      │
      ▼
JSON Validation
      │
      ▼
Markdown Generator
      │
      ▼
 Wiki Manager
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
│   ├── cache/
│   ├── manifests/
│   ├── staging/
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
| `config/` | YAML configuration files |
| `data/inbox/` | Input files for ingestion |
| `data/cache/` | Temporary cached data |
| `data/logs/` | Application logs |
| `data/manifests/` | Reserved for persistent processing state |
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
```

Default configuration:
```yaml
app:
  name: AI Memory
  environment: development

paths:
  vault_root: ./vault
  inbox_root: ./data/inbox
  cache_root: ./data/cache
  logs_root: ./data/logs

ollama:
  host: http://localhost:11434
  model: qwen3:8b
  timeout_seconds: 120

logging:
  level: INFO
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

## 🧑‍💻 Development Guide

```bash
# Install development dependencies
python -m pip install -e ".[dev]"

# Run the full test suite
python -m pytest

# Run a specific test file
python -m pytest tests/integration/test_complete_workflow.py

# Lint
ruff check .

# Type check
mypy app
```

### Development Principles
- Keep the project runnable after every change
- Prefer typed models for cross-module communication
- Keep Ollama access behind `app.infrastructure.llm`
- Keep vault writes behind `app.infrastructure.vault`
- Do not overwrite user-written Obsidian content
- Add tests when changing shared behavior

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
