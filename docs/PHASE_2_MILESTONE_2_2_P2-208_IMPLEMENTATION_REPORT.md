# P2-208 Implementation Report — Email attachment parsing (recursive ingestion)

**Task:** P2-208 (Milestone 2.2 — Metadata Extraction Framework; milestone gate)
**Frozen contract:** `docs/PHASE_2_MILESTONE_2_2_ENGINEERING_SPECIFICATION.md` §P2-208 (lines 226–244)
**Date:** 2026-08-01
**Status:** Ready for engineering review

## Implementation Summary

Implemented recursive email-attachment ingestion per the frozen §P2-208
contract: an RFC822 email becomes a parent note; its `Content-Disposition:
attachment` parts are written to temporary child sources, re-ingested through
the same `DocumentIngestionService`, and each child carries `parent_id`.
Today's behavior is preserved when attachments are disabled or absent.

- **Attachment extraction (`EmailIngestor`):** `ingest()` now passes the parsed
  MIME message to `_attach_extracted_attachments` when
  `metadata.enabled and metadata.email_attachments` (both default `true`).
  `_extract_attachments` iterates `msg.iter_attachments()` — **direct children
  only** — filtering for `Content-Disposition: attachment`, and writes each to a
  `tempfile.mkdtemp(prefix="pam_email_attachments_")` child file. The parent
  document keeps today's header+body text and gains
  `extra.attachments` (filenames) + `extra.attachment_paths` (temp paths).
  Names are sanitized (`_safe_attachment_name` strips path components; falls
  back to a hash-based name) and deduplicated (`_unique_name`, `a.txt → a-1.txt`).
  `message/rfc822` nested parts (payload is a `Message`, `get_payload(decode=True)`
  returns `None`) are serialized via `nested.as_bytes()` so an `.eml` child can be
  re-ingested as email. `iter_attachments()` over `walk()` is deliberate: `walk()`
  recurses into nested emails and would flatten the depth guard (grandchild
  attachments extracted as the parent's). Empty extractions clean the temp dir up.
- **Workflow re-ingestion (`IngestionWorkflow`):** `run()` was split — the old
  body became `_process_document(document, *, parent_id)`. After the parent note
  is produced, `_ingest_children(document)` reads `attachment_paths`, sets
  `parent_id = document.source`, and re-ingests each child through the **same**
  `DocumentIngestionService` (`_ingest_child`), stamping
  `child.metadata.extra["parent_id"]` before `_process_document(child, parent_id=...)`.
  Children never recurse further — a nested email's own attachments are extended
  into the cleanup list but not re-ingested (depth guard / no infinite recursion).
  Temp files are removed in a `finally` via `_cleanup_attachment_temp_files`
  (files unlinked, now-empty temp dirs `rmdir`'d, `OSError` ignored), so cleanup
  also runs when a child ingest fails or the cap is hit.
- **Limits:** `max_attachments` is enforced in `_ingest_children` (skip + warn
  beyond the cap). `max_file_size_mb` is reused because children go through the
  same `DocumentIngestionService._enforce_size_limit`. Both roll back cleanly:
  `email_attachments: false` (or `enabled: false`) restores today's
  single-document behavior — `EmailIngestor` adds no attachment keys and
  `_ingest_children` returns early.
- **Production settings wiring (R1 remediation):** `IngestionWorkflow.from_runtime`
  now passes `settings` into `DocumentIngestionService(settings=settings)`, so the
  service's `MetadataSettings` — `email_attachments`, `max_file_size_mb`, and the
  extractor/enrichment gate — are the runtime settings through both production
  entry points (`app/cli/entry.py` and `app/queue/worker.py`). The `EmailIngestor`
  extraction gate, the size-limit check, and the workflow cap all read the same
  configured values; the frozen rollback contract and size-limit enforcement hold
  on the production path (verified by `test_create_default_*` regression tests).
- **`ProcessedDocument.parent_id: str | None`:** additive field (default `None`),
  stamped in `_run_routed_processor` next to the P2-205 `language` stamp. The
  durable record on the source document is `metadata.extra["parent_id"]`.

## Files Modified

| File | Change |
|------|--------|
| `app/infrastructure/ingestion/email_ingestor.py` | `__init__` gains `metadata: MetadataSettings | None`; `ingest()` appends attachment extraction (gated on `enabled and email_attachments`); new `_attach_extracted_attachments` / `_extract_attachments` (direct-child `iter_attachments`, temp dir, nested-`message/rfc822` serialization); new `_safe_attachment_name` / `_unique_name` helpers |
| `app/pipelines/ingest_workflow.py` | `run()` split into `_process_document(document, *, parent_id)`; new `_ingest_children` (cap + cleanup) / `_ingest_child` (re-ingest + `parent_id` stamp + nested cleanup) / `_cleanup_attachment_temp_files`; `_run_routed_processor` gains `parent_id` kwarg and stamps `ProcessedDocument.parent_id`; `from_runtime` passes `settings` into `DocumentIngestionService` (R1) |
| `app/domain/processed_document.py` | additive `parent_id: str | None = None` field |
| `app/infrastructure/ingestion/service.py` | `__init__` sets `self._settings` before building ingestors; `EmailIngestor(metadata=self._metadata())` (previously no-arg) |
| `tests/unit/test_email_attachments.py` | **new** — 14 tests (attachment extraction, gating, sanitization/dedup, nested-email serialization, workflow parent/child, `max_attachments` cap, child-failure skip, depth guard, temp cleanup) |
| `tests/integration/test_email_attachment_ingestion.py` | **new** — frozen AC: 3-PDF-attachment email → 1 parent + 3 children with `parent_id`, 4 notes written, temp files cleaned; **plus R1 regression net:** 4 `test_create_default_*` tests through the production wiring (`email_attachments=false` → no extraction + no temp dirs, `max_file_size_mb` enforced, `max_attachments` honored, service receives settings) |

No config changes — `intelligence.metadata.{email_attachments,max_attachments,max_file_size_mb}`
already exist and are now consumed.

## Test Results

| Gate | Result |
|------|--------|
| `python -m pytest tests/unit -q` | 605 passed / 0 deselected (baseline 591 preserved + 14 new; 0 regressions) |
| `python -m pytest tests/integration -q --ignore=tests/integration/smoke_test.py` | 14 passed / 7 deselected (baseline 10/6 + 4 R1 regression tests; AC test integration-marked) |
| `python -m pytest tests/integration/test_email_attachment_ingestion.py -m integration` | 1 passed (frozen AC: 3 PDF attachments → 4 notes with `parent_id`) |
| `python -m ruff check app tests` | 64 errors (pre-existing baseline; zero in new/changed files) |
| `python -m mypy app` | 4 pre-existing errors (fitz/pptx/whisper/numpy stubs); changed files clean |

Regression: existing `.eml` tests unchanged — `tests/unit/test_ingestion.py:177`,
`tests/integration/test_ingestion_metadata.py:166` (enrichment superset), and the
markdown e2e workflow (`test_complete_workflow.py`) all still pass.

## Remaining Risks

- **One-level recursion is a hard cap, not a config:** a nested `.eml`
  attachment is re-ingested as a child email, but its own attachments are only
  extracted to temp files and cleaned up — they do **not** become notes. This is
  the frozen DoD ("cap recursion at one level below the parent unless
  configured"); configuring deeper recursion is not implemented.
- **Over-size child cannot be tested end-to-end via one shared limit:** the
  parent `.eml` is base64-inflated relative to a single decoded attachment, so
  the parent's own `_enforce_size_limit` check always trips first. The child
  failure path (warning + skip + cleanup) is covered by the
  `_ParentThenFailingService` unit test; limit reuse is covered by the existing
  service-level tests in `tests/unit/test_ingestion_hooks.py:103` and, through
  the production wiring, by `test_create_default_enforces_max_file_size_mb`.
- **Temp-file cleanup is `finally`-dependent:** files live in
  `%TEMP%/pam_email_attachments_*` until `run()` unwinds. A hard process crash
  between extraction and cleanup leaks temp files (best-effort `OSError`-ignored
  cleanup otherwise).
- **Injected custom `processor=` bypasses language adaptation:** unchanged from
  P2-205 (observation O3); children inherit the same behavior as the parent.
- **`max_attachments` is per-email (frozen):** the cap counts attachments of one
  parent; the frozen contract did not define a global/queue-wide cap.

## Milestone Readiness Assessment

P2-208 was the final Milestone 2.2 critical-path task
(§5: P2-201 → P2-202 → P2-207 → P2-208). With P2-205 and P2-208 both landed and
gated, every frozen Milestone 2.2 task on the critical path is
implemented. The engineering review flagged R1 (production wiring ignored
`email_attachments` / `max_file_size_mb`); the R1 remediation is implemented
(settings threaded into `DocumentIngestionService` + `test_create_default_*`
regression net) and the task is back with engineering for re-review. Remaining
before milestone close: re-review of this task, verification of AC 2 /
end-to-end live-LLM acceptance items, and the preflight items the milestone
defers to post-close (per
`docs/PHASE_2_MILESTONE_2_2_P2-205_ENGINEERING_REVIEW.md`).
