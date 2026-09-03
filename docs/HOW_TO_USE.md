# How to Use PAM

Practical, command-by-command usage of **Personal AI Memory (PAM)** for day-to-day work. All commands below reflect the current **V1.1.0** CLI (verified in `app/cli/entry.py`).

## Command index

| Command | Purpose |
|---------|---------|
| `pam status` | processed / skipped / failed counts and queue state |
| `pam doctor` | environment, dependency, and configuration checks |
| `pam config` / `config-show` | show current configuration (`--json`, `-e ENV`) |
| `pam sources` | list indexed sources with per-source chunk counts and truthful status |
| `pam remove <source>` | de-index a source (vectors, graph, manifest) — never deletes vault notes |
| `pam watch` | watch an inbox folder and ingest new files |
| `pam search <query>` | hybrid retrieval with optional filters |
| `pam ask <question>` | retrieval-grounded RAG answer with `[SOURCE N]` citations |
| `pam ingest ...` | ingest files / URLs (subcommands below) |

## Ingesting content

```bash
pam ingest file path/file.md        # auto-detect type
pam ingest markdown path/notes.md   # typed subcommands
pam ingest pdf      path/report.pdf
pam ingest txt      path/notes.txt  # also code / plain text
pam ingest github   owner/repo      # network integration (opt-in)
pam ingest youtube  <video-url>     # network integration (opt-in)
```

Duplicate files are detected by SHA-256 and skipped. Unsupported or failing sources are routed to `failed/` and can be retried — the process never crashes.

## Searching and asking

```bash
pam search "some topic"                           # default
pam search "topic" --top-k N                      # more/fewer results
pam search "topic" --source-type pdf              # filter by source type
pam search "topic" --min-score 0.3                # cosine threshold
pam search "topic" --filter '{"metadata":{"x":1}}'# exact metadata filter

pam ask "what does this cover?"                   # RAG answer with citations
pam ask "why X?" --top-k 5 --min-score 0.3        # tune retrieval
```

Search fuses dense (cosine) and sparse (BM25) signals with RRF (k=60). `pam ask` grounds the local LLM answer in the retrieved chunks and refuses when context is insufficient.

## Managing sources

```bash
pam sources                     # list indexed sources
pam remove <source>             # de-index a source
```

`pam remove` removes the source's vectors, knowledge-graph nodes/edges, and manifest/ledger entry. It **never deletes** the corresponding vault note and refuses ambiguous or unknown sources.

## Naming conventions

`pam ingest` uses content-type subcommands (e.g. `file`, `markdown`, `pdf`, `txt`) for local files and explicit integration subcommands (`github`, `youtube`) for network sources. Source types are normalized so the classifier and router can pick the correct processor.

## Local-first

Everything runs locally against Ollama — no cloud calls. QA uses the configured local model and the bounded context (`MAX_CONTEXT_CHUNKS=8`, `MAX_CONTEXT_CHARS=12000`).

## Troubleshooting

- **No answers / abstains:** retrieval found insufficient context; try lowering `--min-score` or adding source material.
- **No results from `pam search`:** confirm the source was indexed (`pam sources`) and the model is up (`pam doctor`).
- **Slow response:** QA is single-worker and local; the default timeout is 120 s.

See [`GETTING_STARTED.md`](./GETTING_STARTED.md) for installation and [`KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md) for limits.
