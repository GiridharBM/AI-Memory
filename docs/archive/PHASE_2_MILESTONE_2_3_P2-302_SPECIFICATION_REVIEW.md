# Milestone 2.3 — P2-302 Implementation Specification Review

**Reviewed document:** `docs/PHASE_2_MILESTONE_2_3_P2-302_IMPLEMENTATION_SPECIFICATION.md`
**Governing contract:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` v1.1 (🔒 FROZEN 2026-08-01) — §4.1/§4.3, §6, §7, §8 AC1/AC2, §10 R1, §11.1/§11.2, §12, §13, §14; roadmap D1/D4/D6/D9.
**Date:** 2026-08-01
**Review method:** Full read of the P2-302 spec; line-by-line comparison against the frozen engineering spec and roadmap decisions. Algorithm claims verified against live code: `app/infrastructure/semantic_chunking.py` (`_HEADING_PATTERN`, `_split_by_headings`) and `app/infrastructure/ingestion/utils.py` (`clean_text`/`_protect_code_blocks`). **No code implemented.**

---

## 1. Frozen Specification Compliance — PASS

- **File ownership (frozen §11.1 P2-302 row = `structure/detector.py`, DoD "nested ATX → correct tree; fenced `#` not mis-split"):** the spec delivers exactly `_detect_headings` and nothing more. `StructureAnalyzer`/`analyze`, `_detect_blocks`, `_build_tree`, composition-root stubs, `TEXT_BEARING_KINDS`, `MAX_SECTIONS`, and `max_structure_text_bytes` are all explicitly deferred with their owning tasks (§2.2, §6.2) — the boundary is drawn correctly and matches frozen §11.1.
- **Internal API name (frozen §4.3 `_detect_headings(lines)`):** kept verbatim (§6.2).
- **Heading rule (frozen §10 R1 / roadmap D9 `^#{1,6}\s+\S`):** the spec's `^(#{1,6})\s+(\S.*)$` is D9-equivalent for matching (both require 1–6 marks, ≥1 whitespace, then a non-whitespace char) and adds the title capture group. Verified the per-line (no `re.M`) application preserves the frozen strictness (§5.1).
- **Fence-state before heading match (frozen §10 R1 / AC2):** the machine runs before heading evaluation and skips fenced lines (§5.2). Verified against `clean_text._protect_code_blocks` (`utils.py:57-82`): both toggle on `stripped.startswith("```")` — machine and input are consistent by construction.
- **AC1/AC2 (frozen §8):** mapped one-to-one to spec AC1/AC2 with the frozen evidence shapes (hierarchy unit tests; fence fixture).
- **`MAX_HEADING_LEVEL = 6` (frozen §7/D6) and waves (frozen §11.2):** present; P2-302 ‖ P2-303 after P2-301, no intra-milestone dependency introduced.
- **Chunker unchanged (frozen AC5/§9/§14):** the "explicitly not modified" list (§8) and AC7 gate pin it.
- **No config, caps as code constants (frozen §7/L5/D6):** §9 confirms zero config impact.

## 2. Architecture — PASS

- Placement at the frozen §4.3 package path `app/infrastructure/document_intelligence/structure/`, with a minimal package-marker `__init__.py` (importability) — correct.
- Pure module, no module-level mutable state (reentrant per frozen O-2), never raises (frozen §3 failure modes), no wiring this task — consistent with the wave-2 detector role.
- `Heading` is a plain (non-pydantic) mutable dataclass returned by an *internal* function; the domain surface stays `DocumentSection` (P2-301). The frozen spec leaves the intermediate detector→builder representation unspecified, so this is a legitimate implementation detail — and the four-field freeze (risk 7) prevents surface creep.
- Reentrancy note is accurate.

## 3. Dependency Correctness — PASS

- Dependency on P2-301 is correctly characterized as **conceptual** (milestone order): `_detect_headings` returns `Heading` records and does not import the pydantic models; P2-304 performs the record→`DocumentSection` mapping. This does not violate frozen §11.1 (P2-302 dep = P2-301) since the models are the milestone prerequisite and the detector's own deps are stdlib only.
- Zero new packages; stdlib-only (`re`, `dataclasses`, `typing.Sequence`) — consistent with frozen §3 ("pure stdlib parsing", no wheel verification).
- The D1 input-text contract (`lines = exact_text.split("\n")`, post-`clean_text`) is correct: `clean_text` normalizes all newlines to `\n` and dedents headings, so line-start anchoring and the `line_index` seam are sound.

## 4. Interfaces — PASS

- `_detect_headings(lines: Sequence[str]) -> list[Heading]` matches the frozen internal API name; the return record fields (`level`, `line_index`, `title`, `parent`) are internally consistent and sufficient for P2-304 (line index → char offset via the pinned split).
- The `Heading` forward-reference (`parent: Heading | None = None`) is safe under the file's `from __future__ import annotations` convention.
- Import path, contract (never raises, document order / stable R8), and the explicit deferred-API list are all stated — no ambiguity about what belongs to this task.

## 5. Algorithms — PASS

- **D9 rule:** every negative case asserted in §5.1 was independently checked against the regex: `#`, `# `, `#\t` (no `\S`), `#NoSpace` (no `\s+`), `####### X` (only ≤6 marks match, then `\s` fails), indented `  # X` (line-start anchor). All correct.
- **Fence machine:** matches the `clean_text` convention exactly (triple-backtick only, toggle on stripped `startswith("```")`, info string on open, unclosed → rest is code). `~~~` excluded consistently with `clean_text` (frozen §2.2 best-effort).
- **D4 hierarchy:** the stack scan (pop while `top.level >= L`, attach to `stack[-1]`) produces exactly the frozen AC1 shape — nested chain, level-skip (`# A`→`### C` ⇒ `C.parent=A`), sibling detachment, re-rooting — verified by trace.
- **Level clamp (D6):** `min(max(level,1),6)` is correct defense-in-depth; making it a pure helper is the right call for testability given D9 makes >6 unreachable through the regex (risk 3 resolves the apparent tension honestly).
- **Pseudocode (§5.5)** matches the prose §5.1–§5.3 exactly — no drift between normative text and code sketch.

## 6. Acceptance Criteria — PASS

AC1–AC7 are each objectively falsifiable and traceable (frozen AC1/AC2 → AC1/AC2; roadmap D4/D9/D6/D1 → AC3–AC6; frozen §9/§12 gates → AC7). No criterion is untestable or vacuous. The `line_index` seam (AC6) is a useful extra that pins the P2-304 handoff.

## 7. Definition of Done — PASS (one completeness note, see O3)

Every checkbox traces to a frozen requirement or roadmap decision; no invented items. The coverage criterion cites only the ≥80% project gate — see O3 for the missing parser-suite target.

## 8. Testability — PASS

- All unit tests land in the frozen-spec file `tests/unit/test_structure_analysis.py` (§13); inline strings are appropriate for detector tests, and the two committed fixtures (`nested_headings.md`, `fenced_code.md`) match the frozen §13/L6 fixture list and are each exercised.
- The depth-cap test is made meaningful via the `_normalize_heading_level` helper (the one genuinely clever resolution in the spec).
- Regression command matches the frozen §13 matrix; no integration/perf tests this task is the correct split (P2-305/P2-306).

## 9. Rollback — PASS

Additive-only (new package + tests + fixtures); nothing in `app/` references `_detect_headings` yet (verified the only current consumers of the module tree are M2.1/M2.2 metadata/ocr packages — none touch `structure/`), so the single-commit revert is a zero-blast-radius removal. Honest that the `enabled: false` flag rollback (frozen §14) only becomes applicable at P2-305. Aligned with §14 on code/data/dependency levels.

---

## Findings

### O1 — Incorrect rationale in §5.2 (fence inside blockquote/list)

The bullet states: "```` ``` ```` inside a blockquote/list line (e.g. `> ``` `) is **not** a fence toggler because `clean_text` strips then checks `startswith("```")` on the whole line — **the post-`clean_text` text cannot contain such a line**, so the machine and the input are consistent by construction."

The final claim is **false**. Verified against `utils.py:57-82`: `clean_text` does **not** protect `> ``` ` (its stripped form `> ```` ` doesn't start with ```` ``` ````), so the line survives normalization as a blockquote (`_normalize_line` → `_normalize_blockquote`) and **is** present in post-`clean_text` text. The conclusion is nonetheless correct — the detector's own rule (`stripped.startswith("```")`) also treats it as a non-toggle, so machine and input remain consistent — but the stated reason is wrong.

**Fix (one sentence):** replace "the post-`clean_text` text cannot contain such a line" with "``clean_text` also treats it as a non-fence line (it is never code-block-protected), so the detector's rule agrees with the input by construction." Non-blocking: the normative rule (§5.2 first sentence) is correct and unchanged.

### O2 — Imprecise divergence wording in §5.1

The parenthetical "(the divergence is on the `\s+` vs `\s+.\S` content requirement, which is frozen-mandated)" is garbled. The real divergence between the chunker's `^#{1,6}\s+.+` and the detector's `^(#{1,6})\s+(\S.*)$` is the **`.+` vs `\S`** content requirement: the chunker's `.` accepts whitespace-only content after the marks (and its `\s+` can cross a line break), while the detector requires the first content character to be non-whitespace on the same line. Both patterns reject 7 marks, so that sub-claim is right; only the phrase naming the differing token is wrong.

**Fix (one line):** write "the divergence is `.` (chunker) vs `\S` (detector) on the first content character". Non-blocking: matching behavior prescribed in §5.1 is correct.

### O3 — DoD/test strategy omit the frozen parser-suite coverage target

The DoD and §12 cite only "coverage ≥ 80%" (the `fail_under` gate). Frozen §12 requires "coverage ≥ 80% (**parser suite ≥ 90%**)" and §10 R7 targets the parser suite at ≥90%. `structure/detector.py` is new parser surface, so the task DoD should add "detector.py (new parser module) ≥ 90%" — consistent with P2-301's changed-file-at-100% precedent and trivially achievable with the planned tests.

**Fix (one line):** add the parser-suite ≥90% target to the DoD coverage checkbox and §12. Non-blocking: the milestone gate (§12) already enforces it; this closes the task-level gap.

---

## Verdict

✅ **Ready for Implementation**

The spec is algorithmically correct and fully consistent with the frozen M2.3 contract: file ownership, the D9 heading rule, the fence-state machine, the D4 hierarchy scan, the `MAX_HEADING_LEVEL` clamp, the D1 line-index seam, deferred-API boundaries, rollback, and the AC/DoD mappings all check out — with the D9 and fence claims verified against the live chunker and `clean_text` code. The three findings are documentation-level (two wrong rationale sentences, one missing coverage-target reference); none alters the prescribed behavior or the implementation contract, and all have one-line fixes that can be applied during implementation.
