# P2-208 Engineering Review Report — Email attachment parsing (recursive ingestion)

**Reviewer:** Principal Engineering Reviewer
**Task:** P2-208 (Milestone 2.2 — Metadata Extraction Framework; milestone gate)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` §P2-208 (lines 226–244)
**Date:** 2026-08-01
**Scope:** P2-208 only. Review-only — no code modified.

## Verdict

❌ **Needs Remediation** — one required item (R1), otherwise sound.

R1 is a production-wiring defect that breaks two frozen contract items through the
actual production entry points. It is a one-line fix plus one regression test.

---

## Verification by Area

### 1. Recursive ingestion behavior — ✅ PASS

`EmailIngestor` (`app/infrastructure/ingestion/email_ingestor.py`) extracts
`Content-Disposition: attachment` parts to `tempfile` child sources and exposes
them via `extra.attachments` / `extra.attachment_paths`.
`IngestionWorkflow.run` (`app/pipelines/ingest_workflow.py:220`) splits into
`_process_document(document, *, parent_id)` for the parent, then
`_ingest_children(document)` re-ingests each child through the **same**
`DocumentIngestionService` and calls `_process_document(child, parent_id=...)`.
Frozen AC verified end-to-end:
`tests/integration/test_email_attachment_ingestion.py` — an RFC822 email with 3
PDF attachments produces 1 parent + 3 child notes (4 notes in the vault), all
children processed, temp files removed. Passes.

### 2. Parent/child relationships — ✅ PASS

- `ProcessedDocument.parent_id: str | None` added additively
  (`app/domain/processed_document.py:22`), stamped in `_run_routed_processor`
  next to the P2-205 language stamp (ingest_workflow.py:461).
- Durable record `child.metadata.extra["parent_id"] = parent.source` is stamped
  in `_ingest_child` before processing (ingest_workflow.py:396-400).
- Parent itself carries no `parent_id` (verified in tests). Relationship value
  is the parent source path string — unambiguous within a run.
- Note: the relationship is **recorded but not yet consumed** downstream (no
  vault-naming or backlink wiring). This matches the frozen objective ("child
  document carrying `parent_id`") and the checklist's later "parent/child vault
  naming" item; flagged as O3.

### 3. Recursion safeguards — ✅ PASS

- **Depth guard:** `_ingest_child` → `_process_document` never calls
  `_ingest_children`; a nested `.eml` is re-ingested once as a child email, and
  its own attachments are extended into the cleanup list but not re-ingested.
  Bounded at one level below the parent (frozen DoD). Verified by
  `test_nested_email_ingested_once_no_infinite_recursion`.
- **Extraction scope:** `_extract_attachments` iterates `msg.iter_attachments()`
  (direct children) rather than `msg.walk()`, so grandchild attachments are not
  flattened onto the parent. This was the right call — `walk()` recursed into
  nested emails and flattened the guard (found and fixed during implementation).
- **Breadth cap:** `max_attachments` enforced in `_ingest_children` with
  skip+warning (ingest_workflow.py:362-371); beyond-cap temp files still cleaned.
- **Size limit:** children re-ingest through the service's `_enforce_size_limit`.
  See R1 for the production-wiring caveat.
- **Temp cleanup:** `_cleanup_attachment_temp_files` runs in a `finally`
  (ingest_workflow.py:373-374), so cleanup also runs on child failure and cap
  overrun. Files unlinked, empty dirs `rmdir`'d, `OSError` ignored.
- **No cycle possible:** child sources are freshly created `mkdtemp` files;
  a file cannot contain itself.

### 4. Backward compatibility — ⚠️ PASS WITH CAVEAT

- Non-email documents: no `attachment_paths` key → `_ingest_children` returns
  early (verified `test_non_email_document_untouched`).
- `EmailIngestor()` default constructor unchanged; `metadata` param optional.
- `ProcessedDocument.parent_id` is additive (default `None`); existing
  construction sites unaffected.
- `enabled: false` → no extraction. `email_attachments: false` → single-doc
  behavior restored — **but only when settings reach the service** (see R1).
  Through the production `create_default` wiring this rollback path leaks temp
  files and does not actually stop extraction.

### 5. Tests — ✅ PASS (with gaps)

14 unit tests (`tests/unit/test_email_attachments.py`) + 1 integration AC test
(`tests/integration/test_email_attachment_ingestion.py`). Coverage: extraction,
both gate-off paths, inline-parts exclusion, path-traversal sanitization,
filename dedup, nested-email serialization, parent/child stamping, cap, child-
failure skip + cleanup, non-email untouched, depth guard, temp cleanup, and the
frozen 3-PDF AC. Regression: 605 unit / 10 integration / ruff 64 baseline /
mypy 4 baseline — all preserved, zero new violations.

Gaps (all non-blocking, see Observations): no test exercises the
`from_runtime`/`create_default` production wiring with overridden settings (O4 —
this is precisely how R1 slipped through); the over-size-child workflow test is
infeasible under a single shared limit (documented in the report; failure path
covered by the `_ParentThenFailingService` stub).

### 6. Documentation — ✅ PASS (one claim overstates production)

`docs/PHASE_2_MILESTONE_2_2_P2-208_IMPLEMENTATION_REPORT.md` is accurate on the
mechanisms and gate results. Two claims hold only when settings reach the
service: "reuses `max_file_size_mb`" and "`email_attachments: false` restores
today's single-document behavior" — both fail through the production wiring
(R1). The report should be amended once R1 is fixed.

---

## Findings

### R1 — REQUIRED: production wiring drops `intelligence.metadata` settings from the ingestion service

`IngestionWorkflow.from_runtime` constructs
`ingestion_service=DocumentIngestionService()` **without `settings`**
(`app/pipelines/ingest_workflow.py:150`). `create_default` (line 201) and both
production entry points — `app/cli/entry.py:372` and `app/queue/worker.py:84` —
route through it. The service therefore always runs with default
`MetadataSettings()`, independent of the user configuration that the workflow
itself reads via `self._metadata()` (ingest_workflow.py:125-128).

Frozen contract impact (§P2-208: "enforce `max_attachments` + `max_file_size_mb`";
"Consumes `intelligence.metadata.{email_attachments,max_attachments,max_file_size_mb}`";
Rollback Plan "`email_attachments: false` restores today's single-document behavior"):

1. **`email_attachments: false` leaks temp files.** The workflow gate
   (`_ingest_children`, ingest_workflow.py:353-355) early-returns before any
   cleanup, but the service-side `EmailIngestor` still extracts attachments
   (its gate reads the service's default settings). Every ingested email with
   attachments leaks one `pam_email_attachments_*` temp dir. **Empirically
   confirmed:** a single run through this wiring leaves exactly 1 leftover dir;
   the same run with settings passed to the service leaves 0.
2. **`max_file_size_mb` is not honored.** The service `_enforce_size_limit`
   (service.py:173-182) uses its own default (50 MB), so a user-configured limit
   is bypassed for the parent and for re-ingested children. **Empirically
   confirmed:** a 1 MB+1 byte file ingests successfully with
   `max_file_size_mb=1` configured, through a no-settings service.
3. `max_attachments` **is** honored (the workflow reads settings) — no defect there.

Tests mask this because the `_workflow` helper passes the same `settings` to
both the service and the workflow (test_email_attachments.py:140-145).

**Required fix (reviewer does not modify code):**
- `from_runtime`: pass `settings=settings` into `DocumentIngestionService(...)`.
- Add a regression test that builds the workflow via the production wiring with
  overridden metadata settings (`email_attachments=False` → no temp leftovers;
  `max_file_size_mb` enforced; `max_attachments` honored), so the
  service/workflow setting alignment is pinned.
- Amend the implementation report's rollback/size-limit claims to match.

### O1 — Temp files leak if parent processing fails

The `finally` cleanup lives only inside `_ingest_children`
(ingest_workflow.py:373-374). If `_process_document` raises for the parent
(AI/processor/writer/knowledge-engine failure) before `_ingest_children` runs
(run(), ingest_workflow.py:246-247), the parent's extracted attachment temp
files are never cleaned. Non-blocking (abnormal path, temp files only). Upgrade
path: wrap the parent + children flow in one `try/finally` in `run()`.

### O2 — Attachments nested inside a `multipart/related` (or other sub-container) are skipped

`iter_attachments()` yields direct children; `Content-Disposition: attachment`
parts nested one level inside a `multipart/related` container (a real-world MUA
layout for HTML emails) are not examined, so such attachments are lost. The
direct-children choice correctly preserves the depth guard — the upgrade path is
to walk the tree but stop at `message/rfc822` boundaries. Non-blocking for the
frozen AC (3 direct-child PDFs); worth a follow-up.

### O3 — `parent_id` is recorded but not yet consumed

Both `metadata.extra["parent_id"]` and `ProcessedDocument.parent_id` are
informational today — no vault naming, backlink, or query wiring uses them. This
matches the frozen objective; the checklist's "parent/child vault naming" item
remains future work.

### O4 — No test covers the production wiring path

All P2-208 workflow tests pass settings to both service and workflow, so the
service/workflow settings split in `create_default` is untested. R1 would have
been caught by a single `create_default`-wiring test.

### O5 — Over-size child not testable end-to-end via one shared limit (acknowledged)

A single decoded attachment is always smaller than the base64-inflated parent
`.eml`, so the parent's own size check trips first; the child failure path is
covered by the stub-based test and the size-limit reuse by existing
service-level tests (`tests/unit/test_ingestion_hooks.py:103`). Documented in
the report; no action required.

---

## Gate Results (unchanged by review)

| Gate | Result |
|------|--------|
| `python -m pytest tests/unit -q` | 605 passed / 0 deselected |
| `python -m pytest tests/integration -q --ignore=tests/integration/smoke_test.py` | 10 passed / 7 deselected |
| AC test (`-m integration`) | 1 passed (3-PDF email → 4 notes) |
| `python -m ruff check app tests` | 64 pre-existing baseline; zero new |
| `python -m mypy app` | 4 pre-existing baseline; changed files clean |

---

## Summary

The recursive-ingestion feature itself is correct and well-tested: parent/child
stamping, the one-level depth guard, the `max_attachments` cap, direct-children
extraction, temp cleanup, and backward compatibility all hold, and the frozen AC
passes. **One required remediation (R1):** the production
`create_default`/`from_runtime` path builds the ingestion service without
settings, so the frozen `email_attachments` rollback leaks temp files and
`max_file_size_mb` is not enforced through the actual CLI/queue wiring. The fix
is a one-line settings pass-through plus a wiring regression test. After R1 is
resolved and the report amended, this task is ready for milestone close.
