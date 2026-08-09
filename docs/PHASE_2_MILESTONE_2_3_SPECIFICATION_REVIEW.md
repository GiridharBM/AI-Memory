# Milestone 2.3 Specification Review Report

**Reviewed document:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` (v1.0, draft — pending freeze)
**Companion documents read:** `docs/PHASE_2_MILESTONE_2_3_IMPLEMENTATION_ROADMAP.md`, `docs/MASTER_ENGINEERING_DESIGN_DOCUMENT.md` (§2.4/§2.6/§7.3, G12–G14), `docs/01_Current_Implementation_Report.md`, `docs/02_Current_Project_Status_Report.md`
**Reviewer:** Principal AI Architect + Principal Engineering Reviewer
**Date:** 2026-08-01
**Review method:** Line-by-line comparison against the frozen Phase 2 v1.1 baseline and Engineering Baseline addenda; every code-level claim verified against the live codebase (`app/pipelines/ingest_workflow.py`, `app/infrastructure/routing/processor_impls.py`, `app/domain/documents.py`, `app/domain/processed_document.py`, `app/core/config.py`, `app/infrastructure/semantic_chunking.py`).
**Scope:** Architectural consistency, dependency correctness, interface design, data models, configuration, implementation order, acceptance criteria, definitions of done, rollback strategy, testing strategy, backward compatibility, future extensibility.

---

## 1. Verdict Summary

| Dimension | Verdict |
|-----------|---------|
| Architectural consistency | ❌ **Fail** — R-1 (structure has no surviving owner) |
| Dependency correctness | ✅ Pass |
| Interface design | ✅ Pass (with O-2 note) |
| Data models | ⚠️ Pass with note (O-1) |
| Configuration | ⚠️ Pass with note (C-5, C-6) |
| Implementation order | ✅ Pass |
| Acceptance criteria | ❌ **Fail** — R-1 (AC4 not observable) |
| Definitions of done | ✅ Pass |
| Rollback strategy | ⚠️ Pass with note (vacuous until R-1 resolves) |
| Testing strategy | ⚠️ Pass with note (R-1 affects AC4 integration test) |
| Backward compatibility | ✅ Pass |
| Future extensibility | ✅ Pass (with O-4 note) |

**Verdict: ❌ Needs Specification Remediation** — one Required finding (R-1) must be resolved before freeze; the C/O findings should be dispositioned at freeze time.

---

## 2. Findings

### R-1 (Required) — `structure` enrichment into `ProcessedDocument` is lost: the pipeline discards the only object that would carry it

**Location:** Spec §1 objective 2 (line 16), §2.1, §6 sequence diagram (line 171 `RP->>PD: doc.structure = result`), P2-305 (line 253), AC4.

**Problem:** The spec — faithfully following frozen P2-305 "enrichment call is additive inside `_run_routed_processor` after processor success" — has the analyzer assign `result.structure` on the `ProcessedDocument` returned by the routed processor. **That object does not survive the call.** Verified in `_run_routed_processor` (`app/pipelines/ingest_workflow.py:457-477`):

```python
result = processor.process(document)          # result: ProcessedDocument
result.language = language
result.parent_id = parent_id
enriched = document.model_copy(               # enriched: SourceDocument
    update={"text": result.extracted_text or document.text,
            "source_type": result.source_type},
)
return enriched, result.confidence, result.ocr   # result itself is discarded
```

The workflow continues with the enriched `SourceDocument`, which is `ConfigDict(extra="forbid")` with **no** `structure` field (`app/domain/documents.py:27-37`). Nothing downstream — note generation, `_run_knowledge_engine` chunking, `IngestionWorkflowResult` — can observe `structure`. Objective 2's "so it survives the pipeline and is available to later consumers" is therefore not achievable as written, and **AC4's integration test ("Markdown + text file through `IngestionWorkflow` asserting `document.structure` non-empty") has no observable target.** The same pattern for `parent_id` in M2.2 was solved by riding `document.metadata.extra` (`ingest_workflow.py:397` `extra["parent_id"] = parent_id`), which is the proven channel.

**Required remediation (choose one in the spec, then update §6/§5.2 diagrams and AC4):**
1. **Lazy (proven pattern):** serialize the analyzer result into `document.metadata.extra["structure"]` on the enriched document (`model_dump()`), and attach to the note/`IngestionWorkflowResult` as the "stored with the note/analysis" target state (frozen spec §3 Target State). Zero signature changes.
2. **Explicit:** change `_run_routed_processor`'s return contract to also surface the `ProcessedDocument` (or a `structure` field), threaded through `_process_document`.
3. **Schema:** add an additive `structure` field to `SourceDocument` — most invasive; not recommended this milestone.

AC4 must assert against the chosen observable surface (e.g., `IngestionWorkflowResult`/note metadata), not the discarded ProcessedDocument.

---

### C-1 (Recommended) — Effort arithmetic is internally inconsistent

Spec §11.1 (line 256): "~3.75 dev-days (frozen estimate: **3 dev-days**)" while the task table sums to 3.75 d (0.5+1+1+0.5+0.5+0.25). The roadmap already resolves this to a **4 dev-day budget**. Reconcile the spec to the same number (mirror the M2.2 F-3 / addendum-4 precedent) so the gate budget is unambiguous.

### C-2 (Recommended) — Block ID scheme contradiction between §4.2 and §15.4

§4.2 (line 84) defines `block_id = "b-<section_id>-<n>"`; §15.4 (line 386) renders a block in section `s-1-1` as `b-s11-1`. Under the scheme it must be `b-s-1-1-1`. Fix the diagram.

### C-3 (Recommended) — "text-bearing kinds" is undefined

Objective 1/2, DoD, and diagrams (lines 15, 16, 31, 162, 353) use "text-bearing" while AC4 pins "markdown/text kinds". Pin the set as a module constant `TEXT_BEARING_KINDS = frozenset({"markdown", "text"})` and state explicitly that PDF/OCR-prose kinds are **excluded** this milestone (matches AC4; documented upgrade path when consumers exist). Not a config key (L5).

### C-4 (Recommended) — "nested-depth cap" has no value

§12 checklist (line 289) and §13 unit scope (line 304) reference a "nested-depth cap" without defining it. Pin: `MAX_HEADING_LEVEL = 6` (ATX), `MAX_SECTIONS = 10_000` (exceeded → warn + truncate in tree order, never raise).

### C-5 (Recommended) — `enrich_analysis_input` conflicts with the spec's own L5

The spec declares `enrich_analysis_input: false` (lines 42, 192, 195) as a normative config key, yet lesson L5 (§11.3) says "no config keys declared that are not consumed." Resolve by labeling it a **contract-only field** (baseline addendum 3 / R-7), explicitly stating no code reads it this milestone — the same way the roadmap's D7 records the exception.

### C-6 (Recommended) — P2-306 vs P2-305 file ownership

The task table lists `core/config.py` under P2-306 (frozen §4.3), but `StructureSettings` must exist by P2-305 for `_run_routed_processor` to read `enabled`. State the split explicitly in the task table: settings in P2-305, only the 5 MB cap constant in P2-306.

### C-7 (Recommended) — Flow diagrams must show the post-R-1 persistence channel

§6 sequence diagram (lines 162-171) and §5.2 diagram draw `structure` onto a ProcessedDocument that continues through the pipeline. Once R-1's channel is chosen, these diagrams must show where `structure` actually rides (enriched document metadata / workflow result / note), or they will mislead implementers.

---

### O-1 (Optional) — pydantic-vs-dataclass model inconsistency (MEDD-recognized)

`DocumentStructure`/`DocumentSection`/`DocumentBlock` are pydantic (spec §3) while `ProcessedDocument` is `@dataclass(slots=True)` (MEDD §1.5 line 152 flags this as a system-wide inconsistency). Functionally fine; follow the `MetadataExtraction` precedent (pydantic model in `app/domain/document_intelligence.py`). A one-line note in P2-301 suffices.

### O-2 (Optional) — specify `StructureAnalyzer` statelessness/reentrancy

The worker processes documents sequentially today, but a shared mutable analyzer would break under future parallelism. State that `analyze()` is pure/reentrant (no shared mutable state; all state local to the call).

### O-3 (Optional) — record the heading-rule divergence in the spec

The detector rule `^#{1,6}\s+\S` deliberately diverges from `SemanticChunker._HEADING_PATTERN` (`^#{1,6}\s+.+`, fence-unaware). This is intentional (AC2 vs AC5) and documented in roadmap D9 but not in the spec; one line in §10 R1 mitigation would make the spec self-contained.

### O-4 (Optional) — define the Phase 3 consumption seam

MEDD §7.3 target architecture ends with "parent ID assignment → DocumentChunk[]". A one-line contract that Phase 3 maps `DocumentSection.id` → chunk `metadata.parent_section_id` would make the "input contract" (objective 4) concrete without implementing anything.

---

## 3. Dimension-by-Dimension Review

### 3.1 Architectural consistency — ❌ Fail (R-1)
- "No pipeline stages added; no flow reordered" is respected; enrichment is a single additive call site — but the call site as specified writes to an object that is then discarded. The one architectural defect in an otherwise faithful mapping of frozen §3.

### 3.2 Dependency correctness — ✅ Pass
- Task DAG is correct and cycle-free: P2-301 → {302, 303} → 304 → 305 → 306; P2-302 ‖ P2-303 valid (both need only P2-301).
- Zero new dependencies (stdlib `re` + existing pydantic); no wheel risk; environment prerequisite (M2.2 gate closed) correctly stated.
- Hidden dependency checked: analyzer input `result.extracted_text or document.text` equals the text later chunked (`ingest_workflow.py:514-516` on the enriched document) — offset contract holds.

### 3.3 Interface design — ✅ Pass
- `StructureAnalyzer.analyze(text, source) -> DocumentStructure`, public APIs (`analyze_document_structure`, `StructureAnalyzer`, three models), and internal APIs (`_detect_headings`, `_detect_blocks`, `_build_tree`) match frozen §2.3 verbatim. Registry-free fixed service is the right call (C-1 boundary).

### 3.4 Data models — ⚠️ Pass with note (O-1)
- Fields (id/title/level/parent_id/blocks/start_char/end_char) match frozen; additive `structure: DocumentStructure | None = None` on `ProcessedDocument` with `None` default is correct and backward compatible. See O-1 for the pydantic-in-slots-dataclass note.

### 3.5 Configuration — ⚠️ Pass with note (C-5, C-6)
- `intelligence.structure.enabled: true` + `enrich_analysis_input: false` match addendum 3; plumbing path (`from_runtime` → workflow → `_run_routed_processor`) matches the proven P2-203/P2-208 remediation pattern. C-5 (contract-only key) and C-6 (file ownership) need one-line resolutions.

### 3.6 Implementation order — ✅ Pass
- Waves and critical path are sound; R-2 hard gate (P2-305 before M2.4/2.5/2.6 wiring) correctly surfaced and binding.

### 3.7 Acceptance criteria — ❌ Fail (R-1)
- AC1/AC2/AC3/AC5 are precise and testable. AC4 ("document.structure populated … when enabled") has no observable surface because of R-1. Must be re-targeted to the chosen persistence channel.

### 3.8 Definitions of done — ✅ Pass
- Each task's DoD is concrete and testable once R-1 lands; offsets-verified-against-samples, 5 MB cap, and chunker-regression items are unambiguous.

### 3.9 Rollback strategy — ⚠️ Pass with note
- `enabled: false` → structure stays `None`; additive-only; no legacy branch (R-4); per-task atomic commits. Until R-1 resolves, "M2.2-identical documents" is trivially true regardless of the flag — the rollback contract gains real meaning only when structure has an observable owner.

### 3.10 Testing strategy — ⚠️ Pass with note
- Unit/integration/regression/perf/manual layers map to concrete files and markers; AC→test traceability is explicit; fixtures committed (L6); fence-vs-heading and offset-accuracy tests are the right risk focus. AC4 integration test needs re-targeting (R-1); baseline counts (605 unit / 14 integration) verified against the M2.2 gate.

### 3.11 Backward compatibility — ✅ Pass
- Additive field, `None` default, chunker untouched (AC5), notes byte-identical this phase (no template consumption), no migration, no legacy branch.

### 3.12 Future extensibility — ✅ Pass
- `DocumentStructure` is the correct Phase 3 input contract (MEDD G14 / §7.3: heading detection → section splitting → parent ID assignment); shared call site is the reuse seam for M2.4/2.5/2.6 (R-2). O-4 would make the Phase 3 seam explicit.

---

## 4. Non-blocking Recommendations
1. Resolve R-1 by pinning the structure persistence channel (metadata-extra is the proven, minimal option) and re-targeting AC4 + §6/§5.2 diagrams.
2. Reconcile effort to 4 dev-days (C-1); fix the §15.4 block-ID example (C-2).
3. Pin `TEXT_BEARING_KINDS` (C-3), the caps (C-4), the `enrich_analysis_input` contract-only label (C-5), and the P2-305/P2-306 file split (C-6).
4. Apply the O-items at implementation time (statelessness note, heading-rule note, Phase 3 seam, model-placement note).

---

## 5. Final Verdict

❌ **Needs Specification Remediation**

The specification is faithful to the frozen v1.1 baseline, its dependency graph and ordering are correct, its interfaces reproduce the proven M2.2 patterns, and its performance/rollback/backward-compatibility contracts are sound. However, **R-1 is a genuine architectural defect**: as written, structure is attached to a `ProcessedDocument` that the pipeline discards, making objective 2 and AC4 unverifiable and the frozen "stored with the note/analysis" target state unreachable. R-1 must be remediated (pin the persistence channel and re-target AC4 + diagrams) before the spec can be frozen; C-1…C-7 are one-line dispositions to be bound at freeze time.
