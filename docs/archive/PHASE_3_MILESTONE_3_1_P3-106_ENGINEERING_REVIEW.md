# Milestone 3.1 — P3-106 Engineering Review

**Task:** P3-106 — Finalize chunking tests + fixtures
**Review date:** 2026-08-06
**Contract:** `docs/PHASE_3_MILESTONE_3_1_IMPLEMENTATION_ROADMAP.md` (P3-106 block, lines 151-162; closure annotation at line 164)
**Approved spec:** `docs/PHASE_3_MILESTONE_3_1_SPECIFICATION_REVIEW.md` (APPROVED; R-2 three-engine parametrization, D5 contiguous-span, governing byte-exact contract, O-1/O-2/O-3 carried through)
**Verdict:** **APPROVED**

---

## 0. Review Method

Independent review — the P3-106 implementation report was **not** trusted. Every claim was
re-derived from the frozen spec, the live source, and re-run gates:

- Spec and acceptance criteria re-read from the roadmap block; spec review re-read.
- All changed/new files read from source: `test_sentence_tokenizer.py` (405 lines),
  `test_knowledge_engine.py` (parent + R-2 subclass), `test_chunking_pipeline.py`, both
  committed fixtures, plus `semantic_chunking.py`, `ingest_workflow.py`, `conftest.py`, and
  `test_knowledge_engine_persistence.py` precedents.
- Full suite re-run; integration-marked suite re-run; ruff and mypy re-run from scratch;
  coverage re-run; R-2 parametrized enumeration; reviewer-authored probe scripts exercised
  runtime behavior end-to-end (engine resolution, byte-exact contract, D5 span reconstruction,
  determinism, performance).
- Rollback re-verified by surgically reverting the P3-106 changes and running the **entire**
  suite under the revert, then restoring and re-running to confirm byte-identical state.
- Documentation accuracy checked claim-by-claim against live evidence.

---

## 1. Specification Compliance (frozen block)

| Frozen requirement | Independent verification | Result |
|--------------------|--------------------------|--------|
| Finalize `test_sentence_tokenizer.py` | Source read: fixture path `Path(__file__).parents[1] / "fixtures" / "chunking"` correct; perf text `* 24000` (1,008,000 chars > 1 MB); D9 punkt_tab byte-exact test present | ✅ exact |
| `test_knowledge_engine.py` existing tests **UNCHANGED** | Parent `TestSemanticChunking` read byte-for-byte: identical to pre-P3-106 state (cross-checked against P3-104/105 reports and rollback re-run); 15 tests, 0 edits | ✅ unchanged |
| New integration test file | `tests/integration/test_chunking_pipeline.py` present, `pytestmark = pytest.mark.integration`, `_nltk_available()` helper via public `get_sentence_tokenizer("nltk")` | ✅ |
| Fixtures committed | `tests/fixtures/chunking/abbreviations.md` (13 lines) + `cjk.md` (7 lines) present in tree | ✅ |
| R-2: existing chunking suite green under all three engine paths, nltk import-guarded | R-2 subclass collected **45 real tests** (15 × heuristic / nltk / auto), **0 skips** (nltk present in env), all pass | ✅ |
| D9 byte-exact reproduction of the governing `"AAAA.BBBB."` contract | `"".join(spans) == "AAAA.BBBB.CCCC.DDDD."` asserted (superset of the `"AAAA.BBBB."` spec ask); live probe confirms `['AAAA.', 'AAAA.BBBB.', 'BBBB.CCCC.', 'CCCC.DDDD.']` under all three engines | ✅ |
| Perf ≤ 1 s per 1 MB | 1 MB probe: heuristic 0.063 s, nltk 0.172 s | ✅ |

## 2. Acceptance Criteria (roadmap §5, as frozen)

| Criterion | Independent verification | Result |
|-----------|--------------------------|--------|
| Existing chunking tests pass with new tokenizer under all three engine paths | R-2 45/45 green (default-suite run, not `-m`-filtered) | ✅ |
| Existing tests' behavior preserved | Full-suite rollback proof: revert → **exactly 1005 passed / 31 deselected** (P3-105 baseline, byte-identical); restore → byte-verified identical files + **1059 / 33** | ✅ |
| Governing byte-exact contract preserved | D9 test + live probe (all three engines) + `"AAAA.BBBB."` prefix spans present | ✅ |
| Span reconstruction on committed fixtures (D5 contiguous-span contract) | All 6 fixture D5 assertions green; live probe: abbreviations.md heuristic 13 / nltk 14 / auto 14 spans, cjk.md heuristic 8 / nltk 1 / auto 1 spans — all D5-clean (`text == "".join(spans)`), including the multi-sentence closing `"你好吗？"` + `"3.14 元。"` span under heuristic | ✅ |

## 3. Definition of Done

| DoD | Independent verification | Result |
|-----|--------------------------|--------|
| Regression + integration + perf green | Full suite 1059/33; integration 2/2 new; perf ≤ 1 s | ✅ |
| Parametrized suite green under heuristic/nltk/auto, nltk import-guarded | 45/45 real, 0 skips; `skipif` on the nltk registry flag | ✅ |
| Fixtures committed | Present in tree, referenced by absolute fixture dir | ✅ |
| Ruff / mypy zero **new** findings | Full-repo ruff: 4 findings, ALL pre-existing (E501 372/397/843, F841 533 — the documented baseline 303/328/774 + F841 464, shifted +69 by the R-2 insertion). Mypy: 13 errors, ALL pre-existing environmental (pptx/fitz/faster_whisper stubs, numpy 3.14 syntax); zero on P3-106-touched files (test-only, not in mypy scope) | ✅ |
| Coverage ≥ 80% (tokenizer suite ≥ 90%) | Full suite 89% (`--fail-under=80` exits 0); tokenizer suite 97% (105 stmts, 3 miss = nltk-absent branches) | ✅ |

## 4. Independent Verification Results

### 4.1 Runtime behavior — reviewer probe (`ALL PROBES PASSED`, 11 checks)
Engine resolution: `"auto"` → `_NltkSentenceTokenizer`, `"heuristic"` → `_HeuristicSentenceTokenizer`,
`"nltk"` → `_NltkSentenceTokenizer` (nltk registered in this env). Governing byte-exact contract
`"".join == "AAAA.BBBB.CCCC.DDDD."` True for all three engines. AC1 fixture: 2 sentences under
both engines. Heuristic determinism: two chunkers → identical span sequences.

### 4.2 Rollback behavior — full-suite proof (independently re-verified)
Working tree is fully uncommitted, so rollback was proven by surgical per-file revert with
temp backup + SHA-256 byte verification (not `git stash`). Revert of the P3-106 footprint →
**entire suite: 1005 passed / 31 deselected** — byte-identical to the P3-105 baseline (the 54
new tests are exactly P3-106's, and only P3-106's, additions). Restore → file hashes identical
to the original (test_sentence_tokenizer.py `1587697056…1D79A`, test_knowledge_engine.py
`D2DB1FB6…D0330`, test_chunking_pipeline.py `CDBFAF7A…25389`) and suite back to **1059 / 33**.
Rollback is clean both directions; the new tests gate exactly P3-106 behavior.

### 4.3 Deterministic behavior
Heuristic chunker span sequences identical across instances (probe). Integration
`test_heuristic_engine_deterministic_through_pipeline`: two pipeline runs → identical chunk
character counts through `IngestionWorkflow` (embedding service faked, chunker selected via
settings). Heuristic is the stdlib path and the R-2 default under nltk absence — no randomness.

### 4.4 Backward compatibility
- **Zero production source changes**: P3-106 touched only tests + fixtures + docs. `git status`
  footprint: `M test_knowledge_engine.py`; `?? test_sentence_tokenizer.py`,
  `test_chunking_pipeline.py`, `fixtures/chunking/`, P3-106 report. No `app/` file involved.
- Parent `TestSemanticChunking` byte-identical; all 15 cases pass unchanged under `"auto"`.
- Full suite 1059 = 1005 baseline + 45 R-2 + 9 tokenizer — no hidden regressions; rollback proof
  confirms the baseline is exactly preserved.

### 4.5 Ruff
Full-repo `ruff check .`: 4 findings, zero on P3-106-touched files. The four are the documented
pre-existing baseline in `test_knowledge_engine.py` (E501/F841), line-shifted +69 by the R-2
insertion. `ruff --fix` during implementation removed an unused `dataclasses` import and sorted
imports — the tree is clean of P3-106-introduced lint. **No new findings.**

### 4.6 Mypy
`mypy app/`: 13 errors, all pre-existing environmental (missing stubs for `pptx`/`fitz`/
`faster_whisper`, numpy 3.14 `Type statement` syntax). None on P3-106 files (test-only change;
the test modules are outside mypy's `files` scope). **No new findings.**

### 4.7 Unit tests
Full default suite: **1059 passed / 33 deselected**. Unit files: `test_sentence_tokenizer.py`
+ `test_knowledge_engine.py` = **192 passed** (138 baseline + 54 new: 45 R-2 + 9 tokenizer).
R-2 enumeration: 45 collected, heuristic 15 / nltk 15 / auto 15, 0 skips, 45 passed.
`test_sentence_chunk_offsets_accurate_single_spaces` is overridden engine-aware in the subclass
while the parent's original nltk-mode assertion still runs in `TestSemanticChunking` under
`"auto"` — no engine path loses the offset-accuracy check.

### 4.8 Integration tests
`-m integration`: **30 passed / 1 skipped** (Tesseract not installed) / **1 failed** —
`smoke_test::test_live_ollama_analysis_and_note_generation`. Same pre-existing O-3 flake as the
P3-104/105 reviews: asserts 21 sections in live `llama3.1:8b` output; missing-section sets
differ across runs (live-model nondeterminism); the test never imports P3-106 code. Not a
regression and not fixable within P3-106. The two new integration tests pass 2/2; the default
(non-`-m`) run keeps the smoke test deselected (33 deselected = 31 baseline + 2 new).

### 4.9 Coverage
Full suite: **89%** with `--fail-under=80` passing. Tokenizer suite: **97%** (3 uncovered
statements are the nltk-absent fallback branches in `_nltk_available()` / heuristic fallback —
not reachable in this env, spec-correct). DoD coverage gate exceeded.

### 4.10 Documentation
- Implementation report: every gate number independently reproduced (1059/33, 45/45, 192 unit,
  2 integration, 97%/89% coverage, rollback 1005/31 + byte-verified restore, ruff/mypy zero-new,
  engine-segmentation rationale, D7 abbreviation rule, perf timings). One wording inaccuracy,
  see O-1.
- Roadmap P3-106 closure annotation: numbers and claims consistent with independent runs.
- Spec review: APPROVED and consistent with observed behavior (R-2, D5, byte-exact, O-1/O-2/O-3).

---

## 5. Findings

### Blocking
None.

### Recommended
None.

### Optional
- **O-1 (doc wording only):** the implementation report and roadmap closure describe `cjk.md`
  as containing CJK text with 「」 quotes; the fixture actually wraps `你好吗？` in ASCII
  `"` quotes. The fixture still meaningfully exercises CJK terminators (。！？) and a decimal
  (3.14 元) with the multi-sentence closing span, so behavior is unaffected — the phrase
  "with「」quotes" should read "with quotes" for accuracy.
- **O-2 (informational, by design):** the integration parity assertion
  (`auto == heuristic` chunk counts) executes only when nltk is absent; in the current
  environment it asserts both counts > 0 plus pipeline determinism, matching the roadmap's
  frozen "when nltk absent" wording. The equality path would be exercised by an nltk-absent CI
  run; no change requested.

---

## 6. Verdict

**APPROVED**

All specification items, acceptance criteria, and definition-of-done conditions are met and
independently verified. The change is purely additive (full-suite rollback proof both
directions, byte-verified), preserves existing test behavior byte-for-byte, covers the three
engine paths with 45 real parametrized tests and an integration pipeline test, introduces no
new lint or type findings, keeps coverage above the DoD gate, and documents the deliberate
engine-segmentation differences (D7). The only findings are optional/non-blocking; the sole
unrelated integration failure is the pre-existing live-Ollama smoke flake (O-3).

---

*End of P3-106 engineering review.*
