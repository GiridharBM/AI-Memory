# Phase 2 — Milestone 2.3 Specification Remediation Report

**Specification:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` (v1.0 → **v1.1**)
**Review record:** `docs/PHASE_2_MILESTONE_2_3_SPECIFICATION_REVIEW.md` — verdict ❌ Needs Specification Remediation
**Date:** 2026-08-01
**Scope:** Documentation-only. **No implementation code was modified.**

---

## R-1 (BLOCKER) — Structure enrichment targets an object that does not survive the pipeline

### Finding
`_run_routed_processor` (`app/pipelines/ingest_workflow.py:457-477`) discards the `ProcessedDocument result`: only `confidence`, `ocr`, `extracted_text`, and `source_type` are consumed, and the value returned up the pipeline is an enriched `SourceDocument` with pydantic `ConfigDict(extra="forbid")` (`app/domain/documents.py:27-37`) and **no** `structure` field. `ProcessedDocument.structure` would be unobservable to every downstream consumer. AC4 had no observable target.

### Remediation
Reused the proven `parent_id` channel (`_ingest_child` writes `extra["parent_id"] = parent_id` at `ingest_workflow.py:397`): structure is serialized into **`document.metadata.extra["structure"] = structure.model_dump(mode="json")`** on the enriched `SourceDocument`. `ProcessedDocument` is **not** modified. The deviation from frozen P2-305 is recorded normatively in the spec as **§5.4 "Structure enrichment channel (R-1 remediation — deviation from frozen P2-305)"**.

| Change | Spec location |
|--------|---------------|
| Objective 2 re-targeted to `metadata.extra["structure"]` on the enriched document; objective 4 pins the Phase 3 consumption seam (`model_validate` + `DocumentSection.id` → chunk `parent_id`). | §1 objectives 2, 4 |
| Enrichment goal re-worded to the `metadata.extra` channel. | §2.1 |
| Dependencies table: `SourceDocument.metadata.extra` is now the persistence channel; `ProcessedDocument` marked not-modified. | §3 |
| Serialization contract (`model_dump(mode="json")` / `model_validate`) added; `ProcessedDocument` field removal noted as deviation. | §4.2 |
| **New normative subsection** — 5-step enrichment channel (text selection, serialization, storage inside the existing `model_copy`/update step, absence contract, survival on `IngestionWorkflowResult`/persisted metadata) + Phase 3 consumer contract. | §5.4 (new) |
| Placement diagram + §6 sequence diagram rewritten: `STRUC → enriched SourceDocument metadata.extra["structure"]`; persistence step now writes the key on the surviving document. | §5.2, §6 |
| AC4 re-targeted: `IngestionWorkflowResult.document.metadata.extra["structure"]` deserializes to a non-empty `DocumentStructure`; absent when disabled / non-text-bearing. | §8 |
| DoD + engineering-review checklist P2-305 updated to the channel. | §9, §12 |
| R3 risk re-scoped to `metadata.extra` growth; R1 mitigation adds the intentional heading-rule divergence note. | §10 |
| P2-305 task row: files = `ingest_workflow.py`, `core/config.py`, `config/default.yaml` (no `processed_document.py`); DoD = key populated/absent. | §11.1 |
| L5 lesson row gains the `enrich_analysis_input` contract-only exception. | §11.3 |
| Integration + unit + manual test rows assert `extra["structure"]` round-trip; `enabled: false` → key absent. | §13 |
| Rollback: per-feature = no key written; data = additive key only, no domain model change, no migration. | §14 |
| §15.2 data-flow diagram: `G[no "structure" key]` → `H[enriched SourceDocument metadata.extra["structure"]]`. | §15.2 |

---

## C-1 — Effort estimate inconsistency (3.75 d / "3 dev-days" / roadmap 4-day budget)

**Remediation:** §11.1 total now reads: task-sum 3.75 d → **milestone budget 4 dev-days**, citing the M2.2 addendum-4 precedent (rounded with buffer over a frozen 3 d estimate).

## C-2 — Block-ID contradiction (§4.2 scheme vs §15.4 diagram)

**Remediation:** §15.4 diagram corrected to the `b-<section_id>-<n>` scheme: `b-s1-1` → `b-s-1-1`, `b-s11-1` → `b-s-1-1-1`, `b-s2-1` → `b-s-2-1`, `b-s2-2` → `b-s-2-2`.

## C-3 — "Text-bearing kinds" undefined

**Remediation:** §7 defines the code constant **`TEXT_BEARING_KINDS = frozenset({"markdown", "text"})`**; PDF/OCR-prose kinds explicitly excluded this milestone with a documented upgrade path. Referenced from §2.1, §5.4, §8 AC4, §9, §13.

## C-4 — Nested-depth cap undefined

**Remediation:** §7 defines **`MAX_HEADING_LEVEL = 6`** (ATX; deeper levels normalize to 6) and **`MAX_SECTIONS = 10_000`** (warn + truncate in tree order, never raise). Referenced from §9, §12 (P2-304 checklist), §13 unit scope.

## C-5 — `enrich_analysis_input` conflicts with L5

**Remediation:** The key is now normative-and-contract-only in §7 and the §7 YAML block: **no code reads it this milestone** (addendum 3 / R-7). Recorded as a declared L5 exception in §11.3 and as a review-gate note in §12.

## C-6 — `core/config.py` ownership ambiguity (P2-305 vs P2-306)

**Remediation:** §11.1 P2-305 owns `core/config.py` + `config/default.yaml` (settings plumbing); P2-306 touches only `structure/detector.py` (config already defined) and enforces the caps.

## C-7 — Flow diagrams must show the post-R-1 persistence channel

**Remediation:** §6 sequence diagram and §15.2 data-flow diagram both now show the `metadata.extra["structure"]` write on the surviving enriched document, plus the `enabled:false`/non-text-bearing → no-key branch.

---

## O-1 — Pydantic models inside a `@dataclass(slots=True)` `ProcessedDocument`

**Applied:** §12 P2-301 review item notes pydantic models live in `app/domain/document_intelligence.py` per the `MetadataExtraction` precedent (line 10) and that `ProcessedDocument` stays untouched.

## O-2 — Analyzer statelessness / reentrancy

**Applied:** §5.4 adds a reentrancy contract — `analyze()` is pure, no shared mutable state, safe under future parallel ingestion.

## O-3 — Heading-rule divergence from the chunker

**Applied:** §10 R1 mitigation documents that the detector's `^#{1,6}\s+\S` is deliberately stricter than `SemanticChunker._HEADING_PATTERN` (`^#{1,6}\s+.+`, fence-unaware), keeping the chunker byte-identical (AC5) while the detector is fence-correct (AC2).

## O-4 — Phase 3 consumption seam

**Applied:** §1 objective 4 pins the seam — Phase 3 reads `metadata.extra["structure"]` → `DocumentStructure.model_validate` → maps `DocumentSection.id` → chunk `parent_id` (MEDD §7.3 "parent ID assignment").

---

## Cross-document consistency note

The remediation is confined to the engineering specification. The following documents **retain pre-remediation wording and were not edited** (out of scope for this task):
- `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` (frozen v1.1 — cannot be edited).
- `docs/PHASE_2_MILESTONE_2_3_IMPLEMENTATION_ROADMAP.md` (P2-305 rows, AC4, P2-301 files still reference `ProcessedDocument.structure`).
- `docs/PHASE_2_MILESTONE_2_3_SPECIFICATION_REVIEW.md` (the findings record).

**Follow-up:** before Milestone 2.3 implementation begins, the roadmap should be aligned to the §5.4 channel (or the spec freeze record should cite this report as the authoritative remediation). No code changes were made.

---

## Verification

- v1.0 → v1.1 header with remediation lineage; status set to **pending freeze**. ✓
- No remaining `ProcessedDocument.structure`, `document.structure`, `doc.structure`, `structure = None`, `structure stays None`, `b-s11-1`/`b-s1-1`, or `processed_document.py` references anywhere in the spec. ✓
- All six task rows, both diagrams, AC4, DoD, checklist, test, and rollback sections internally consistent with the `metadata.extra["structure"]` channel. ✓
