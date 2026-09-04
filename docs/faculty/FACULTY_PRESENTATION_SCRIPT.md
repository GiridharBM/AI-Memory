# PAM — Faculty Presentation Script (5–10 min)

> Companion to [`../FACULTY_PRESENTATION_GUIDE.md`](../FACULTY_PRESENTATION_GUIDE.md).
> Concrete 12-slide flow with everything a presenter should say. Total ~5–10 minutes.
> Use the Mermaid diagrams in [`../architecture.md`](../architecture.md) for Slide 5.

---

## Slide 1 — Title + one-sentence definition

**Title:** Personal AI Memory (PAM) — private, local retrieval-grounded question answering over your own documents. **V1.1.0.**

**Bullets**
- PAM ingests your files into a connected Obsidian knowledge base.
- Hybrid search plus question answering with citations.
- Fully local/offline — your data never leaves your machine.

**Say:** "PAM is a local-first AI system that turns your documents into a searchable, answerable knowledge base — entirely on your own machine, against a local model."

**Likely question:** "Is this just a wrapper around ChatGPT?" → **No — it's local-only, uses your own corpus, and grounds every answer in your notes with citations.**

---

## Slide 2 — Problem statement

**Bullets**
- Knowledge is scattered across many formats and folders.
- Keyword search fails on prose and images.
- Generic chatbots can't access your private material.

**Say:** "People accumulate knowledge in dozens of formats with no good way to find, connect, or recall it. General chatbots don't have your corpus."

**Likely question:** "Why not just put everything in one folder and use grep?" → "Grep can't match meaning, and it can't answer questions; PAM does semantic retrieval and grounded QA."

---

## Slide 3 — Motivation / why generic chatbots are insufficient

**Bullets**
- Chatbots answer from pretrained knowledge — not your documents.
- You can't trust private data to a cloud chat.
- Need find + connect + recall, offline and privately.

**Say:** "A normal chatbot has no memory of your work and would require sending it to a server. PAM answers from your own, private corpus."

**Likely question:** "What problem does abstraction (abstention) solve here?" → "It prevents the model from making up answers when your notes don't contain the needed fact."

---

## Slide 4 — Proposed solution

**Bullets**
- Ingestion pipeline → semantic chunks → embeddings.
- Hybrid retrieval (dense + BM25 + RRF).
- Grounded QA with citations + abstention.

**Say:** "PAM turns sources into an indexed knowledge base, retrieves the most relevant chunks, and answers grounded in them — while staying fully local."

**Likely question:** "What does retrieval-grounded mean?" → "The answer is built only from retrieved chunks of your own notes, with citations, not from the model's general knowledge."

---

## Slide 5 — Architecture diagram

**Bullets** (pipeline top-to-bottom)
- Ingestion → Routing → Extraction → Chunking → Embedding.
- Vector store + knowledge graph.
- Hybrid retrieval → abstention → local QA → citations → CLI.

*(Draw/display the Mermaid pipeline from architecture.md.)*

**Say:** "Here is the actual V1.1.0 architecture — a one-way pipeline from document to answer, with a durable source lifecycle underneath."

**Likely question:** "Why a one-way / clean architecture?" → "Strict one-way dependencies keep the system auditable and testable, which faculty can verify in the architecture document."

---

## Slide 6 — Document ingestion pipeline

**Bullets**
- Registry of type-specific ingestors → classifier/router.
- Enrichment: metadata, OCR, tables, images, entities, knowledge graph.
- Semantic chunking (sentence + heading hierarchy).
- SHA-256 dedup + durable manifest/ledger.
- Verified core: PDF, DOCX, TXT, Markdown, code/text (+ GitHub/YouTube opt-in).

**Say:** "Each source is detected, routed, normalized, enriched, chunked, and hashed so we never re-process the same file."

**Likely question:** "Do you support every format?" → "Verified end-to-end for PDF/DOCX/TXT/Markdown/code; PPTX, XLSX, scanned PDFs, images, audio, video are not uniformly guaranteed. The project distinguishes 'library can parse' from 'product support.'"

---

## Slide 7 — Retrieval + QA + citation pipeline

**Bullets**
- Dense cosine + BM25, fused by RRF (k=60).
- `min_cosine` 0.25; filters (top-k, source, score, metadata).
- Grounded local LLM (`qwen3:8b`), bounded context, 120 s timeout.
- `[SOURCE N]` citations + abstention when context is insufficient.

**Say:** "We retrieve the most relevant chunks, ground the local model's answer in them, and attach citations so every claim is traceable."

**Likely question:** "How is hallucination reduced?" → "By grounding in retrieved notes, requiring citations, and abstaining when evidence is insufficient instead of fabricating."

---

## Slide 8 — Source management + reliability

**Bullets**
- `pam sources` / `pam remove` (never deletes vault notes).
- SHA-256 dedup; durable ledger.
- Failure-safe re-ingestion (no partial replacement on failure).
- Truthful `pam status`; corrupted-manifest quarantine.

**Say:** "PAM tracks every source in a durable ledger, so you can list, refresh, or remove sources safely — and the tool reports its state truthfully."

**Likely question:** "What happens if re-ingestion fails halfway?" → "Prior chunks are preserved; old data is removed only after a full successful re-embed/re-index."

---

## Slide 9 — Security / privacy / local-first design

**Bullets**
- Local Ollama; no cloud calls.
- Secret-bearing files blocked from ingestion.
- Failure containment + corruption quarantine.
- Offline-capable.

**Say:** "Everything runs locally, and the system deliberately blocks secret-bearing files and contains failures."

**Likely question:** "How do you know no data leaves the machine?" → "All embedding and QA calls go to a local Ollama server; the design is local-first by construction."

---

## Slide 10 — Evaluation + testing

**Bullets**
- 1712 passed / 57 integration-deselected / 0 failed; Ruff pass; mypy 0 (CI-visible).
- Historical retrieval: Hit@5 ≈ 0.924, MRR ≈ 0.877, FNR = 0.0, p95 ≈ 47 ms.
- FPR ≈ 0.857 — mostly content-sufficiency misses (see note).
- 32 evaluation-contract tests.

**Say:** "The suite is clean at 1712/0, and historical retrieval evaluation is recorded honestly — including its limitations."

**Likely question:** "Why is FPR about 85%?" → "FPR ≈ 0.857; most false positives were content-sufficiency misses — chunks on-topic but lacking the exact required fact — not 'wrong answers.' This drove the retrieval freeze."

---

## Slide 11 — Limitations

**Bullets**
- Local single-user architecture; retrieval frozen.
- Not all formats are deep product support.
- Experimental features disabled.
- Remote GitHub CI not independently verified.

**Say:** "We're candid about limits: retrieval is frozen, some formats aren't guaranteed end-to-end, and experiments are retained but disabled."

**Likely question:** "Why freeze retrieval?" → "Experiments showed changing retrieval alone didn't reliably fix the answerability/content-sufficiency problem, so we locked a verified baseline."

---

## Slide 12 — Future work

**Bullets**
- Validate/enable experimental retrieval features (reranker, HyDE, answerability).
- Broaden verified ingestion support.
- Parallel processing / performance.

**Say:** "Future work is about proving the experimental features to production quality and broadening format coverage."

**Likely question:** "Is any of this shipped?" → "V1.1.0 is the current release; the experimental features are implemented but deliberately disabled — this is intentional and documented."

---

## Timing (5–10 min)

- Slides 1–4: ~2–3 min (define, motivate, propose).
- Slides 5–7: ~3 min (architecture, ingestion, retrieval/QA).
- Slides 8–10: ~2–3 min (reliability, security, evaluation).
- Slides 11–12: ~1–2 min (limits, future).
