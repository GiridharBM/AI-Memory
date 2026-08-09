# Milestone 3.1 — P3-103 Implementation Report

**Task:** P3-103 — NLTK `punkt_tab` engine (optional)
**Status:** DONE — implemented, tested, not wired into ingestion (per scope)
**Date:** 2026-08-06
**Contract:** `docs/PHASE_3_MILESTONE_3_1_IMPLEMENTATION_ROADMAP.md` (P3-103 block, D1/D4/D5/D9, Wave-0 preflight)
**Scope rule honored:** ONLY P3-103 implemented; no future task work. P3-104 (chunker wiring), P3-105 (config), P3-106 (regression suite) not started. `SemanticChunker` untouched. P3-101/P3-102 behavior preserved (full suite +34 tests from the P3-102 baseline, 0 regressions).

---

## 1. Wave-0 Preflight — DEVIATION RECORDED

The roadmap's Wave-0 preflight (Phase 2 R-5 precedent) was run before implementation and **failed its core premise**:

1. **Wheel preflight — `punkt_tab` is NOT bundled in any nltk wheel.** `pip download --only-binary :all:` of nltk `3.8.1`, `3.9.0`, and `3.10.2` was inspected (all py3-none-any universal wheels): **none contains any tokenizer data** (no `nltk/tokenizers/`, no pickles, no `punkt_tab` files). The roadmap's D1 statement — "its data ships bundled in the wheel (no model download, fully offline)" — is factually false for every nltk release.
2. **Bare `PunktSentenceTokenizer()` (no parameters) is unusable for the AC.** With empty `PunktParameters` it has **0 trained abbreviations**, so `"Dr. Smith went to Washington. He arrived at 9:00 a.m."` splits into **3 sentences** (AC1 requires exactly 2); `"etc."`/`"U.S."` mid-sentence also mis-split.
3. **The pretrained model works and satisfies every check, but requires a one-time data download.** nltk 3.9+ ships the `PunktTokenizer` class (verified present in both 3.9.0 and 3.10.2 wheels) whose `load_lang("english")` reads `tokenizers/punkt_tab/english/` (232 KB of text data) from the local `nltk_data` tree via `nltk.data.find`. With `nltk.download("punkt_tab")` performed, AC1 → exactly 2 sentences, the D9 governing fixture → 4 spans, deterministic, D5 reconstruction holds.

**Decision (user-approved, 2026-08-06):** deviate from D1's "bundled, no download" premise and use the **pretrained model with a documented one-time `nltk.download("punkt_tab")`** setup step for the optional `intelligence` extra. The engine remains import-guarded; if nltk **or** the data is absent, `"auto"` logs one warning and returns the heuristic engine (D4/C-3 semantics preserved; ingestion never breaks). The nltk download happens once at setup (or package-manager-managed `nltk_data`), never at runtime.

**D9 behavioral preflight (governing byte-exact fixture):** `PunktTokenizer("english")` on `"AAAA. BBBB. CCCC. DDDD."` → `['AAAA.', 'BBBB.', 'CCCC.', 'DDDD.']` — identical spans to the regex `_SENTENCE_END` engine, so the chunker's overlap concatenation still reproduces `"AAAA.BBBB."` (the `test_chunk_overlap_uses_original_predecessor` regression contract). **No divergence → D9 contingency not triggered on behavior.** The deviation is exclusively the data-sourcing premise, recorded above.

## 2. What Was Implemented

Per the frozen task block (Objective / Interfaces / Implementation Steps):

| Deliverable | Location | Notes |
|-------------|----------|-------|
| `_NltkSentenceTokenizer` | `app/infrastructure/sentence_tokenizer.py` (new class) | Optional engine implementing `SentenceTokenizer.split(text) -> list[str]`; wraps nltk 3.9+ `PunktTokenizer("english")` (pretrained `punkt_tab`). Conforms to D5 (whitespace-only gaps; spans partition the text; empty/whitespace → `[]`) |
| Import guard | same module, top import block | `try: from nltk.tokenize.punkt import PunktTokenizer … except ImportError: _PunktTokenizer = None` — module imports cleanly without nltk (`# type: ignore[import-not-found, import-untyped]`; `# pragma: no cover` on the absent branch) |
| `_nltk_available()` | same module | Now checks **both** importability and data presence: probes `PunktTokenizer("english")` and returns False on `LookupError` (data missing). Factory `"auto"` path unchanged in shape |
| **Import-time guarded registration** | `if _nltk_available(): register_sentence_tokenizer("nltk", _NltkSentenceTokenizer)` | Registered only when nltk importable **and** `punkt_tab` data present. Otherwise `"nltk"` is simply not registered → `"auto"` → heuristic + one warning; explicit `"nltk"` → clear `SentenceTokenizerSelectionError` |
| `pyproject.toml` | `[project.optional-dependencies] intelligence` | Added `"nltk>=3.9"` (D4, C-2 — reuses the single shared optional-extras surface; no new required dependency, no separate extra). `PunktTokenizer` API verified present in 3.9 and 3.10 |
| Unit tests | `tests/unit/test_sentence_tokenizer.py` (extended) | 17 new tests (see §3) |
| Test hygiene fix (P3-101 O-1) | `test_selection_is_stable_per_call` | Changed direct module attribute assignment (`tokenizer_mod._nltk_available = lambda: False`) to `monkeypatch.setattr(...)`. The direct assignment **leaked `_nltk_available=False` into all later tests in the file** (it is never restored by the `_isolated_registry` fixture, which only snapshots `_ENGINE_REGISTRY`); P3-103's real-engine tests exposed the leak. Fix is behavior-neutral (already flagged as P3-101 O-1) |

## 3. Test Results

**New tests:** 17 added → `tests/unit/test_sentence_tokenizer.py` now **51 passed** in an nltk-enabled env.

| Test | Verifies |
|------|----------|
| `TestNltkTokenizer::test_ac1_fixture_is_exactly_two_sentences` | **P3-103 AC** — `"Dr. Smith went to Washington. He arrived at 9:00 a.m."` → exactly 2 sentences |
| `test_governing_fixture_produces_four_spans` | D9 governing fixture spans match the regex engine (overlap contract preserved) |
| `test_mid_sentence_abbreviations_not_boundaries` | `etc.` mid-sentence not a boundary |
| `test_empty_and_whitespace_yield_empty_list`, `test_trailing_fragment_preserved`, `test_deterministic` | D5 contract edges |
| `test_d5_whitespace_only_separators` (parametrized × 8) | **D5 span reconstruction** across the 8 governing fixtures, incl. the CJK fixture `"甲。乙。"` **without inserted whitespace** |
| `TestNltkEngineSelection` (× 2) | real `"auto"` prefers the registered nltk engine; explicit `"nltk"` returns it |
| `TestNltkAbsentFallback::test_auto_falls_back_to_real_heuristic_with_one_warning` | **env-independent** — monkeypatches `_nltk_available` → False; asserts real heuristic engine + exactly one warning, never a crash (D4/C-3) |

Engine tests are `@pytest.mark.skipif(not ("nltk" in _ENGINE_REGISTRY))` — they **skip cleanly** on any machine without nltk/`punkt_tab`, exactly as the roadmap's "import-guarded engine test (skipped when nltk absent)" requires. The absent-path test is not skipped (runs everywhere).

| Gate | Result |
|------|--------|
| Tokenizer unit tests (nltk present) | **51/51 passed** |
| Full default suite | **998 passed / 31 deselected** (P3-102 baseline 981/31; **+17 net new, 0 regressions**) |
| Integration suite | 29 passed, 1 skipped (Tesseract not installed), **1 failed** — `smoke_test.py::test_live_ollama_analysis_and_note_generation`, a live-Ollama smoke test requiring a running server (pre-existing environmental failure, identical at the P3-102 baseline; exercises `OllamaClient`/`ObsidianMarkdownGenerator`, untouched by P3-103) |
| Coverage (module) | **97%** (P3-102 was 95%; repo floor 80%). 3 uncovered lines (205, 208-209) = the guard's *absent* branches (`_PunktTokenizer is None` / `except LookupError`), unexecutable in an env with nltk + data present — verified manually via `nltk.data.path` override |
| Ruff | All checks passed on modified files |
| Mypy | No issues on the module (nltk import covered by `import-untyped, import-not-found` ignores) |

## 4. Acceptance Criteria / DoD Verification

| Criterion (frozen) | Status |
|--------------------|--------|
| With nltk installed, "Dr. Smith went to Washington. He arrived at 9:00 a.m." → exactly 2 sentences | ✅ `test_ac1_fixture_is_exactly_two_sentences` (runs; nltk 3.10.2 + `punkt_tab` present) |
| With nltk absent, `"auto"` logs one warning and returns the heuristic engine | ✅ `TestNltkAbsentFallback` (env-independent) + live subprocess check (`nltk.data.path` overridden to empty → registered `['heuristic']`, warning logged, heuristic returned, no crash) |
| **Optional-dep path proven both ways** (DoD) | ✅ nltk+data present → nltk engine registered, `auto`→nltk; nltk importable but data absent → not registered → `auto`→heuristic+warning; nltk absent → same, via the `ImportError` guard (`# pragma: no cover`, absent branch) |
| **Wheel preflight recorded** (DoD, Phase 2 R-5 precedent) | ✅ §1 — nltk 3.8.1/3.9.0/3.10.2 wheels inspected: no bundled tokenizer data; deviation recorded and user-approved (one-time `nltk.download("punkt_tab")`) |
| **`punkt_tab` conformance on the governing byte-exact fixture** (DoD) | ✅ `"AAAA. BBBB. CCCC. DDDD."` → 4 spans, identical to the regex engine; overlap regression contract `"AAAA.BBBB."` preserved. No D9 contingency needed |
| Import-guarded engine test (skipped when nltk absent) | ✅ `skipif` on registry membership |
| D5 contract (incl. CJK without inserted whitespace) | ✅ parametrized reconstruction × 8 |
| nltk absent → clear warning + heuristic fallback, not a crash | ✅ warning text "NLTK sentence tokenizer unavailable; using heuristic engine." |
| Not wired into ingestion | ✅ `semantic_chunking.py`, `config/`, `routing/`, `pipelines/` untouched |

## 5. Files Changed

| File | Action |
|------|--------|
| `app/infrastructure/sentence_tokenizer.py` | **modified** — import-guarded `PunktTokenizer` import; `_NltkSentenceTokenizer`; `_nltk_available()` now checks import + data presence; conditional registration; module docstring updated |
| `pyproject.toml` | **modified** — `nltk>=3.9` added to the optional `intelligence` extra (D4, C-2) |
| `tests/unit/test_sentence_tokenizer.py` | **modified** — +17 tests (`TestNltkTokenizer` ×13, `TestNltkEngineSelection` ×2, `TestNltkAbsentFallback` ×1, engine-selection assert); P3-101 O-1 test-hygiene fix |
| `docs/PHASE_3_MILESTONE_3_1_IMPLEMENTATION_ROADMAP.md` | **modified** — P3-103 deviation/closure annotation |

No public API changes: `SentenceTokenizer`, `get_sentence_tokenizer`, `register_sentence_tokenizer`, `SentenceTokenizerSelectionError` signatures and behavior unchanged. `_NltkSentenceTokenizer` is private (reached via the factory).

## 6. Rollback Plan

Pure addition, not wired into any ingestion path. Rollback = remove the P3-103 additions:
- `sentence_tokenizer.py`: drop the nltk import block, `_NltkSentenceTokenizer`, the `_nltk_available()` rewrite, and the conditional registration (restores the P3-102 module exactly — `_nltk_available()` reverts to the import-only check);
- `pyproject.toml`: drop the `nltk>=3.9` line from the `intelligence` extra;
- test file: drop the 17 nltk tests (the P3-101 O-1 monkeypatch fix is behavior-neutral and may be retained).

**Verified:** with the engine effectively absent (nltk data path forced empty before import), the tokenizer suite runs **35 passed / 16 skipped** — the 34 P3-101/P3-102 tests plus the env-independent absent-fallback test all pass, the nltk engine tests skip cleanly, and `"auto"` degrades to the heuristic with one warning. The full default suite at that state is a subset of the verified 998 (the nltk-engine tests skip, everything else identical). No config, schema, or required-dependency change to unwind; the two interpreters were only extended with the optional `nltk` package + one-time `punkt_tab` data for AC verification.

## 7. Notes

- **Environment:** nltk 3.10.2 installed in both the venv (`.venv`) and the global suite interpreter (C:\Python314, which holds the `intelligence` extras Pillow/pdfplumber/etc. — the baseline 981-passed suite runs there). `punkt_tab` downloaded once to `C:\Users\girid\AppData\Roaming\nltk_data` (nltk's standard search path). The venv lacks the intelligence extras, so the full suite (which collects the OCR/PIL unit tests) runs on the global interpreter; both interpreters behave identically for the tokenizer module.
- **nltk 3.9 vs 3.10:** `PunktTokenizer` + `load_lang` verified present in the nltk 3.9.0 wheel, so the `nltk>=3.9` pin is valid for the implementation.
- **Setup step documented for the optional engine:** `pip install -e .[intelligence]` then `nltk.download("punkt_tab")`. Without either, `"auto"` degrades to the heuristic with one logged warning; ingestion behavior is unchanged until P3-104.

## 8. Next Steps (NOT part of this task)

Awaiting engineering review of P3-103. Then, in milestone order: P3-104 (wire into `SemanticChunker`) → P3-105 (config `chunking.sentence_tokenizer`) → P3-106 (regression + fixture suite under all three engine paths). The P3-103 deviation (one-time `punkt_tab` download vs. D1's "bundled" premise) should be ratified in the Phase 3 engineering spec review.

---

*End of P3-103 implementation report. Implementation stopped — awaiting engineering review.*
