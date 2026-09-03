# Getting Started

How to set up **LLM-Wiki / Personal AI Memory (PAM)** from zero: prerequisites, install, first run, and first ingest.

> Current release: **V1.1.0**. See [`PROJECT_STATUS.md`](./PROJECT_STATUS.md) for the canonical current state and [`architecture.md`](./architecture.md) for how it is built.

## 1. Prerequisites

- **Python** 3.11–3.13 (validated in CI).
- **Ollama** installed and running locally, with the QA model and embedding model available:
  - QA: `qwen3:8b` (default)
  - Embeddings: `nomic-embed-text` (default)
- **Disk space** for `vault/`, `data/` (vector store, BM25 index, knowledge graph, manifests), and `logs/`.

If a required library is missing, PAM routes unsupported source types to a `failed/` folder and returns structured errors rather than crashing — see [`KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md).

## 2. Install

From the repository root:

```bash
pip install -e .
```

This installs the `pam` CLI. Dependencies are declared in `requirements.txt` / `pyproject.toml`.

## 3. Configure

Configuration is loaded from Pydantic defaults, `config/default.yaml`, environment-specific files under `config/`, and `PAM_`-prefixed environment variables. Check the active configuration:

```bash
pam config            # show current config
pam config --json     # show as JSON
```

For production use the values in [`PROJECT_STATUS.md`](./PROJECT_STATUS.md) (Ollama QA + embed models, context 8192, QA timeout 120 s, `min_cosine 0.25`).

## 4. Verify the install

```bash
pam status          # processed / skipped / failed counts and queue state
pam doctor          # environment / dependency / configuration checks
```

`pam status` and `pam doctor` confirm the tool is wired to your local Ollama and vault correctly before you ingest content.

## 5. First ingest

Ingest a single file with auto-detection:

```bash
pam ingest file path/to/your-document.md
```

Typed subcommands are also available:

```bash
pam ingest markdown path/to/notes.md
pam ingest pdf      path/to/report.pdf
pam ingest txt      path/to/notes.txt   # or a generic .py / .txt file
```

Network integrations (explicit opt-in):

```bash
pam ingest github   <owner>/<repo>
pam ingest youtube  <video-url>
```

Watch a folder for new files:

```bash
pam watch path/to/inbox
```

Each ingested source becomes a note in the Obsidian vault (`vault/Notes/`) and its chunks are indexed for search.

## 6. Try it

```bash
pam search "your topic" --top-k 5      # hybrid retrieval, dense + BM25 (RRF k=60)
pam ask "what does the project cover?" # grounded RAG answer with [SOURCE N] citations
pam sources                            # list indexed sources with chunk counts
```

## 7. Next steps

- [`HOW_TO_USE.md`](./HOW_TO_USE.md) — full command reference and workflows.
- [`IMPLEMENTATION_GUIDE.md`](./IMPLEMENTATION_GUIDE.md) — how the codebase is organized.
- [`KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md) — honest limits (what is and is not supported).
- Root [`README.md`](../README.md) — project overview.
