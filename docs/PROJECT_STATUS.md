# PAM Project Status

> **Current version: PAM V1.1.0** (published release).
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
| **Version** | **V1.1.0** |
| Tag | `v1.1.0` |
| Release commit | `e5d9129` |

The commit after the release (`7aac60b`) is a documentation-organization change and
does **not** change the V1.1.0 release tag. Subsequent commits are documentation /
maintenance work; the V1.1.0 tag remains the published release reference.

> Note: the packaged `pyproject.toml` still carries `version = "1.0.0"`. V1.1.0 is
> the release/tag designation for this project and is tracked by the Git tag, not a
> `pyproject.toml` bump. This is a known packaging detail and does not change the
> published-release designation below.

---

## Release State

- **V1.1.0 published** — tag `v1.1.0` → `e5d9129`, pushed to `origin/main`.
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
- **Known test flake** — a logging-isolation flake (`test_cli_remove.py`) surfaces under
  specific full-suite test ordering; it is a test-hygiene issue, not a production defect.
- **Stale evaluation assertions** — `test_eval_dataset.py` asserts the older v2.0
  dataset contract while the working-tree dataset is v3.0; these are known stale
  evaluation assertions, not product defects.
- **Packaging version** — `pyproject.toml` version is `1.0.0`; V1.1.0 is tracked by the
  Git tag (see Current Release).

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

- **~1703 passed**
- **57 deselected** (integration-marker tests excluded from the default run)
- **8 failed**, consisting of:
  - **7 known stale evaluation assertions** (`test_eval_dataset.py` v2.0-vs-v3.0 contract)
  - **1 known logging-isolation flake** (`test_cli_remove.py`, test-hygiene)

These 8 are not eight product defects. The detailed verification state is maintained in
the testing/release documentation (`docs/TESTING_AND_VERIFICATION.md`, release
provenance records in `docs/releases/`). Do not assume "all tests pass"; verify against
the current release records.

---

## Known Technical Debt

Verified open items:

1. `test_eval_dataset.py` stale v2.0-vs-v3.0 assertions (7).
2. Logging-isolation test flake (`test_cli_remove.py`) under specific suite ordering.
3. Retrieval threshold reconciliation (0.25 production vs experimental alternatives).
4. Vector-store / KG persistence not fully transactional across both stores.
5. KG shared-node removal semantics.
6. `pyproject.toml` version (`1.0.0`) not aligned with the V1.1.0 release label.

---

## Next Logical Work

Conservative categories (no committed V1.2 feature roadmap unless separately
established):

- **Documentation maintenance** — keep status/testing notes current.
- **Reliability improvements** — address the known logging-isolation flake and
  persistence-atomicity items.
- **Measured retrieval research** — continue retrieval/evaluation work as experiment
  (frozen in V1.1 production).
- **Faster evidence verification** — progress on answerability/evidence as an
  experimental feature.
- **Persistence consistency** — improve vector-store/KG transactional behavior.