# P3-101 Engineering Review Report

**Task:** P3-101 — Sentence tokenizer interface + engine factory (scaffold)
**Reviewer:** Principal Software Architect and Engineering Reviewer
**Date:** 2026-08-06
**Scope:** Review ONLY P3-101 implementation. **No code modified.**
**Reviewed against:** `docs/PHASE_3_MILESTONE_3_1_IMPLEMENTATION_ROADMAP.md` (P3-101 block — the approved source of truth; no frozen Phase 3 engineering specification exists per roadmap §intro), M3.1 Specification Review, P3-101 Implementation Report, live source + tests. **The implementation report was NOT trusted; all gates re-run independently.**

---

## 1. Verification Matrix

| # | Review criterion | Result |
|---|------------------|--------|
| 1 | Approved Phase 3.1 specification (P3-101 block) | ✅ Pass |
| 2 | Acceptance Criteria | ⚠️ Pass (deferred — Recommended R-1) |
| 3 | Definition of Done | ✅ Pass |
| 4 | Runtime behavior | ✅ Pass |
| 5 | Public interfaces | ✅ Pass |
| 6 | Rollback guarantees | ✅ Pass |
| 7 | Backward compatibility | ✅ Pass |
| 8 | Unit tests | ✅ Pass |
| 9 | Integration tests | ✅ N/A (spec assigns to P3-106); no impact |
| 10 | Ruff | ✅ Pass (new files) |
| 11 | Mypy | ✅ Pass (module clean; pre-existing repo/toolchain errors unrelated) |
| 12 | Documentation | ✅ Pass (report claims re-verified accurate) |

---

## 2. Criterion-by-Criterion Findings

### 1. Approved specification (P3-101 roadmap block) — ✅ Pass
Spec (roadmap §4 P3-101): Objective = `SentenceTokenizer` protocol (`split(text) -> list[str]`) + factory `get_sentence_tokenizer(engine="auto")` that resolves and returns a tokenizer instance; files = `app/infrastructure/sentence_tokenizer.py` (new — protocol, factory, engine registry; mirrors the M2.1 OCR engine-registry pattern); tests = `tests/unit/test_sentence_tokenizer.py` (new).
- ✅ Implementation matches every field of the task block. `app/infrastructure/sentence_tokenizer.py` (100 lines) contains protocol + registry + factory; the OCR pattern is followed (`register`/`select`-style registry + selection error, mirroring `ocr/base.py`).
- ✅ Scope guard honored: **no** heuristic engine (P3-102), **no** nltk engine (P3-103), **no** chunker wiring (P3-104/105), **no** config change, **no** `pyproject.toml` dependency. Verified: `pyproject.toml` contains no `nltk`/`spaCy`/`tiktoken`; grep shows `sentence_tokenizer` symbols exist **only** in the two new files.

### 2. Acceptance Criteria — ⚠️ Deferred (Recommended R-1)
Spec AC: "`get_sentence_tokenizer("auto")` returns a working tokenizer in every environment (nltk present or absent); empty/whitespace-only text → `[]`; never raises on the factory path."
- ❌ **Not met in the delivered state.** With the (intentional) empty registry — the actual production state until P3-102 registers the heuristic engine — `get_sentence_tokenizer()` (default `"auto"`) **raises** `SentenceTokenizerSelectionError`. There is no real engine, so no `split()` exists to return `[]` for empty/whitespace text.
- This is the **documented, user-confirmed scope deferral** (registry scaffold only; fakes exercise resolution in tests; the "working tokenizer"/`[]`/never-raises ACs land with the real engines). It is consistent with the M2.1 P2-101 precedent (empty-registry stub until engines landed) and the roadmap's own note that P3-102 makes `"auto"` never raise. **Not a blocking defect against the agreed scope — but the roadmap's P3-101 AC text remains literally unsatisfied, which must be recorded and closed at P3-102** (see Recommended R-1).
- The parts of the AC that are satisfiable at this boundary are met: `"auto"` with nltk **absent but heuristic registered** → heuristic + one warning (verified live); `"auto"` with nltk available → nltk (verified live via monkeypatched import seam); empty/whitespace → `[]` is locked as the D5 contract at the protocol surface (tested against a conforming fake).

### 3. Definition of Done — ✅ Pass
Spec DoD: "Interface reviewed; factory unit-tested; no ingestion behavior change yet."
- ✅ Interface reviewed (this report). ✅ Factory unit-tested (12 tests). ✅ No ingestion behavior change: `app/infrastructure/semantic_chunking.py` has **no diff**; `config/`, `routing/`, `ingestion/`, `pipelines/` untouched by this task.

### 4. Runtime behavior — ✅ Pass
Independently exercised live (not from the report):
- `"auto"` + nltk unavailable (real env: `import nltk` → ModuleNotFoundError, `find_spec` False) → heuristic engine + exactly one WARNING record. ✅
- `"auto"` + nltk importable (monkeypatched seam) → nltk engine. ✅
- Explicit `"heuristic"` / `"nltk"` → correct registered engine. ✅
- Selection stable per call (two consecutive `"auto"` resolutions → same engine type). ✅
- Unknown value (`"regex"`) → clear `SentenceTokenizerSelectionError` naming the valid set. ✅
- Known-but-unregistered (`"heuristic"` with empty registry) and empty-registry `"auto"` → distinct clear errors. ✅
- `_nltk_available()` import guard degrades to `False` on ImportError only; optional-import convention matches the repo (`# type: ignore[import-not-found]`, cf. `metadata/mime.py`, `tables/extractor.py`).

### 5. Public interfaces — ✅ Pass
- ✅ `class SentenceTokenizer(Protocol): def split(self, text: str) -> list[str]` — exact spec signature, `@runtime_checkable` (mirrors `OcrEngine`).
- ✅ `def get_sentence_tokenizer(engine: str = "auto") -> SentenceTokenizer` — exact spec signature.
- ✅ Contract docstring states D5: contiguous spans `s1+w1+s2+...+w(n-1)+sn`, whitespace-only separators consumed at boundaries only, no intra-sentence/strip/case/Unicode changes, plus the `[]` empty-text clause. Matches roadmap D5/R-1.
- ✅ `register_sentence_tokenizer` registry seam present (engines register themselves; matches "engine registry" wording). `SentenceTokenizerSelectionError` mirrors `OCRSelectionError`.

### 6. Rollback guarantees — ✅ Pass
- Pure addition: 2 new files + report doc. No existing file modified by P3-101 (working-tree diffs in `config.py`/`ingest_workflow.py`/`pyproject.toml` are pre-existing Phase-2-era changes; grep confirms they contain no `sentence_tokenizer` content).
- No config key, no schema, no dependency, no data migration. Removal = safe revert of the new files (matches roadmap §8 "atomic commits + gates"; P3-101 is task-atomic).

### 7. Backward compatibility — ✅ Pass
- `semantic_chunking.py` untouched (no diff) — `SemanticChunker` and its regex `_SENTENCE_END` path behave exactly as before.
- `app/infrastructure/__init__.py` is a docstring-only package — no eager imports, so importing the package does not execute the new module (no import-time side effects).
- New module imported only by its own test. No production caller exists yet (correct for a scaffold).
- Full suite independently re-run: **959 passed / 31 deselected** vs baseline 947/31 → **+12 net, 0 regressions, deselection count unchanged**.

### 8. Unit tests — ✅ Pass
`tests/unit/test_sentence_tokenizer.py` — **12/12 passed** (independent re-run).
Spec test-list coverage:
- Factory returns an engine for `"heuristic"`/`"nltk"` ✅ (registered fakes)
- `"auto"` with nltk absent → heuristic + **one** logged warning ✅ (`caplog` asserts exactly one WARNING record mentioning the fallback)
- Unknown engine value → clear config error ✅
- Selection stable per call ✅
- Extras (appropriate for the scaffold): registry register/overwrite, known-but-unregistered and empty-registry errors, protocol `isinstance`, D5 empty/whitespace→`[]` contract locked at the protocol surface, autouse registry isolation fixture.
- Coverage: **84%** on the module (independently re-verified; repo floor 80%). The 5 uncovered lines are the real `_nltk_available()` true-branch — unexecutable in this environment because nltk is genuinely absent; the branch is covered via the monkeypatched seam. Acceptable.

### 9. Integration tests — ✅ N/A
Roadmap §5 assigns integration to P3-106 (`tests/integration/test_chunking_pipeline.py`). P3-101 requires none; no integration test touched or affected (31 deselected unchanged).

### 10. Ruff — ✅ Pass
`python -m ruff check` on both new files: **All checks passed** (line-length 100, E/F/I/B/UP). No new repo errors.

### 11. Mypy — ✅ Pass (module)
`python -m mypy app/infrastructure/sentence_tokenizer.py`: **Success — no issues found**. Signatures fully typed (`disallow_untyped_defs` honored).
Note: mypy on the test file and on `app` surfaces **pre-existing** toolchain/repo errors unrelated to P3-101 (numpy `.pyi` under Python 3.14 with `python_version="3.11"`; `faster_whisper`/`pptx_ingestor` stub gaps). Verified identical in nature to the environment baseline; P3-101 adds zero new mypy errors.

### 12. Documentation — ✅ Pass
Implementation report independently re-checked against live evidence:
- "12 passed", "959 passed / 31 deselected (947 baseline + 12)", "84% coverage", "ruff clean", "mypy no issues on new module" — **all accurate**.
- Files-changed table accurate (2 new files; report does not claim `pyproject.toml` edits).
- AC table is **transparent**: the "working tokenizer / empty→`[]` / never raises" ACs are marked ⏳ with explicit "scope-confirmed deferral" wording rather than a false ✅. This honesty is correct and preserved in this review (R-1).

---

## 3. Findings

### Blocking
- **None.**

### Recommended
- **R-1 — Record and close the AC deferral at P3-102.** The roadmap's P3-101 AC ("returns a working tokenizer in every environment; empty/whitespace → `[]`; never raises on the factory path") is **not satisfied by the delivered scaffold**: with the empty registry, `get_sentence_tokenizer()` raises. The deferral is user-confirmed and architecturally correct (no engine can exist before P3-102/103), but the roadmap AC block must be annotated to reflect the scaffold scope, and **P3-102's DoD must include closing this AC** (heuristic always registered ⇒ `"auto"` never raises, `[]` for empty/whitespace). Until then, the literal AC text overstates what P3-101 alone delivers.

### Optional
- **O-1 — `test_selection_is_stable_per_call` mutates `tokenizer_mod._nltk_available` by direct assignment** (`test_sentence_tokenizer.py:81`) rather than the `monkeypatch` fixture used by `TestAutoResolution`. The assignment leaks to the module for the rest of the session and survives the registry-restoring autouse fixture; safe today only because later tests re-set the seam. Use `monkeypatch` for consistency and isolation.
- **O-2 — `register_sentence_tokenizer` accepts any name, including `"auto"`** (stored, never consulted by the factory) and non-D3 names. D3 forbids a `"regex"` legacy value; the factory rejects unknown names at selection time, but registration is unvalidated. Consider validating against `{"heuristic", "nltk"}` (or at minimum rejecting `"auto"`) when P3-102/103 register real engines.
- **O-3 — The auto-fallback warning is emitted on every fallback resolution**, including when nltk was never registered (not merely uninstalled). Spec-conformant ("one logged warning" per call, D4), but a caller resolving per chunk in a loop would log repeatedly. If that matters, emit once per process at P3-103.

---

## 4. Verdict

The implementation is a faithful, minimal realization of the approved P3-101 scaffold within the explicitly confirmed scope. The protocol, registry, and factory match the normative interfaces exactly; the D5 contract is locked at the protocol surface; runtime resolution behavior (auto nltk-preference, one-warning heuristic fallback, stable selection, clear selection errors) is verified live; the task is isolated from ingestion — backward compatible and rollback-safe; unit tests cover the spec test list with 84% module coverage; ruff clean; mypy clean on the module; and the implementation report's claims all re-verified accurate, including its honest marking of the deferred ACs.

The single substantive gap — the roadmap's literal AC being unmet while the registry is empty — is a scope-confirmed deferral, not an implementation defect, and is captured as Recommended R-1 with an explicit closure obligation at P3-102.

✅ **APPROVED**

---

*End of P3-101 engineering review. No code modified during review.*
