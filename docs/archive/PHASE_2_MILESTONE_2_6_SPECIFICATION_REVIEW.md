# Milestone 2.6 Specification Review -- Code & Notebook Intelligence

**Reviewer:** Principal Engineering Reviewer
**Date:** 2026-08-04 (regenerated)
**Spec version:** Frozen section 4.6 (PHASE_2_IMPLEMENTATION_SPECIFICATION.md lines 270-303) — post-remediation
**Codebase snapshot:** Post-M2.5, all 825 tests passing
**Scope:** Full 11-dimension verification

---

## Executive Summary

**APPROVED — all 10 Required findings resolved in the specification.**

The spec is architecturally consistent with the existing codebase. All previously identified gaps (processor passthrough behavior, enrichment hook, ingestor scope, config block, rollback test, input shape, AC5 scope, dependency graph, wave sequencing, enforcement location) have been addressed with concrete, implementation-ready clarifications. No remaining blockers for M2.6 implementation.

---

## 1. Architecture

### Current state (unchanged — implementation not started)

| Component | Status | Location |
|-----------|--------|----------|
| CodeProcessor | Passthrough stub | processor_impls.py:159-167 |
| NotebookProcessor | Passthrough stub | processor_impls.py:253-261 |
| NotebookIngestor | Working, flattens cells to text with fences | notebook_ingestor.py:20-77 |
| CodeStructure / NotebookStructure | **Not defined** | Missing from domain/document_intelligence.py |
| app/infrastructure/document_intelligence/code/ | **Directory does not exist** | No model.py, parser.py, languages.py, notebook.py |
| intelligence.code config block | **Not defined in codebase** — now fully specified in frozen spec | Spec lines 292 |
| extensions.py | Has CODE_EXTENSIONS (frozenset of suffixes) but **no language-name mapping** | app/core/extensions.py:6-16 |
| DocumentClassification.requires_code_parsing | Defined, set True for kind=="code" but **never consumed** | classifier.py:95,107; routing.py:22 |

### Findings

**REQ-1 (Required — RESOLVED): CodeProcessor/NotebookProcessor passthrough behavior.**

Spec now clarifies: processors remain passthrough (consistent with M2.4 TableProcessor); code/notebook structure attachment happens in a new `_enrich_code()` method at the P2-305 shared hook, gated by `intelligence.code.enabled` and `kind in {"code", "notebook"}`. This is explicit in both the Required Refactoring row (line 289) and P2-606 AC (line 381).

**REQ-2 (Required — RESOLVED): The _enrich_code() hook is now specified.**

P2-606 AC specifies: "structure attachment happens in a new `_enrich_code()` method at the P2-305 shared hook, gated by `intelligence.code.enabled` and `kind in {"code", "notebook"}` (follows `_enrich_tables()`/`_enrich_images()` pattern)". P2-606 DoD adds: "Add `_enrich_code(document, kind)` to `ingest_workflow.py` following the `_enrich_tables()` / `_enrich_images()` pattern."

**REQ-3 (Required — RESOLVED): NotebookIngestor upgrade scope pinned to Option 2.**

Required Refactoring row (line 289) and P2-605 AC (line 380) both state: `NotebookIngestor.ingest()` calls `NotebookParser.parse(raw)` and attaches the result to `metadata.extra["notebook_structure"]` — consistent with the `PdfIngestor` metadata pattern.

**REQ-4 (Required — RESOLVED): intelligence.code config block now fully specified.**

Configuration Changes row (line 292) specifies `CodeSettings` with full type signatures: `enabled: bool = True`, `languages: Literal["default"] = "default"`, `max_cell_outputs: int = 10`, `max_code_chars: int = 100000`, `include_docstrings: bool = True`. Config value semantics documented: `"default"` = built-in `extensions.py` suffix-to-language mapping (other values deferred); `max_code_chars` = Python `str` length (files exceeding truncated with logged warning). P2-606 AC confirms `CodeSettings` added to `IntelligenceSettings`.

**REQ-5 (Required — RESOLVED): Rollback test now in P2-606 DoD.**

P2-606 DoD (line 381) includes: "rollback test passes". This, combined with the config block (REQ-4), makes the rollback contract testable.

**REQ-6 (Required — RESOLVED): NotebookParser.parse() input shape pinned.**

Interfaces row (line 288) now states: `raw` is the full notebook dict (output of `json.loads`); parser extracts `cells`, `metadata.kernelspec`, and `metadata.language_info` internally. P2-605 AC confirms: "accepts full notebook dict (output of `json.loads`), extracts cells + metadata internally."

**REQ-7 (Required — RESOLVED): AC5 moved to Phase 3.**

Acceptance Criteria (line 299) now has 4 items (down from 5). AC5 ("analysis prompt no longer contains megabyte-scale outputs") is removed from AC and moved to Definition of Done (line 298): "Phase 3 concern: analysis prompt no longer contains megabyte-scale outputs (requires DocumentAIProcessor prompt construction — M2.6 attaches the structure; Phase 3 consumes it)."

**REQ-8 (Required — RESOLVED): P2-602 added to P2-606 dependency list.**

P2-606 deps (line 381) now include `P2-602`: "P2-305, P2-602, P2-603, P2-605". Dependency graph edge (line 400) updated to `TAB -->|notebook code cells reuse language registry| COD`.

**REQ-9 (Required — RESOLVED): Wave 4 sequencing clarified — M2.6 after M2.4.**

Wave table (line 425) now reads: "4 (after 2.4) | **2.6 Code & Notebook**". Dependency graph edge (line 408) updated to hard: "2.4 → 2.6 (hard)". Section 6.2 point 4 updated: "2.6 after 2.4 in wave 4". Section 6.3 parallel tasks updated: M2.6 removed from parallel set, wave-4 sequencing note added.

**REQ-10 (Required — RESOLVED): AC3 enforcement location pinned to NotebookParser.parse().**

Acceptance Criteria AC3 (line 299) now states: "outputs capped at `max_cell_outputs` during `NotebookParser.parse()` (entries beyond the cap replaced with `[truncated]` marker)". Performance Considerations (line 293) confirms: "notebook cell outputs capped at `max_cell_outputs` during `NotebookParser.parse()`".

---

## 2. Dependency Graph

### Updated dependency chain

```
P2-601 (models) -> P2-602 (language registry) -> P2-603 (AST parser) -> P2-604 (heuristic fallback)
P2-601 (models) -> P2-605 (notebook parser)
P2-305 + P2-602 + P2-603 + P2-605 -> P2-606 (wiring)
```

### Findings

**REQ-8 (Required — RESOLVED):** P2-602 now appears in P2-606 dependency list.

**REQ-9 (Required — RESOLVED):** M2.6 is sequenced after M2.4 in wave 4. The TAB → COD edge is now hard (not soft). Shared-file conflicts are eliminated by sequential execution.

---

## 3. Acceptance Criteria

| AC | Spec text (line 299) | Verdict | Resolution |
|----|----------------------|---------|------------|
| AC1 | "Python file → structure lists imports/functions/classes with offsets and docstrings" | Pass | -- |
| AC2 | "Invalid-Python file → heuristic structure, no crash" | Pass | -- |
| AC3 | ".ipynb fixture → ordered cells with types and execution counts, outputs capped at `max_cell_outputs` during `NotebookParser.parse()` (entries beyond the cap replaced with `[truncated]` marker)" | Pass | REQ-10 resolved: enforcement location pinned to parser |
| AC4 | "Non-Python file → line-based fallback" | Pass | -- |

**REQ-7 (Required — RESOLVED):** AC5 removed from acceptance criteria; moved to Definition of Done as a Phase 3 concern. M2.6 now has 4 verifiable acceptance criteria.

---

## 4. Rollback Contracts

| Claim | Current state | Verdict |
|-------|---------------|---------|
| intelligence.code.enabled: false restores Phase-1 behavior | Config block now fully specified in frozen spec; P2-606 DoD includes rollback test; rollback contract is testable | PASS |

**REQ-5 (Required — RESOLVED):** Rollback contract is now testable. Config block exists in spec (REQ-4). P2-606 DoD includes rollback test. When `enabled=false`: enrichment hook skips `_enrich_code()`, processors remain passthrough, `NotebookIngestor` reverts to flattening.

---

## 5. Configuration

| Spec config key | Type | Default | Status |
|-----------------|------|---------|--------|
| intelligence.code.enabled | bool | true | **Specified** — CodeSettings model with full type |
| intelligence.code.languages | Literal["default"] | "default" | **Specified** — "default" = built-in extensions.py mapping; extensibility deferred |
| intelligence.code.max_cell_outputs | int | 10 | **Specified** — enforced in NotebookParser.parse() |
| intelligence.code.max_code_chars | int | 100000 | **Specified** — Python str length; truncation with logged warning |
| intelligence.code.include_docstrings | bool | true | **Specified** |

No remaining configuration findings.

---

## 6. Public Interfaces

| Interface | Spec definition (line 288) | Status |
|-----------|---------------------------|--------|
| class CodeParser(Protocol) | `languages: frozenset[str]; parse(text, filename) -> CodeStructure` | **Specified** |
| class NotebookParser | `parse(raw: dict) -> NotebookStructure` — raw is full notebook dict | **Specified** |
| CodeStructure | language, imports, functions, classes, docstrings, char_ranges | **Specified** (greenfield — models in P2-601) |
| NotebookStructure | cells: list[NotebookCell] | **Specified** (greenfield) |
| NotebookCell | id, type, source, outputs, execution_count | **Specified** (greenfield) |
| parse_code(text, filename) | Public API | **Specified** |
| parse_notebook(raw) | Public API — raw is full notebook dict | **Specified** |

All interfaces are greenfield. No conflicts with existing interfaces.

---

## 7. Naming Consistency

| Spec name | Codebase convention | Consistent? |
|-----------|---------------------|-------------|
| CodeStructure / NotebookStructure | Matches DocumentStructure, ImageInfo, Table | Yes |
| CodeParser / NotebookParser | Matches StructureAnalyzer, TableExtractor, ImageAnalyzer | Yes |
| code/languages.py | Other modules use __init__.py for public API | Minor (OPT-1 deferred) |
| intelligence.code.* | Matches intelligence.images.*, intelligence.tables.*, intelligence.ocr.* | Yes |
| NotebookCell | Matches TableRow, DocumentBlock | Yes |
| _language_from_filename | Internal API, underscore-prefixed | Yes |

No remaining naming findings.

---

## 8. Implementation Feasibility

### P2-601: Models (0.25d, Low, L risk)
Greenfield pydantic models in document_intelligence.py. No external deps. Trivial.

### P2-602: Language registry (0.25d, Low, L risk)
Maps extensions.py CODE_EXTENSIONS to language names. Pure dict lookup. Trivial.

### P2-603: Python AST parser (1d, Medium, M risk)
ast stdlib module. Feasible within 1 day.

### P2-604: Heuristic fallback parser (0.5d, Medium, M risk)
Line-based regex. Conservative patterns. Feasible.

### P2-605: Notebook parser + ingestor upgrade (1d, Medium, M risk)
JSON structure well-defined. Output capping logic + ingestor integration. Feasible.

### P2-606: Processor + pipeline enrichment (0.5d, Low, M risk)
Follows established M2.4/M2.5 pattern exactly. `_enrich_code()` method, config wiring, rollback test. Low risk.

---

## 9. Documentation Consistency

| Document | M2.6 coverage | Status |
|----------|---------------|--------|
| PHASE_2_IMPLEMENTATION_SPECIFICATION.md | Full section 4.6 task breakdown | Primary source — **updated** |
| PHASE_2_ENGINEERING_BASELINE.md | Line 38: "2.6 — Code & Notebook Intelligence" row | Present |
| MASTER_ENGINEERING_DESIGN_DOCUMENT.md | Section 7.3 Future Work: Code-aware chunking | Forward reference |
| 05_Development_Roadmap.md | Phase 7 row | Present |
| 01_Current_Implementation_Report.md | No M2.6 section (expected) | Consistent |
| changelog.md | No 0.7.0 entry (expected) | Consistent |

---

## 10. Previous Milestone Assumptions

| Assumption | Validation |
|------------|------------|
| P2-305 enrichment hook exists | Verified — _run_routed_processor has _enrich_structure, _enrich_tables, _enrich_images |
| P2-305 hook reusable by M2.6 | Verified — _enrich_code specified in P2-606 AC; pattern established |
| extensions.py provides suffix -> language mapping | Partial — has suffix sets (CODE_EXTENSIONS) but no language names; P2-602 builds the mapping (specified) |
| ProcessedDocument accepts additive fields | Verified — structure, ocr, image_info, tables already added via metadata.extra |
| NotebookIngestor upgrade path | **Resolved** — Option 2 pinned (ingestor calls parser, attaches structure) |
| requires_code_parsing is consumed | NOT consumed — forward-looking field for Phase 3 (no M2.6 impact) |

---

## 11. Integration Points

| Integration Point | Spec | Codebase | Status |
|-------------------|------|----------|--------|
| Classifier -> Processor | kind=code -> CodeProcessor; kind=notebook -> NotebookProcessor | router.py maps correctly | OK |
| Enrichment hook | _enrich_code(document, kind) called from _run_routed_processor | Hook exists; _enrich_code specified in P2-606 AC | **Resolved** (REQ-2) |
| Config propagation | intelligence.code.* -> CodeSettings -> IngestionWorkflow -> processors | Config block specified in frozen spec | **Resolved** (REQ-4) |
| Language registry | CodeProcessor/NotebookProcessor use registry for language detection | Registry absent; P2-602 specified | Blocked (implementation not started) |
| Notebook ingestion | NotebookIngestor calls NotebookParser, attaches structure | Currently flattens text; Option 2 pinned | **Resolved** (REQ-3) |
| Note generation | ObsidianMarkdownGenerator renders code/notebook sections | Not in M2.6 scope (Phase 3) | Deferred |

---

## Summary of Findings

### Required (10 — ALL RESOLVED)

| ID | Finding | Status | Resolution |
|-----|---------|--------|------------|
| REQ-1 | CodeProcessor/NotebookProcessor passthrough behavior unspecified | **RESOLVED** | P2-606 AC + Required Refactoring: processors remain passthrough; structure in _enrich_code() |
| REQ-2 | _enrich_code() hook not specified | **RESOLVED** | P2-606 AC + DoD: _enrich_code(document, kind) gated by enabled + kind; follows _enrich_tables/_enrich_images pattern |
| REQ-3 | NotebookIngestor upgrade scope ambiguous | **RESOLVED** | P2-605 AC + Required Refactoring: Option 2 pinned — ingestor calls parser, attaches to metadata.extra |
| REQ-4 | intelligence.code config block absent | **RESOLVED** | Configuration Changes row: full CodeSettings with type signatures, defaults, semantics |
| REQ-5 | Rollback contract untestable | **RESOLVED** | P2-606 DoD: rollback test required; config block now specified (REQ-4) |
| REQ-6 | NotebookParser.parse() input shape unspecified | **RESOLVED** | Interfaces row + P2-605 AC: raw is full notebook dict; parser extracts cells + metadata internally |
| REQ-7 | AC5 not verifiable in M2.6 | **RESOLVED** | AC5 removed from AC; moved to Definition of Done as Phase 3 concern |
| REQ-8 | P2-606 missing dependency on P2-602 | **RESOLVED** | P2-606 deps: P2-305, P2-602, P2-603, P2-605 |
| REQ-9 | Wave 4 parallelism creates shared-file conflicts | **RESOLVED** | M2.6 sequenced after M2.4 in wave 4; TAB → COD edge now hard |
| REQ-10 | AC3 enforcement location unspecified | **RESOLVED** | P2-605 AC + Performance Considerations: capping enforced in NotebookParser.parse() |

### Recommended (5 — no action required for M2.6 implementation)

| ID | Finding | Status |
|-----|---------|--------|
| REQ-11 | languages: default config value underspecified | Resolved in Configuration Changes row (extensibility deferred to post-M2.6) |
| REQ-12 | max_code_chars units ambiguous | Resolved: "Python str length" documented |
| REQ-13 | CodeParser.languages set semantics unspecified | Resolved: `frozenset[str]` of language names; _AstCodeParser.languages = frozenset({"python"}) per P2-603 |
| REQ-14 | requires_code_parsing set but never consumed | Not consumed in M2.6; forward-looking field for Phase 3 |

### Optional (2 — deferred)

| ID | Finding | Status |
|-----|---------|--------|
| OPT-1 | code/languages.py naming breaks __init__.py pattern | Deferred — minor style, not blocking |
| OPT-2 | Add MEDD cross-reference from Phase 3 to M2.6 | Deferred — documentation completeness |

---

## Recommendation

**APPROVED for implementation.** All 10 Required findings are resolved in the frozen specification. The spec now provides unambiguous implementation guidance for all six M2.6 tasks.

---

**Signed:** Principal Engineering Reviewer
**Date:** 2026-08-04
