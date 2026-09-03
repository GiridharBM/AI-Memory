# Implementation Guide

How **Personal AI Memory (PAM)** is implemented, layer by layer, and how to work in the codebase. This is a developer-facing companion to [`architecture.md`](./architecture.md).

> Current release: **V1.1.0**. Retrieval is frozen for V1.1.0; the layered structure below is the source of truth for how the system is organized.

## Layer structure

| Layer (`app/`) | Responsibility | Key modules |
|----------------|----------------|-------------|
| **`cli/`** | Presentation — Typer command surface | `entry.py` (status, doctor, config, watch, search, ask, sources, remove, ingest) |
| **`application/`** | Orchestration of use cases | `qa_workflow.py`, `qa_measurement_harness.py` (experimental), `system_facts.py`, `ai_processor.py` |
| **`pipelines/`** | End-to-end document-to-note pipeline | `ingest_workflow.py` |
| **`domain/`** | Data contracts and models | `documents`, `analysis`, `notes`, `processed_document`, `vector_store`, `semantic_chunking`, `knowledge_graph` |
| **`infrastructure/`** | Concrete services | `ingestion/` (ingestors), `routing/` (classifier, router, processors), `document_intelligence/` (metadata, ocr, structure, tables, images, entities, relationships, graph), `semantic_chunking.py`, `vector_store.py`, `search.py`, `llm/` (Ollama), `vault/` (VaultWriter, WikiManager), `state/manifest.py` |
| **`watcher/`** | File-system watch and queue trigger | `service.py`, `scanner.py` |
| **`queue/`** | Persistent processing queue | `manager.py`, `worker.py`, `state.py`, `models.py`, `stats.py` |
| **`core/`** | Runtime configuration | `config.py` (`Settings`) |

- `app/infrastructure/banded_verifier.py` and `_kab` verifier code are **experimental** (disabled in production).
- `app/application/qa_measurement_harness.py` is an experimental measurement harness.

## Main flows

1. **Ingest** — `IngestionWorkflow.run(source)` → `DocumentIngestionService.ingest()` → registry-chosen `BaseIngestor` → classifier/router → processor → enrichment (metadata, structure, tables, images, entities, relationships, graph) → `SemanticChunker` → `EmbeddingService` → `VectorStore` → manifest/ledger → `VaultWriter`/`WikiManager`.
2. **Search** — `SearchService.search()` → `HybridSearch.search()` → `VectorStore` (dense) + `BM25Index` (lexical) → RRF fusion (k=60) → filters → `SearchHit`.
3. **Ask (RAG)** — `QAWorkflow.ask()` → search → `build_context()` (bounded) → `build_qa_user_prompt()` → `OllamaClient.generate_text()` → `QAAnswer` with `[SOURCE N]` citations.
4. **Source management** — `pam sources` lists indexed sources; `pam remove` de-indexes vectors/graph/ledger without touching vault notes (V1.1.0).
5. **System facts** — `SystemFacts` answers "about the tool" questions deterministically, without retrieval or LLM.

## Configuration

`app/core/config.py` loads validated configuration from, in order:

1. Pydantic model defaults
2. `config/default.yaml`
3. environment-specific files under `config/`
4. `PAM_`-prefixed environment variables

Settings groups include `app`, `paths`, `ollama`, `logging`, `watcher`, `queue`, `manifest`, `processing`, `models`, `intelligence.*`, and `chunking.*`.

## Conventions and guardrails

- **Local-first** — everything runs against local Ollama; no cloud calls.
- **Failure containment** — ingestion returns structured results instead of crashing; queue workers catch ingest/AI errors; a corrupted manifest is quarantined and rebuilt; hybrid search degrades to dense- or lexical-only.
- **Additive schema** — `metadata.extra` uses an additive `schema_version` for backwards compatibility.
- **RESPECT the freeze** — retrieval configuration (embed model, RRF, `min_cosine 0.25`) is frozen for V1.1.0. Do not change it as part of unrelated work.

## Testing

- Unit tests: `tests/unit/` (~71 files) — run `pytest tests/unit -q` (1688 passed / 1 deselected / 1 known logging-isolation flake as of V1.1.0).
- Evaluation contract: `tests/unit/test_eval_dataset.py` (32 passed).
- Integration: `tests/integration/` (18 files, `integration`-marked, excluded from the default run).

See [`TESTING_AND_VERIFICATION.md`](./TESTING_AND_VERIFICATION.md) for full detail and the historical records.
