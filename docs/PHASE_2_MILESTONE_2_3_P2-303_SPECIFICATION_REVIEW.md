# Milestone 2.3 — P2-303 Implementation Specification Review

**Reviewed document:** `docs/PHASE_2_MILESTONE_2_3_P2-303_IMPLEMENTATION_SPECIFICATION.md`
**Governing contract:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` v1.1 (🔒 FROZEN 2026-08-01) — §4.3 (internal API `_detect_blocks`), §6 (data flow), §7 (R2 offsets), §8 AC3, §10 R1/R2, §11.1 (P2-303 row), §11.2 (waves), §12, §13, §14; roadmap D1/D4/D5/D9/L6.
**Date:** 2026-08-01
**Review method:** Full read of the P2-303 spec; line-by-line comparison against the frozen engineering spec and roadmap decisions. Algorithm claims verified against live code: `app/infrastructure/ingestion/utils.py` (`clean_text`, `_protect_code_blocks`, `_normalize_line`, `_LIST_PATTERN`, `_TABLE_SEPARATOR_PATTERN`) and the shipped P2-302 `app/infrastructure/document_intelligence/structure/detector.py` (`_HEADING_RE`, fence-toggle rule). Regression blast-radius claims verified via repository grep (no production caller of `_detect_blocks` exists). **No code implemented.**

---

## 1. Frozen Specification Compliance — PASS

- **File ownership (frozen §11.1 P2-303 row = `structure/detector.py`, DoD "Blocks typed with accurate char offsets"):** the spec delivers exactly `_detect_blocks` + `Block` appended to the frozen package file, with P2-302 code explicitly frozen in place (§2.2, §8 "P2-302 code untouched"). `_build_tree`, `analyze`, `StructureAnalyzer`, composition root, `TEXT_BEARING_KINDS`, `MAX_SECTIONS`, `max_structure_text_bytes` are all deferred with their owning tasks (§2.2, §6.2) — the boundary matches frozen §11.1 exactly.
- **Internal API name (frozen §4.3 `_detect_blocks(text, ranges)`):** kept verbatim (§6.2).
- **Five block types (frozen §2.1 / §4.2 `DocumentBlock.type`):** `BlockKind = Literal["paragraph", "list", "code", "blockquote", "table"]` matches the frozen strings character-for-character (§6.1).
- **Accurate offsets (frozen §8 AC3 / §10 R2):** literal-slice invariant `text[start:end] == block.text`, half-open `[start, end)`, offsets relative to the exact analyzed text (D1 seam, §5.3) — matches the P2-301 `DocumentBlock` validator contract and frozen R2.
- **Fenced `#` never mis-split (frozen §8 AC2 / roadmap D9):** fence toggle runs before range membership and before heading evaluation (§5.2 items 1–2), reusing the P2-302 toggle rule; AC6 adds a consistency test across both detectors. D9 heading skip (`_HEADING_RE` reused, not re-copied) keeps the block detector line-start-strict.
- **`clean_text`-normalized tables (roadmap P2-303 "after clean_text normalization"):** §5.2 item 8 detects tables on the normalized form; the boundary test (§12) pins the seam. Verified against `_normalize_line` (`utils.py:101-119`): classification order heading → list → blockquote → table → paragraph is preserved.
- **Chunker unchanged (frozen AC5/§9/§14):** the explicit not-modified list (§8) and AC8 pin `semantic_chunking.py` byte-identical.
- **No config, caps as code constants (frozen §7/L5/D6):** §9 confirms zero config impact; `MAX_SECTIONS`/`max_structure_text_bytes` correctly deferred to P2-305/306.
- **Waves (frozen §11.2):** P2-303 is runtime-independent of P2-302 (ranges supplied by P2-304) while appending to the same module — consistent with wave 2 `P2-302 ‖ P2-303`.

## 2. Architecture — PASS

- Placement at the frozen §4.3 path, appended to the existing `structure/detector.py`; the spec's own §16 consistency table cross-checks all 15 frozen elements.
- Pure function, no module-level mutable state (reentrant per frozen O-2), never raises (frozen §3 failure modes); all state (`in_fence`, run buffers, `pos`) is call-local. The pseudocode structure supports this.
- Classification regexes are **local copies, not imports** (§4 documented decision) — correct: `structure/` must not reach into `ingestion/` private names; the boundary test catches drift at the seam. The pinned strings in §5.1 are byte-identical to `utils.py:11`/`utils.py:13` (verified).
- **No wiring** — nothing in `app/` calls `_detect_blocks` this task; P2-304 is the first consumer. Verified by grep: no production reference exists. Rollback is therefore clean-removal.
- Reentrancy and failure-mode notes are accurate.

## 3. Dependency Correctness — PASS

- Dependency on P2-301 is correctly characterized as **conceptual**: `_detect_blocks` returns plain `Block` records and does not import the pydantic models; P2-304 maps `Block` → `DocumentBlock` (adding `block_id` per D5). This satisfies frozen §11.1 (P2-303 dep = P2-301) without a runtime coupling.
- Dependency on P2-302 is **real and sound**: same module; `_HEADING_RE` is genuinely *reused* (module-level constant), so the heading-skip rule can never drift from P2-302; the fence-toggle rule is re-implemented identically (`stripped.startswith("```")`).
- Zero new packages; stdlib-only (`re`, `dataclasses`, `typing`, `collections.abc.Sequence`) — consistent with frozen §3 "pure stdlib parsing".
- The D1 input contract (post-`clean_text` text, `text.split("\n")` + offset accumulation, ranges into that same text) is correct: `clean_text` normalizes newlines and strips the document, so line-start anchoring and offset accumulation are sound; P2-304 derives ranges on the identical split (frozen R2 drift guard).

## 4. Interfaces — PASS

- `_detect_blocks(text: str, ranges: Sequence[tuple[int, int]]) -> list[Block]` matches the frozen internal API name and shape.
- `Block` (`type`, `text`, `start_char`, `end_char`) is a plain mutable dataclass; **deliberately id-less** — correct, because `block_id` (`b-<section.id>-<n>`, roadmap D5) requires the owning section id, which only exists after P2-304 builds the tree. Assigning ids here would couple the detector to tree structure (the spec's risk 5 says so explicitly).
- `BlockKind` mirrors the domain `BlockType` strings without importing pydantic; the domain surface stays `DocumentSection`/`DocumentBlock` (P2-301).
- Contract (never raises, non-overlapping, document order / stable R8, empty ranges → `[]`) is unambiguous; the deferred-API list (§6.2) removes any doubt about scope.

## 5. Algorithms — PASS (two reference-sketch defects; see O1, O2)

- **Classification precedence (§5.2):** the 9-step order is consistent with `_normalize_line` for the non-fence rules (heading before list before blockquote before table before paragraph; blank first). The list-continuation condition (`run_type == "list" and not startswith((">", "|"))`) matches the prose "non-blank, non-special line" — heading/fence/blank are already excluded upstream; blockquote (`>`) and pipe-run (`|`) are the only remaining specials, and both correctly break continuation.
- **Offsets (§5.3):** single-scan `pos += len(line) + 1` accumulation over `text.split("\n")` (the exact split P2-302 pins and P2-304 reuses); `end_char = start + len(joined)` guarantees the literal-slice invariant by construction, matching the P2-301 `DocumentBlock` validator (start inclusive / end exclusive). Range-edge flushing and per-line membership prevent cross-section blocks; the fence/range invariant (no heading inside a fence ⇒ no range boundary inside a fence) is sound.
- **Table verdict (§5.2 item 8):** the prose is correct — buffer the whole `|`-leading run, emit `table` iff ≥ 1 separator row, else `paragraph`; a lone pipe line with no separator is a paragraph. The single-column separator edge (`|:---|` does not match `_TABLE_SEPARATOR_RE`, which requires ≥ 2 columns) is inherited from `utils.py:13` and is consistent with `clean_text` — not a defect of this spec.
- **Fence machine:** identical toggle rule to `_detect_headings`; code blocks span open→close fence lines inclusive; unclosed → to end of text; `~~~` excluded consistently (frozen §2.2 best-effort). AC6's cross-detector consistency test is the right guarantee.
- **Pseudocode (§5.4):** see O1 (pipe-run flush placement) and O2 (closure rebinding) — both are defects *in the sketch only*; the normative prose and ACs are correct and unambiguous.

## 6. Acceptance Criteria — PASS

AC1–AC8 are each objectively falsifiable and traceable: AC1 (five types, frozen AC3), AC2 (slice integrity, R2), AC3 (list nesting/continuation, roadmap + R1), AC4 (blockquote, roadmap), AC5 (tables on normalized form + clean_text boundary, roadmap), AC6 (fence consistency, frozen AC2), AC7 (paragraph/range semantics, roadmap/R2), AC8 (no out-of-scope changes + chunker byte-identical + green suite, frozen §9/§12). Evidence column names concrete test classes and gates; no criterion is vacuous.

## 7. Definition of Done — PASS

Every checkbox traces to a frozen requirement or roadmap decision; no invented items. Notably, the DoD **does** include the parser-suite target ("`detector.py` parser suite ≥ 90%", §11) — the P2-302 O3 lesson was applied. The atomic-commit checkbox (§14) is present. The coverage-criterion wording is correct.

## 8. Testability — PASS

- All unit tests land in the frozen-spec file `tests/unit/test_structure_analysis.py` (§13); the 13-row §12 matrix maps one-to-one onto the roadmap P2-303 "Tests required" list (block types, `blocks.md` offsets, list nesting, blockquote continuation, pipe tables post-`clean_text`, multi-line fences, blank-line paragraph splitting).
- The `blocks.md` fixture as the offset vehicle (hard-coded tuples pinned to committed bytes) is the right mechanism for AC2/AC3; the slice-invariant property check across all fixtures makes the R2 guarantee testable, not just asserted.
- The clean_text-boundary test (raw → `clean_text` → `_detect_blocks`) pins the "after clean_text normalization" requirement at the seam; the fixture-stability assertion is a strong, cheap addition.
- No integration/perf tests this task is the correct split (P2-305/P2-306 own those); regression command matches the frozen §13 matrix.

## 9. Rollback — PASS

Additive-only (append to an existing module + fixtures + tests); verified by grep that **nothing in `app/` references `_detect_blocks` yet**, so the single-atomic-commit revert (§14) is a zero-blast-radius removal. Honest that the `enabled: false` flag rollback only becomes applicable at P2-305. Aligned with §14 on data (no persistence touched), code (no legacy branch), and dependency (none new) levels.

---

## Findings

### O1 — §5.4 pseudocode flushes the pipe run at entry, contradicting the normative prose

The pseudocode's item-8 branch calls `flush()` unconditionally on every `|`-leading line before the separator verdict is known. Traced against a two-row normalized table (`| a | b |` / `|:---|---:|` / `| 1 | 2 |`), a literal implementation emits **three blocks** (paragraph, table, paragraph) instead of **one table block** — directly violating §5.2 item 8 ("if the run contains ≥ 1 separator → one table block for the whole run") and AC5. The prose is correct and normative; only the sketch is wrong.

**Fix (one line in the pseudocode):** move the flush so it runs only when a *new* pipe run starts — `if not pipe_run: flush()` before `pipe_start = pos` (the run's verdict then fires when the run ends: blank / heading / non-`|` line / range edge / EOF, which `flush()` already handles). Non-blocking: the normative contract is unchanged; the implementer must follow §5.2 item 8, not the sketch.

### O2 — §5.4 pseudocode `flush()` rebinds closure locals → `UnboundLocalError`

The pseudocode's `flush()` assigns `run_type = None` and `pipe_has_separator = False`, both of which are also bound in the enclosing `_detect_blocks` body. Python therefore treats them as *locals of `flush`*, so `if run_type is not None:` raises `UnboundLocalError` at runtime — the sketch as written cannot execute.

**Fix (one line in the pseudocode):** declare `nonlocal run_type, pipe_has_separator` at the top of `flush()`. Non-blocking: no behavior change; the prose does not describe this detail and the correct semantics are obvious.

### O3 — §5.4 degenerate-note contradicts the pseudocode and AC6 for a lone ` ``` `

The degenerate-input bullet ("a lone ` ``` ` → fence state toggled with no content (no blocks)") contradicts the same section's closing `if fence_lines: emit("code", ...)` (a lone ` ``` ` leaves `fence_lines` non-empty → one `code` block) and §5.2 item 2 (an unclosed fence emits one code block to end of text). The pseudocode behavior is the consistent one (a lone opening fence is an unclosed fence); the note is wrong.

**Fix (one line):** change the note to "a lone ` ``` ` toggles fence state and yields one `code` block (unclosed fence to end of text)". Non-blocking: the pseudocode and AC6 govern; the note merely misleads.

### O4 — §5.2 "identical to `_normalize_line`'s precedence" is imprecise about the fence rule

The fence toggle does **not** live in `_normalize_line` (`utils.py:101-119`) — it lives in the separate `_protect_code_blocks` pass (`utils.py:57-82`). The claim is accurate for the non-fence classification order (heading → list → blockquote → table → paragraph), which is what the prose actually needs, but the stated source line for the *fence* rule is wrong.

**Fix (one clause):** write "identical to `clean_text`'s normalization conventions — `_normalize_line` for the classification order and `_protect_code_blocks` for the fence toggle". Non-blocking: the rule itself (items 1–2) is correct and matches P2-302.

### O5 — Fixture descriptions understate `clean_text` normalization effects

The §8/§12 fixture guidance ("a lone `| x | y |` line (paragraph boundary)") holds only if that line is **blank-separated** from the preceding table — a pipe-leading line adjacent to a table's rows is absorbed into the same pipe run and becomes a table row (§5.2 item 8). Separately, a pipe-*containing* non-pipe-leading line (e.g. `Lone pipe | line.`) is normalized by `clean_text` into a `| ... |` row, and a blockquote depth `>>` normalizes to `> >` (`_normalize_blockquote`); un-normalized fixture content will not be a genuine post-`clean_text` snapshot.

**Fix (note in §8/§12):** state that the lone-pipe paragraph must be blank-separated and that all fixture content must be the actual `clean_text` output (verifiable via a stability assertion). Non-blocking: `blocks.md`/`lists_and_quotes.md`/`table_block.md` are implementation details; the detector contract is unaffected.

---

## Verdict

✅ **Ready for Implementation**

The spec is fully consistent with the frozen M2.3 contract: file ownership, the five-type `BlockKind`, the reused D9 heading skip, the fence-state machine shared with `_detect_headings`, the slice-exact offset contract (R2), the `clean_text`-normalized table rule, deferred-API boundaries, rollback, and the AC/DoD mappings all check out — with the list-continuation, blockquote, range-edge, and fence/range claims traced and verified against the live `utils.py` and shipped P2-302 `detector.py`. The five findings are all in the *reference sketch and documentation layer* (two pseudocode defects, one contradictory degenerate note, two imprecise phrasing items); the normative prose, acceptance criteria, and test matrix are correct and unambiguous, and every fix is mechanical (one-line pseudocode edits or doc-note corrections). No finding changes the prescribed behavior or the implementation contract.
