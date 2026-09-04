# Faculty Presentation Guide

How to explain **Personal AI Memory (PAM)** to faculty, in 30 seconds, 2 minutes, or 5 minutes, plus the questions faculty typically ask and how to answer them honestly.

> For deep, accurate details behind every claim, see [`PROJECT_STATUS.md`](./PROJECT_STATUS.md), [`architecture.md`](./architecture.md), and [`KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md).

## The one-sentence pitch

> "PAM is a local-first, offline AI that turns documents, code, audio, images, and web content into a connected Obsidian knowledge base with hybrid search and retrieval-grounded question answering — and it runs entirely on your own machine against a local model."

## 30 seconds (elevator)

- **What:** Personal AI Memory — a local-first tool that ingests your documents and lets you search and ask questions over them.
- **How:** it ingests files, semantically chunks them, embeds them with a local model, and uses hybrid search (dense + BM25 fused with RRF) so `pam ask` answers with citations grounded in your actual notes.
- **Local-first:** no cloud; QA runs against local Ollama (e.g. `qwen3:8b`), embeddings with `nomic-embed-text`.
- **Current:** released **V1.1.0** — added source management, ingestion safety, and truthful status on top of the frozen V1.0.0 core.

## 2 minutes

1. **Problem:** knowledge scattered in files, PDFs, code, and web content is hard to search, connect, and ask questions over.
2. **PAM's answer:** an ingestion pipeline (registry of type-specific ingestors → classifier/router → enrichment: metadata, OCR, tables, images, entities, knowledge graph → semantic chunking → embedding) that turns sources into an indexed knowledge base and an Obsidian vault.
3. **Retrieval:** hybrid — dense cosine + BM25, fused with RRF (k=60), with filters (top-k, source-type, min-score, metadata).
4. **QA:** `pam ask` grounds the local LLM's answer in retrieved chunks, gives `[SOURCE N]` citations, and abstains when context is insufficient. It also answers "about the tool" questions deterministically via system facts.
5. **V1.1.0 focus:** source management (`pam sources`/`pam remove`), ingestion UX & safety, truthful `pam status`, and QA hardening — while deliberately freezing retrieval.
6. **Engineering rigor:** 1712 tests pass / 57 deselected / 0 failed, 32 evaluation-contract tests, clean Ruff and mypy, and full verification records in [`TESTING_AND_VERIFICATION.md`](./TESTING_AND_VERIFICATION.md).

## 5 minutes (full walkthrough)

Add to the 2-minute version:

- **Architecture tour** — draw the pipeline (ingest → chunk → embed → index → hybrid search → LLM → vault) using the Mermaid diagrams in [`architecture.md`](./architecture.md).
- **Live demo** — `pam status`, `pam sources`, `pam search "topic"`, `pam ask "what does this cover?"`, showing citations.
- **Design decisions & rationale** — hybrid retrieval with RRF; single-worker local pipeline; additive `metadata.extra` schema for backwards compat; failure containment (structured errors, `failed/` folder, corrupted-manifest quarantine); secret-bearing-file blocking.
- **Honest limits** (impress faculty with candor) — see [`KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md): e.g. not every claimed ingestor is deep product support (PPTX/XLSX/images/audio/video are not guaranteed end-to-end); retrieval is frozen; experimental features (reranking, HyDE, answerability, banded verification) are disabled.
- **Evaluation** — Hit@5 ≈ 0.924, MRR ≈ 0.877, FNR = 0.0, p95 ≈ 47 ms historically; an elevated FPR (~0.857, mostly content-sufficiency misses, not "wrong answers") drove the retrieval freeze.
- **Future work** — see [`DEVELOPMENT_ROADMAP.md`](./DEVELOPMENT_ROADMAP.md).

## Anticipated faculty questions (and honest answers)

**Q: Is this cloud-based / does it send data anywhere?**
A: No. PAM is local-first — everything (embeddings and QA) runs against local Ollama. No cloud calls.

**Q: How is retrieval different from a keyword search?**
A: It's hybrid: dense semantic similarity (cosine on local embeddings) fused with BM25 lexical matching via RRF, so it finds conceptually-related content, not just exact keywords, with filters for source type, score, and metadata.

**Q: Does the LLM ever make things up?**
A: Answers are grounded in retrieved chunks and carry `[SOURCE N]` citations; the system abstains when context is insufficient instead of fabricating. System-fact questions are answered deterministically without the LLM.

**Q: What are the limitations?**
A: Local single-machine/single-worker pipeline; retrieval is deliberately frozen for V1.1.0; not every ingestor (PPTX/XLSX/images/audio/video) is proven end-to-end product support; experimental enhancements are disabled. Full list in [`KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md).

**Q: How was it verified?**
A: 1712 tests pass / 57 deselected / 0 failed, plus 32 evaluation-contract tests, integration tests, and a documented verification record — see [`TESTING_AND_VERIFICATION.md`](./TESTING_AND_VERIFICATION.md). Ruff passes and `mypy app/` reports 0 production errors. A former logging-isolation test flake was fixed; a separate MIME random-input test has shown occasional environment nondeterminism but passed the final run. (Remote GitHub CI was not independently verified from this environment; local checks pass.)

**Q: What did *you* actually build vs. use a library for?**
A: The pipeline, chunker, vector store, BM25 index, hybrid retrieval, RAG workflow, source management, and system facts are custom code; OCR/tables/metadata use well-scoped extractor/processor registries; the LLM and embeddings come from local Ollama. See [`IMPLEMENTATION_GUIDE.md`](./IMPLEMENTATION_GUIDE.md).
