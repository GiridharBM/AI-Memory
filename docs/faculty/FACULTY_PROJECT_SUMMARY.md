# PAM — Faculty Project Summary

> Companion to [`../FACULTY_PRESENTATION_GUIDE.md`](../FACULTY_PRESENTATION_GUIDE.md).
> Every fact below is drawn from the current V1.1.0 documentation. Where a fact is
> not established by current project documentation it is marked as such.

## 1. Project title

**Personal AI Memory (PAM)** — package `personal-ai-memory`, current release **V1.1.0**.

## 2. Problem statement

Knowledge accumulates in many formats (PDFs, DOCX, Markdown, code, notebooks,
spreadsheets, images, audio, video, web content) scattered across folders. Conventional
search fails on prose and images, and generic chatbots have no access to the user's
private material.

## 3. Motivation

People need to (1) **find** what they know, (2) **connect** related ideas across
documents, (3) **recall** concepts in review-ready formats, and (4) do it all
**offline and privately**. A normal chatbot cannot do this because it has no access
to — and must not be trusted with — the user's personal corpus.

## 4. Proposed solution

A **local-first, offline-first AI system** that converts documents, code, notebooks,
and more into a **connected Obsidian knowledge base** with semantic and hybrid search
and **retrieval-grounded question answering** with citations.

## 5. What PAM means

- **P**ersonal — your own data, on your own machine.
- **AI** — local models for understanding and answering.
- **Memory** — a durable index/knowledge base that persists across sessions.

## 6. What PAM actually does

- Ingests and normalizes sources, semantically chunks them, embeds them with a local
  model, and indexes them into a vector store plus a knowledge graph.
- Offers hybrid search (`pam search`) — dense + BM25 fused by RRF.
- Answers questions (`pam ask`) grounded in retrieved chunks with `[SOURCE N]`
  citations, and abstains when context is insufficient.
- Manages sources: `pam sources`, `pam remove`, safe re-ingestion, deduplication,
  truthful `pam status`.

## 7. Why PAM is different from a normal chatbot

A normal chatbot answers from its own pretrained knowledge and has no private context.
PAM is **grounded**: every answer is built from the user's own retrieved notes, carries
citations to those notes, and abstains rather than fabricating when evidence is
insufficient. It also explains the *source*, not just the answer.

## 8. Local / private architecture

Everything — embeddings (local `nomic-embed-text`) and QA (local `qwen3:8b`) — runs
against a **local Ollama** server. No cloud calls. This is documented as "local-first"
throughout the project.

## 9. End-to-end data flow

```
User / Document
      ↓
Ingestion
      ↓
Classification / Routing
      ↓
Extraction / Normalization
      ↓
Semantic Chunking
      ↓
Embedding
      ↓
Vector Store + Knowledge Graph
      ↓
Hybrid Retrieval
      ↓
Abstention / Evidence Handling
      ↓
Local QA Model
      ↓
Citation / Answer Contract
      ↓
CLI Output
```

## 10. Ingestion pipeline

A registry of type-specific ingestors reads and normalizes raw sources; a
classifier/router selects the appropriate processor; enrichment (metadata, OCR,
tables, images, entities, knowledge graph) runs; then content is semantically chunked
and embedded.

## 11. Chunking and embedding

Text is split into semantically coherent chunks (sentence segmentation + heading
hierarchy). Each chunk is embedded with the local Ollama embedding model and stored in
the in-memory vector store (with JSON persistence).

## 12. Retrieval

Hybrid: dense cosine similarity + BM25 lexical matching, **fused by RRF (k=60)**,
with filters (top-k, source-type, min-score, metadata). `min_cosine` is frozen at 0.25.

## 13. Abstention / evidence handling

When retrieved context is insufficient to support an answer, the system abstains
instead of fabricating. (The dedicated answerability/evidence-verification components
are implemented but disabled in V1.1.0 production; see Production vs Experimental.)

## 14. Local QA generation

`pam ask` gathers retrieved chunks into a bounded context (configurable), builds a
grounded system prompt, and calls the local Ollama model. QA has a default timeout of
120 s and an 8192-token Ollama context.

## 15. Citations

Answers carry `[SOURCE N]` markers that resolve to the specific retrieved sources, so
a faculty evaluator can trace every claim back to a source note.

## 16. Source management

`pam sources` lists sources with per-source chunk counts and truthful status.
`pam remove <source>` removes vectors, knowledge-graph nodes/edges, and ledger/manifest
entries — but **never deletes** the corresponding vault note, by design.

## 17. Deduplication

Each file is identified by a **SHA-256 hash** and tracked in a manifest/durable
ledger, so the same source is not processed repeatedly.

## 18. Safe re-ingestion

Re-ingesting an existing source removes prior chunks **only after a full successful
re-embed/re-index**; on failure the previous data is preserved. No unsafe partial
replacement.

## 19. Source removal

Removal de-indexes vectors, graph, and ledger entry. It deliberately does **not**
delete the vault note (avoids data loss by design); to fully remove content the note
must be removed manually.

## 20. Status / observability

`pam status` truthfully reports processed/skipped/failed ingests and queue state;
sources without a ledger match are labeled `indexed (no ledger)`. `pam doctor`
verifies Ollama, config, and paths.

## 21. Security protections

- **Local-first:** no cloud/data exfiltration path.
- **Secret-bearing files are blocked** from ingestion.
- **Failure containment:** structured errors, a `failed/` folder, and corruption
  quarantine (a corrupted manifest is quarantined and rebuilt, not fatal).
- Durable ledger/manifest for traceability.

## 22. System-facts fast path

Questions "about the tool" (version, status, feature status, QA model, capabilities)
are answered **deterministically from system facts — without retrieval or an LLM call**.

## 23. Testing and verification

- **1712 tests passed / 57 deselected (integration-marked) / 0 failed**.
- Ruff passes; `mypy app/` reports 0 production/CI-visible errors.
- The four mypy errors in untracked `app/application/qa_measurement_harness.py` are
  **research-only and outside CI**.
- Remote GitHub CI was **not independently verified** from this environment; local
  CI-equivalent checks pass. No claim of green remote CI is made.
- A former CLI logging-isolation test flake was fixed (`ea8a95b`); one MIME
  random-input test has shown occasional test-environment nondeterminism but passed
  the final run.

## 24. Limitations

- Local single-machine / single-worker pipeline.
- **Retrieval is deliberately frozen** for V1.1.0.
- Not every ingestor is deep product support: **PPTX, XLSX, OCR/scanned PDFs, images,
  audio, video are not uniformly guaranteed** end-to-end. Verified core formats are
  PDF, DOCX, TXT, Markdown, and code/text, plus GitHub/YouTube opt-in where supported
  ("library ≠ product support").
- Experimental features are disabled in production.
- Full list: [`../KNOWN_LIMITATIONS.md`](../KNOWN_LIMITATIONS.md).

## 25. Future work

Roadmapped (deferred) work includes broadened/verified ingestion support, parallel
processing, and enabling/validating the experimental retrieval features once they meet
production quality/latency guardrails. See
[`../DEVELOPMENT_ROADMAP.md`](../DEVELOPMENT_ROADMAP.md).

---

## Source lifecycle

```
Source
  ↓
Manifest / Durable Ledger
  ↓
Deduplication
  ↓
Ingestion
  ↓
Index + Knowledge Graph
  ↓
Re-ingestion / Remove
  ↓
Status
```

---

## Production vs Experimental

**Production / verified:** ingestion lifecycle, source management, deduplication, safe
re-ingestion, removal, hybrid retrieval, abstention-aware QA contract, citations,
system-facts fast path, local model execution, security guardrails, status/doctor
tooling.

**Disabled / experimental:** CrossEncoder reranker, HyDE, answerability verifier,
banded verifier, QA measurement research harness.

Experimental means **retained for research but disabled from the production V1.1.0
path** — not deleted. (Default: `reranker.enabled=false`, `hyde.enabled=false`,
`answerability.enabled=false`.)

---

## Built vs used

**Built / integrated by the project:** ingestion lifecycle, document routing,
normalization/chunking pipeline, deduplication, durable ledger, re-ingestion safety,
source removal, hybrid-retrieval orchestration (dense + BM25 index + RRF fusion),
abstention-aware QA workflow, citation contract, system-facts routing, CLI workflows,
security guards, testing/evaluation infrastructure.

**Used as dependencies / infrastructure (named in the project documentation):**
- **Ollama** — local runtime for models/embeddings.
- **qwen3:8b** — local QA model.
- **nomic-embed-text** — local embedding model.
- **Tesseract** — optional OCR fallback.

The project did **not** implement the LLM/embedding models or foundational inference
libraries itself; it orchestrates and integrates them.

---

## Rationale behind major decisions ("why")

- **Why local-first?** Privacy and offline use — personal material never leaves the
  machine. (Phase 12 of the task; see also [`../architecture.md`](../architecture.md).)
- **Why CLI-first?** Single-user local tool; a terminal interface keeps the
  architecture small and auditable.
- **Why freeze retrieval?** Experiments showed that changing retrieval alone did not
  reliably solve the answerability/content-sufficiency problem; the frozen setup is
  the verified production baseline.
- **Why disable reranking/HyDE/answerability?** They are implemented but did not meet
  production quality/latency guardrails, so they are off in V1.1.0 default.
- **Why preserve experiments?** They are retained for research and future validation,
  not deleted.
- **Why a durable ingestion ledger?** For deduplication, safe re-ingestion, removal,
  and truthful status/traceability.
- **Why failure-safe re-ingestion?** To avoid data loss or unsafe partial replacement
  if re-indexing fails mid-way.
- **Why source removal?** To let users revoke/refresh what PAM knows from their corpus.
- **Why system-facts short-circuit?** To answer "about the tool" questions fast and
  deterministically without retrieval or an LLM call.
- **Why citations?** Grounding and verifiability — every answer traces to a source.
- **Why maintain explicit limitations?** Academic honesty: claims are kept auditable
  and not overstated.

> Not established by current project documentation: any specific performance numbers
> beyond the historical retrieval/profiling values recorded in the evaluation docs,
> and any claim that remote CI is green.
