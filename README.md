<div align="center">

# 🧠 PAM — Personal AI Memory

**A local-first AI memory system that turns your notes, documents, and files into a searchable, connected knowledge base — retrieved and answered by a local LLM.**

![Status](https://img.shields.io/badge/status-V1.1.0-success)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)
![Local First](https://img.shields.io/badge/design-local--first%20%7C%20private-informational)

</div>

---

## Current Release

**PAM V1.1.0** (tag `v1.1.0`) is the latest published release.

V1.1 focuses on **reliability, source management, ingestion safety, CLI usability, and truthful status** — not on retrieval-quality improvements. The retrieval pipeline was intentionally frozen for V1.1 (see [Retrieval Status](#retrieval-status)).

After the V1.1.0 release, the project continues with documentation and maintenance work. The V1.1.0 tag remains the published release; later commits are post-release documentation/maintenance and do not change the release.

See [`docs/PROJECT_STATUS.md`](./docs/PROJECT_STATUS.md) for the current canonical status of the project.

---

## What PAM Does

PAM is a **local-first** personal AI memory system. It ingests your local documents (notes, PDFs, Markdown, code, spreadsheets, and more), chunks and embeds them, stores them in a local vector store, and lets you:

- **retrieve** relevant knowledge with hybrid (semantic + keyword) search, and
- **ask grounded questions** against that knowledge with a local LLM.

Everything runs on your machine through a local [Ollama](https://ollama.com) server. No document content leaves your machine.

---

## Core Capabilities

Verified in the current V1.1.0 implementation:

- **Document ingestion** — `pam ingest file <path>` auto-detects and ingests many local formats; typed subcommands (`markdown`, `pdf`, `txt`) and network sources (`github`, `youtube`) are also available.
- **Source listing** — `pam sources` lists the sources currently indexed, from durable state (read-only).
- **Source removal** — `pam remove <source>` removes a source's vectors, knowledge-graph nodes/edges, and manifest entries. It never deletes vault notes.
- **Status** — `pam status` shows a concise, truthful overview of current PAM state (read-only).
- **Local retrieval & QA** — hybrid search (`pam search`) and grounded question answering (`pam ask`) over your local knowledge base.
- **Citations / source reporting** — answers are returned with source references from the retrieved results.
- **System-facts fast path** — deterministic answers for "about the tool" questions (version, source count, feature status, and more) without invoking retrieval or the LLM.
- **Ingestion retry & deduplication** — recoverable failures are retried; files already processed are skipped by SHA-256 hash.
- **Safe re-ingestion** — already-ingested sources can be re-ingested without corrupting the index.
- **Secret-bearing source blocking** — local secret/credential files are blocked before any content is read or processed (see [Security](#security)).
- **Bounded QA timeout** — the QA generation call is bounded by a configured timeout (default 120 s) so a single answer cannot hang indefinitely.

---

## Architecture

High-level data flow:

```
Sources (files, URLs)
      │
      ▼
Ingestion (classify → route → extract / analyze)
      │
      ▼
Chunking / Embeddings / Storage (vector store + knowledge graph + manifest)
      │
      ▼
Retrieval (hybrid: semantic + keyword, fused)
      │
      ▼
QA / Citations (grounded answer + system-facts fast path)
      │
      ▼
CLI (pam)
```

**System-facts** is a fast path: questions about the tool itself (version, status, feature flags, source/chunk counts) are answered deterministically from application state — the retrieval, reranker, HyDE, and answerability pipeline is not invoked for those.

The reranker, HyDE, and answerability modules are **implemented but disabled** in the default runtime and are not part of the normal active pipeline (see [Experimental Features](#experimental-features)).

---

## Local Setup

PAM requires:

- **Python 3.11+** (validated on 3.11, 3.12, 3.13)
- **Ollama** running locally with the models you intend to use (default `qwen3:8b` for QA, `nomic-embed-text` for embeddings)
- Git (to clone) and a local filesystem for the project and vault

Clone, create a virtual environment, and install:

```bash
git clone https://github.com/GiridharBM/AI-Memory.git
cd AI-Memory
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e ".[dev,intelligence]"
```

The `intelligence` extras enable OCR (vision model + optional Tesseract), language detection, and related features.

**Ollama context:** the validated local setup uses an **8192-token Ollama context length** (`OLLAMA_CONTEXT_LENGTH=8192`). Local `qwen3:8b` generation can take seconds or longer depending on query complexity and hardware; measured latency is not guaranteed on every machine.

---

## Basic Usage

```bash
pam status          # concise, truthful overview of current state
pam doctor          # verify Ollama, config, and paths
pam ingest file path/to/document.pdf
pam sources         # list indexed sources
pam search "query"  # hybrid retrieval
pam ask "question"  # grounded answer with citations
pam remove <source> # remove one source from the index
pam watch           # watch an inbox folder for new files
pam config          # show resolved configuration
```

Network sources (explicit, opt-in):

```bash
pam ingest github https://github.com/owner/repository
pam ingest youtube https://www.youtube.com/watch?v=VIDEO_ID
```

---

## Source Management

- **`pam sources`** — read-only list of indexed sources (from durable state; it never queries the corpus or launches the LLM).
- **`pam ingest file <path>`** — ingest a source. Duplicate detection (SHA-256) skips files already processed; recoverable failures are retried.
- **`pam remove <source>`** — remove one source's vectors, knowledge-graph entries, and manifest entries. It identifies the source deterministically, refuses ambiguous/unknown sources without deleting anything, and **never deletes vault notes** (notes may contain user-written content). There is no "remove everything" operation.
- **`pam status`** — reports processed/skipped/failed ingests, indexed sources and chunks, and queue state, truthfully (read-only).

---

## QA / Answers

`pam ask "question"`:

1. **System-facts fast path** — if the question is about the tool (version, source count, feature status, QA model, capabilities, status), it is answered deterministically without retrieval or the LLM.
2. Otherwise, **retrieve** the most relevant chunks from your knowledge base (hybrid semantic + keyword search), **build a bounded context**, and have the local LLM **answer from that context only**.
3. The answer includes **source references** from the retrieved results.

If no sufficiently relevant context is retrieved (e.g. the top match falls below the minimum cosine threshold), PAM **abstains** rather than guessing. The QA generation call is bounded by a configured timeout (default 120 s).

---

## Security

PAM blocks local **secret-bearing files** from ingestion before any content is read or processed. This includes `.env` / `.env.*` files, private-key/credential files (`.pem`, `.key`, `.ppk`, `.p12`, `.pfx`), and files named like `credentials`, `secret(s)`, `passwd`, `shadow`, or `htpasswd`. The guard targets local secret files so secret contents never enter the pipeline.

PAM is **local-first**: all LLM, embedding, vision, and audio calls go to your local Ollama server. The only network operations are the two explicit external-source commands (`pam ingest github`, `pam ingest youtube`).

This is a targeted ingestion-safety guard, not a claim of comprehensive general-purpose security.

---

## Testing

PAM has a substantial automated test suite. Verification is reported as a **dated snapshot** rather than a single marketing number. The latest known verification state is documented in the project's testing/release records (`docs/PROJECT_STATUS.md`, `docs/TESTING_AND_VERIFICATION.md`, and the release provenance records in `docs/releases/`).

The most recent verification snapshot reflects ~1703 passed, with 8 known exceptions (7 stale evaluation-dataset assertions and 1 known logging-isolation test flake) that are documented — they are not eight product defects. The current release state and known test exceptions are maintained in the project's status and release documentation, not as a static badge here.

---

## Retrieval Status

**The retrieval pipeline is intentionally frozen for V1.1.0.**

- Retrieval-improvement experiments were conducted before and around the V1.1 target.
- Further retrieval improvements remain **experimental / deferred**.
- PAM does **not** claim that retrieval is perfect.

The measured frozen-retrieval evaluation included a notable false-positive rate. Important context: many measured false positives were **content-sufficiency misses** — retrieved text could be topically on-topic but lack the exact fact required to answer a query. This is one reason evidence verification and retrieval improvements remain deferred. Detailed numbers belong in the evaluation/testing documentation, not this README.

PAM is honest about this: local hybrid retrieval returns what it returns, and QA abstains when retrieved context is insufficient.

---

## Experimental Features

These are **implemented, but disabled** in the V1.1.0 default runtime. They are not part of the normal active pipeline because the project did not establish that they met production quality/latency guardrails. They are not broken and not removed:

| Feature | Status | Notes |
|---|---|---|
| **CrossEncoder reranker** | implemented, disabled | `reranker.enabled = false` |
| **HyDE** (HyDE query expansion) | implemented, disabled | `hyde.enabled = false` |
| **Answerability verifier** (evidence gate) | implemented, disabled | `answerability.enabled = false` |

---

## Known Limitations

An honest, user-facing summary:

1. **Retrieval content sufficiency** — retrieval can return topically relevant chunks that do not contain the exact fact required to answer a query.
2. **Retrieval quality** — the frozen retrieval baseline does not satisfy every desired experimental quality guardrail. This is a known limitation, not a catastrophic failure.
3. **Local LLM latency** — local `qwen3:8b` generation can take seconds or longer depending on query complexity and hardware.
4. **Context configuration** — the validated local setup uses an 8192-token Ollama context.
5. **Storage atomicity** — vector-store and knowledge-graph persistence are not fully transactional across both stores.
6. **Knowledge-graph removal caveat** — shared KG nodes/relationships can require more careful semantics than a simple per-source deletion.
7. **Platform/environment scope** — validated conservatively: Linux (CI), Windows (local development), with macOS designed to be cross-platform but not independently validated in CI.

PAM depends on a running local Ollama runtime; there is no hosted/cloud answer path.

---

## License

Licensed under the **MIT License** — see [LICENSE](./LICENSE) for details.