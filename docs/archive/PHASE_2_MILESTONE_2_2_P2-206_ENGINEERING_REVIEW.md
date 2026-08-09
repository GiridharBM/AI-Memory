# P2-206 Engineering Review — Hook Chain (Pre/Post) + Limits

**Task:** P2-206 (Milestone 2.2 — Metadata Extraction Framework)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` §P2-206 (lines 182–199)
**Reviewer:** Principal Engineering Reviewer
**Date:** 2026-08-01
**Review scope:** P2-206 implementation only (hook chain, size/time limits, config consumption). No code modified.

---

## 1. Specification Compliance

| Frozen requirement (§P2-206) | Status | Evidence |
|---|---|---|
| `IngestionHook` protocol with `name`, `pre(source)->SourceReference`, `post(document)->SourceDocument` | ✅ | `metadata/hooks.py:22-34`, matches frozen §2 exactly |
| Chain order = config order | ✅ | `service.py:_run_pre_hooks`/`_run_post_hooks` iterate `metadata.hooks.pre/post` lists in order; `test_chain_order_preserved` |
| Pre-hook returning modified `SourceReference` passes it on | ✅ | `service.py:175` rebinds `source`; `test_pre_hook_redirects_source` |
| Pre-hook raising `IngestionError` aborts with structured `DocumentIngestionResult.error` | ✅ | `service.py:176-177` re-raises; caught at `ingest()`; `test_pre_hook_ingestion_error_aborts` |
| Size guard `max_file_size_mb` before read in `_ingest_source`; over-limit → `IngestionError`, no read | ✅ | `service.py:141,148-157` runs before `_select_ingestor`/`ingest`; spy ingestor asserts 0 calls |
| Post-hooks on returned `SourceDocument`; may rewrite `document.text` | ✅ | `service.py:182-195`; `test_post_hook_rewrites_text` |
| Every hook in try/except — raised hook logged and skipped, ingestion continues | ✅ | `service.py:178-179,192-194`; `test_hook_error_logged_and_skipped` |
| Wire `url_timeout_seconds` into remote fetch (already-timeout default; assert plumbing) | ✅ | config default 30 == `github_readme_ingestor._REQUEST_TIMEOUT_SECONDS` 30; `test_url_timeout_default_matches_remote_fetch` |
| Config consumed: `intelligence.metadata.{enabled,max_file_size_mb,url_timeout_seconds,hooks.pre,hooks.post}` | ✅ | `MetadataSettings` + YAML block match frozen §3; consumed in `_enforce_size_limit`/`_run_*_hooks` |
| Public API `register_hook()` | ✅ | exported from `hooks.py:65` and `metadata/__init__.py` |

## 2. Architecture Compliance

- **Package layout** matches frozen §2: `metadata/hooks.py` created inside `document_intelligence/metadata/`; shared domain models reused from `app.domain.documents`.
- **Import direction is safe.** `service.py` imports `document_intelligence.metadata` (ingestion → document_intelligence); the reverse (metadata → ingestion) is absent, preserving the P2-202 constraint ("no cross-layer imports from the metadata package into ingestion"). `hooks.py` redefines the `SourceReference = str | Path` alias locally instead of importing from `ingestion.base` — this deliberately avoids a cycle and is structurally identical (structural typing), consistent with the P2-202 precedent.
- **Registry pattern** mirrors the P2-201 extractor registry (`get_default_*` lazy singleton + `register_*` public alias) — consistent project convention.
- **No-arg constructor preserved.** `DocumentIngestionService()` still constructs unchanged (`ingest_workflow.py:139` untouched); `settings`/`hooks` are optional keyword-only additions. Verified by existing pipeline tests passing.

## 3. Public Interfaces

- `IngestionHook` protocol: runtime-checkable, exact frozen signature. ✅
- `register_hook(hook)` public alias delegates to the default registry. ✅
- `HookRegistry` with idempotent `register`, `get`, constructor injection — supports hermetic tests and plugin-style registration. ✅
- `DocumentIngestionService.__init__(ingestors=None, *, settings=None, hooks=None)` is backward compatible. ✅

## 4. Error Handling

- Pre-hook `IngestionError` → propagates → structured `DocumentIngestionResult.error` with `source`/`source_path`/`source_type`/`reason` populated. ✅
- Pre-hook generic exception → logged via `logger.exception` → skipped → ingestion continues. ✅
- Post-hook any exception → logged → skipped → document retained. ✅
- Unknown hook name → `logger.warning` → skipped (no crash). `test_unknown_hook_name_warns_and_continues`. ✅
- Size guard fires before any read and before ingestor selection — memory-exhaustion guard satisfied (FR-ING-7). ✅
- `enabled: false` gates both the size guard and the hook chain → Phase-1-identical documents (R-4 rollback). ✅

## 5. Test Coverage

12 new tests in `tests/unit/test_ingestion_hooks.py`. Full suite: **546 passed / 2 deselected** (534 baseline + 12 new), zero regressions.

Covered: size guard before-read (spy), disabled bypass, disabled skips hooks, pre-hook redirect, pre-hook `IngestionError` abort, post-hook text rewrite, generic hook error swallowed, chain order, unknown hook name, public-alias registry resolution, protocol runtime-checkability, timeout plumbing.

## 6. Performance

- Size guard is a single `stat()` call per local `Path` source, performed once before read — negligible.
- Hook chain iterates config-declared name lists (empty by default) — O(n) on declared hooks, not on registry size.
- No reads added; no allocations in the hot path beyond a per-call `MetadataSettings()` when `settings is None` (trivial).

## 7. Documentation

`docs/PHASE_2_MILESTONE_2_2_P2-206_IMPLEMENTATION_REPORT.md` is accurate and complete (Summary, Files, Tests, Results, Risks, Next Task = P2-207).

## 8. Regression Safety

- `git` working tree: no test file modified outside the new `test_ingestion_hooks.py`; production changes confined to `config.py`, `service.py`, `hooks.py`, `metadata/__init__.py`, `default.yaml`.
- `python -m ruff check app tests`: 64 errors — **unchanged pre-existing baseline**, no new findings.
- `python -m mypy app`: only pre-existing stub errors (fitz/docx/pptx/yaml/numpy); no new errors in P2-206 files.
- Config `extra="forbid"` preserved on all new models; YAML block validates against frozen §3.

---

## Observations (non-blocking)

1. **`register_hook()` alias is not directly exercised.** `test_register_hook_public_alias_resolves_by_name` manipulates the private `_hooks` dict and never calls the public `register_hook()` it is named after. The alias is a trivial delegation, so this is low-risk, but the frozen public API currently has no direct test.
2. **Post-hook error path not explicitly tested.** `test_hook_error_logged_and_skipped` covers a pre-hook raising `RuntimeError`; the post-hook error path (all exceptions swallowed, document retained) is asserted only by code reading, not by a dedicated test.
3. **URL size limit intentionally not applied.** Size guard applies to local `Path` sources only; remote sources rely on the timeout default. This matches frozen scope (remote deep-tuning is Scope-out, §1 line 17).
4. **No-arg constructor now enforces the 50 MB default** (via default `MetadataSettings(enabled=True, max_file_size_mb=50)`). This matches the frozen `enabled: true` addendum, but is a subtle behavior change for the bare-constructor path; callers needing Phase-1 behavior must pass `enabled: false` explicitly.

---

## Verdict

✅ **Approved**

P2-206 fully satisfies the frozen contract: all §P2-206 acceptance criteria and Definition of Done are met, gates are clean (546 tests, ruff/mypy baselines unchanged), and the hook-chain design is architecturally consistent with the P2-201/202 registry pattern. The four observations above are minor and require no code changes before proceeding to **P2-207 (metadata enrichment wiring)**.
