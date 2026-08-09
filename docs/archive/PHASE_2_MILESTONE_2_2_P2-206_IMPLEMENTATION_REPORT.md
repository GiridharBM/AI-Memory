# P2-206 Implementation Report — Hook Chain (Pre/Post) + Limits

**Task:** P2-206 (Milestone 2.2 — Metadata Extraction Framework)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` §P2-206 (lines 182–199)
**Date:** 2026-08-01
**Status:** Ready for engineering review

## Implementation Summary

Implemented the `IngestionHook` protocol + hook chain inside
`DocumentIngestionService.ingest()` and the ingestion size/time limit
enforcement, per the frozen §P2-206 contract (FR-ING-5/6/7/8).

- **`IngestionHook` protocol + registry** (`metadata/hooks.py`): `pre(source) -> SourceReference` / `post(document) -> SourceDocument` with a `name`; a `HookRegistry` mapping name→hook (idempotent `register`); public `register_hook()` alias onto a lazy process-wide default registry (mirrors the P2-201 `register_extractor()` pattern).
- **Hook chain in the service:** `DocumentIngestionService` builds the chain from `settings.intelligence.metadata.hooks.pre`/`hooks.post` plugin names (config order). Pre-hooks run on the `SourceReference` before `ingestor.ingest()`; a pre-hook raising `IngestionError` aborts into a structured `DocumentIngestionResult.error`; a post-hook may rewrite `document.text`. Chain order = config order. Unknown names warn and are skipped.
- **Per-hook try/except:** a hook raising any non-`IngestionError` exception is logged and skipped; ingestion continues (failure mode §3).
- **Size guard (FR-ING-7):** `max_file_size_mb` checked against `source.stat().st_size` in `_ingest_source` **before** any read; over-limit raises `IngestionError` → structured error with no read.
- **Rollback (R-4):** `intelligence.metadata.enabled: false` (or empty `hooks.*`) bypasses the size guard and the hook chain entirely — documents are Phase-1-identical. No `legacy` mode.
- **Config (FR-ING-8):** new `MetadataSettings` (enabled, extractors, mime_enabled, language_detection_enabled, max_file_size_mb, url_timeout_seconds, email_attachments, max_attachments, hooks.pre/post) added to `IntelligenceSettings`; `intelligence.metadata` block added to `config/default.yaml` matching the frozen §3 normative block. `url_timeout_seconds: 30` asserted to match the remote-fetch default (`github_readme_ingestor._REQUEST_TIMEOUT_SECONDS = 30`).
- **No-arg constructor preserved:** `DocumentIngestionService()` still works unchanged (`ingest_workflow.py:139`); `settings`/`hooks` are optional keyword-only params.

## Files Modified

| File | Change |
|------|--------|
| `app/infrastructure/document_intelligence/metadata/hooks.py` | **new** — `IngestionHook` protocol, `HookRegistry`, `get_default_hook_registry()`, `register_hook()` |
| `app/infrastructure/document_intelligence/metadata/__init__.py` | re-export `IngestionHook`, `register_hook()`, `get_default_hook_registry()` (frozen public API §2) |
| `app/infrastructure/ingestion/service.py` | hook chain + size guard in `_ingest_source`; optional `settings`/`hooks` ctor params |
| `app/core/config.py` | new `MetadataSettings` + `HookChainSettings`; `metadata` field on `IntelligenceSettings` |
| `config/default.yaml` | new `intelligence.metadata` block (frozen §3) |
| `tests/unit/test_ingestion_hooks.py` | **new** — 12 hook/size-limit unit tests |

## Tests Executed

`python -m pytest tests -q` → **546 passed, 2 deselected** (534 baseline + 12 new, 0 regressions).

New tests in `tests/unit/test_ingestion_hooks.py` (12):

- Size guard rejects over-limit file **before read** (spy ingestor asserts 0 calls).
- `enabled: false` bypasses the size guard (AC: Phase-1-identical).
- `enabled: false` skips the hook chain entirely.
- Pre-hook redirects the `SourceReference` (modified source passes on).
- Pre-hook raising `IngestionError` aborts with a structured error.
- Post-hook rewrites `document.text` (AC 3b).
- Hook raising a generic exception is logged + skipped; ingestion succeeds (AC: errors don't break ingestion).
- Chain order preserved = config order (AC).
- Unknown hook name warns and continues.
- `register_hook()` public alias resolves named hooks from the default registry.
- Protocol is runtime-checkable.
- `url_timeout_seconds` default (30) matches the remote-fetch default.

## Test Results

| Gate | Result |
|------|--------|
| `python -m pytest tests -q` | 546 passed / 2 deselected |
| `python -m ruff check app tests` | 64 errors (pre-existing baseline; no new) |
| `python -m mypy app` | pre-existing only (yaml/docx/pptx/numpy stubs); no new |

## Remaining Risks

- **Remote-source size guard:** the 50 MB check applies to local `Path` sources. URL-based sources are handled by existing timeout defaults; `url_timeout_seconds` deep-tuning is out of scope per frozen §1 ("remote URL timeout deep-tuning beyond defaults" is Scope-out).
- **Hook plugin discovery:** hooks are resolved by config name against the default registry. There is no auto-discovery of hook modules — future plugins must call `register_hook()` (matches the frozen §2 plugin-registry contract; no auto-loading was specified).

## Next Recommended Task

**P2-207 — Metadata enrichment wiring:** wire `MetadataExtractor`/MIME/language services into `DocumentIngestionService.ingest()` at the single call site (config `intelligence.metadata.extractors: "default"`), so extracted metadata flows into `SourceDocument.metadata` as a superset of Phase-1 values. P2-206 unblocks it (hook chain + limits already in place).
