# PAM — One-Page Project Summary

**Personal AI Memory (PAM)** — `personal-ai-memory` v1.1.0. Local-first AI that turns your documents into a searchable, answerable knowledge base.

**Problem.** Knowledge scattered across PDFs, DOCX, Markdown, code, and web content is hard to search, connect, and ask questions over; generic chatbots can't access private material and must not be sent it.

**Solution.** Ingest → classify/route → extract → semantic-chunk → embed → index (vector store + knowledge graph) → hybrid retrieval → grounded local QA → cited answers, all on your own machine.

**What it does.**
- **Ingest** verified core formats (PDF, DOCX, TXT, Markdown, code/text; GitHub/YouTube opt-in); SHA-256 dedup; durable ledger; safe re-ingestion; `pam remove`.
- **Search:** hybrid dense cosine + BM25, fused by RRF (k=60).
- **Ask:** retrieval-grounded QA with `[SOURCE N]` citations and abstention when evidence is insufficient.
- **System facts:** "about the tool" questions answered deterministically, no LLM.
- **Local/private:** embeddings (`nomic-embed-text`) and QA (`qwen3:8b`) via local Ollama; secret-bearing files blocked; no cloud.

**Verification.**
- 1712 tests passed / 57 integration-deselected / 0 failed; Ruff pass; `mypy app/` 0 production/CI-visible errors.
- Historical retrieval eval: Hit@5 ≈ 0.924, MRR ≈ 0.877, FNR = 0.0, p95 ≈ 47 ms; FPR ≈ 0.857 (mostly content-sufficiency misses, not wrong answers).
- Remote GitHub CI not independently verified; no green-CI claim.

**Limitations.** Local single-user pipeline; retrieval frozen; not all formats are deep product support; experimental features (reranker, HyDE, answerability) disabled but retained.

**Future.** Validate/enable experiments, broaden verified ingestion, improve performance.

**Built vs. used.** Built: pipeline, chunking, dedup, ledger, retrieval orchestration, QA workflow, citations, system-facts, CLI, security guards, testing infra. Used (documented): Ollama, `qwen3:8b`, `nomic-embed-text`, optional Tesseract.

*Sources:* [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md), [`../architecture.md`](../architecture.md), [`../TESTING_AND_VERIFICATION.md`](../TESTING_AND_VERIFICATION.md), [`../KNOWN_LIMITATIONS.md`](../KNOWN_LIMITATIONS.md).
