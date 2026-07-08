# Personal AI Memory System

A local-first Personal AI Memory System for turning documents, repositories, and transcripts into an evolving Obsidian wiki.

The system runs on your machine with Python, Ollama, Qwen3:8B, Markdown, and Obsidian. It ingests source material, cleans the text, asks a local model for structured knowledge, generates Obsidian-compatible notes, and updates the vault without overwriting user-written content.

## Status

Version 1 includes:

- Configuration and environment variable support
- Reusable logging with console and rotating file logs
- PDF, Markdown, TXT, GitHub README, and YouTube transcript ingestion
- Text preprocessing that preserves headings, lists, paragraphs, and fenced code blocks
- Ollama integration with structured JSON validation and retries
- Obsidian Markdown generation
- Vault writing, wiki index updates, and duplicate-note protection
- Typer CLI with Rich terminal output
- Pytest coverage for configuration, logging, ingestion, processing, Markdown generation, wiki management, CLI, and the complete workflow

Version 1 intentionally does not include vector databases, RAG, graph databases, or a web UI.

## Installation

### Requirements

- Python 3.11 or newer
- Git
- Ollama
- Obsidian
- Qwen3:8B pulled in Ollama

### Clone The Repository

```bash
git clone <repository-url>
cd LLM-Wiki
```

### Create A Virtual Environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS or Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### Install Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e ".[dev]"
```

### Verify Installation

```bash
python -m pytest
pam doctor
```

The test suite should pass without requiring a live Ollama model because model calls are mocked in tests.

## Ollama Setup

Install Ollama from the official Ollama website, then pull the model:

```bash
ollama pull qwen3:8b
```

Start Ollama if it is not already running:

```bash
ollama serve
```

The default endpoint is:

```text
http://localhost:11434
```

The default model is:

```text
qwen3:8b
```

You can override these values with configuration or environment variables:

```bash
PAM_OLLAMA__HOST=http://localhost:11434
PAM_OLLAMA__MODEL=qwen3:8b
```

## Obsidian Setup

The application writes Markdown files into the configured vault path.

By default, the vault path is:

```text
./vault
```

You can either:

- Open the project `vault/` folder as an Obsidian vault.
- Point the application at an existing Obsidian vault.

Example environment override:

```bash
PAM_PATHS__VAULT_ROOT=D:\Obsidian\PersonalAIWiki
```

The wiki manager maintains these files in the vault root:

- `index.md`
- `overview.md`
- `log.md`

Generated notes are stored under:

```text
Notes/
```

Generated content is wrapped in managed markers so user-written content is preserved:

```markdown
<!-- PAM:BEGIN MANAGED -->
Generated content
<!-- PAM:END MANAGED -->
```

## CLI Usage

The CLI entrypoint is:

```bash
pam
```

Show status:

```bash
pam status
```

Run local health checks:

```bash
pam doctor
```

Show resolved configuration:

```bash
pam config
pam config --json
```

Ingest a PDF:

```bash
pam ingest pdf path/to/file.pdf
```

Ingest Markdown:

```bash
pam ingest markdown path/to/file.md
```

Ingest TXT:

```bash
pam ingest txt path/to/file.txt
```

Ingest a GitHub repository README:

```bash
pam ingest github https://github.com/owner/repository
```

Ingest a YouTube transcript:

```bash
pam ingest youtube https://www.youtube.com/watch?v=VIDEO_ID
```

## Examples

### Example: Local Markdown Note

```bash
pam ingest markdown ./data/inbox/agent-notes.md
```

Workflow:

```text
Markdown file -> cleaned text -> Ollama JSON -> Obsidian note -> vault update
```

Output:

```text
vault/
  Notes/
    Suggested Note Title.md
  index.md
  overview.md
  log.md
```

### Example: GitHub Repository README

```bash
pam ingest github https://github.com/ollama/ollama
```

The system downloads the repository README, extracts clean Markdown, analyzes it with Ollama, and saves the generated note into Obsidian.

### Example: YouTube Transcript

```bash
pam ingest youtube https://www.youtube.com/watch?v=VIDEO_ID
```

If a transcript is unavailable, the command exits gracefully with a clear error message.

## Project Architecture

The system is organized as a clean, local-first pipeline.

```text
Input
  -> Ingestion
  -> Text preprocessing
  -> Ollama processing
  -> JSON validation
  -> Markdown generation
  -> Wiki update
  -> Obsidian vault write
```

Primary layers:

- `app.cli`: Typer command-line interface.
- `app.core`: configuration, logging, and shared technical foundations.
- `app.domain`: typed business objects such as source documents, analyses, and generated notes.
- `app.infrastructure`: adapters for ingestion, Ollama, vault persistence, and external systems.
- `app.application`: application services such as AI processing.
- `app.pipelines`: end-to-end workflows.
- `app.prompts`: prompt templates sent to Ollama.
- `app.templates`: Markdown generation for Obsidian notes.

See [docs/architecture.md](docs/architecture.md) for the detailed architecture.

## Folder Structure

```text
personal-ai-memory/
  app/
    application/
    cli/
    core/
    domain/
    infrastructure/
      ingestion/
      llm/
      logging/
      state/
      vault/
    pipelines/
    prompts/
    templates/
  config/
    default.yaml
    development.yaml
    production.yaml
  data/
    cache/
    inbox/
    logs/
    manifests/
    staging/
  docs/
  scripts/
  tests/
    integration/
    unit/
  vault/
  pyproject.toml
  requirements.txt
  README.md
```

Important folders:

- `app/`: production Python package.
- `config/`: YAML configuration files.
- `data/inbox/`: optional local drop zone for source files.
- `data/logs/`: rotating application logs.
- `data/manifests/`: reserved for persistent processing state.
- `tests/`: unit and integration tests.
- `vault/`: default Obsidian vault output folder.

## Configuration

Configuration is loaded in this order:

1. `config/default.yaml`
2. `config/<environment>.yaml`
3. Environment variables prefixed with `PAM_`

Default environment:

```text
development
```

Select another environment:

```bash
PAM_ENVIRONMENT=production
```

Nested environment variables use double underscores:

```bash
PAM_OLLAMA__MODEL=qwen3:8b
PAM_LOGGING__LEVEL=DEBUG
PAM_PATHS__VAULT_ROOT=D:\Obsidian\PersonalAIWiki
```

Key configuration sections:

- `app`: app name and environment.
- `paths`: vault, inbox, staging, manifest, cache, and log paths.
- `ollama`: endpoint, model, timeout, retry count, and retry backoff.
- `logging`: console logging, file logging, colors, rotation size, and backup count.

Show resolved config:

```bash
pam config
```

## Generated Note Format

Each generated note includes:

- YAML frontmatter
- Title
- Summary
- Key Concepts
- Definitions
- Important Entities
- Related Topics
- Tags
- References
- Generated date
- Source
- Obsidian wiki links where useful

Concepts, definitions, entities, and related topics are rendered with `[[wiki links]]` so the vault can grow into a connected knowledge base over time.

## Development Guide

### Install Development Dependencies

```bash
python -m pip install -e ".[dev]"
```

### Run Tests

```bash
python -m pytest
```

### Run A Specific Test File

```bash
python -m pytest tests/integration/test_complete_workflow.py
```

### Lint

```bash
ruff check .
```

### Type Check

```bash
mypy app
```

### Development Principles

- Keep the project runnable after every change.
- Prefer typed models for cross-module communication.
- Keep Ollama access behind `app.infrastructure.llm`.
- Keep vault writes behind `app.infrastructure.vault`.
- Do not overwrite user-written Obsidian content.
- Add tests when changing shared behavior.

## Testing Strategy

The test suite uses pytest and mocks external model behavior.

Coverage includes:

- Configuration validation and environment overrides
- Logging setup and file output
- Ingestion adapters
- Text preprocessing
- Ollama client behavior with mocked transport
- AI processing and malformed JSON retries
- Markdown generation
- Wiki manager and vault writer behavior
- CLI command behavior
- Complete end-to-end workflow

Run the full suite:

```bash
python -m pytest
```

Current expected result:

```text
36 passed
```

## Future Roadmap

Planned future versions may add:

- Incremental source manifests and change detection
- Folder ingestion
- Full GitHub repository ingestion beyond README files
- Research paper-specific extraction
- Better transcript metadata
- Local embeddings
- Vector search with ChromaDB, FAISS, or Qdrant
- RAG over the generated vault
- Knowledge graph support
- Obsidian backlink refinement
- Scheduled ingestion
- Conflict-aware note merging
- Web or desktop UI

The current architecture is designed so these capabilities can be added without rewriting ingestion, AI processing, Markdown generation, or vault persistence.

## License

This project is currently marked as proprietary in `pyproject.toml`.
