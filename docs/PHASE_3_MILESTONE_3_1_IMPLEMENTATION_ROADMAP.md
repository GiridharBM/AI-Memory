# Milestone 3.1 — NLP Sentence Segmentation (G12): Implementation Roadmap

**Source of truth:** **No frozen Phase 3 engineering specification exists in the repository as of 2026-08-05.** This roadmap is derived from the available authoritative sources and follows the Phase 2 conventions. Task IDs, decisions, and acceptance criteria below are **proposed** and must be ratified by the Phase 3 engineering specification before implementation.
**Upstream chain:** MEDD §5 Phase 3 → MEDD §7.3 / §7.4 (module specs) → `docs/05_Development_Roadmap.md` §3.1 → this roadmap → (future) Phase 3 Engineering Specification.
**Specification review remediation (2026-08-05):** blocking findings R-1 (sentence-tokenizer whitespace/offsets contract) and R-2 (regression under all three engine paths) resolved; recommended C-1 (naming), C-2 (extra ownership), C-3 (tiktoken scope) applied. See `docs/PHASE_3_MILESTONE_3_1_SPECIFICATION_REVIEW.md`.
**Baseline (verified live from repo docs 2026-08-05):** Phase 2 COMPLETE and approved (Milestones 2.1–2.6; M2.6 FINAL APPROVAL; release 0.7.0, 2026-08-04). Full suite **947 passed / 31 deselected**; coverage **88.88%** (floor 80%); ruff/mypy zero new errors. `SemanticChunker` at `app/infrastructure/semantic_chunking.py` — regex `_SENTENCE_END` at line 14, `_split_by_sentences` at lines 138–158, constructed at `app/pipelines/ingest_workflow.py:247`, invoked at lines 749–753. `pyproject.toml` has **no** `nltk`/`spaCy`/`tiktoken`; an optional `intelligence` extra already exists. `nltk` is **not** installed in the current venv (default `"auto"` therefore resolves to the heuristic engine today); `tiktoken` is importable but **undeclared**.
**Status:** Implementation plan. No code is implemented by this document.

---

## 1. Task Summary

| ID | Title | Priority | Deps | Complexity | Est. | Risk |
|----|-------|----------|------|------------|------|------|
| P3-101 | Sentence tokenizer interface + engine factory | P0 | — | Low | 0.25 d | L |
| P3-102 | Heuristic fallback tokenizer (stdlib) | P0 | P3-101 | Medium | 1 d | M |
| P3-103 | NLTK `punkt_tab` engine (optional) | P1 | P3-101 | Low | 0.5 d | M |
| P3-104 | `SemanticChunker` integration | P0 | P3-101, P3-102 | Medium | 0.5 d | M |
| P3-105 | Config + plumbing (`chunking.sentence_tokenizer`) | P0 | P3-104 | Low | 0.5 d | L |
| P3-106 | Regression + fixture suite (all engine paths) | P0 | P3-104, P3-105 | Low | 0.5 d | L |

**Total:** 6 tasks, ~3.25 d → milestone budget **3–4 dev-days** (rounded with buffer; reconciled against the 05 roadmap 3-day nominal for §3.1).

---

## 2. Implementation Order (binding)

| Wave | Tasks | Rationale |
|------|-------|-----------|
| 0 | Preflight (not a task): confirm Phase 2 gate closed (M2.6 final approval on file; 947 unit + integration green; coverage ≥ 80%). Wheel preflight per Phase 2 R-5 precedent: `pip download --only-binary :all: nltk>=3.9` on `cp314-win_amd64` (nltk is a pure-Python universal wheel with `punkt_tab` data bundled since 3.9 — no model download, no network at runtime). **Behavioral preflight:** run nltk `punkt_tab` against the governing byte-exact fixture (R-2 / D9). |
| 1 | P3-101 | Protocol + factory first; both engines consume it. |
| 2 | P3-102 ‖ P3-103 | Heuristic (stdlib) and NLTK engine are independent once the interface exists. |
| 3 | P3-104 | Chunker integration — the milestone's single behavior change. |
| 4 | P3-105 | Config plumbing so selection is toggleable. |
| 5 | P3-106 | Regression + fixture suite proves the frozen success criterion (all existing chunking tests pass with the new tokenizer) under all three engine paths. |

**Critical path:** P3-101 → P3-102 → P3-104 → P3-105 → P3-106.
**Parallel:** P3-102 ‖ P3-103 (wave 2).
**Scope guard (hard):** M3.1 **does not** consume `metadata.extra["structure"]` — hierarchical parent-ID assignment is Milestone 3.2 (G14). M3.1 only swaps the sentence splitter inside the existing chunker.

---

## 3. Key Implementation Decisions (proposed — pending frozen spec)

| # | Decision | Detail |
|---|----------|--------|
| D1 | **Engine choice: NLTK `punkt_tab`, not spaCy** | `punkt_tab` is pure-Python, wheel-safe, and its data ships **bundled in the wheel** (no model download, fully offline — matches the project's local-first, minimal-dependency bias; ADR-001 precedent). spaCy requires a model download and heavy transitive deps. Deviation from the 05 roadmap's "spaCy recommended for quality" is explicit and recorded here as a **proposed ADR** (mirror the M2.4 ADR-002 precedent). Both engines sit behind one interface, so spaCy can be added later without a code change. |
| D2 | **Integration point** | `SemanticChunker._split_by_sentences` (semantic_chunking.py:138–158) is the **only** sentence-split site in the codebase (single caller, lines 749–753). The private method delegates to the injected tokenizer; heading/paragraph/overlap logic stays untouched. |
| D3 | **Engine values** | `"auto"` (default; NLTK if importable, else heuristic), `"nltk"`, `"heuristic"`. **No `"regex"` legacy value** — per Phase 2 R-4 (no deprecated branch retained); the heuristic is a superset and the regression gate proves the existing tests pass. Strict byte-identical legacy behavior, if ever demanded, is reachable only by reverting the commit range. |
| D4 | **nltk placement** | Optional dependency in `[project.optional-dependencies] intelligence` (same extra as Pillow/pdfplumber), **reusing the single shared optional-extras surface — no separate `chunking` extra is created** (C-2). **C-3 optional-dep DoD clause applies:** with nltk absent, `"auto"` degrades to the heuristic engine with one logged warning; ingestion never breaks. No new *required* runtime dependency. |
| D5 | **Sentence tokenizer contract — whitespace normalized at boundaries (R-1)** | `split(text)` partitions `text` into a **contiguous sequence of sentence spans** `s₁…sₙ` such that `text == s₁ + w₁ + s₂ + … + wₙ₋₁ + sₙ`, where each `wᵢ` is a (possibly empty) **whitespace-only separator consumed at the boundary**. **Whitespace may be normalized only at sentence boundaries**; no other transformation is applied (no intra-sentence whitespace changes, no stripping of sentence content, no case/Unicode changes). This matches both engines (the current `_SENTENCE_END` regex consumes the `\s+` lookbehind/span, and `punkt_tab` consumes boundary whitespace) and keeps the `_split_by_sentences` single-space re-join (line 148) and its `start_char`/`end_char` math **unchanged and internally consistent** (D5a). The **governing regression contract** is the existing byte-exact case `tests/unit/test_knowledge_engine.py:129-136` (`test_chunk_overlap_uses_original_predecessor`, asserting `"AAAA.BBBB."`): the sentence path must reproduce it exactly under every engine the regression gate runs. |
| D6 | **Config block** | New top-level `chunking:` block (`chunking.sentence_tokenizer: "auto"`), bound by a new `ChunkingSettings` in `app/core/config.py` (mirrors `processing:`/`models:` blocks; chunking is a core pipeline stage, not document-intelligence — kept out of `intelligence:`). Plumbed via `from_runtime` → `SemanticChunker(sentence_tokenizer=...)` at `ingest_workflow.py:247`. |
| D7 | **CJK handling (heuristic)** | `。！？` treated as sentence terminators in the heuristic engine; per D5 the CJK boundary separator is empty (no whitespace consumed), so CJK fixtures reconstruct without inserted whitespace (punkt covers punctuation languages in the nltk path; CJK token-count parity is G13/Phase 3.3, out of scope here). |
| D8 | **Determinism** | Engine selection resolved **once per chunker instance** (at construction) and logged; both engines are deterministic on identical input. |
| D9 | **nltk boundary-conformance contingency (R-2)** | Wave-0 behavioral preflight runs `punkt_tab` against the governing byte-exact fixture before implementation. If `punkt_tab` diverges (e.g., treats `"AAAA."` as a non-final token), the milestone reports a deviation and pins `"auto"` to the **heuristic** engine (nltk remains available as explicit opt-in) so the frozen success criterion stays provable with zero production-code workaround. |

**Naming decision (C-1, R-1 resolution):** the M3.1 field is **`sentence_tokenizer`** (G12, sentence segmentation). MEDD §7.4's `tokenizer: str = "cl100k_base"` and `max_chunk_tokens` are the **token-aware** fields for G13 (Phase 3.3) and are **not** added in M3.1; the future Phase 3 spec ratifies `sentence_tokenizer` for G12 and reserves `tokenizer`/`max_chunk_tokens` for M3.3.

---

## 4. Per-Task Plan

---

### P3-101 — Sentence tokenizer interface + engine factory

| Field | Detail |
|-------|--------|
| **Task ID** | P3-101 |
| **Objective** | Define a `SentenceTokenizer` protocol (`split(text) -> list[str]`) and a factory `get_sentence_tokenizer(engine="auto")` that resolves and returns a tokenizer instance once. The protocol contract is D5: contiguous sentence spans; whitespace normalized only at boundaries. |
| **Dependencies** | None (milestone foundation). |
| **Estimated complexity** | Low. |
| **Files expected to change** | `app/infrastructure/sentence_tokenizer.py` (new — protocol, factory, engine registry; mirrors the M2.1 OCR engine-registry pattern). |
| **Public interfaces** | `class SentenceTokenizer(Protocol): def split(self, text: str) -> list[str]`; `def get_sentence_tokenizer(engine: str = "auto") -> SentenceTokenizer`. Contract docstring states D5 (boundary-whitespace normalization). |
| **Tests to create** | `tests/unit/test_sentence_tokenizer.py` (new): factory returns an engine for `"heuristic"`/`"nltk"`; `"auto"` with nltk absent → heuristic + one logged warning; unknown engine value → clear config error; selection is stable per call. |
| **Acceptance Criteria** | `get_sentence_tokenizer("auto")` returns a working tokenizer in every environment (nltk present or absent); empty/whitespace-only text → `[]`; never raises on the factory path. |

> **AC closure (P3-102, 2026-08-06):** the P3-101 scaffold shipped with an empty registry, so the literal AC was not satisfiable at that task boundary (recorded as Recommended R-1 in `docs/PHASE_3_MILESTONE_3_1_P3-101_ENGINEERING_REVIEW.md`). P3-102 registers the stdlib heuristic engine unconditionally at import, closing this AC: `"auto"` now resolves to a working tokenizer in every environment (nltk present or absent) and never raises; empty/whitespace-only text → `[]`. Verified in `tests/unit/test_sentence_tokenizer.py` (`TestHeuristicIsDefaultFallback`).
| **Definition of Done** | Interface reviewed; factory unit-tested; no ingestion behavior change yet. |

---

### P3-102 — Heuristic fallback tokenizer (stdlib)

| Field | Detail |
|-------|--------|
| **Task ID** | P3-102 |
| **Objective** | Replace the `_SENTENCE_END` regex (`(?<=[.!?])\s+(?=[A-Z\d])`) with an abbreviation-aware stdlib tokenizer: handles common abbreviations (Dr., Mr., U.S.A.), ellipses, decimal numbers, quoted sentences, non-period terminators (`!?`), and CJK terminators (`。！？`) per D7. Conforms to the D5 contract (whitespace consumed only at boundaries). |
| **Dependencies** | P3-101. |
| **Estimated complexity** | Medium. |
| **Files expected to change** | `app/infrastructure/sentence_tokenizer.py` (new — `_HeuristicSentenceTokenizer`; abbreviation list as a module constant). |
| **Public interfaces** | `get_sentence_tokenizer("heuristic")` returns the heuristic engine. |
| **Tests to create** | `tests/unit/test_sentence_tokenizer.py`: abbreviation boundary cases; ellipses; decimal numbers (e.g. "3.14"); quoted sentences; `!?` terminators; CJK `。！？`; no trailing empty fragment; determinism; **normalized-equivalence reconstruction per the D5 contract** — on committed fixtures the returned spans reconstruct the source with only inter-sentence whitespace consumed (e.g., fixture `"AAAA. BBBB."` → spans `["AAAA.", "BBBB."]`; CJK fixture `"甲。乙。"` → `["甲。", "乙。"]` with **no** whitespace inserted at the empty separator). |
| **Acceptance Criteria** | "Dr. Smith went to Washington. He arrived at 9:00 a.m." → exactly 2 sentences; "U.S.A. is large." → 1 sentence; "3.14 and 2.71 are constants." → 1 sentence; sentence boundaries never fall mid-abbreviation. **Whitespace may be normalized during sentence splitting, at sentence boundaries only** (D5). |
| **Definition of Done** | Heuristic suite green; must pass all existing `TestSemanticChunking` cases when wired in (proved by P3-104/P3-106). |

> **Engineering review (2026-08-06):** **APPROVED** — all 3 acceptance criteria pass (verified live, not only via tests); D5 reconstruction invariant holds on the governing fixtures; D7 CJK terminators use empty separators; R-1 closure confirmed (`"auto"` returns the heuristic, never raises, empty/whitespace → `[]`); `SemanticChunker` and all public APIs untouched (backward compatible, rollback-safe); 34/34 unit tests, 95% module coverage, ruff/mypy clean, full suite 981 passed (+22, 0 regressions), integration impact nil. Blocking/recommended findings: none. Optional: O-1 inherent abbreviation-list boundary suppression (e.g. `a.m.`/`etc.`/`U.S.` before a new sentence — spec-mandated tradeoff; P3-103 punkt engine is the upgrade path), O-2 quoted `!`/`?` fragment case, O-3 carried-forward P3-101 O-1 (test monkeypatch style), O-4 rollback phrasing vs. uncommitted working tree. See `docs/PHASE_3_MILESTONE_3_1_P3-102_ENGINEERING_REVIEW.md`.

| Field | Detail |
|-------|--------|
| **Task ID** | P3-103 |
| **Objective** | Add an optional NLTK `punkt_tab` sentence-tokenizer engine. Data ships bundled in the wheel — no download, offline. nltk absent → clear, logged degradation to heuristic (C-3 DoD clause, D4). Conforms to the D5 contract. |
| **Dependencies** | P3-101. |
| **Estimated complexity** | Low. |
| **Files expected to change** | `app/infrastructure/sentence_tokenizer.py` (new — `_NltkSentenceTokenizer`, import-guarded); `pyproject.toml` (add `nltk>=3.9` to the optional `intelligence` extra — D4, C-2). |
| **Public interfaces** | `get_sentence_tokenizer("nltk")`; `get_sentence_tokenizer("auto")` prefers nltk when importable. |
| **Tests to create** | Import-guarded engine test (skipped when nltk absent); when nltk present: the AC1 abbreviation fixture, determinism, and span-reconstruction per the D5 contract (CJK fixture without inserted whitespace); absent-nltk path → `ImportError`-style clear warning + heuristic fallback, not a crash. |
| **Acceptance Criteria** | With nltk installed, "Dr. Smith went to Washington. He arrived at 9:00 a.m." → exactly 2 sentences; with nltk absent, `"auto"` logs one warning and returns the heuristic engine. |
| **Definition of Done** | Optional-dep path proven both ways; wheel preflight recorded in the completion report (Phase 2 R-5 precedent); `punkt_tab` conformance on the governing byte-exact fixture verified or D9 contingency invoked. |

> **Deviation + closure (P3-103, 2026-08-06):** Wave-0 wheel preflight **failed D1's premise**: nltk 3.8.1/3.9.0/3.10.2 wheels contain **no** bundled `punkt_tab` data, and bare `PunktSentenceTokenizer()` (empty params) fails the AC (Dr. → 3 sentences). User-approved deviation: the engine uses the pretrained `PunktTokenizer("english")` with a documented **one-time `nltk.download("punkt_tab")`** setup step for the optional `intelligence` extra (nltk>=3.9 added to it); runtime stays offline. Import-guarded registration: nltk or data absent → `"auto"` logs one warning and returns the heuristic. D9 behavioral preflight **passed** (governing fixture → 4 spans, identical to the regex engine; `"AAAA.BBBB."` overlap contract preserved). Both ACs verified live; full suite **998 passed / 31 deselected** (+17, 0 regressions); ruff/mypy clean; module coverage 97%. See `docs/PHASE_3_MILESTONE_3_1_P3-103_IMPLEMENTATION_REPORT.md`.

---

### P3-104 — `SemanticChunker` integration

| Field | Detail |
|-------|--------|
| **Task ID** | P3-104 |
| **Objective** | Wire the tokenizer into the chunker: add a `sentence_tokenizer: str = "auto"` dataclass field; `_split_by_sentences` delegates to the resolved engine instead of `_SENTENCE_END`; heading/paragraph/overlap logic unchanged; the single-space re-join and offsets math unchanged (D5/D5a). |
| **Dependencies** | P3-101, P3-102. |
| **Estimated complexity** | Medium. |
| **Files expected to change** | `app/infrastructure/semantic_chunking.py` (`_split_by_sentences` delegation; new field; engine resolution once per instance — D8); `app/infrastructure/sentence_tokenizer.py` (resolution helper consumed here). |
| **Public interfaces** | `SemanticChunker` gains `sentence_tokenizer: str = "auto"` (dataclass field with default — backward compatible; `SemanticChunker()` still constructs). |
| **Tests to create** | Extend `tests/unit/test_knowledge_engine.py` `TestSemanticChunking`: a `max_chunk_chars`-exceeding paragraph containing "Dr. Smith went to Washington. He arrived at 9:00 a.m." splits into exactly 2 sentence-aligned chunks (not 6); `start_char`/`end_char` accurate for multi-chunk long paragraphs; `sentence_tokenizer="heuristic"` behaves deterministically. **Existing cases unchanged.** |
| **Acceptance Criteria** | Chunk boundaries align with true sentence boundaries; the existing byte-exact case `test_chunk_overlap_uses_original_predecessor` (`tests/unit/test_knowledge_engine.py:129-136`) reproduces `"AAAA.BBBB."` exactly (R-1 governing contract); offsets preserved; existing `TestSemanticChunking` cases pass unchanged with default `"auto"`. |
| **Definition of Done** | Integration + extension tests green; chunker still byte-compatible for non-sentence-split paths. |

> **Closure (P3-104, 2026-08-06):** Implemented to spec — no deviation. `sentence_tokenizer: str = "auto"` field added; engine resolved once per instance at construction (D8) via `get_sentence_tokenizer` and logged; `_split_by_sentences` delegates to the resolved engine; `_SENTENCE_END` regex removed (dead after delegation); heading/paragraph/overlap logic and the D5a re-join/offset math untouched. 3 new `TestSemanticChunking` tests (AC1 → exactly 2 sentence-aligned chunks — a real gate, the old regex produced 3; offset contiguity; heuristic determinism); existing 12 cases unchanged. Governing `"AAAA.BBBB."` contract verified live under `auto`/`heuristic`/`nltk`; nltk-absent fallback verified (auto→heuristic + one warning, no crash); fail-fast on unknown engine at construction. Full suite **1001 passed / 31 deselected** (+3, 0 regressions); integration 30 passed / 1 skipped; mypy clean; ruff zero new findings. Rollback verified (revert → only the 2 new tests fail). See `docs/PHASE_3_MILESTONE_3_1_P3-104_IMPLEMENTATION_REPORT.md`.

---

### P3-105 — Config + plumbing

| Field | Detail |
|-------|--------|
| **Task ID** | P3-105 |
| **Objective** | Add `ChunkingSettings(sentence_tokenizer: Literal["auto", "nltk", "heuristic"] = "auto")`; add the `chunking:` block to `config/default.yaml`; plumb through the full production chain (`from_runtime` → `SemanticChunker(sentence_tokenizer=...)` at `ingest_workflow.py:247`). Both entry points (CLI and queue worker) reach the same construction path (L2 check). **Commit coupling:** `Settings` is `extra="forbid"` (`app/core/config.py:381-385`), so `ChunkingSettings` and the `chunking:` yaml key must land in the same atomic commit (O-1). |
| **Dependencies** | P3-104. |
| **Estimated complexity** | Low. |
| **Files expected to change** | `app/core/config.py` (`ChunkingSettings`, added to `Settings`); `config/default.yaml` (`chunking:` block); `app/pipelines/ingest_workflow.py` (line 247 construction). |
| **Public interfaces** | `settings.chunking.sentence_tokenizer` exposed; CLI `pam doctor` (`app/cli/entry.py:163`) may report the resolved engine (optional, defer if it grows). |
| **Tests to create** | `test_config.py` (extend): `ChunkingSettings` defaults; env override; invalid value rejected. `test_knowledge_engine.py` or a wiring test: `sentence_tokenizer: "heuristic"` through `from_runtime` reaches the chunker. |
| **Acceptance Criteria** | Config value drives engine selection end-to-end; default `"auto"` reproduces the post-P3-104 behavior; `"heuristic"` = deterministic stdlib path (the rollback position). |
| **Definition of Done** | Config test + wiring test green for both entry points (CLI `entry.py:372`, worker `worker.py:84`); no dead config (every value consumed — L5). |

> **Closure (P3-105, 2026-08-06):** Implemented to spec — no deviation. `ChunkingSettings(sentence_tokenizer: Literal["auto","nltk","heuristic"] = "auto")` added to `config.py` (extra="forbid", matching sibling blocks) and to `Settings` via `default_factory`; `chunking:` block added to `config/default.yaml`; `create_default` now constructs `SemanticChunker(sentence_tokenizer=settings.chunking.sentence_tokenizer)` at `ingest_workflow.py:247`. Both entry points (CLI `entry.py:372`, worker `worker.py:84`) route through that single construction site (L2 confirmed). 3 new `test_config.py` tests (defaults, `PAM_CHUNKING__SENTENCE_TOKENIZER` env override, invalid value rejected at both `ChunkingSettings` and `load_settings`) + 1 wiring test asserting `create_default` propagates `"heuristic"` to a `_HeuristicSentenceTokenizer`; existing tests unchanged. AC verified live: `heuristic` → `_HeuristicSentenceTokenizer`, `auto` → `_NltkSentenceTokenizer` (post-P3-104 behavior preserved); L5 no dead config (single field, consumed at the construction site). Full suite **1005 passed / 31 deselected** (+4, 0 regressions); ruff zero new findings; mypy clean on `config.py` (ingest_workflow findings pre-existing/environmental). Rollback verified (revert → only the 4 new tests fail). See `docs/PHASE_3_MILESTONE_3_1_P3-105_IMPLEMENTATION_REPORT.md`.

---

### P3-106 — Regression + fixture suite (all engine paths)

| Field | Detail |
|-------|--------|
| **Task ID** | P3-106 |
| **Objective** | Prove the milestone's core success criterion — **all existing chunking tests pass with the new tokenizer** — under **all three engine paths** (R-2), and lock sentence behavior with committed fixtures. |
| **Dependencies** | P3-104, P3-105. |
| **Estimated complexity** | Low. |
| **Files expected to change** | `tests/unit/test_sentence_tokenizer.py` (finalize); `tests/unit/test_knowledge_engine.py` (existing tests **unchanged**; new cases added only for new behavior); `tests/integration/test_chunking_pipeline.py` (new); `tests/fixtures/chunking/abbreviations.md`, `tests/fixtures/chunking/cjk.md` (new fixtures, committed per Phase 2 C-4 precedent). |
| **Tests to create** | **Parametrized regression (R-2):** run the full existing `TestSemanticChunking` suite (and all existing chunking-adjacent tests) with `sentence_tokenizer="heuristic"` and `sentence_tokenizer="nltk"` (import-guarded, skipped when the extra is absent) **and** the default `"auto"` — both runtime paths execute whenever nltk is installed (`"auto"` → nltk, plus the explicit `"heuristic"` run); one dedicated boundary test asserting `punkt_tab` reproduces the `"AAAA.BBBB."` byte-exact expectation (D9). Integration: real markdown doc through `IngestionWorkflow` with `"auto"` vs `"heuristic"` → chunk counts equal when nltk absent; performance: 1 MB text split ≤ 1 s (generous ceiling, Baseline §8.4 pattern). |
| **Acceptance Criteria** | AC of §5 all met; full suite green under all three engine paths (R-2); governing byte-exact contract holds; span-reconstruction on committed fixtures per D5 (whitespace normalized at boundaries only). |
| **Definition of Done** | Regression + integration + performance tests green; parametrized suite green under `heuristic`, `nltk`, and `auto` (nltk path import-guarded); fixtures committed; ruff/mypy zero new errors; coverage ≥ 80% (tokenizer suite target ≥ 90%). |

> **Closure (P3-106, 2026-08-06):** Implemented to spec — test-only, no source changes. Committed fixtures `tests/fixtures/chunking/abbreviations.md` + `cjk.md`; `test_sentence_tokenizer.py` finalized (D9 byte-exact boundary test on `punkt_tab`, fixture span-reconstruction over both fixtures × all three engines, 1 MB ≤ 1 s perf for heuristic + nltk); `test_knowledge_engine.py` gained `TestSemanticChunkingAllEnginePaths(TestSemanticChunking)` re-running the full existing 15-test suite under `heuristic`/`nltk`/`auto` (nltk import-guarded; existing tests byte-identical — the one nltk-segmentation-coupled offset test is overridden engine-aware in the subclass, parent unchanged); new `@pytest.mark.integration` `test_chunking_pipeline.py` (real markdown through `IngestionWorkflow`, auto vs heuristic parity — equal counts when nltk absent — plus heuristic determinism through the pipeline). Full default suite **1059 passed / 33 deselected** (baseline 1005/31; +54, 0 regressions); R-2 class **45/45, 0 skips** (nltk present, all three paths real); integration 30 passed / 1 skipped (Tesseract) / 1 pre-existing live-Ollama smoke flake (O-3, untouched); tokenizer coverage **97%** (target ≥ 90%), full **89%** (gate ≥ 80%); ruff/mypy zero new findings (4 remaining `test_knowledge_engine.py` findings pre-existing, shifted +69 lines); rollback verified — revert → exactly **1005 passed / 31 deselected** (P3-105 baseline), restore byte-verified via SHA-256. See `docs/PHASE_3_MILESTONE_3_1_P3-106_IMPLEMENTATION_REPORT.md`. Final implementation task of M3.1.

---

## 5. Tests Required (milestone-level map)

| Layer | Files | Covers |
|-------|-------|--------|
| Unit | `tests/unit/test_sentence_tokenizer.py` (new) | P3-101 factory + engine selection; P3-102 heuristic (abbreviations/ellipses/decimals/quotes/CJK/determinism/span-reconstruction); P3-103 nltk guarded |
| Unit (extend) | `tests/unit/test_knowledge_engine.py` `TestSemanticChunking` | P3-104 sentence-aligned chunking; offsets; byte-exact governing contract; existing cases unchanged |
| Unit (extend) | `tests/unit/test_config.py` | P3-105 `ChunkingSettings` defaults/override/validation |
| Integration | `tests/integration/test_chunking_pipeline.py` (new, `@pytest.mark.integration`) | Real doc through `IngestionWorkflow`; engine parity; CLI + worker reach the new config (L2) |
| Regression (**R-2**) | full existing suite, **parametrized over `heuristic`, `nltk`, `auto`** | Frozen success criterion: **all existing chunking tests pass with the new tokenizer** under every engine path; both runtime paths execute whenever nltk is installed (`"nltk"` and `"auto"`→nltk, plus `"heuristic"`); nltk path import-guarded |
| Performance | within unit suite | ≤ 1 s per 1 MB sentence split |

**Fixtures (committed to `tests/fixtures/chunking/`):** `abbreviations.md`, `cjk.md`. Oversize text generated in-test (not committed).

---

## 6. Cross-Milestone Dependencies

- **Receives:** the completed Phase 2 baseline only — the pinned M3.1 seam is the chunker's existing sentence-split site. No new Phase-2 state is consumed.
- **Feeds forward:** M3.2 (G14 hierarchical chunking) consumes sentence boundaries when it maps `metadata.extra["structure"]` → `DocumentSection.id` → chunk `parent_id` (seam pinned by M2.3); M3.3 (G13 token-aware sizing) sizes per sentence; M3.4 (topic segmentation) embeds sentence windows of 3–5 sentences (05 roadmap §3.4 dependencies list Phase 3.1).
- **Not consumed here:** `metadata.extra["structure"]` is untouched in M3.1 (M3.2 scope).
- **`tiktoken` is out of M3.1 scope (C-3):** M3.1 requires no token counting. Note for M3.3: `tiktoken` is currently importable in the environment but **undeclared** in `pyproject.toml`; M3.3 must formally declare it (or a pure-Python alternative) and preflight wheels per Phase 2 R-5.

---

## 7. Cross-check against available sources (no frozen spec exists)

| Source | Claim | M3.1 disposition |
|--------|-------|------------------|
| MEDD §5 Phase 3 | Deliverable "NLP sentence segmentation (spaCy)" / G12 / **3 days** | Task set covers G12 only; effort 3–4 dev-days reconciles with the 3-day nominal. spaCy naming deviates per D1 (proposed ADR). |
| MEDD §5 Phase 3 success criteria | "Sentence boundaries respect abbreviations (Dr., Mr., U.S.A.)" | AC1/AC2. The other three success criteria map to M3.2/M3.3/M3.4 — **out of scope** (scope guard in §2). |
| MEDD §7.4 | Target architecture "Text → NLP sentence segmentation → heading → section → …" | M3.1 swaps only the sentence step; heading/section/parent steps remain M3.2. |
| MEDD §7.4 interface | `tokenizer: str = "cl100k_base"` | That is the **token-aware** field (G13/M3.3). Not added here — naming decision in §3 (C-1). |
| 05 roadmap §3.1 | Dependencies "spaCy or nltk (spaCy recommended for quality)"; effort 3 days; success criterion "Dr. Smith … splits into 2 sentences (not 6). All existing chunking tests pass" | D1 picks nltk (deviation recorded); effort reconciled; AC1 + §5 regression gate carry the success criterion verbatim under all three engine paths (R-2). |
| Existing regression suite | `tests/unit/test_knowledge_engine.py:129-136` byte-exact `"AAAA.BBBB."` | The governing contract for the sentence path (D5, R-1); chunker offsets math unchanged. |
| Phase 2 spec §5 dependency graph | No Phase 3 edges defined; M2.3 pinned the Phase 3 consumption seam (`metadata.extra["structure"]`) | M3.1 consumes Phase 2 baseline only; the structure seam is deferred to M3.2. Phase 2 R-5 wheel-preflight + C-3 optional-dep DoD conventions adopted. |

**Recorded deviations (pending frozen spec):** D1 (nltk over spaCy) and the `sentence_tokenizer` field name vs MEDD §7.4's `tokenizer` (G13 field). Both are proposed ADRs for the Phase 3 engineering specification.

---

## 8. Rollback Considerations

| Level | Mechanism | Detail |
|-------|-----------|--------|
| Config | `chunking.sentence_tokenizer: "heuristic"` | Deterministic stdlib path, zero new runtime dependencies; the rollback position for nltk (`"auto"` without the extra installed is identical). |
| Dependency | Optional extra only | nltk lives in `[project.optional-dependencies] intelligence`; uninstalling restores the heuristic path — no code change (C-3 DoD). |
| Data | No schema change | `DocumentChunk` and the vector-store schema are untouched; chunker field defaults `"auto"`; additive only. |
| Code | No deprecated branch | No `"regex"` legacy engine value retained (Phase 2 R-4). Strict byte-identical Phase-2 regex behavior, if ever demanded, is reachable only by reverting the commit range. |
| Process | Atomic commits + gates | Each task = one atomic commit (Phase 2 convention); a failing milestone reverts by reverting its commit range; the parametrized regression gate (all existing chunking tests pass unchanged under `heuristic`/`nltk`/`auto`) is the primary safety net. |

---

## 9. Milestone Gate Checklist

- [x] P3-101 protocol + factory reviewed; selection stable; unknown engine → clear error.
- [x] P3-102 heuristic handles abbreviations/ellipses/decimals/quotes/CJK; span-reconstruction per D5 (whitespace normalized at boundaries only).
- [x] P3-103 nltk `punkt_tab` offline; absent → one logged warning + heuristic (C-3 DoD); wheel preflight recorded; `punkt_tab` conformance on the governing fixture verified (D9 behavioral preflight passed).
- [x] P3-104 chunker delegates; `start_char`/`end_char` accurate; default `SemanticChunker()` still constructs; byte-exact `"AAAA.BBBB."` reproduced (R-1).
- [x] P3-105 `chunking.sentence_tokenizer` consumed end-to-end; `ChunkingSettings` + `chunking:` yaml key in the same commit (O-1); CLI + worker both reach it; no dead config.
- [x] P3-106 **all existing chunking tests pass with the new tokenizer under `heuristic`, `nltk`, and `auto`** (R-2; 45/45, 0 skips; nltk path import-guarded); "Dr. Smith…" → 2 sentences; full regression green under every engine path present; coverage 89.03% (tokenizer 97.14%); ruff/mypy zero new errors.
- [x] Rollback verified: `sentence_tokenizer: "heuristic"` + no extra installed → deterministic, zero new deps.
- [x] Documentation: `changelog.md` ([0.8.0] entry), MEDD §7.4 "Current Implementation" paragraph, 01 report chunking status updated.
- [x] Completion report produced before Milestone 3.2 begins; proposed ADR (D1) and the missing-spec caveat recorded for the Phase 3 engineering specification.

---

*End of Milestone 3.1 Implementation Roadmap. Prepared against MEDD §5/§7 and the 05 Development Roadmap pending the frozen Phase 3 engineering specification. Revised 2026-08-05 to resolve Specification Review findings R-1, R-2 and apply C-1, C-2, C-3.*
