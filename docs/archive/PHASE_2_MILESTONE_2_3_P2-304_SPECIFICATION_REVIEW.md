# Milestone 2.3 — P2-304 Implementation Specification Review

**Reviewed document:** `docs/PHASE_2_MILESTONE_2_3_P2-304_IMPLEMENTATION_SPECIFICATION.md`
**Governing contract:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` v1.1 (🔒 FROZEN 2026-08-01) — §4.1 (normative `StructureAnalyzer.analyze` + public APIs), §4.2 (domain models), §4.3 (package layout + composition root), §5.1/§6 (data flow), §7 (caps / C-4), §8 (R8 stable IDs), §10 R2/R8, §11.1 (P2-304 row), §12, §13, §14; roadmap D1/D4/D5/D6/D9/L6.
**Date:** 2026-08-02
**Review method:** Full read of the P2-304 spec; line-by-line comparison against the frozen engineering spec and roadmap decisions. Algorithm claims verified by hand-tracing against the shipped code: `app/infrastructure/document_intelligence/structure/detector.py` (`_detect_headings` with D4 parent linkage and unhashable `Heading` dataclass; `_detect_blocks` with document-global fence state) and `app/domain/document_intelligence.py` (P2-301 models with offset/slice validators). Section-span, ID, block-attribute, fence/range, and truncation math re-derived independently on sample inputs. Regression blast-radius claims verified via repository grep. **No code implemented.**

---

## 1. Frozen Specification Compliance — PASS

- **File ownership (frozen §11.1 P2-304 row = `structure/detector.py`, DoD "Sections contain blocks; offsets contiguous; degenerate input → empty tree"):** the spec delivers `_build_tree` + `StructureAnalyzer` + the two public entry points appended to the frozen package file, with P2-302/303 code explicitly frozen in place (§2.2, §8 "P2-302/303 code untouched"). `TEXT_BEARING_KINDS`, `enabled` plumbing, the enrichment hook, and the 5 MB cap are deferred with their owning tasks (§2.2, §6.3).
- **Normative interface (frozen §4.1 `StructureAnalyzer.analyze(text, source) -> DocumentStructure`):** kept verbatim (§5.5, §6.1), including the `source` parameter — see O5.
- **Public APIs (frozen §4.1 `analyze_document_structure(text, source)`, `StructureAnalyzer`; §4.3 composition root):** both functions specified with frozen names (§5.7, §6.1) and exposed from `app/infrastructure/document_intelligence/__init__.py` (§8) exactly as frozen §4.3 requires.
- **Internal API (frozen §4.3 `_build_tree(sections)`):** kept verbatim (§5.4, §6.2), taking the assembled section list and returning `DocumentStructure` — the literal reading of the frozen name and of the §5.1 sequence-diagram call `_build_tree(sections) -> nested DocumentStructure`. See O3.
- **Section IDs (roadmap D4, frozen §10 R8):** `s-1` / `s-1-1` path scheme, deterministic from heading order, level-skip → parent path (§5.2) — matches roadmap D4's `# A` → `### C` ⇒ `C.parent_id = "s-1"`, `s-1-1` example.
- **Block IDs (roadmap D5, frozen §15.4):** `b-<section.id>-<n>`, `n` restarting per section (§5.3) — re-derives the frozen §15.4 examples (`s-1` block 1 → `b-s-1-1`; `s-1-1` block 1 → `b-s-1-1-1`) correctly.
- **`MAX_SECTIONS = 10_000` (frozen §7 / C-4):** value, warn + truncate in tree order, never raise — all verbatim (§5.4). Ownership reconciliation verified against the frozen text — see O4.
- **Empty fixture (frozen §13 list):** `tests/fixtures/structure/empty.md` is the last uncreated committed fixture; P2-303's spec explicitly deferred it to P2-304's empty-tree testing. Consistent.
- **`ProcessedDocument` untouched (R-1, frozen §5.4):** explicit not-modified list (§8). Chunker byte-identical (AC5) also pinned (§8).
- **No config keys (frozen §7/L5/D6):** §9 confirms zero config impact; `MAX_SECTIONS` is a code constant, `default.yaml` untouched.
- **Waves (frozen §11.2):** P2-304 is wave 3, consuming both wave-2 detectors — matches the spec's dependency table (§3) and the frozen task-dependency graph (§15.3).

## 2. Architecture — PASS

- Placement at the frozen §4.3 path; the spec's §16 consistency table cross-checks 15 frozen/roadmap elements.
- `StructureAnalyzer` is **stateless** and `get_default_structure_analyzer()` returns a **fresh instance per call** — the strongest reentrancy posture (frozen O-2) and immaterial to callers since the class holds no state. Sound choice over a module singleton.
- Composition-root re-export (§4, §8) is additive and import-cycle-free: `document_intelligence/__init__.py` → `structure.detector` → `app.domain.document_intelligence` → pydantic; no reverse edge exists.
- Failure modes (frozen §3): never-raises by construction — every composed operation (`_detect_headings`, `_detect_blocks`, arithmetic, pydantic construction from already-valid data) is never-raises or validated at the model boundary.
- **No wiring:** `analyze` / `analyze_document_structure` are not called from production this task (P2-305 is the first consumer); rollback is clean-removal. Verified by grep.

## 3. Dependency Correctness — PASS

- Frozen §11.1 lists P2-304 deps = P2-302, P2-303. The spec lists both **plus P2-301 (transitive)** — correct and complete: the builder consumes the P2-301 models directly (constructs `DocumentBlock`/`DocumentSection`/`DocumentStructure`), so the chain P2-301 → P2-302/303 → P2-304 is fully realized.
- Dependency on P2-302 is real and sound: `_detect_headings` supplies `level`, `line_index`, `title`, and the **pre-resolved D4 `parent` linkage**; the builder consumes all four and re-derives no hierarchy. The spec correctly notes `Heading` is **unhashable** (mutable `@dataclass`, `eq=True`, `frozen=False` ⇒ `__hash__ = None`) and keys the ID map by `id(heading)` (§5.5) — verified against the live dataclass.
- Dependency on P2-303 is real: `_detect_blocks` per-section body ranges; `Block.type` (the `BlockKind` Literal) equals the domain `BlockType` strings, so the verbatim copy into `DocumentBlock` is validated.
- Zero new packages; the only new stdlib import is `warnings` (frozen §3 "pure stdlib parsing" holds).
- The D1 seam (identical `text.split("\n")` + `pos += len(line) + 1`) is stated as **normative and exclusive** ("any other splitter is forbidden") — the correct R2 drift guard, consistent with P2-302's `line_index` and P2-303's offset accumulation.

## 4. Interfaces — PASS

- `analyze(self, text, source) -> DocumentStructure`, `analyze_document_structure(text, source)`, `get_default_structure_analyzer()`, and `_build_tree(sections)` all match the frozen §4.1/§4.3 names and shapes.
- The contract (never raises; D1 exact text; deterministic output R8; empty-on-degenerate; `MAX_SECTIONS` truncation with `UserWarning`) is unambiguous.
- The deferred-API list (§6.3) — `TEXT_BEARING_KINDS`, `max_structure_text_bytes`, `enabled` settings, the `_run_routed_processor` hook, any `ProcessedDocument` change — cleanly bounds scope and matches frozen §11.1 ownership.
- Both import paths (composition root + `structure.detector`) are stated, so P2-305's single-import wiring is specified in advance.

## 5. Algorithms — PASS

Hand-traced independently on representative inputs (nested sections, level-skip, preamble + fence, unclosed fence, trailing heading line); all claims hold:

- **Section spans (§5.1):** `start_char` at the heading line, `end_char` at the next heading line (else `len(text)`), body range `[heading_end, next_heading_start)` clamped to `len(text)`. Re-derived on `"# A\npara1\n## B\npara2\n"`: A=`[0,10)`, B=`[10,21)`, contiguous (`A.end == B.start`), last section ends at `len(text)`, bodies exclude both heading lines. The `min(..., len(text))` clamp correctly handles a heading as the final line (empty body → `[]` blocks, no invalid range).
- **Section assembly (§5.2):** `child_counts` keyed by parent id (root `None`) reproduces roadmap D4 exactly, including level-skip and sibling numbering; `parent_id` is read from the P2-302-pre-resolved `heading.parent`, so no hierarchy re-derivation.
- **Block assignment (§5.3):** D5 numbering re-derived (`s-1` → `b-s-1-1`, `s-1-1` → `b-s-1-1-1`); verbatim `type`/`text`/offsets satisfy the P2-301 `DocumentBlock` slice validator by construction.
- **Fence/range equivalence (§5.3):** the invariant argument is **sound**. Section boundaries sit on heading lines; `_detect_headings` never emits a heading inside a fence; and an unclosed fence *suppresses* subsequent `#` lines (they become fence content), so a fence can never straddle a section boundary. Fresh per-section `_detect_blocks` state is therefore correct. Traced the unclosed-fence case (`# A\n` + unclosed fence) — one `code` block in A's section, later `# B` correctly swallowed as fence content, not a heading.
- **`_build_tree` (§5.4):** warn + truncate to the first `MAX_SECTIONS`; parents precede children in document order, so the kept prefix preserves parent-reference validity. Degenerate → `DocumentStructure(sections=[])`.
- **Complexity:** `_detect_headings` O(n) + `line_starts` O(n) + per-section `_detect_blocks` summing to O(n) (body ranges partition) — genuinely O(n), matching the frozen §3 ceiling for P2-306 to assert. See O6 for the constant-factor note.

## 6. Acceptance Criteria — PASS

AC1–AC8 each map to a frozen criterion or roadmap decision and name concrete falsifiable evidence: AC1 (blocks in sections + D5 IDs, roadmap D5), AC2 (contiguous spans + slice integrity, frozen §9/R2), AC3 (D4 IDs + stability, frozen §8 R8), AC4 (degenerate → empty, frozen §9/§6), AC5 (`MAX_SECTIONS` truncation, frozen §7/C-4), AC6 (entry points + composition root, frozen §4.1/§4.3), AC7 (preamble exclusion, pinned limitation), AC8 (no out-of-scope changes + chunker byte-identical, frozen §9/§12/AC5). No criterion is vacuous.

## 7. Definition of Done — PASS

Every checkbox traces to a frozen requirement or roadmap decision, including the parser-suite target (`detector.py` ≥ 90%, frozen §12/R7 — the P2-302 O3 lesson is applied), the composition-root checkbox (frozen §4.3), the committed `empty.md` fixture (frozen §13), and the single-atomic-commit item (§14). No invented items.

## 8. Testability — PASS

- All unit tests land in the frozen-spec file `tests/unit/test_structure_analysis.py`; the nine planned classes map one-to-one onto the roadmap P2-304 "Tests required" list (correct blocks, contiguous offsets, empty input, malformed → best-effort, `MAX_SECTIONS` truncation, ID stability) plus entry-point/`source`/preamble/R-1-boundary tests.
- The `MAX_SECTIONS` test generates `"# h\n" * 10_001` inline (~20 KB) — the right mechanism (no 10k-line committed fixture); `pytest.warns` on the truncation path is the correct assertion.
- Existing structure fixtures fed **through `analyze()`** (not `_detect_*` directly) exercises the full assembly path end-to-end — stronger than unit-level only.
- Correct split: no integration tests this task (P2-305 owns the ingestion path), no perf tests (P2-306 owns cap/timing); the regression command matches the frozen §13 matrix.
- One forward note (O1): the AC-evidence mapping implies P2-305's fixtures must contain headings.

## 9. Rollback — PASS

Additive-only (append to an existing module + a two-line composition-root re-export + tests + one 0-byte fixture); verified by grep that **nothing in `app/` calls the analyzer yet**, so the single-atomic-commit revert (§14) is a zero-blast-radius removal. Honest that the `enabled: false` flag rollback only becomes applicable at P2-305. Aligned with §14 on data (no persistence touched), code (no legacy branch), and dependency (none new) levels.

---

## Findings

### O1 — Frozen AC4's "non-empty `extra["structure"]`" depends on P2-305 fixture choice

P2-304 correctly pins "no headings → `DocumentStructure(sections=[])`" (`TestDegenerate`). Frozen §8 AC4's integration test asserts a **non-empty** `extra["structure"]` "with stable section IDs" — so P2-305's markdown **and** text integration fixtures must **contain ATX headings**. A heading-less text file would serialize `{"sections": []}` (valid, but empty) and fail that assertion. This is a forward note to P2-305, not a P2-304 defect; the behavior is now pinned and documented here.

### O2 — Preamble exclusion is a real semantic choice with a Phase-3 consequence

Text before the first heading is dropped from the tree (§5.6, `TestPreambleDropped`). This is inherent to the frozen models (a `DocumentSection` requires `title`/`level` from a heading) and correctly documented — but the review records the consequence: under Phase-3 hierarchical chunking (MEDD G14, which maps `DocumentSection.id` → chunk `parent_id`), preamble chunks would have no section parent. Acceptable and documented; flag for the Phase-3 contract note, not this milestone.

### O3 — `_build_tree(sections)` is the literal reading; assembly lives in `analyze`

Frozen §4.3 names `_build_tree(sections)` and §5.1's sequence diagram has it return the nested `DocumentStructure`. The spec honors that literal signature (input = assembled sections, output = structure) and puts the heading→section assembly (IDs, parents, spans, blocks) in `analyze`. The alternative — moving ID/parent assembly into `_build_tree` — would reshape the frozen API name/signature, so the spec's reading is the correct one. Confirmed, not a defect; noted so a reviewer of the eventual diff expects the assembly in `analyze`.

### O4 — `MAX_SECTIONS` ownership reconciliation verified against the frozen text

The frozen text attributes the cap to **both** §12 (checklist "P2-304 tree builder: … `MAX_HEADING_LEVEL`/`MAX_SECTIONS` caps enforced (C-4)") and §11.1 (P2-306 row "…`MAX_SECTIONS` enforced; O(n) timing test"). The spec assigns truncation to P2-304 (the tree-builder row, where the operation inherently lives) and lets P2-306 retain the 5 MB cap + timing verification — reading P2-306's "enforced" as verify-enforcement. This is the coherent reading and is explicitly documented in §16. Confirmed. `MAX_HEADING_LEVEL` needs no new code (P2-302 clamp + P2-301 `Field(le=6)`) — also correctly documented (§5.2).

### O5 — `source` accepted-but-unused is correct

Frozen §4.1 mandates `analyze(text, source)`; no frozen model field consumes `source`. The spec documents it as a contract parameter for the shared M2.4/2.5/2.6 call site (§5.6) — the right call, and it preempts a reviewer flagging it as dead code. Confirmed.

### O6 — Per-section `_detect_blocks` calls: O(n) but with a constant-factor note

One `_detect_blocks` invocation per section means a pathological 10,000-section, ~1 MB document costs ~10,000 function calls (each with a fresh `in_ranges` closure). Total work remains O(n) and the ranges partition the body, so the P2-306 timing ceiling (≤ 1 s / 1 MB) absorbs it comfortably; no batching is warranted. Noted for P2-306's timing test to use a section-dense (not just text-dense) sample if it wants to measure worst case.

---

## Verdict

✅ **Ready for Implementation**

The spec is fully consistent with the frozen M2.3 contract: file ownership, the normative `StructureAnalyzer.analyze` signature and public APIs, the `_build_tree(sections)` internal API, the composition-root exposure, the D4/D5 ID schemes (re-derived against frozen §15.4), contiguous span semantics, `MAX_SECTIONS` truncation, the empty-fixture ownership, rollback, and the AC/DoD mappings all check out — with the section-span, ID, block-attribute, fence/range-equivalence, and truncation claims independently hand-traced against the shipped `detector.py` and P2-301 models. All six findings are **non-blocking**: two are forward notes to other tasks (O1 P2-305 fixture choice; O2 Phase-3 contract), two are confirmed-correct readings worth recording (O3 `_build_tree` semantics; O4 `MAX_SECTIONS` reconciliation), and two are documentation/constant-factor notes (O5 `source`; O6 per-section call overhead). No finding changes the prescribed behavior or the implementation contract.
