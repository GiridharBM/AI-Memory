# Testing and Verification

Verification evidence for LLM-Wiki / Personal AI Memory (PAM). The authoritative completion evidence is `PHASE_6_FINAL_APPROVAL.md`; per-phase verification records are preserved in `docs/archive/`.

## Final state (v0.12.0, Phase 6 approval)

| Suite | Result |
|-------|--------|
| **Unit tests** | **1398 passed / 59 deselected / 0 failed** |
| **Coverage** | **90.04%** (7269 statements, 724 missed) — floor is 80% |
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
| v0.12.0 | **1398 tests, 90.04% — final** |

Per-milestone test/count changes are recorded in the original milestone reports (`docs/archive/`).
