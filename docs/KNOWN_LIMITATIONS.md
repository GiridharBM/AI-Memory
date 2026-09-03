# Known Limitations

Honest, source-verified limitations of **Personal AI Memory (PAM) V1.1.0**, with mitigations where they exist. This document exists so the project's limits are stated rather than hidden — something evaluators value.

For the canonical current state, see [`PROJECT_STATUS.md`](./PROJECT_STATUS.md); for future directions see [`DEVELOPMENT_ROADMAP.md`](./DEVELOPMENT_ROADMAP.md).

## 1. Ingestion support is not uniform

The **verified / core** ingestion set (proven end-to-end) is:

- PDF, DOCX, TXT, Markdown, generic text/code
- Network integrations (explicit, opt-in): GitHub, YouTube

**Not guaranteed end-to-end** even though ingestors/libraries may exist in the source tree:

- PPTX, XLSX, images / OCR, scanned PDFs, audio, video, arbitrary web content
- Cross-check: a library existing in `requirements.txt` or an ingestor existing in the registry is **not** proof of working product support.

**Mitigation:** unsupported or failing sources are routed to `failed/` and retried rather than crashing; `pam status` reports failed counts truthfully. When in doubt, test a source type before claiming support.

## 2. Local, single-machine, single-worker

- The pipeline is intentionally **single-machine** and **single-worker** (`workers: int = 1` in the queue config): serial, not parallel.
- Performance is bounded by local hardware and local Ollama. Historical p95 search latency ≈ 47 ms on the evaluation hardware; yours will vary.
- No horizontal scaling, no distributed indexing, no cloud offloading (by design — local-first).

## 3. Retrieval is frozen for V1.1.0

- Retrieval configuration (embed model, RRF fusion, `min_cosine 0.25`) is **frozen** for V1.1.0.
- Historical retrieval metrics: Hit@5 ≈ 0.924, MRR ≈ 0.877, FNR = 0.0, p95 ≈ 47 ms, **FPR ≈ 0.857**.
- The elevated FPR is **mostly content-sufficiency misses** — retrieved chunks were topically relevant but the answer was absent from the corpus — **not** "85.7% wrong answers". This measurement drove the decision to freeze retrieval rather than chase experimental gains.
- **Experimental / disabled (research only):** reranking (`reranker.enabled=false`), HyDE (`hyde.enabled=false`), answerability gating (`answerability.enabled=false`), banded verification. Their code/tests exist but are not production-gated. Do not present them as shipping features.

## 4. LLM behavior

- QA answers are grounded in retrieved chunks with `[SOURCE N]` citations and abstain when context is insufficient, but the underlying model is still a local LLM — it can be imperfect within its grounding.
- QA runs on local Ollama (e.g. `qwen3:8b`) with a bounded context (8192) and a default timeout of 120 s.
- "About the tool" questions are answered deterministically by system facts, not the LLM.

## 5. Vault / note model

- `pam remove <source>` de-indexes vectors, graph, and ledger entry but **never deletes** the corresponding vault note. This avoids data loss by design; to fully remove content you must also remove the note manually.
- Re-ingesting an already-indexed source atomically replaces prior chunks only after a full successful re-embed/re-index; on failure the previous data is preserved.

## 6. Operational notes

- Secret-bearing files are blocked from ingestion.
- A corrupted manifest is quarantined and rebuilt rather than crashing the process.
- One known **logging-isolation test flake** (`test_cli_remove.py::test_remove_one_source_and_unrelated_survives`) passes in isolation but fails in the full suite under certain ordering — a test-hygiene issue, not a product defect. It is not fixed as part of documentation work.

## 7. Backwards compatibility

- `metadata.extra` uses an additive `schema_version` for backwards compatibility; older persisted data may not reflect newer features and is not rewritten by V1.1.0.

## Future directions

See [`DEVELOPMENT_ROADMAP.md`](./DEVELOPMENT_ROADMAP.md) for what is deferred (e.g. broadened ingestion support, parallel processing, enabling/validating experimental retrieval features).
