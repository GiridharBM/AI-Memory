# Milestone 2.2 — Documentation Synchronization Report

**Author:** Principal Technical Writer / Engineering Architect
**Date:** 2026-08-01
**Scope:** Synchronize project documentation with the completed, approved Milestone 2.2 (Metadata Extraction Framework) implementation.
**Constraint honored:** No source code modified. All claims verified against the live codebase and the approved implementation/engineering-review reports. No features invented.

---

## Summary

| Document | Status | Sections updated |
|---|---|---|
| `docs/changelog.md` | ✅ Updated | New `[0.3.0]` entry (Milestone 2.2) |
| `docs/01_Current_Implementation_Report.md` | ✅ Rewritten | Architecture, folder structure, pipeline, ingestion, new §7 Metadata Extraction Framework, prompt generation, configuration, error handling, limitations, missing features |
| `docs/MASTER_ENGINEERING_DESIGN_DOCUMENT.md` | ✅ Synchronized | §2.4 (Current Implementation, Problems, Goals, Architecture diagram, Interfaces, Data Models, Error Handling, Security, Trade-offs, ADR-001, Acceptance Criteria, Future Enhancements), top-level architecture diagram, subsystems table, roadmap/epic rows, risk R07, §10.1 checklist |
| ADR-001 (inside MEDD §2.4) | ✅ Updated | Consequence note now describes the three-tier detection chain |

---

## 1. `docs/changelog.md`

**Change:** Added `## [0.3.0] — 2026-08-01 — Milestone 2.2: Metadata Extraction Framework` above the untouched `[0.2.0]` (Milestone 2.1) entry, plus the `[0.3.0]` link reference. Keep a Changelog / SemVer format preserved.

**Covered items (task requirement → entry):**
- Metadata Framework → "Metadata extraction subsystem" (protocol + `MetadataExtraction` model)
- Metadata Extractors → "Built-in stdlib-only extractors" (Pdf/Docx/Pptx/Notebook/Audio/Email)
- MIME Detection → `detect_mime` (magic-byte sniff, optional `python-magic`, fallback table)
- Language Detection → `detect_language` (`py3langid` + stdlib heuristic, en/fr/de/ja)
- Metadata Registry → `DocumentMetadataService` registry + `register_extractor()`
- Metadata Enrichment → enrichment fields (`language`, `parent_id`, `extra` merge)
- Pre/Post Ingestion Hooks → `IngestionHook` protocol + configurable hook chains
- Email Attachment Processing → `EmailIngestor` attachment extraction + recursive re-ingestion
- Parent/Child document support → `parent_id` linking, `max_attachments` cap, depth guard
- Configuration additions → `intelligence.metadata.*` block
- New APIs → `detect_mime`, `detect_language`, `register_extractor`, `register_hook`, `MetadataExtraction`, `DocumentMetadataService`
- Tests → `### Tests` section (605 unit, 14/7 integration, AC test, coverage 86.80%, fallback-path coverage, regression tests)

**Verification note:** the claim "`url_timeout_seconds` plumbing into downloader/reader calls" (originally from the P2-206 review) was **corrected** — live grep shows the key is defined in `MetadataSettings` but never consumed; `GitHubReadmeIngestor` uses a hardcoded 30s timeout. The entry now says "`url_timeout_seconds` config key added" only.

## 2. `docs/01_Current_Implementation_Report.md`

**Change:** Full rewrite to reflect the current implementation; every obsolete statement removed. Section-by-section:

| Section | Update |
|---|---|
| §1 Overview | Mentions metadata enrichment of ingested documents |
| §2 Architecture | Diagram now shows `document_intelligence/metadata/` (extractors, mime, language, hooks) |
| §3 Folder Structure | Added `metadata/` files; `email_ingestor.py` noted as attachment-extracting; `domain/document_intelligence.py`; classifier/processor comments updated |
| §4 Pipeline | Enrichment embedded in the ingestion step; MIME + language in classify; `parent_id`; child re-ingestion; respond-in-{language} analysis |
| §5 Ingestion | `DocumentIngestionService` now documents settings injection, size guard, pre/post hooks, enrichment; `EmailIngestor` row updated (`.eml`, attachment extraction); limitations updated |
| §6 OCR | Unchanged (already current) |
| **§7 Metadata Extraction Framework (NEW)** | 7.1 protocol + registry; 7.2 built-in extractors table; 7.3 MIME detection (3-tier); 7.4 language detection; 7.5 enrichment pipeline + hook chain; 7.6 prompt language integration; 7.7 email attachments + parent/child; 7.8 configuration table; 7.9 limitations |
| §8–§18 | Renumbered; stale "prompt is hardcoded, not configurable" removed from Prompt Generation; language-aware user prompt + configurable OCR/vision/handwriting templates documented |
| §19–§21 | Renumbered; configuration section documents `intelligence.{ocr,prompts,metadata}` |
| §22 Error Handling | Added rows for metadata-enrichment containment and hook-error containment |
| §23 Current Limitations | Added metadata rows (stdlib-only extractors, no EXIF/R-3, en/fr/de/ja heuristic, one-level email depth, `parent_id` unconsumed, `url_timeout_seconds` not consumed) |
| §24 Missing Features | Added "Image/EXIF metadata" (partially implemented, deferred to M2.5) |
| §25 Missing Features | Table renumbered to §25 |

## 3. `docs/MASTER_ENGINEERING_DESIGN_DOCUMENT.md`

**Change:** §2.4 synchronized plus directly-contradicting references elsewhere.

### §2.4 Subsystem: Document Ingestion
- **Current Implementation** — now describes the 21-ingestor service running the enrichment pipeline (size guard → pre-hooks → ingestor → metadata extraction/merge → post-hooks) and the full `metadata/` subsystem (registry, extractors, MIME, language, hooks, email attachments).
- **Problems** — removed "No pre/post processing hooks"; added the accurate gap that `url_timeout_seconds` is defined but unconsumed.
- **Goals** — MIME detection, hook system, and size limits struck through as **Implemented**; lazy instantiation and unified URL/file handling remain future.
- **Architecture (sequence diagram)** — updated to the real flow: `_normalize_source` → `_enforce_size_limit` → `_run_pre_hooks` → `_select_ingestor` (extension match) → `ingest` → `_enrich_document` → `_run_post_hooks`; added note on email-attachment child re-ingestion.
- **Interfaces** — `DocumentIngestionService.__init__` now shows `settings`, `hooks`, `metadata_service`; added `DocumentMetadataService` class contract.
- **Data Models** — added `MetadataExtraction`.
- **Error Handling** — added enrichment and hook failure semantics.
- **Security Considerations** — added attachment filename sanitization, `max_attachments` cap, temp-file `finally` cleanup.
- **Trade-offs** — extension-vs-MIME wording now matches the implemented ADR-001 precedence.
- **Acceptance Criteria** — each item marked with its verification result (incl. AC 6 email→4 notes).
- **Future Enhancements** — removed "Email attachment recursive processing"; replaced with nested-recursion and `url_timeout_seconds` consumption items.

### ADR-001 (consequence note)
Replaced "extension-only when unavailable / extension-only detection" with the implemented chain:

```
Extension (mimetypes.guess_type + .ipynb supplement)
    ↓  (extensionless or unknown extension only)
Magic-byte sniff: python-magic from_buffer (if importable)
    ↓  (absent, or libmagic returns generic text/plain / application/octet-stream)
Stdlib fallback table (_sniff_mime)
```

plus the consequence that known extensions always win and a warn-once log fires when `python-magic` is absent.

### Related references (outside §2.4)
- Top-level architecture diagram — classifier line now "extension + MIME + language → kind".
- Subsystems table — added "Metadata Extraction" row (Stable, M2.2).
- §7.9 ingestion component — `IngestionHook` extension point marked implemented.
- Phase 2 roadmap table — MIME detection, language detection, hooks, and email attachment parsing rows marked ✅ delivered; table-detection rows left pending.
- Epic 2 feature list — the four delivered items marked ✅; PDF table items left pending.
- Risk register R07 — mitigation updated from "extension-only detection" to "stdlib magic-number sniff table + warn-once log".
- §10.1 Version 1.0 checklist — ADR-001 item checked off and reworded to the implemented chain.

## 4. Verification Method

Every claim was checked against the live codebase before writing:
- `app/infrastructure/document_intelligence/metadata/{__init__,extractors,mime,language,hooks}.py` — read in full.
- `app/infrastructure/ingestion/service.py` — enrichment/hook/size-guard flow verified.
- `app/infrastructure/ingestion/email_ingestor.py` — attachment extraction, sanitization, temp cleanup verified.
- `app/pipelines/ingest_workflow.py` — `_ingest_children` / `_ingest_child` / `parent_id` verified.
- `app/infrastructure/routing/classifier.py` — `_detect_mime` / `_detect_language` gating verified.
- `app/application/ai_processor.py` + `app/prompts/document_analysis.py` — language propagation verified.
- `app/core/config.py` + `config/default.yaml` — `MetadataSettings` block and defaults verified.
- Negative check: `url_timeout_seconds` is defined but not consumed anywhere (grep across the whole `app/` tree) — documented as a limitation, not as implemented.

## 5. Not In Scope

- `docs/02_Current_Project_Status_Report.md`, `03_Future_Architecture_Report.md`, `04_Evaluation_Benchmark_Report.md`, `05_Development_Roadmap.md` — not part of this task; flagged for separate review if milestone close-out requires them current.
- The Milestone 2.2 completion report / release artifacts remain outstanding close-out deliverables.
