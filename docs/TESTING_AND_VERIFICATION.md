# Testing and Verification

Verification evidence for LLM-Wiki / Personal AI Memory (PAM). The Phase-6 completion evidence is `PHASE_6_FINAL_APPROVAL.md`; per-phase verification records are preserved in `docs/archive/`. **Current V1.1.0 state:** `PROJECT_STATUS.md`.

## Current V1.1.0 testing state

The current verified snapshot for the **default unit suite** (`pytest tests/unit`, which excludes `integration`-marked tests) is:

| Suite | Result |
|-------|--------|
| **Unit tests (default)** | **1688 passed / 1 deselected / 1 failed** |
| **Failed** | `test_cli_remove.py::test_remove_one_source_and_unrelated_survives` — a known **logging-isolation flake**; it **passes in isolation** and is a test-hygiene/ordering issue, not a product defect. **Do not fix as part of docs work.** |
| **Deselected** | 1 `integration`-marked test excluded from the default run |
| **Evaluation dataset-contract tests** | `tests/unit/test_eval_dataset.py` = **32 passed** (reconciled to the v3.0 dataset contract) |
| **Evaluation tooling** | `eval/scripts/run_eval.py` and `eval/scripts/ground_truth_audit.py` derive source-keys/categories from dataset metadata and are compatible with the current v3.0 dataset |

**Test categories:**
- **Unit** (`tests/unit/`, ~71 files) — includes CLI (`test_cli*.py`), pipeline, QA, ingestion, source-management, system-facts, and evaluation-contract tests.
- **Integration** (`tests/integration/`, 18 files) — `integration`-marked, excluded from the default run; hit live/external services and are run explicitly when required.
- **Evaluation** — `tests/unit/test_eval_dataset.py` (v3.0 contract, 32 passed); eval scripts under `eval/scripts/`.
- **Historical/stale** — older evaluation assertions were reconciled; historical numbers are recorded below in the "Final V1.0.0 gate" and "Final state" sections.
- **Experimental** — testing for disabled research features (e.g. `test_answerability_gate.py`, `test_banded_verifier.py`, `test_qa_measurement.py`) is treated as research/experimental, not production-gating.

> The full historical V1.0 verification records are preserved below for provenance.

---

## Final V1.0.0 gate (2026-08-11, re-run at finalization)

| Suite | Result |
|-------|--------|
| **Unit tests** | **1375 passed / 57 deselected / 0 failed** |
| **Test files** | 56 unit + 16 integration (collected) |
| **Coverage** | **89.80%** (7176 statements, 732 missed) — floor is 80% |
| **Ruff** | No new findings in V1.0.0-changed files; repo-wide `ruff check .` has 59 **pre-existing** findings (test line-lengths/unused imports + B904 in optional-dep ingestors) |
| **Mypy** | No new findings; 5 **pre-existing** environment/stub errors (fitz, docx, pptx, faster-whisper, numpy on Python 3.11 target) |
| **`git diff --check`** | Clean (only LF→CRLF line-ending warnings) |
| **Live `pam status`** | ✅ Configuration loaded, Inbox ready, Ollama **Connected** (qwen3:8b), Vault connected |
| **Live `pam search`** | ✅ Returns ranked hybrid results against the real vector store |
| **Live `pam ask`** | ✅ Returns grounded answer with Sources table (top-k retrieval → Ollama → `[SOURCE N]`) |

This document's table below is the historical Phase-6 gate record.

## Final state (v0.12.0, Phase 6 approval)

| Suite | Result |
|-------|--------|
| **Unit tests** | **1359 passed / 57 deselected / 0 failed** |
| **Test files** | 55 unit + 17 integration |
| **Coverage** | 90.04% (7269 statements, 724 missed) — floor is 80% *(measured at the Phase 6 gate; not re-measured after cleanup commit `2433f70`)* |
| **Integration tests** | **85 passed / 1 skipped / 1 env-fail** (the env-fail is the live-Ollama smoke test, which requires a running Ollama server) |
| **End-to-end (E2E)** | **25 / 25 PASS** |
| **Perf — ingest** | 20,000 tokens × 384 dims embed + store ≈ **271 ms** |
| **Perf — search** | ≈ **190.2 ms** average over the sample set |
| **Ruff (lint)** | 59 pre-existing warnings; **0 new** introduced |
| **Mypy (types)** | Clean within scope (numpy-stub / Python 3.14 notes only) |
| **`pip check`** | Clean — no dependency conflicts |

**Verdict: APPROVED / PROJECT COMPLETE.**

## How to reproduce

```bash
# unit + integration
pytest

# coverage (90% floor)
pytest --cov=app --cov-fail-under=80

# lint / types
ruff check .
mypy app
pip check
```

> Note: the live-Ollama integration smoke test requires a running local Ollama server; without it, that single test reports env-fail (not a code failure).

## Acceptance gates (Phase 6)

1. All planned Phase 6 changes landed and were committed atomically.
2. Final verification pass run and recorded (numbers above).
3. Negative checklist (deferred/partial items) reviewed — no silent degradation.
4. Leftovers/exceptions explicitly captured, not hidden.
5. Approval granted on completion criteria — **APPROVED**.

## Negative checklist (known non-goals, deliberately deferred)

- FAISS/ANN index — vector search is in-memory O(n); acceptable for personal-scale vaults.
- External vector DB, REST API, web UI, auth, multi-user, Docker, monitoring — future vision, out of scope.
- RAG/context retrieval, cross-encoder re-ranking, query rewriting, parent-child retrieval — deferred at Phase 5.
- MEDD evaluation tooling (retrieval/chunking/LLM quality metrics, hallucination detection) — backlogged at Phase 6.
- Layout preservation in OCR, tree-sitter/ML code parsing, notebook cell execution — excluded from Phase 2 scope.

## Verification history by version

| Version | Notes |
|---------|-------|
| v0.1.0 | 421 tests, 86.07% coverage (Phase 1 gate) |
| v0.2.0 | 506 tests, 87.02% |
| v0.3.0 | 605 tests, 86.80% |
| v0.4.0 | 747 tests, 88.43% |
| v0.5.0 | 778 tests, 88.29% |
| v0.6.0 | 825 tests, 88.00% |
| v0.7.0 | 947 tests, 88.88% |
| v0.8.0 | 1059 tests, 89.03% |
| v0.9.0 | 1125 tests (coverage recorded in milestone notes) |
| v0.10.0 | 1273 tests |
| v0.11.0 | 1384 tests, 90.00% |
| v0.12.0 | **1398 tests, 90.04% — final (Phase 6 gate)** |

The current suite after cleanup commit `2433f70` is **1359 passed / 57 deselected** (55 unit + 17 integration files); the Phase 6 gate figure above is the historical approval record.

Per-milestone test/count changes are recorded in the original milestone reports (`docs/archive/`).
