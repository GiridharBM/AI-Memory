# Milestone 2.2 — Metadata Extraction Framework: Engineering Specification

**Source of truth:** `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` v1.1 (**FROZEN**, Engineering Baseline 2026-08-01), Milestone 2.2 row (§3) + Task Breakdown §4.2.
**Baseline:** `docs/PHASE_2_ENGINEERING_BASELINE.md`. **Binding addenda §10 that apply here:** (1) `enabled: true` in the `intelligence.metadata` config block; (4) Estimated Effort updated to 4–5 dev-days.
**Scope of this document:** expand Milestone 2.2 into executable engineering tasks. **No code is implemented by this document.**
**Version:** 1.0
**Status:** 🔒 **FROZEN (2026-08-01).** Freeze contract: `docs/PHASE_2_MILESTONE_2_2_SPECIFICATION_FREEZE.md`. Future implementation must follow this document unless a formal design revision is approved per the Change Control Policy (Baseline §11). Review record: `docs/PHASE_2_MILESTONE_2_2_SPECIFICATION_REVIEW.md` (✅ Ready for Implementation).

---

## 1. Milestone Overview (normative, from frozen spec)

| Field | Value |
|-------|-------|
| **Objective** | Metadata is complete, consistent across source types, language-aware, and filterable (Phase 4 search metadata filtering depends on it). |
| **Scope (in)** | `MetadataExtractor` interface + registry; built-in extractors (pdf/audio/email/docx/pptx/notebook); **email attachment parsing** (MIME parse → parent email note + recursive ingestion of attachments as child documents — MEDD Phase 2 roadmap, P2-208); image/EXIF **`DocumentMetadata`-level fields only** (raw EXIF read + `ImageInfo` owned by Milestone 2.5 P2-502 — single-owner boundary, R-3); MIME detection service (stdlib + optional `python-magic` per ADR-001); language detection service (optional `py3langid` + pure-heuristic fallback); prompt adaptation; hook chain; size/time limits. |
| **Scope (out)** | Metadata *search filtering* (Phase 4); remote URL timeout deep-tuning beyond defaults. |
| **Current implementation** | Only `PdfIngestor` fills title/author/dates/producer (`pdf_ingestor.py:47-67`); `ImageIngestor` MIME via static map; `DocumentClassification.language` and `ProcessedDocument.language` never set (`processed_document.py:19`); `classifier.py:84` uses stdlib `mimetypes.guess_type`; analysis prompt is English-only; `EmailIngestor` (`email_ingestor.py`) extracts headers+body into a single `SourceDocument` — **no attachment parsing exists today** (R-1). |
| **Target state** | Ingestion runs registered metadata extractors → merged `MetadataExtraction` → `DocumentMetadata`; classifier consults MIME service; language service populates `DocumentClassification.language`; analysis prompt includes a language instruction; hooks execute before/after `ingestor.ingest()`; emails parse into a parent document and each attachment ingests as a child document carrying `parent_id` (R-1). |
| **Dependencies** | Optional (new): `python-magic` (ADR-001: warning-only if absent), `py3langid`. Required new: none — all built-in extractors are stdlib-only (zipfile/ElementTree for docx/pptx core props, `json` for notebooks, PyMuPDF already present for PDF). Wheel availability must be verified for `cp314-win_amd64` at milestone start, including python-magic's libmagic DLL (R-5 / Baseline R11). |
| **Backward compatibility** | All new fields additive; metadata enrichment is a superset of today's values; MIME detection never overrides an explicit ingestor match for known extensions (ADR-001). |
| **Rollback** | `intelligence.metadata.enabled: false` bypasses enrichment and returns Phase-1-identical documents; MIME/language toggles independently disableable; **no legacy branch retained** (R-4). |
| **Estimated effort** | 4–5 dev-days (**addendum 4**; tasks total ~5 d). |
| **Complexity / Risk** | Low–Medium / medium (highest per-task risk: P2-208 recursive attachment ingestion). |

---

## 2. Normative Interfaces (from frozen spec — do not alter)

```python
class MetadataExtractor(Protocol):
    source_types: tuple[str, ...]
    def extract(self, document: SourceDocument) -> dict[str, Any]

class IngestionHook(Protocol):
    name: str
    def pre(self, source: SourceReference) -> SourceReference
    def post(self, document: SourceDocument) -> SourceDocument

class LanguageDetector(Protocol):
    def detect(self, text: str) -> tuple[str, float]
```

- Public APIs: `MetadataExtraction`, `DocumentMetadataService`, `detect_language(text)`, `detect_mime(path)`, `register_extractor()`, `register_hook()`.
- Internal APIs: per-type built-in extractors; `_magic_fallback(path)`; `_language_heuristic(text)`.
- Package layout (§7.2 frozen): `app/infrastructure/document_intelligence/metadata/` = `__init__.py` (registry + `DocumentMetadataService`), `extractors.py`, `mime.py`, `language.py`, `hooks.py`; shared domain models in `app/domain/document_intelligence.py` (`MetadataExtraction`).

## 3. Normative Configuration (frozen §3 row + addenda — do not alter)

```yaml
intelligence:
  metadata:
    enabled: true            # addendum 1; false ⇒ Phase-1-identical documents (R-4)
    extractors: "default"    # "default" = the five built-ins; future plugin names
    mime_enabled: true       # false ⇒ stdlib guess_type path, no magic sniff
    language_detection_enabled: true
    max_file_size_mb: 50     # pre-hook rejects before file read (FR-ING-7)
    url_timeout_seconds: 30  # remote-source guard (FR-ING-8)
    email_attachments: true  # P2-208
    max_attachments: 20      # attachment-bomb cap; reuse of max_file_size_mb
    hooks:
      pre: []                # plugin names, run before ingestor.ingest()
      post: []               # plugin names, run after ingestor.ingest()
```

Rollback contract: `enabled: false` must return Phase-1-identical documents; MIME and language detection are independently disableable; no `legacy` mode exists (R-4).

---

## 4. Task Breakdown

### P2-201 — Metadata extractor interface + registry

| Field | Detail |
|-------|--------|
| **Task ID** | P2-201 |
| **Objective** | Define the `MetadataExtractor` protocol, a `DocumentMetadataService` registry (register/select/merge), and the `MetadataExtraction` model — with a deterministic empty-registry error. |
| **Purpose** | The pluggable seam every other 2.2 task builds on; one deterministic metadata path replaces per-ingestor ad-hoc code (design principle "easy to extend"). |
| **Dependencies** | None (milestone foundation). |
| **Files likely affected** | `app/domain/document_intelligence.py` (new — `MetadataExtraction`), `app/infrastructure/document_intelligence/metadata/__init__.py` (new — registry + `DocumentMetadataService` skeleton), `metadata/extractors.py` (new, empty until P2-202). |
| **Classes likely affected** | `DocumentMetadataService` (new), `MetadataExtractor` (Protocol, new), `MetadataExtraction` (new). |
| **Interfaces** | `MetadataExtractor` protocol as in §2; `DocumentMetadataService.register(extractor)` / `extractors_for(source_type)`; merge rule: extracted keys map to `DocumentMetadata` fields, unknown keys go to `extra`; `MetadataExtraction(source_type, values: dict[str, Any], extractor: str)`. |
| **Implementation Steps** | (1) Create the `document_intelligence/` package + `metadata/` subpackage; (2) define `MetadataExtraction` in `domain/document_intelligence.py`; (3) define the `MetadataExtractor` Protocol; (4) implement `DocumentMetadataService` with `register`, `extractors_for`, and a `merge(metadata: DocumentMetadata, extraction) -> DocumentMetadata` helper (additive: only known fields written); (5) no-extractor-for-type path returns an empty extraction + debug log, never raises; (6) `register_extractor()` public alias. |
| **Configuration Changes** | None (config consumed at P2-207). |
| **Testing Strategy** | Unit: register/select per `source_types`; merge writes known fields only and routes unknown keys to `extra`; no-extractor type → empty merge; duplicate-registration behavior defined. |
| **Acceptance Criteria** | `MetadataExtractor` protocol + registry + merge work; no ingestion behavior change yet. |
| **Definition of Done** | Interface reviewed, unit-tested, not wired into ingestion. |
| **Rollback Plan** | Pure addition; not wired anywhere yet — removal is a safe revert. |
| **Estimated Complexity** | Low. |
| **Risk** | Low. |

---

### P2-202 — Built-in extractors (pdf/audio/email/docx/pptx/notebook)

| Field | Detail |
|-------|--------|
| **Task ID** | P2-202 |
| **Objective** | Implement five stdlib-only extractors that fill title/author/dates/page_count/mime deterministically; move PDF metadata logic out of `PdfIngestor` into a PDF extractor (behavior preserved); image `DocumentMetadata` fields are consumed from 2.5's `ImageInfo` when present — **no second EXIF reader** (R-3). |
| **Purpose** | One deterministic metadata path for every source type; today only PDF fills real metadata and most `DocumentMetadata` fields are empty for non-PDF types. |
| **Dependencies** | P2-201. |
| **Files likely affected** | `metadata/extractors.py` (new — pdf/audio/email/docx/pptx/notebook), `ingestion/pdf_ingestor.py` (move PDF metadata logic; no new dep). |
| **Classes likely affected** | `PdfExtractor`, `AudioExtractor`, `EmailExtractor`, `DocxExtractor`, `PptxExtractor`, `NotebookExtractor` (all new), `PdfIngestor` (metadata block relocated). |
| **Interfaces** | Each implements `MetadataExtractor`; `source_types` match the classifier kinds (`pdf`, `audio`, `email`, `docx`, `pptx`, `notebook`). |
| **Implementation Steps** | (1) PDF: reuse the PyMuPDF metadata read already in `pdf_ingestor.py:47-67` (title/author/page_count + dates), moved verbatim; (2) docx/pptx: read core properties via stdlib `zipfile` + `ElementTree` (`docProps/core.xml`, `docProps/app.xml`) — no `python-docx` dependency; (3) notebook: top-level `json` fields (name/kernelspec) — no `nbformat` dependency; (4) audio: deterministic file-level fields (filename title, timestamps, mime) — no new tag library; (5) email: subject/from/date headers as today's `EmailIngestor`; (6) image fields: do NOT read EXIF here; consume `ImageInfo` from `ProcessedDocument`/metadata when 2.5 has populated it (R-3); (7) keep `PdfIngestor` producing identical `SourceDocument` values. |
| **Configuration Changes** | None new (wired at P2-207). |
| **Testing Strategy** | Unit: per-type fixture tests (a real `.docx`, `.pptx`, `.ipynb`, `.eml`, `.pdf` committed fixture each); PDF extractor output equals current `PdfIngestor` metadata (regression). |
| **Acceptance Criteria** | Each type fills title/author/dates/page_count/mime deterministically; image fields consumed from 2.5 `ImageInfo` when present — no second EXIF reader (R-3). |
| **Definition of Done** | Per-type unit tests; `PdfIngestor` behavior unchanged. |
| **Rollback Plan** | Not wired to ingestion yet; removal is a safe revert. |
| **Estimated Complexity** | Medium. |
| **Risk** | Medium. |

---

### P2-203 — MIME detection service (G15)

| Field | Detail |
|-------|--------|
| **Task ID** | P2-203 |
| **Objective** | Implement `detect_mime(path)`: magic-number sniff (first 512 bytes) with a fallback table, optional `python-magic` when present, `_magic_fallback(path)` otherwise; extensionless markdown detected via magic bytes. |
| **Purpose** | Fixes extension-only detection that misreads extensionless/renamed files; satisfies MEDD G15; feeds the classifier's `mime_type`. |
| **Dependencies** | None. |
| **Files likely affected** | `metadata/mime.py` (new), `routing/classifier.py` (consult service for the `mime_type` field). |
| **Classes likely affected** | `DocumentClassifier` (minor: MIME consult), `detect_mime` (new), `_magic_fallback` (new). |
| **Interfaces** | `detect_mime(path: Path) -> str`; `_magic_fallback(path) -> str` (stdlib-only sniff: markdown `%PDF-`/`{`/`# `/Markdown text, `PK` zip, PNG/JPEG/audio headers); python-magic used only if importable. |
| **Implementation Steps** | (1) Import `magic` lazily; absent → log one warning (once) + `_magic_fallback`; (2) `_magic_fallback` sniffs ≤ 512 bytes for common signatures incl. Markdown (`# ` / `---` / plain-text heuristic); (3) `detect_mime` never overrides an explicit ingestor match for known extensions (ADR-001); (4) classifier replaces `mimetypes.guess_type` (`classifier.py:84`) with `detect_mime` when `mime_enabled: true`, keeping the stdlib path when disabled. |
| **Configuration Changes** | Consumes `intelligence.metadata.mime_enabled`; no new keys. |
| **Testing Strategy** | Unit: extensionless Markdown → `text/markdown`; renamed `.pdf` still detected; `python-magic` absent → one warning + fallback table still correct (monkeypatched import); ADR-001 precedence test (known extension keeps ingestor match). |
| **Acceptance Criteria** | Extensionless file containing Markdown is classified `markdown` via MIME; `python-magic` absent logs one warning, system still works (AC 5). |
| **Definition of Done** | Fallback table tests; ADR-001 respected; warning-once behavior tested. |
| **Rollback Plan** | `mime_enabled: false` restores `mimetypes.guess_type`; additive module. |
| **Estimated Complexity** | Low. |
| **Risk** | Medium (libmagic wheel risk — R11; mitigated by fallback table). |

---

### P2-204 — Language detection service (G16)

| Field | Detail |
|-------|--------|
| **Task ID** | P2-204 |
| **Objective** | Implement `detect_language(text)`: optional `py3langid`, pure-heuristic fallback `_language_heuristic`, confidence threshold → default `"en"` + log. |
| **Purpose** | Satisfies MEDD G16; today `language` is never populated for any document. |
| **Dependencies** | None. |
| **Files likely affected** | `metadata/language.py` (new), `pyproject.toml` (optional extra `intelligence`: `py3langid`). |
| **Classes likely affected** | `LanguageDetector` (Protocol, new), `detect_language` (new), `_language_heuristic` (new). |
| **Interfaces** | `detect_language(text: str) -> tuple[str, float]` (lang, confidence); detector returns `("en", 0.0)` on low confidence; operates on the first ≤ 10 KB only (performance ceiling). |
| **Implementation Steps** | (1) Import `py3langid` lazily; absent → fallback + debug log; (2) `_language_heuristic`: stopword/character-set detection for a small fixed set (en/fr/de/ja) — pure stdlib; (3) confidence below threshold (e.g. 0.5) → `("en", 0.0)` + warning (R7 mitigation); (4) expose `detect_language` and `register`-able detector per the §2 Protocol; (5) read only first ≤ 10 KB of text. |
| **Configuration Changes** | Consumes `intelligence.metadata.language_detection_enabled`; no new keys (threshold constant in code, `ponytail:` fixed default). |
| **Testing Strategy** | Unit: French/German/Japanese sample texts → `fr`/`de`/`ja`; short/technical text → `en` fallback; absent-`py3langid` → heuristic path still correct; low-confidence → `en` + warning. |
| **Acceptance Criteria** | `py3langid` optional; heuristic fallback; confidence threshold → default `"en"`; fr/de/ja detected. |
| **Definition of Done** | Language tests (fr/de/ja); heuristic fallback proven with py3langid absent. |
| **Rollback Plan** | `language_detection_enabled: false` disables; additive module. |
| **Estimated Complexity** | Low. |
| **Risk** | Medium (mis-classification of short/technical text — R7; mitigated by threshold + manual override config). |

---

### P2-205 — Language propagation + prompt adaptation

| Field | Detail |
|-------|--------|
| **Task ID** | P2-205 |
| **Objective** | Populate `DocumentClassification.language` and `ProcessedDocument.language`; add a respond-in-`{language}` instruction to the analysis user prompt (additive, schema unchanged — R8 mitigation). |
| **Purpose** | Multilingual analysis; establishes the `{language}` prompt-slot contract that 2.1/2.5 prompt templates consume (frozen §5/§6.3; addendum 2 adds this to P2-505's deps). |
| **Dependencies** | P2-204. |
| **Files likely affected** | `routing/classifier.py`, `prompts/document_analysis.py` (`build_document_analysis_user_prompt`), `ingest_workflow.py`. |
| **Classes likely affected** | `DocumentClassifier`, `build_document_analysis_user_prompt`, `IngestionWorkflow` (plumbing). |
| **Interfaces** | `DocumentClassification.language: str | None` (populated from `detect_language` on the source text); `ProcessedDocument.language` set from classification; prompt gains an optional `language: str = "en"` param. |
| **Implementation Steps** | (1) Classifier calls `detect_language` on the source text when `language_detection_enabled`; sets `classification.language`; (2) workflow propagates to `ProcessedDocument.language`; (3) `build_document_analysis_user_prompt` gains a `language` argument and appends the instruction "Respond in {language}." when `language != "en"` — schema/JSON contract unchanged (R8); (4) keep the prompt byte-identical to today when language is `"en"` (default). |
| **Configuration Changes** | Consumes `language_detection_enabled`; no new prompt keys here (the `{language}` slot in `intelligence.prompts.*` is bound at P2-107/P2-505). |
| **Testing Strategy** | Unit: French document ⇒ `classification.language == "fr"` and the analysis user-prompt contains a respond-in-French instruction (AC 2); English default produces today's exact prompt string (regression); language propagation end-to-end. |
| **Acceptance Criteria** | French text ⇒ `language="fr"` in classification + respond-in-French instruction in the analysis user-prompt (AC 2). |
| **Definition of Done** | Unit tests for prompt string + propagation; English path byte-identical. |
| **Rollback Plan** | `language_detection_enabled: false` keeps `language=None` and today's prompt. |
| **Estimated Complexity** | Low. |
| **Risk** | Medium (French prompt adaptation must not degrade structured-JSON reliability — R8; validated by unit test + review field-completeness check). |

---

### P2-206 — Hook chain (pre/post) + limits (FR-ING-5/6/7/8)

| Field | Detail |
|-------|--------|
| **Task ID** | P2-206 |
| **Objective** | Implement the `IngestionHook` protocol + chain inside `DocumentIngestionService.ingest()`: pre-hooks reject >50 MB before file read; post-hooks modify the document; hook errors never break ingestion; enforce size/time limits. |
| **Purpose** | Delivers FR-ING-5/6 (hooks) and FR-ING-7/8 (size/time enforcement); the hook pattern every later milestone reuses. |
| **Dependencies** | P2-201. |
| **Files likely affected** | `metadata/hooks.py` (new), `ingestion/service.py`, `core/config.py`, `config/default.yaml`. |
| **Classes likely affected** | `DocumentIngestionService` (hook chain + size guard), `IngestionHook` (Protocol, new), `Settings` (metadata block). |
| **Interfaces** | `IngestionHook` as in §2; chain order = config order; pre-hook returning a modified `SourceReference` passes it on; a pre-hook raising `IngestionError` (e.g. "over size limit") aborts with a structured `DocumentIngestionResult.error`. |
| **Implementation Steps** | (1) Define the hook chain in `DocumentIngestionService`: load plugins named in `hooks.pre`/`hooks.post`; (2) size guard: check `max_file_size_mb` before read in `_ingest_source` (disk/memory exhaustion guard — MEDD §2.4); over-limit → `IngestionError` with no read; (3) pre-hooks run on the `SourceReference` before `ingestor.ingest()`; a rejecting pre-hook aborts cleanly; (4) post-hooks run on the returned `SourceDocument`; a modifying post-hook may rewrite `document.text`; (5) every hook wrapped in try/except — a raised hook is logged and skipped, ingestion continues (failure mode §3); (6) wire `url_timeout_seconds` into remote fetch (already-timeout default; assert plumbing). |
| **Configuration Changes** | `intelligence.metadata.{enabled,max_file_size_mb,url_timeout_seconds,hooks.pre,hooks.post}` consumed. |
| **Testing Strategy** | Unit: pre-hook rejecting >50 MB prevents ingestion (AC 3a); post-hook appends text (AC 3b); a hook that raises → logged + ingestion continues; over-size file errors before read; hook order preserved. |
| **Acceptance Criteria** | A `pre` hook rejecting >50 MB prevents ingestion; a `post` hook appends text; hook errors don't break ingestion. |
| **Definition of Done** | Hook + size-limit tests; per-hook try/except proven. |
| **Rollback Plan** | `enabled: false` (or empty `hooks.*`) bypasses hooks; additive. |
| **Estimated Complexity** | Medium. |
| **Risk** | Medium. |

---

### P2-207 — Metadata enrichment wiring in ingestion service

| Field | Detail |
|-------|--------|
| **Task ID** | P2-207 |
| **Objective** | Wire the extractors + hooks into `DocumentIngestionService.ingest()` so every ingested document gets merged metadata; result is a superset of Phase 1. |
| **Purpose** | The single wiring point where the metadata layer goes live; gates on `enabled` for the Phase-1-identical rollback contract. |
| **Dependencies** | P2-202, P2-206. |
| **Files likely affected** | `ingestion/service.py`, `config/default.yaml`. |
| **Classes likely affected** | `DocumentIngestionService` (enrichment call site), `DocumentMetadataService` (invoked), `Settings`. |
| **Interfaces** | `DocumentIngestionService.ingest()` runs, in order: size guard → pre-hooks → `ingestor.ingest()` → extractors-for-type merge → post-hooks. Public signatures unchanged. |
| **Implementation Steps** | (1) After `ingestor.ingest()` returns, run `DocumentMetadataService` extractors for the document's source type and merge into `document.metadata` (superset of Phase 1 values); (2) when `intelligence.metadata.enabled: false`, skip the whole block — document identical to Phase 1 (R-4); (3) guard each extraction in try/except (extractor failure → debug log, document unchanged); (4) one call site, no flow re-ordering (required refactoring §3). |
| **Configuration Changes** | `intelligence.metadata.enabled` + `extractors` consumed (values per §3). |
| **Testing Strategy** | Integration: real files (PDF, docx, notebook, email) through `ingest()` assert enriched metadata superset; `enabled: false` → Phase-1-identical documents (byte compare where feasible); extractor failure isolation. |
| **Acceptance Criteria** | `DocumentIngestionService.ingest()` runs extractors + hooks; result metadata superset of Phase 1 (AC 4). |
| **Definition of Done** | Integration test on real files; disabled-path regression. |
| **Rollback Plan** | `enabled: false` returns Phase-1-identical documents; no legacy branch (R-4). |
| **Estimated Complexity** | Low. |
| **Risk** | Medium. |

---

### P2-208 — Email attachment parsing (recursive ingestion)

| Field | Detail |
|-------|--------|
| **Task ID** | P2-208 |
| **Objective** | Parse RFC822 emails into a parent note; ingest each attachment as a child document carrying `parent_id`; enforce `max_attachments` + `max_file_size_mb`; no infinite recursion. |
| **Purpose** | MEDD Phase 2 roadmap "Email attachment parsing" + Epic 2 AC; today `EmailIngestor` discards attachments entirely. |
| **Dependencies** | P2-202, P2-207. |
| **Files likely affected** | `ingestion/email_ingestor.py` (extend — attachments currently dropped), `ingestion/service.py` (child-document recursion), `ingest_workflow.py`, `domain/processed_document.py` (`parent_id`, additive). |
| **Classes likely affected** | `EmailIngestor`, `DocumentIngestionService` (child re-ingest), `ProcessedDocument` (additive `parent_id`), `IngestionWorkflow`. |
| **Interfaces** | `ProcessedDocument.parent_id: str | None` (additive, default `None`); `EmailIngestor` extracts `Content-Disposition: attachment` parts to temp child sources; child documents are ingested through the same `DocumentIngestionService` (reuses size limit — no infinite recursion: a child attachment is never re-parsed as email unless its own MIME type is email, and `max_attachments` caps breadth). |
| **Implementation Steps** | (1) In `EmailIngestor`, walk MIME parts for `Content-Disposition: attachment`; write each to a `tempfile` child source (finally-cleanup after ingestion); (2) parent note: keep today's header+body text, set `extra.attachments = [child filenames]`; (3) `ingest_workflow.py` re-ingests each child via the existing pipeline with `ProcessedDocument.parent_id = parent id`; (4) enforce `max_attachments` (skip + warn beyond cap) and reuse `max_file_size_mb` per child (attachment-bomb mitigation — R1/R11 risk row); (5) depth guard: nested email attachments require their own ingest path; cap recursion at one level below the parent unless configured (no infinite recursion — DoD); (6) 3-PDF-attachment email → 1 parent + 3 children with `parent_id` set (MEDD Epic 2 AC, R-1). |
| **Configuration Changes** | Consumes `intelligence.metadata.{email_attachments,max_attachments,max_file_size_mb}`; no new keys. |
| **Testing Strategy** | Integration: committed RFC822 fixture with 3 PDF attachments → 4 notes with `parent_id` set (AC 6); `max_attachments` cap test (e.g. 5 attachments, cap 3 → 3 children + warn); over-size attachment → `IngestionError`, no child; no-infinite-recursion test (nested email fixture bounded); regression: existing `.eml` tests unchanged. |
| **Acceptance Criteria** | An RFC822 email with 3 PDF attachments produces 1 parent note + 3 child notes with `parent_id` set (R-1, AC 6). |
| **Definition of Done** | Email fixture tests (RFC822 + attachments); `max_attachments` cap test; no infinite recursion. |
| **Rollback Plan** | `email_attachments: false` restores today's single-document behavior; `ProcessedDocument.parent_id` additive only. |
| **Estimated Complexity** | Medium. |
| **Risk** | High (recursive ingestion is the milestone's largest blast radius; mitigate per frozen risks: `max_attachments` cap + size-limit reuse + depth guard). |

---

## 5. Implementation Order

| Step | Tasks | Rationale |
|------|-------|-----------|
| 0 | **Preflight (not a task):** verify `python-magic` (libmagic) + `py3langid` wheel availability on `cp314-win_amd64` via `pip download --only-binary` (R-5 / Baseline R11). |
| 1 | P2-201 | Foundation protocol + registry + merge — everything else depends on it. |
| 2 | P2-203 ‖ P2-204 ‖ P2-206 | MIME and language services are independent of the extractor registry; P2-206 needs only P2-201. Parallelize. |
| 3 | P2-202 ‖ P2-205 | Built-in extractors (on P2-201) and language propagation (on P2-204) are independent. |
| 4 | P2-207 | Enrichment wiring needs P2-202 + P2-206; milestone integration point. |
| 5 | P2-208 | Email attachment recursion needs P2-202 + P2-207; milestone gate. |

**Critical path:** P2-201 → P2-202 → P2-207 → P2-208 (and P2-201 → P2-206 → P2-207). **Parallel:** P2-203 ‖ P2-204 ‖ P2-206 (wave 2); P2-202 ‖ P2-205 (wave 3). **Hard order:** P2-207 needs P2-202 + P2-206; P2-208 needs P2-207. P2-205 must land **before** 2.1/2.5 prompt-config work so the `{language}` slot contract exists once (frozen §5/§6.3; addendum 2).

## 6. Dependency Graph

```mermaid
graph TD
    P201[P2-201 interface + registry] --> P202[P2-202 built-in extractors]
    P201 --> P206[P2-206 hooks + limits]
    P204[P2-204 language service] --> P205[P2-205 propagation + prompt]
    P202 --> P207[P2-207 enrichment wiring]
    P206 --> P207
    P207 --> P208[P2-208 email attachment parsing]
    P202 -. email extractor .-> P208
    P203[P2-203 MIME service] -. consulted by .-> P205x[classifier (P2-205)]
    P205 -. {language} slot contract .-> P2x1[2.1 OCR / 2.5 image prompts]
```

Edges: P2-203 and P2-204 are independent (may run any time); P2-203 is consumed by the classifier alongside P2-205; P2-208 consumes the P2-202 email extractor and the P2-207 wiring. The **task-dependency (hard) edges** are P2-201→{202,206}, P2-204→205, {202,206}→207, {202,207}→208.

## 7. Testing Plan

| Layer | Scope | Command / Marker |
|-------|-------|------------------|
| Unit | Registry/merge rules; per-type extractors; MIME fallback table; language detect + heuristic + threshold; prompt adaptation string; hook pre-reject/post-modify + error isolation; size-limit error path; `enabled: false` regression | `tests/unit/test_metadata_extraction.py` (new), `tests/unit/test_classifier.py` — `python -m pytest tests/unit -q -p no:cacheprovider` |
| Integration | Real `pam ingest`-equivalent on a French `.md` + a renamed extensionless file asserting metadata + prompt; hooks wired through `DocumentIngestionService`; RFC822-with-attachments → parent + children with `parent_id` | `tests/integration/test_ingestion_metadata.py` (new) — `@pytest.mark.integration`, opt-in `-m integration`, hermetic |
| Regression | `test_routing.py` extension-map loop, `test_classifier`, `test_ingestion.py`, `test_workflow_routing.py`, all existing ingestion + `.eml` tests pass unchanged | `python -m pytest tests -q -p no:cacheprovider` |
| Performance | MIME sniff ≤ 50 ms (first 512 bytes only); language detection on first ≤ 10 KB only; extractors run once per document; hook chain short-circuits on reject | §3 performance ceilings, `time.perf_counter` assertions |
| Manual | `pam ingest` an extensionless Markdown file, a French PDF, and a `.eml` with 3 PDF attachments; verify `language` populated, prompt in French, 4 notes linked by `parent_id`, no temp leakage | §3 acceptance criteria + §8 checklist |
| Benchmark | N/A for this milestone (deterministic extraction; covered by perf ceilings) | — |

Absent-dependency paths (`python-magic`, `py3langid`) are import-guarded with the ADR-001 warning-only contract; no optional dep is required for the milestone's default behavior.

## 8. Review Checklist (milestone gate)

- [ ] P2-201 registry + protocol + merge reviewed; no-extractor path never raises.
- [ ] P2-202 five built-in extractors stdlib-only; `PdfIngestor` behavior byte-identical; image fields consumed from 2.5 `ImageInfo`, no second EXIF reader (R-3).
- [ ] P2-203 `detect_mime` + fallback table; extensionless Markdown classified via MIME (AC 1); ADR-001 precedence; warning-once on absent `python-magic` (AC 5).
- [ ] P2-204 `detect_language` + heuristic fallback; fr/de/ja tests; threshold → `"en"` (R7).
- [ ] P2-205 `classification.language` + `ProcessedDocument.language` populated; respond-in-French prompt (AC 2); English path byte-identical; `{language}` slot contract documented for 2.1/2.5.
- [ ] P2-206 pre-hook rejects >50 MB before read (AC 3a); post-hook appends text (AC 3b); hook errors don't break ingestion; URL timeout plumbing asserted.
- [ ] P2-207 enrichment superset of Phase 1 (AC 4); `enabled: false` → Phase-1-identical (R-4).
- [ ] P2-208 RFC822 + 3 PDF attachments → 4 notes with `parent_id` (AC 6); `max_attachments` cap; no infinite recursion; `email_attachments: false` restores today's behavior.
- [ ] All 432 pre-existing tests pass unchanged; coverage ≥ 80%; `ruff` no new errors; `mypy` no new type errors.
- [ ] Per-task atomic commits; rollback via `intelligence.metadata.enabled: false` verified.
- [ ] Optional-dep wheels verified on `cp314-win_amd64` incl. libmagic (R5/R11); changelog + 01 report + MEDD §2.4 + ADR-001 consequence note updated.
- [ ] Milestone 2.2 completion report produced before Milestone 2.3 begins (frozen §12 gates).

---

*End of Milestone 2.2 Engineering Specification.*
