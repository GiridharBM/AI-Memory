# Milestone 3.1 — P3-105 Engineering Review

**Task:** P3-105 — Config + plumbing
**Review date:** 2026-08-06
**Contract:** `docs/PHASE_3_MILESTONE_3_1_IMPLEMENTATION_ROADMAP.md` (P3-105 block, lines 133-148)
**Verdict:** **APPROVED**

---

## 0. Review Method

Independent review — the implementation report was **not** trusted. Every claim was
re-derived from the frozen spec, the live source, and re-run gates:

- Spec re-read from the roadmap block; code re-read from `config.py`, `ingest_workflow.py`,
  `config/default.yaml`, `sentence_tokenizer.py`, and both test files.
- Full test suite re-run; integration-marked suite re-run; ruff and mypy re-run from scratch.
- A reviewer-authored probe script exercised runtime behavior end-to-end.
- Rollback verified by surgically reverting the three P3-105 source changes and running the
  **entire** suite under the revert.

---

## 1. Specification Compliance (frozen block)

| Frozen requirement | Verification | Result |
|--------------------|--------------|--------|
| `ChunkingSettings(sentence_tokenizer: Literal["auto", "nltk", "heuristic"] = "auto")` | Source read: `config.py:364-375` — exact type/default, `extra="forbid"` | ✅ exact |
| `chunking:` block in `config/default.yaml` | Source read + `load_settings()` round-trip probe | ✅ present, parses |
| Plumbed through the production chain at `ingest_workflow.py:247` | Source read: `chunker=SemanticChunker(sentence_tokenizer=settings.chunking.sentence_tokenizer)` at lines 247-249, passed via `from_runtime` | ✅ exact site |
| Both entry points reach the same construction path (L2) | `grep` over `app/`: production construction sites are exactly `app/cli/entry.py:372` and `app/queue/worker.py:84`, both `IngestionWorkflow.create_default(settings)`; watch service runs through the worker | ✅ single site |
| Commit coupling (O-1) — `extra="forbid"` | `Settings` is `extra="forbid"`; model + field + yaml key + plumbing land together in this change (no half-state is constructible) | ✅ |
| Public interface `settings.chunking.sentence_tokenizer` | Probes: `load_settings().chunking.sentence_tokenizer` resolves | ✅ |
| `pam doctor` reporting (optional, may defer) | Not implemented — roadmap explicitly marks optional | ✅ deferred per spec |
| Tests: `test_config.py` defaults/env/invalid; wiring test | Present: 3 config tests + 1 wiring test (roadmap allows `test_knowledge_engine.py` **or** a wiring test) | ✅ |

## 2. Acceptance Criteria

| Criterion | Independent verification | Result |
|-----------|-------------------------|--------|
| Config value drives engine selection end-to-end | Probe: `PAM_CHUNKING__SENTENCE_TOKENIZER=heuristic` → `create_default` chunker resolves `_HeuristicSentenceTokenizer`; `=nltk` → `_NltkSentenceTokenizer` | ✅ |
| Default `"auto"` reproduces post-P3-104 behavior | Probe: default → `_NltkSentenceTokenizer` (nltk present) — identical to pre-P3-105 `SemanticChunker()`; nltk-blocked subprocess → `_HeuristicSentenceTokenizer` + one D4 warning, no crash | ✅ |
| `"heuristic"` = deterministic stdlib path (rollback position) | Probe: `heuristic` → `_HeuristicSentenceTokenizer`; determinism probe below | ✅ |

## 3. Definition of Done

| DoD | Independent verification | Result |
|-----|-------------------------|--------|
| Config test + wiring test green for **both entry points** | Wiring test exercises `create_default` (the exact construction both `entry.py:372` and `worker.py:84` call). Entry-point suites `test_cli.py` / `test_queue_worker.py` pass unchanged. L2 single-site verified by grep | ✅ |
| No dead config (every value consumed — L5) | Repo-wide grep: the only `chunking`/`sentence_tokenizer` config surface is defined (`config.py:375`), exposed (`config.py:411`), consumed (`ingest_workflow.py:248`); all three legal values map to engines registered in `sentence_tokenizer.py` | ✅ |

## 4. Independent Verification Results

### 4.1 Runtime behavior — reviewer probe (`ALL PROBES PASSED`, 13 checks)
Defaults + model equality, yaml round-trip, env override → `heuristic` propagates through
`create_default` to a `_HeuristicSentenceTokenizer`, env override → `nltk`, invalid env value
→ `ConfigurationError` (fail-fast at the config boundary), default `auto` → nltk, bare
`SemanticChunker()` backward-compatible, `Settings(...)` without a `chunking` key constructs
via `default_factory`, heuristic chunking identical across instances.

### 4.2 Rollback behavior — full-suite proof
Surgical revert of the three P3-105 source changes (P3-104 left intact) → **entire** suite:
`4 failed, 1001 passed, 31 deselected`. The only failures are exactly the 4 new P3-105 tests;
the 1001/31 result is byte-identical to the pre-P3-105 baseline. Rollback is clean and the new
tests gate exactly P3-105 behavior.

### 4.3 Deterministic behavior
Heuristic chunker produces identical `(text, start_char, end_char)` sequences across
instances (probe). Config resolution deterministic (`load_settings` twice → identical).
Selection fixed per constructed chunker (P3-104 D8, unchanged).

### 4.4 Backward compatibility
- `SemanticChunker()` / `SemanticChunker(max_chunk_chars=…)` bare construction still valid (new field has a default) — probe + unchanged P3-104 tests.
- `Settings` gains one additive field with `default_factory`; the `tmp_settings` fixture (direct `Settings(...)` with no `chunking` key) is used across the whole suite and passes.
- `ConfigDict(extra="forbid")` coupling: an external config dict that never mentions `chunking` still validates (probe).
- All 17 pre-existing tests in the two changed test files pass unchanged.

### 4.5 Ruff
Full-repo `ruff check .`: 61 findings, **zero on any P3-105-touched file** (`config.py`,
`ingest_workflow.py`, `default.yaml`, `sentence_tokenizer.py`, `test_config.py`,
`test_knowledge_engine_persistence.py`). The `semantic_chunking.py:147` B007 and
`test_knowledge_engine.py` E501/F841 findings match the documented pre-P3-105 baseline.
**No new findings.**

### 4.6 Mypy
`mypy app/core/config.py app/infrastructure/semantic_chunking.py app/infrastructure/sentence_tokenizer.py`
→ **Success: no issues.** `ingest_workflow.py` reports only pre-existing findings (11
`object`-typed-injection errors at lines 130/343/360/612/751/759/774/776/780/792 — none near
the changed lines — plus environmental `faster_whisper`/`numpy` stub failures). **No new findings.**

### 4.7 Unit tests
Full default suite: **1005 passed / 31 deselected** (1001 baseline + 4 new). `test_config.py`
18/18; `test_knowledge_engine.py` incl. all 15 `TestSemanticChunking` cases unchanged.

### 4.8 Integration tests
`-m integration`: **29 passed / 1 skipped** (Tesseract not installed) / **1 failed** —
`smoke_test::test_live_ollama_analysis_and_note_generation`. This test calls a live
`llama3.1:8b` model directly and asserts the generated note contains 21 sections; the failure
is missing optional sections in the **model's** output. Two consecutive runs produced
*different* missing-section sets, confirming live-model nondeterminism. The test never imports
or builds any P3-105-touched code path (no `IngestionWorkflow`, no `SemanticChunker`, no
`load_settings`; its only config import is the unchanged `OllamaSettings`). It is the same
pre-existing live-Ollama flake documented in the P3-104 review (O-3), **not** a P3-105
regression. Note: the default (non-`-m`) run keeps this test deselected.

### 4.9 Documentation
- Implementation report: every verified gate number matches re-run results (1005/31, rollback
  4-fail, ruff zero-new, mypy clean on changed modules, AC probes, file list, pre-existing
  ingest_workflow mypy inventory).
- Roadmap P3-105 closure annotation: numbers and claims consistent with independent runs.
- `sentence_tokenizer.py` docstring now correctly describes the P3-104/P3-105 wiring (was
  stale "not wired into ingestion").
- `ChunkingSettings` docstring accurately states the three modes and D4/D8 semantics.

---

## 5. Findings

### Blocking
None.

### Recommended
None.

### Optional
- **O-1 (test gap, not a defect):** invalid `sentence_tokenizer` values are tested at the
  model and yaml layers but not via the env-override path. The mechanism is shared (manual
  override → pydantic validation → `ConfigurationError`) and a live probe confirmed it works;
  adding one `PAM_CHUNKING__SENTENCE_TOKENIZER=bogus` assertion would close the gap.
- **O-2 (test coupling):** the wiring test asserts `_HeuristicSentenceTokenizer.__name__`,
  coupling to a private class name. Mirrors the P3-104 test precedent; a protocol-level
  assertion (e.g. `.split` behavior) would be more robust, but this is acceptable.
- **O-3 (pre-existing, milestone-level, zero P3-105 path):** the live-Ollama
  `smoke_test` is flaky (missing-section assertion on variable model output; P3-104 review
  O-3). Consider relaxing the all-sections assertion or pinning the model/seed for the
  milestone's regression suite. Not caused by and not fixable within P3-105.

---

## 6. Verdict

**APPROVED**

All specification items, acceptance criteria, and definition-of-done conditions are met and
independently verified. The change is purely additive (full-suite rollback proof), introduces
no new lint or type findings, preserves backward compatibility, and exposes no dead config.

---

*End of P3-105 engineering review.*
