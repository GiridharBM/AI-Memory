# PAM Project Status

> **Current version: PAM V2.0** (release candidate — tag `v2.0.0` pending).
>
> This is the current canonical status document. Historical phase and release
> reports in [`docs/phases/`](./phases/) and [`docs/releases/`](./releases/)
> record the state of the project **when each was written** — they predate or
> surround V1.1.0 and are preserved for provenance. Where they disagree with this
> document about the **current** state, this document reflects the current release.

---

## Current Release

| | |
|---|---|
| **Version** | **V2.0.0 (release candidate)** |
| Tag | `v2.0.0` (pending — a stale experimental `v2.0.0` tag from early history must be replaced) |
| Previous release | **V1.1.0** — tag `v1.1.0` → `e5d9129` (latest *published* release until V2.0 is tagged) |

> Note: `pyproject.toml` now carries `version = "2.0.0"`, aligned with the V2.0
> release designation. The installed package version surfaces in the GUI System
> page via `/system` (`pam_version`).

---

## Release State

- **V1.1.0 published** — tag `v1.1.0` → `e5d9129`, pushed to `origin/main`.
- **V2.0 release candidate** — generation system (P0/P1 scopes, V2-F mindmap,
  V2-H SDXL images) implemented and tested on `main`, awaiting release commit
  and `v2.0.0` tag (see `CHANGELOG.md` and `docs/releases/VERSION_2_0_0_FINAL_REPORT.md`).
- **Retrieval frozen** — the retrieval pipeline was intentionally frozen for V1.1.
  Retrieval-improvement experiments remain experimental / deferred and are not part
  of the V1.1 production path.
- **V1.1 focus** — reliability, source management, ingestion safety, CLI usability,
  truthful status, and local-first operation. Not a retrieval-quality step.

---

## Current Production Capabilities

Verified in the current implementation:

- Document ingestion via CLI (`pam ingest file <path>`, plus `pdf` / `markdown` / `txt`
  and network `github` / `youtube` subcommands).
- Source listing (`pam sources`, read-only, from durable state).
- Source removal (`pam remove <source>` — removes vectors, KG entries, and ledger
  entries; never deletes vault notes).
- Truthful status (`pam status`, read-only).
- Local hybrid retrieval (`pam search`) and grounded QA (`pam ask`).
- Citations / source reporting on answers.
- System-facts fast path (deterministic answers about the tool, no LLM / retrieval).
- Ingestion retry + deduplication (SHA-256) and safe re-ingestion.
- Secret-bearing source blocking (local `.env`/key/credential files blocked before
  processing).
- Bounded QA timeout.

---

## V2.0 Capabilities (Release Candidate)

Verified in the current implementation (full suite **2153 passed / 2
pre-existing skips**; SDXL validated on RTX 5060 Laptop GPU):

- Async generation jobs (`POST /generation`) with progress, cancellation, and
  DONE/FAILED/CANCELLED lifecycle; job/artifact/provenance APIs and GUI
  Library.
- Study-material generation: flashcards, multiple-choice quizzes, structured
  Markdown reports, PPTX presentations, AI-enriched mind maps.
- SDXL image generation (768×768 default; 512 fallback, 1024 opt-in; standard
  20-step and 4-step Turbo fast mode) with prompt planning over retrieved
  evidence. Measured: 100% @768², ≤5.82 GB reserved VRAM, ~8–22 s/image.
- Memory scopes: `all` / `documents` / `topics` / `nodes` restrict generation
  evidence; topics/nodes resolve through the knowledge graph; unknown scopes
  fail closed (P0/P1).
- Versioned artifacts (inline or traversal-safe file-backed) with per-chunk
  evidence-set provenance rendered in the GUI.
- Multimodal ingestion: images (OCR/vision/EXIF/diagrams), audio
  transcription, video ingestion.

Known V2 limitations (see also Current Limitations):

- SDXL requires a CUDA-enabled PyTorch build (cu128+ for Blackwell GPUs);
  CPU-only installs fail fast with a clear error. `diffusers`/`accelerate`/
  `Pillow` declared in `requirements.txt`; torch cu128 installed separately.
- Topic/node scopes resolve each KG node to its single persisted source
  (last-writer-wins); `projects` scopes fail closed (unsupported).
- SDXL in-image text is weak/unreliable; diagrams illustrate structure.
- `GenerationTask` `video` is declared but has no handler (rejected).

---

## Production Configuration

Verified current values (`config/default.yaml` + application defaults):

| Setting | Value | Meaning |
|---|---|---|
| `reranker.enabled` | `false` | CrossEncoder reranker off in default runtime (experimental) |
| `hyde.enabled` | `false` | HyDE query expansion off (experimental) |
| `answerability.enabled` | `false` | Answerability/evidence gate off (experimental) |
| `min_cosine` | `0.25` | Minimum top-match cosine threshold for QA abstention |
| `qa.timeout_seconds` | `120` | Bounded QA generation call timeout |
| QA model | `qwen3:8b` | Default local QA model |
| Embeddings | `nomic-embed-text` | Default embedding model |
| **Ollama context** | **8192** | Validated local setup uses `OLLAMA_CONTEXT_LENGTH = 8192` |

What these mean:

- The experimental features (reranker, HyDE, answerability) are **disabled** in the
  default runtime because the project did not establish that they met production
  quality/latency guardrails. Enabled via `config/default.yaml`.
- `min_cosine` is the QA abstention gate: if the top retrieved match falls below
  0.25 cosine, PAM abstains rather than guessing. This is a user-facing quality
  behavior; experimental threshold work (e.g. other candidate thresholds) belongs in
  evaluation documentation.
- The validated Ollama context is 8192 tokens.

---

## Current Architecture

High-level data flow (production path):

```
Sources (files, URLs)
   ↓
Ingestion (classify → route → extract / analyze)
   ↓
Chunking / Embeddings / Storage (vector store + knowledge graph + manifest)
   ↓
Retrieval (hybrid: semantic + keyword, fused)
   ↓
QA / Citations (grounded answer + system-facts fast path)
   ↓
CLI (pam)
```

- **System-facts fast path** answers "about the tool" questions (version, source count,
  chunk count, feature flags, QA model, capabilities, status) deterministically from
  application state — no retrieval or LLM.
- The reranker/HyDE/answerability modules exist but are **not** in the active pipeline
  (disabled; see Production Configuration).

---

## Current Limitations

### User-facing limitations

1. **Retrieval content sufficiency** — retrieval can return topically relevant chunks
   that lack the exact fact required to answer a query.
2. **Retrieval quality** — the frozen V1 baseline does not satisfy every desired
   experimental quality guardrail (a known limitation, not a catastrophic failure).
3. **Local LLM latency** — local `qwen3:8b` generation can take seconds or longer
   depending on query complexity and hardware.
4. **Context configuration** — validated setup uses an 8192-token Ollama context.
5. **Supported formats/environment** — a focused set of fully-supported formats; some
   formats are partial or broken; validated on Linux (CI) and Windows (local dev),
   macOS not independently CI-validated.
6. **Storage atomicity** — vector-store and knowledge-graph persistence are not fully
   transactional across both stores.
7. **Knowledge-graph removal caveat** — shared KG nodes/relationships can require more
   careful semantics than a simple per-source deletion.

### Engineering limitations

- **Threshold reconciliation** — historical/experimental retrieval threshold work (e.g.
  alternative `min_cosine` candidates around 0.45) was not reconciled into the frozen
  production value (0.25). Documented in evaluation/provenance records.
- **Former test flake (FIXED)** — a logging-isolation flake (`test_cli_remove.py`) that
  surfaced under specific full-suite test ordering was fixed (`ea8a95b`); it was a
  test-hygiene issue, not a production defect.
- **Evaluation tooling aligned to v3.0** — `test_eval_dataset.py` and the eval tooling
  (`eval/scripts/run_eval.py`, `eval/scripts/ground_truth_audit.py`) have been reconciled
  to the current v3.0 dataset contract (contract tests pass).
- **Packaging version** — `pyproject.toml` version is `2.0.0`, aligned with the V2.0
  release designation (see Current Release).

Engineering debt is kept distinct from user-facing product defects.

---

## Experimental / Deferred Work

- **CrossEncoder reranker** — implemented, disabled. Would re-rank retrieved chunks.
- **HyDE** — implemented, disabled. Would expand the query before retrieval.
- **Answerability / evidence verification** — implemented, disabled. Would gate answers
  on post-retrieval evidence sufficiency.
- **Retrieval improvements** — experimental evaluation work remains deferred.

These are not broken or removed; they are off in the V1.1 default runtime because the
project did not establish that they met production quality/latency guardrails.

---

## Evaluation Snapshot

The following are **historical / frozen evaluation measurements**, reproduced from the
project's evaluation records. They are **not** the result of a new benchmark run.

- The frozen retrieval evaluation measured a **false-positive rate ≈ 0.857**.
- Important context: many measured false positives were **content-sufficiency misses** —
  retrieved text could be on-topic but lack the exact fact required to answer a query.
- This is one reason evidence verification and retrieval improvements remain deferred.

Detailed metrics, datasets, and experiment history live in [`../eval/`](../eval/) and the
phase records in `docs/phases/` (e.g. 5D freeze, 5F, 5G). Do not interpret these
measurements as a claim about a new run.

---

## Testing Snapshot

Latest known verification snapshot (dated):

- **2153 passed / 2 pre-existing skips / 57 deselected** (full `pytest tests/` run)
- The **57 deselected** are `integration`-marked and excluded from the default run.
- The **2 skips** are platform-specific (Windows forbids URL-shaped directory names).
- **Ruff passes**; **mypy reports only pre-existing `reranker.py` stub errors**.
- **Frontend `tsc` + `oxlint` + production build pass.**
- **SDXL GPU validation** — 55 measured runs + SHA-matched determinism smoke on
  RTX 5060 Laptop GPU (8 GB); evidence lives outside the repo.
- **Evaluation contract tests pass** — `test_eval_dataset.py` (v3.0 contract) = **32 passed**
- The former CLI remove logging-isolation flake was **fixed** (`ea8a95b`).

Remote GitHub CI was not independently verified from this environment; local
CI-equivalent checks pass.

---

## Known Technical Debt

Verified open items:

1. Vector-store / KG persistence not fully transactional across both stores.
2. KG shared-node removal semantics.
3. Retrieval threshold reconciliation (0.25 production vs experimental alternatives).
4. Topic/node scopes resolve each KG node to its single persisted source
   (last-writer-wins); multi-source history would need a KG identity redesign.
5. `projects` scopes fail closed (grouping undecided).
6. SDXL requires CUDA torch (CPU-only installs fail fast); in-image text is weak.
7. `video` generation task declared but unimplemented (rejected at submit).

---

## Next Logical Work

Conservative categories (no committed V1.2 feature roadmap unless separately
established):

- **Documentation maintenance** — keep status/testing notes current.
- **Reliability improvements** — continue work on persistence-atomicity items.
- **Measured retrieval research** — continue retrieval/evaluation work as experiment
  (frozen in V1.1 production).
- **Faster evidence verification** — progress on answerability/evidence as an
  experimental feature.
- **Persistence consistency** — improve vector-store/KG transactional behavior.