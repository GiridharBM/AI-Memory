# Milestone 3.1 — NLP Sentence Segmentation (G12): Specification Review

**Subject under review:** `docs/PHASE_3_MILESTONE_3_1_IMPLEMENTATION_ROADMAP.md` (the proposed M3.1 engineering specification — no frozen Phase 3 spec exists in the repo).
**Reviewed against:** the live repository (verified 2026-08-05), MEDD §5/§7.3/§7.4, `docs/05_Development_Roadmap.md` §3.1, and Phase 2 conventions.
**Review mode:** read-only. No code or production files modified.
**Verdict:** **APPROVED** — blocking findings R-1 and R-2 remediated in the spec (re-review 2026-08-05, §5); Recommended C-1/C-2/C-3 applied; Observations O-1/O-2/O-3 carry through unchanged.
**Original verdict (2026-08-05):** NEEDS SPECIFICATION REMEDIATION — 2 Required, 3 Recommended, 3 Observations.

---

## 1. Verification Matrix (evidence from the live repository)

| Dimension | Verdict | Evidence |
|-----------|---------|----------|
| **Architecture** | PASS | Sentence splitting exists at exactly one site: `app/infrastructure/semantic_chunking.py:14` (`_SENTENCE_END`) consumed only by `_split_by_sentences` (lines 138–158). A repo-wide search for `sent_tokenize`/`spacy`/`nltk`/`tiktoken`/`tokeniz` found **zero** other tokenizer code. Single integration point claim (D2) confirmed. |
| **Public interfaces** | PASS | No existing symbol named `SentenceTokenizer`/`get_sentence_tokenizer`/`sentence_tokenizer` (grep-confirmed). `SemanticChunker` (line 19) is a `@dataclass`; adding a field with a default is backward compatible. `DocumentChunk` (`app/domain/semantic_chunking.py:8-18`) is untouched. |
| **Dependency graph** | PASS | `pyproject.toml` has no `nltk`/`spaCy`; the optional `intelligence` extra exists (lines 30–38) — adding `nltk>=3.9` there is consistent. `nltk` is **not** installed in the current venv, so default `"auto"` resolves to the heuristic path deterministically. |
| **Rollback guarantees** | PASS (with note) | Config rollback (`chunking.sentence_tokenizer: "heuristic"` + extra uninstalled → zero new deps) is honest. Byte-identical Phase-2 output requires a commit revert, correctly stated; consistent with Phase 2 R-4 (no deprecated `"regex"` branch). No schema change; `DocumentChunk`/vector-store untouched. |
| **Acceptance Criteria** | **FAIL** | The identity contract `"".join(split(text)) == text` (P3-102, P3-106) is incompatible with whitespace-consuming sentence splitters and with the frozen regression success criterion (see Finding R-1). |
| **Definition of Done** | **FAIL** | The regression gate does not require the full existing suite to pass under **both** engines, although default `"auto"` switches to nltk whenever the extra is installed (Finding R-2). |
| **Runtime wiring** | PASS | Both production entry points construct the workflow through `IngestionWorkflow.create_default(settings)` → `from_runtime` (returns `cls.from_runtime(...)` at `app/pipelines/ingest_workflow.py:238`, `SemanticChunker()` at line 247): CLI `app/cli/entry.py:372`, worker `app/queue/worker.py:84`. P3-105 plumbing through `from_runtime` reaches both. |
| **Existing pipeline compatibility** | PASS | Chunk invocation (`ingest_workflow.py:749-753`) and `chunk(text, source, source_type)` signature are unchanged. Heading/paragraph/overlap logic untouched (P3-104). No stage reordering. |
| **Phase 2 compatibility** | PASS | M3.1 does not read `metadata.extra["structure"]` (that seam stays M3.2/G14), touches no processor, no `ProcessedDocument` field, no intelligence module. Additive-only. |
| **Configuration ownership** | PASS (with notes) | `Settings` is `extra="forbid"` (`app/core/config.py:381-385`); a new top-level `chunking:` block is safe **only** if `ChunkingSettings` lands in the same change (P3-105 does — see Observation O-1). No existing `chunking:`/chunk config exists; `ProcessingSettings` (lines 173–187) is post-processing file movement, so a new block is correct. `pam doctor` exists (`entry.py:163`) making the optional hint feasible. |
| **Testability** | **FAIL** | See Findings R-1/R-2. The byte-exact regression case is the governing contract and the spec's whitespace/offsets claims conflict with it. |
| **Documentation consistency** | PASS | MEDD §7.4 "Current Implementation" (lines 2372–2373) states the chunker is unchanged — M3.1 legitimately changes it and the roadmap's documentation updates cover MEDD/01 report/changelog. Naming divergence from MEDD §7.4 `tokenizer` (G13) is already flagged. |

---

## 2. Findings

### REQUIRED

#### R-1 — Whitespace/offsets contract is internally inconsistent and conflicts with the frozen regression success criterion

**Classification:** Acceptance Criteria + Testability + Rollback violation risk (invalid assumption about the existing test suite).

**Why:** Two spec claims cannot both hold:

1. P3-102/P3-106 assert the tokenizer preserves source identity: `"".join(split(text)) == text`.
2. D5 and P3-104 assert `_split_by_sentences` offset math is **unchanged**, and the frozen success criterion (05 roadmap §3.1) requires **all existing chunking tests pass with the new tokenizer**.

The existing regex `(?<=[.!?])\s+(?=[A-Z\d])` **consumes** inter-sentence whitespace; `_split_by_sentences` re-joins with a single space (`semantic_chunking.py:148`). The live test `tests/unit/test_knowledge_engine.py:129-136` (`test_chunk_overlap_uses_original_predecessor`) asserts **byte-exact** output `"AAAA.BBBB."` that derives from exactly this whitespace-consuming split + single-space join. A whitespace-preserving tokenizer (required to satisfy `"".join == text`) would force a changed join path, drift `end_char` by trailing-whitespace counts, and break the byte-exact assertion (and the `chunk.start_char`/`end_char` accuracy claim). The spec cannot have identity-with-source **and** unchanged offset math **and** the byte-exact test green.

**Minimum spec-only fix:** Pin the tokenizer contract to **whitespace-delimited sentences** — each returned sentence is the text span *between* sentence boundaries with inter-sentence whitespace consumed (matching both engines: the heuristic and `punkt_tab` both drop boundary whitespace). Replace the identity AC with a whitespace-normalized equivalence claim (e.g., `" ".join(split(text)) == " ".join(text.split())`), and declare `test_chunk_overlap_uses_original_predecessor` the governing byte-exact regression contract for the sentence path.

#### R-2 — Regression gate must run the full existing suite under **both** engine paths

**Classification:** Definition of Done + Testability gap (missing test coverage of a runtime-selected path).

**Why:** Default `"auto"` resolves to nltk `punkt_tab` whenever the `intelligence` extra is installed (and the extra is the intended install mode). The roadmap's regression gate (P3-106 / gate checklist) only runs the suite once (default `"auto"`, which today is the heuristic since nltk is absent). "All existing chunking tests pass with the new tokenizer" is therefore only ever proven for one of the two engines — the nltk path is unproven, and `punkt_tab` boundary behavior on the byte-exact fixture is exactly the case most likely to differ.

**Minimum spec-only fix:** Parametrize the sentence-path regression over both engines when available — run the full `TestSemanticChunking` suite with `sentence_tokenizer="heuristic"` **and** `sentence_tokenizer="nltk"` (latter import-guarded/skipped when the extra is absent), and add one dedicated boundary test asserting `punkt_tab` reproduces the `"AAAA.BBBB."` byte-exact expectation. Note the punt_tab caveat in the DoD.

---

### RECOMMENDED

#### C-1 — Optional-extra naming mismatch (`chunking` config vs `intelligence` extra)

**Classification:** Configuration ownership (clarity, not blocking).

**Why:** P3-103 places `nltk` in the `intelligence` optional extra while P3-105 creates a core-pipeline `chunking:` top-level config block. The dependency's install home and the feature's config home describe different subsystems. Reusing the existing extra avoids a second extra and keeps "no new required dep", so this is acceptable — but it should be stated.

**Minimum spec-only fix:** One sentence in P3-103/D4: "nltk reuses the `intelligence` extra (single shared optional-extras surface; a `chunking` extra is not created)."

#### C-2 — Field naming reconciliation vs MEDD §7.4

**Classification:** Documentation consistency (clarity).

**Why:** MEDD §7.4's target interface declares `tokenizer: str = "cl100k_base"` (G13, token-aware). M3.1 proposes `sentence_tokenizer` (G12). The roadmap already flags this; the future Phase 3 spec should ratify `sentence_tokenizer` for G12 and reserve `tokenizer`/`max_chunk_tokens` for G13 to avoid two spellings of the same concept.

**Minimum spec-only fix:** Record the ratified names in the roadmap's naming note so M3.3 inherits them.

#### C-3 — `tiktoken` present in the environment but undeclared

**Classification:** Missing-dependency note (out of M3.1 scope).

**Why:** Verified: `tiktoken` imports successfully in the current venv but is absent from `pyproject.toml`. MEDD §7.4 names it for token counting (G13). M3.1 does not need it; M3.3 must formally declare it (or a pure-Python alternative) and preflight wheels.

**Minimum spec-only fix:** Add an explicit note in the roadmap's cross-milestone section that M3.3 must declare `tiktoken` (currently an undeclared transitive), no action in M3.1.

---

### OBSERVATIONS (no change required)

- **O-1** — `Settings` is `extra="forbid"` (config.py:381-385): the `chunking:` yaml block and `ChunkingSettings` must land in the same atomic commit (P3-105 already couples them; stated so the implementer does not split them).
- **O-2** — Current environment (nltk absent) means default `"auto"` is the heuristic: deterministic, no behavior surprise on upgrade without the extra.
- **O-3** — `pam doctor` (entry.py:163) exists; the P3-105 optional doctor hint is feasible as specified.

---

## 3. Cross-check summary

| Source | Checked | Result |
|--------|---------|--------|
| MEDD §5 Phase 3 (G12, 3 days) | Effort/scope reconciliation | Consistent; M3.1 covers G12 only |
| MEDD §7.3 / 05 roadmap §3.1 consumption seam | No `structure` consumption in M3.1 | Consistent (deferred to M3.2) |
| MEDD §7.4 interface + target architecture | Sentence-step swap only | Consistent; naming note required (C-2) |
| Phase 2 §5 dependency graph / R-4 / C-3 conventions | Optional-dep + no-legacy-branch pattern | Consistent |
| Frozen success criterion: "all existing chunking tests pass with the new tokenizer" | `test_knowledge_engine.py:129-136` byte-exact case | **Conflicts with R-1** — the governing contract must be pinned |

---

## 4. Verdict

**NEEDS SPECIFICATION REMEDIATION** *(superseded — see §5)*

The architecture, interfaces, dependency graph, runtime wiring, pipeline/Phase-2 compatibility, and rollback position are sound and verified. Blocking issues are limited to the **whitespace/offsets contract** (R-1: identity-with-source claim contradicts the byte-exact existing test `test_knowledge_engine.py:129-136` and the unchanged-offset-math assumption) and the **regression gate** (R-2: full suite must pass under both `heuristic` and `nltk` engines). Both are spec-only fixes in `docs/PHASE_3_MILESTONE_3_1_IMPLEMENTATION_ROADMAP.md` — no production code exists yet and none is required to remediate. Re-review after R-1/R-2 are applied.

---

## 5. Remediation Verification (re-review — APPROVED)

**Subject:** `docs/PHASE_3_MILESTONE_3_1_IMPLEMENTATION_ROADMAP.md` (revised 2026-08-05). **Mode:** read-only, verified live against the repository; no files other than the spec and this review were modified.

### R-1 — resolved

| Check | Result |
|-------|--------|
| Identity contract replaced | D5 now states a **contiguous-span contract** (`text == s₁ + w₁ + s₂ + … + wₙ₋₁ + sₙ`, whitespace-only separators `wᵢ` consumed at boundaries) plus "whitespace may be normalized **only at sentence boundaries**". The old `"".join(split)==text` AC is gone from P3-102/P3-106; P3-102 AC now says "Whitespace may be normalized during sentence splitting, at sentence boundaries only (D5)." |
| Contract matches both engines | `_SENTENCE_END` at `semantic_chunking.py:14` consumes the matched `\s+` in the split; `punkt_tab` drops boundary whitespace. Both satisfy the span+separator form. |
| Offset math & re-join preserved | D5/D5a keep the single-space re-join (`semantic_chunking.py:148`) and `start_char`/`end_char` math unchanged; verified consistent by direct trace below. |
| Governing byte-exact contract pinned | D5 names `tests/unit/test_knowledge_engine.py:129-136` (`test_chunk_overlap_uses_original_predecessor`, asserting `"AAAA.BBBB."`) the governing regression contract for the sentence path under every engine. |

**Live trace confirming the governing contract (re-run 2026-08-05):** `_SENTENCE_END.split("AAAA. BBBB. CCCC. DDDD.")` → `["AAAA.", "BBBB.", "CCCC.", "DDDD."]` (whitespace consumed). In `_split_by_sentences`, `5+5+1 > max_chunk_chars=5` forces each sentence into its own chunk, so no space re-join occurs on this path; `_apply_overlap` prepends `previous.text[-8:] + current` → `"AAAA.BBBB."`, `"BBBB.CCCC."`, `"CCCC.DDDD."` — byte-exact as asserted. Full `TestSemanticChunking` suite re-run: **12 passed, 72 deselected** (baseline intact, no behavior change).

### R-2 — resolved

| Check | Result |
|-------|--------|
| Three-engine parametrization | P3-106 now requires the full existing chunking suite under `"heuristic"`, `"nltk"` (import-guarded), **and** default `"auto"`; §5 regression row and §9 gate checklist carry the same requirement. |
| Both runtime paths when nltk installed | Explicit: when nltk is present, `"auto"`→nltk plus the explicit `"heuristic"` run both execute — the nltk path is no longer unproven. |
| Dedicated punkt_tab boundary test | One boundary test asserts `punkt_tab` reproduces the `"AAAA.BBBB."` byte-exact expectation. |
| punt_tab caveat acknowledged | D9 adds a wave-0 behavioral preflight: on divergence, `"auto"` pins to the heuristic and nltk stays explicit opt-in, so the frozen success criterion remains provable with zero production workaround. |

### Recommended (C-1, C-2, C-3) — applied

- C-1: D4/P3-103 state nltk reuses the existing `intelligence` extra (single shared optional-extras surface; no `chunking` extra).
- C-2: §3 naming decision ratifies `sentence_tokenizer` for G12 and reserves `tokenizer`/`max_chunk_tokens` (MEDD §7.4, G13) for M3.3; §7 records the deviation.
- C-3: §6 note that `tiktoken` is importable but undeclared; M3.3 must declare it formally (or a pure-Python alternative) and preflight wheels. No M3.1 action.

### Observations — carried through, no change required

O-1 (config key + class same commit), O-2 (nltk absent → `"auto"` is heuristic today; re-verified live: `import nltk` fails, `import tiktoken` succeeds), O-3 (`pam doctor` at `entry.py:163`).

### Re-verified live facts (unchanged from §1)

`SemanticChunker()` at `ingest_workflow.py:247`; `chunk()` invoked 749–753; `create_default(settings)` at `entry.py:372` and `worker.py:84`; `Settings` `extra="forbid"` at `config.py:381–385`; `pyproject.toml` `intelligence` extra lines 30–38, no `nltk`/`spaCy`/`tiktoken` declared.

### Verdict

**APPROVED.** The revised specification is internally consistent, matches the live repository, and every blocking finding is resolved by spec-only changes. No further specification remediation required.

---

*End of Milestone 3.1 Specification Review. Read-only; no files modified.*
