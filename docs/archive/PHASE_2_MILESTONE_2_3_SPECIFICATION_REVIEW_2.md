# Phase 2 — Milestone 2.3 Engineering Specification — Review 2 (Post-Remediation)

**Specification:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` v1.1 (remediated)
**Remediation record:** `docs/PHASE_2_MILESTONE_2_3_SPECIFICATION_REMEDIATION_REPORT.md`
**Prior review:** `docs/PHASE_2_MILESTONE_2_3_SPECIFICATION_REVIEW.md` — R-1 (blocker) + C-1…C-7 + O-1…O-4
**Date:** 2026-08-01
**Review method:** Line-by-line re-read of v1.1; every code-level claim re-verified against the live codebase (`app/pipelines/ingest_workflow.py`, `app/domain/documents.py`, `app/domain/processed_document.py`, `app/core/config.py`, `app/infrastructure/semantic_chunking.py`, `app/infrastructure/routing/processor_impls.py`, `app/templates/obsidian_note.py`, `app/infrastructure/document_intelligence/__init__.py`, classifier/ingestors). No code modified.

---

## R-1 — Resolved ✅

**Code-verified root cause:** `_run_routed_processor` (`ingest_workflow.py:421-495`) builds `enriched = document.model_copy(update={"text": result.extracted_text or document.text, "source_type": result.source_type})` (lines 463-468) and returns `(enriched, result.confidence, result.ocr)` (line 477) — the `ProcessedDocument` is indeed discarded, and `SourceDocument` is `extra="forbid"` (`documents.py:30`) with no `structure` field.

**Verified remediation (§5.4):** structure serialized into `document.metadata.extra["structure"]`:
- `DocumentMetadata.extra: dict[str, Any]` (`documents.py:24`) accepts arbitrary keys — no schema change; `DocumentMetadata`/`SourceDocument` untouched.
- The proven `parent_id` precedent exists at `ingest_workflow.py:396-400` (fresh `extra` dict + nested `model_copy`); the spec prescribes "exactly like `parent_id`", so the safe nested-copy form is unambiguous.
- The enrichment runs inside `_run_routed_processor` where `result` (ProcessedDocument, with `source_type`/`extracted_text`) is still in scope — implementable exactly as written.
- **AC4 target is real:** `IngestionWorkflowResult.document` (line 63, populated at line 335) is the enriched document, so `result.document.metadata.extra["structure"]` is observable by the integration test and by Phase 3 consumers.
- **Offsets invariant holds:** `_run_knowledge_engine` chunks `document.text` (line 514) — the enriched text, identical to `result.extracted_text or document.text` fed to the analyzer.
- **Note-template claim holds:** `_metadata_section(analysis.extracted_metadata)` (`obsidian_note.py:125`) and explicit-field frontmatter mean `metadata.extra` keys are carried but not rendered (proven by `parent_id`/`attachment_paths`).

## C-1…C-7 — Addressed ✅

| Finding | Resolution | Verified |
|---------|-----------|----------|
| C-1 effort | §11.1: task-sum 3.75 d → **4 dev-day budget** (M2.2 addendum-4 precedent) | ✓ internally consistent everywhere (no other effort figures remain) |
| C-2 block IDs | §15.4: `b-s-1-1`, `b-s-1-1-1`, `b-s-2-1`, `b-s-2-2` under the §4.2 scheme | ✓ |
| C-3 text-bearing kinds | §7: `TEXT_BEARING_KINDS = frozenset({"markdown", "text"})`; PDF/OCR excluded | ✓ kind names match live classifier/ingestors (`"markdown"` classifier.py:34-35, `"text"` :36, txt_ingestor.py:20, markdown_ingestor.py:18) |
| C-4 depth caps | §7: `MAX_HEADING_LEVEL = 6`, `MAX_SECTIONS = 10_000` (warn+truncate); referenced in §9, §12, §13 | ✓ |
| C-5 `enrich_analysis_input` | Contract-only (§7, §7 YAML, §11.3 L5 exception); no task may consume it | ✓ |
| C-6 config ownership | P2-305 owns `core/config.py` + `config/default.yaml`; P2-306 touches only `structure/detector.py` | ✓ matches `IntelligenceSettings` (`config.py:285-292`) needing a new declared `structure:` field (`extra="forbid"`) — feasible |
| C-7 diagrams show channel | §6 sequence + §15.2 data-flow both show the `metadata.extra["structure"]` write + no-key branch | ✓ |

## New inconsistencies introduced? — None material

- One cosmetic artifact found and fixed during this review: the §6 sequence diagram still declared `participant PD as ProcessedDocument` (unused after remediation) while referencing the undeclared `DOC` participant. Corrected to `participant DOC as enriched SourceDocument`. Mermaid renders either way; now self-consistent.
- §5.4 step 5 phrase "persisted note metadata" is loose (the key survives on `IngestionWorkflowResult.document`; the note template ignores extra keys) — the parenthetical already states the accurate contract. Non-blocking wording, no action required.

## Architecture — internally consistent ✅

The `metadata.extra["structure"]` channel is used uniformly across §1 (objectives 2/4), §2.1, §3, §4.2, §5.1/5.2/5.4, §6, §7, §8 AC4, §9, §10 R3, §11.1 P2-305, §12, §13, §14, §15.2. **Zero residual `ProcessedDocument.structure` references** in the spec (verified by grep). Enrichment is additive inside `_run_routed_processor` with no pipeline-stage changes and no hook-registry registration; `SemanticChunker` untouched (AC5). No unrelated-component changes. R-4 "no key ⇒ M2.2-identical" holds on both the processor-None/fallback paths (`ingest_workflow.py:455, 495`) and the disabled path.

## Data flow — implementable ✅

Every step of §5.4 maps to real code:
1. Post-processor-success scope: lines 458-468. `result.source_type` is `ProcessedDocument.source_type` (`processed_document.py:20`), set to `"markdown"`/`"text"` by `MarkdownProcessor`/`TextProcessor` passthroughs (`processor_impls.py:135-139`, :124-128).
2-3. Serialization + nested `model_copy` mirror `ingest_workflow.py:396-400`.
4-5. No-key semantics; survival on `IngestionWorkflowResult.document` (line 335).
Both CLI (`entry.py:373`) and queue worker (`worker.py:176`) reach `run` → `_process_document` → `_run_routed_processor`, supporting the §13 integration coverage claim.

## Public interfaces — coherent ✅

- `StructureAnalyzer.analyze(text, source) -> DocumentStructure`; pure/reentrant (O-2).
- Models in `app/domain/document_intelligence.py` alongside existing `MetadataExtraction` (O-1) — file exists and is the right home.
- Composition root `app/infrastructure/document_intelligence/__init__.py` exists (1-line docstring) and can gain `analyze_document_structure` + `get_default_structure_analyzer`.
- Settings plumbing `create_default` → `from_runtime` → `__init__` (M2.2 L1/L2 pattern) is real (`ingest_workflow.py:131, 167`).

## Dependency graph — correct ✅

§11.1 deps, §11.2 waves, and §15.3 agree: P2-301 → P2-302‖P2-303 → P2-304 → P2-305 → P2-306; outbound R-2 hard dep P2-305 → P2-406/P2-506/P2-606. Critical path correct.

## Acceptance Criteria — testable ✅

- AC1/AC2/AC3: unit-testable on committed fixtures (§13).
- AC4: integration target exists and is observable (`IngestionWorkflowResult.document.metadata.extra["structure"]`, deserializable via `DocumentStructure.model_validate`); negative paths (disabled, non-text-bearing kind) are explicit.
- AC5: regression suites named (`test_knowledge_engine.py`, `test_text_preprocessing.py`) exist and are real.
- Heading-rule divergence (`^#{1,6}\s+\S` vs `SemanticChunker._HEADING_PATTERN` `^#{1,6}\s+.+`, `semantic_chunking.py:13`) is correctly documented in R1 (O-3) and consistent with AC2/AC5.

---

## Verdict

✅ **Ready for Freeze**
