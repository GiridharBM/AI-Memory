# Milestone 2.3 Specification Freeze — Version 1.1

**Frozen by:** Principal Engineering Reviewer (on behalf of the project)
**Date:** 2026-08-01
**Source document:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` (**Version 1.1, FROZEN**)
**Source of truth chain:** MEDD → `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` v1.1 (🔒 FROZEN, Engineering Baseline 2026-08-01) → `docs/PHASE_2_ENGINEERING_BASELINE.md` (binding addenda §10 — addendum 3: `intelligence.structure.enrich_analysis_input: false`) → this document.
**Approval report:** `docs/PHASE_2_MILESTONE_2_3_SPECIFICATION_REVIEW_2.md` — ✅ **Ready for Freeze** (post-remediation).
**Prior review record:** `docs/PHASE_2_MILESTONE_2_3_SPECIFICATION_REVIEW.md` — ❌ Needs Specification Remediation (R-1 + C-1…C-7 + O-1…O-4).
**Remediation record:** `docs/PHASE_2_MILESTONE_2_3_SPECIFICATION_REMEDIATION_REPORT.md`.
**Contract scope rule:** **This document is the implementation contract for Milestone 2.3.** No code is implemented by this document. All future implementation must follow this frozen specification. Only change-control-approved deviations are permitted (Baseline §11). The specification will not be modified again unless a future engineering review identifies a blocker.

---

## 1. Specification Version

| Attribute | Value |
|-----------|-------|
| Document | Milestone 2.3 — Document Structure Analysis |
| Semantic version | **1.1** (remediated; v1.0 never frozen) |
| Status | 🔒 **FROZEN** (2026-08-01) |
| Prerequisite | Milestone 2.2 complete and approved (✅ Milestone 2.2 Approved, 2026-08-01) |
| Baseline | 605 unit + 14 integration tests; coverage ≥ 80%; Python 3.14.6 (Windows) |
| Upstream | Phase 2 Implementation Specification v1.1 (FROZEN) + Engineering Baseline addendum 3 |
| Estimated effort | **4 dev-days** (task-sum 3.75 d rounded with buffer — C-1 reconciliation) |
| New dependencies | **None** (stdlib `re` + existing pydantic only; no wheel verification needed) |
| Rollback contract | `intelligence.structure.enabled: false` returns M2.2-identical documents — no `metadata.extra["structure"]` key written (R-4) |

---

## 2. Included Tasks

| Task | Title | Priority | Deps | Effort | Risk |
|------|-------|----------|------|--------|------|
| P2-301 | Structure domain models | P0 | — | 0.5 d | L |
| P2-302 | Heading hierarchy detector | P0 | P2-301 | 1 d | M |
| P2-303 | Block detector (paragraph/list/fence/blockquote/table) | P0 | P2-301 | 1 d | M |
| P2-304 | Structure tree builder | P0 | P2-302, P2-303 | 0.5 d | L |
| P2-305 | Enrichment into the enriched document (`metadata.extra["structure"]`) | P0 | P2-304 | 0.5 d | M |
| P2-306 | Performance + cap guard | P1 | P2-305 | 0.25 d | L |

**Total: 6 tasks.** Files-per-task and per-task DoD are in the frozen engineering spec §11.1.

**Implementation order (binding, §11.2):** Wave 0 preflight (M2.2 gate closed) → Wave 1 P2-301 → Wave 2 ‖ {P2-302, P2-303} → Wave 3 P2-304 → Wave 4 P2-305 → Wave 5 P2-306.
**Critical path:** P2-301 → P2-302 → P2-304 → P2-305 (and P2-301 → P2-303 → P2-304).

---

## 3. Frozen Dependency Graph

### Intra-milestone (hard edges, cycle-free)
```
P2-301 → P2-302 → P2-304 → P2-305 → P2-306
P2-301 → P2-303 → P2-304
P2-302 ‖ P2-303        (wave-2 parallel; independent once models exist)
```

### Cross-milestone
- **Outbound hard dependency (R-2):** P2-305 (the enrichment call site) must land **before** any M2.4/M2.5/M2.6 wiring task — P2-406, P2-506, P2-606 consume the same call site.
- **Feeds (Phase 3 contract):** `DocumentStructure` + the `metadata.extra["structure"]` serialized channel are the input contract for MEDD G14 hierarchical chunking (§7.3 target architecture) and Phase 4 parent-child retrieval.
- **Receives:** nothing from later milestones this phase (M2.3 is self-contained).
- **Runtime deps:** `re` (stdlib), `pydantic` (existing). `SemanticChunker` and all existing components are **unchanged** (AC5).

---

## 4. Frozen Acceptance Criteria

| # | Criterion |
|---|-----------|
| AC1 | Nested ATX headings produce the correct parent/child hierarchy. |
| AC2 | Code fences and fenced `#` lines are **not** mis-split as headings. |
| AC3 | Blocks (paragraph/list/fence/blockquote/table) are detected with accurate `start_char`/`end_char`. |
| AC4 | `IngestionWorkflowResult.document.metadata.extra["structure"]` is populated (as a serialized `DocumentStructure`) for kinds in `TEXT_BEARING_KINDS` when `enabled: true`; absent when disabled or for other kinds. |
| AC5 | Chunker behavior is byte-identical (regression). |

Evidence per AC is defined in engineering spec §8 and enforced through the test matrix in §13.

---

## 5. Frozen Definition of Done

- [ ] `DocumentStructure` / `DocumentSection` / `DocumentBlock` models with IDs, levels, parent IDs, offsets (P2-301).
- [ ] Heading hierarchy detector — nested ATX → correct tree; fenced `#` not mis-split (P2-302).
- [ ] Block detector — paragraph/list/fence/blockquote/table with accurate char offsets (P2-303).
- [ ] Structure tree builder — sections contain blocks; offsets contiguous; degenerate input → empty tree (P2-304).
- [ ] Enrichment into `document.metadata.extra["structure"]` via `_run_routed_processor` (R-1 channel, §5.4), gated by `structure.enabled` + `TEXT_BEARING_KINDS` (P2-305).
- [ ] 5 MB size cap guard + `MAX_HEADING_LEVEL`/`MAX_SECTIONS` caps + O(n) timing ceiling (P2-306).
- [ ] Offsets verified against sample documents (fixture-based).
- [ ] All gates green: 605 unit + 14 integration tests pass unchanged; coverage ≥ 80%; `ruff` zero new errors; `mypy` zero new type errors.
- [ ] Documentation updated: `changelog.md`, MEDD §7.3 chunking target-architecture input contract, 01 report structure section.
- [ ] Milestone 2.3 completion report produced before Milestone 2.4 begins (frozen §12 gates).

---

## 6. Frozen Public Interfaces

### 6.1 Normative interfaces (from frozen spec §4.1 — do not alter)

```python
class StructureAnalyzer:
    """Detect and build the hierarchical structure of source text."""
    def analyze(self, text: str, source: str) -> DocumentStructure: ...
```

- **Public APIs:** `analyze_document_structure(text, source)`, `StructureAnalyzer`, `DocumentStructure`, `DocumentSection`, `DocumentBlock`.
- **Internal APIs:** `_detect_headings(lines)`, `_detect_blocks(text, ranges)`, `_build_tree(sections)`.
- **Reentrancy:** `analyze()` is pure and reentrant — no shared mutable state (O-2).

### 6.2 Domain models (additive, in `app/domain/document_intelligence.py`)

```python
class DocumentBlock:
    block_id: str          # stable, e.g. "b-<section_id>-<n>"
    type: str              # "paragraph" | "list" | "code" | "blockquote" | "table"
    text: str
    start_char: int
    end_char: int

class DocumentSection:
    id: str                # stable, e.g. "s-1" / "s-1-1"
    title: str
    level: int             # 1..6, from ATX heading depth
    parent_id: str | None
    start_char: int
    end_char: int
    blocks: list[DocumentBlock]

class DocumentStructure:
    sections: list[DocumentSection]
```

- Offsets are relative to the **exact text string passed to `analyze`** — the same text the pipeline will chunk.
- **Serialization contract:** travels as `document.metadata.extra["structure"] = structure.model_dump(mode="json")`; consumers deserialize via `DocumentStructure.model_validate(extra["structure"])`. `ProcessedDocument` is **not** modified.

### 6.3 Package layout

`app/infrastructure/document_intelligence/structure/` = `detector.py` (analyzer + `_detect_headings` + `_detect_blocks` + `_build_tree`); models in shared `app/domain/document_intelligence.py` (next to existing `MetadataExtraction`); composition root `app/infrastructure/document_intelligence/__init__.py` exposes `analyze_document_structure` and `get_default_structure_analyzer()`.

---

## 7. Frozen Configuration

```yaml
intelligence:
  structure:
    enabled: true                 # false ⇒ no "structure" key; M2.2-identical documents (R-4)
    enrich_analysis_input: false  # addendum 3; CONTRACT-ONLY this milestone (C-5) - no code reads it (R-7)
```

- **Normative keys (do not alter):** `enabled`, `enrich_analysis_input`.
- **`enrich_analysis_input` is contract-only** — declared for the future structure-aware-prompting contract, **not read by any code this milestone** (C-5). No task may consume it in M2.3.
- **Code constants (no config keys):**
  - `TEXT_BEARING_KINDS = frozenset({"markdown", "text"})` — the only kinds that receive structure this milestone; PDF/OCR-prose excluded.
  - `max_structure_text_bytes = 5_000_000` (Baseline R5) — analyzed text above this is skipped with a single warning.
  - `MAX_HEADING_LEVEL = 6` (ATX) — deeper heading levels normalize to 6.
  - `MAX_SECTIONS = 10_000` — exceeded → warn + truncate in tree order, never raise.
- **Plumbing (binding, §5.3):** `structure.enabled` reaches the analyzer through `Settings` → `IngestionWorkflow.from_runtime(settings=settings)` → `_run_routed_processor`; reachable from both CLI (`entry.py`) and queue worker (`worker.py`).

---

## 8. Frozen Data Flow

### 8.1 Enrichment channel (engineering spec §5.4 — R-1 remediation, binding)

1. After `result = processor.process(document)` succeeds, when `structure.enabled` is true and `result.source_type in TEXT_BEARING_KINDS`, run `analyzer.analyze(result.extracted_text or document.text, str(document.source))`.
2. Serialize: `structure_dict = structure.model_dump(mode="json")` (empty `DocumentStructure` ⇒ `{"sections": []}`).
3. Store on the enriched document, exactly like `parent_id`: `enriched.metadata.extra["structure"] = structure_dict` (nested `model_copy` per the `parent_id` precedent at `ingest_workflow.py:396-400`).
4. `enabled: false`, a kind outside `TEXT_BEARING_KINDS`, or a raised/oversize analyzer → **no** `"structure"` key (M2.2-identical — R-4).
5. The key survives on `IngestionWorkflowResult.document` and the persisted metadata (extra keys are carried and ignored by the note template — proven by `parent_id`/`attachment_paths`).

### 8.2 Key invariants

- The analyzer receives `result.extracted_text or document.text` — the **exact text** later chunked (`enriched.text` at `_run_knowledge_engine`), so offsets never drift.
- Structure is built on the extracted/OCR text (post-ingestion), not on the source file.
- Fenced code containing `#` must not create headings; headings inside HTML/attributes are best-effort (documented limitation).
- Degenerate input (empty text) → empty structure, never an exception.
- **Heading rule:** `^#{1,6}\s+\S` — deliberately stricter than `SemanticChunker._HEADING_PATTERN` (`^#{1,6}\s+.+`, fence-unaware): chunker unchanged (AC5), detector fence-correct (AC2).

### 8.3 Consumers

**Phase 3+:** read `metadata.extra.get("structure")`, `DocumentStructure.model_validate(...)`, map `DocumentSection.id` → chunk `parent_id` (MEDD §7.3 "parent ID assignment"). No consumer this milestone (R-7/R10 guard).

---

## 9. Frozen Rollback Contract

| Level | Contract |
|-------|----------|
| Per-feature | `intelligence.structure.enabled: false` → structure enrichment skipped; no `metadata.extra["structure"]` key; M2.2-identical documents, zero code change (R-4) |
| Data | Additive only — new optional key `metadata.extra["structure"]`; no field added/removed/re-typed on any domain model; no migration |
| Code | No deprecated branch, no `legacy` value, no duplication (L3) |
| Dependency | None new; nothing to uninstall |

---

## 10. Approval

- [x] Spec versioned **1.1** and status set to **FROZEN** (this document + engineering spec header).
- [x] Reviewed post-remediation by Principal Engineering Reviewer — ✅ **Ready for Freeze** (`PHASE_2_MILESTONE_2_3_SPECIFICATION_REVIEW_2.md`).
- [x] R-1 resolved (structure persists via `metadata.extra["structure"]`; AC4 re-targeted to a real observable surface).
- [x] C-1…C-7 all addressed; O-1…O-4 applied where they clarify.
- [x] Scope (in/out) matches frozen Phase 2 v1.1 Milestone 2.3 row + task breakdown §4.3 exactly (P2-301…P2-306).
- [x] Dependency graph verified cycle-free; implementation order binding.
- [x] Rollback contract and backward-compatibility contract confirmed.
- [x] Performance ceilings bound (5 MB skip, `MAX_HEADING_LEVEL`, `MAX_SECTIONS`, O(n) single scan, ≤ 1 s per 1 MB).
- [x] No code implemented by this freeze.

**Approved:** Milestone 2.3 Specification v1.1 is FROZEN and is the binding implementation contract. All future implementation must follow this frozen specification. The specification will not be modified again unless a future engineering review identifies a blocker; any other deviation requires Change Control approval per Baseline §11.
