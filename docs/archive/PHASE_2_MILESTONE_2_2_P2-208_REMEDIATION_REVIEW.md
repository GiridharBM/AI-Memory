# P2-208 Remediation Review — R1 (production settings wiring)

**Task:** P2-208 (Milestone 2.2 — Metadata Extraction Framework; milestone gate)
**Scope:** Review ONLY the R1 remediation (engineering review of 2026-08-01)
**Reviewer:** Principal Engineering Reviewer
**Date:** 2026-08-01

## Scope and Method

Reviewed the R1 remediation only: the production-wiring fix in
`app/pipelines/ingest_workflow.py`, the `test_create_default_*` regression net
in `tests/integration/test_email_attachment_ingestion.py`, and the amended
implementation report. No code modified. Findings verified statically (code
trace of the wiring and gates) and empirically (all gates re-run on the final
state; plus a scratch probe replicating the pre-fix wiring to prove the
regression net discriminates).

## Verification

### 1. Runtime settings reach `DocumentIngestionService` — ✅ Verified

- `IngestionWorkflow.from_runtime` now constructs
  `DocumentIngestionService(settings=settings)` (`ingest_workflow.py:150`),
  matching the DI pattern used elsewhere in the wiring.
- `create_default(settings)` passes `settings` through to `from_runtime`
  (`ingest_workflow.py:201-218`).
- Both production entry points route through `create_default(settings)`:
  CLI `app/cli/entry.py:372`, queue worker `app/queue/worker.py:84`.
- Service stores `self._settings` (`service.py:60`); `_metadata()` returns
  `self._settings.intelligence.metadata` (`service.py:90-93`), which feeds
  `EmailIngestor(metadata=self._metadata())` (`service.py:85`) and
  `_enforce_size_limit` (`service.py:173-182`).
- Direct regression proof:
  `test_create_default_wires_metadata_settings_to_service` asserts the
  production-built service holds the configured `email_attachments=False`,
  `max_file_size_mb=7`, `max_attachments=3` values.

### 2. `email_attachments=false` disables extraction — ✅ Verified

- Service gate: `EmailIngestor.ingest` only attaches extractions when
  `enabled and email_attachments` (`email_ingestor.py:98`).
- Workflow gate: `_ingest_children` early-returns unless `enabled and
  email_attachments` (`ingest_workflow.py:353-355`).
- Regression test: `test_create_default_email_attachments_false_extracts_nothing`
  → exactly 1 document (parent only), no children, no temp dirs.

### 3. No temporary directories leak — ✅ Verified

- Both run-based regression tests snapshot `tempfile.gettempdir()` for
  `pam_email_attachments_*` before and assert equality after.
- Cleanup runs in a `finally` (`ingest_workflow.py:373-374`), removing files
  then empty dirs.
- Empirically confirmed discriminating power: a scratch probe replicating the
  **pre-fix** wiring (service built without settings, `email_attachments=False`)
  reproduced exactly the review's leak — 1 `pam_email_attachments_*` dir left
  after `run()` — so the regression assertion fails on the old wiring. On the
  fixed wiring the test passes with zero leftovers. (Probe artifacts cleaned;
  environment left as found.)

### 4. `max_file_size_mb` is enforced — ✅ Verified

- `_enforce_size_limit` reads `metadata.max_file_size_mb` from the service's
  settings (`service.py:173-182`).
- Regression test: `test_create_default_enforces_max_file_size_mb` (limit=1 MB,
  1 MiB + 1 byte file, via the production-built service) → ingest fails with a
  size-limit error.
- Empirical probe confirmed the old wiring accepts the oversized file
  (default 64 MB), so this test fails pre-fix.

### 5. `max_attachments` still works — ✅ Verified

- `test_create_default_honors_max_attachments` (cap=1, two attachments) → 2
  documents (parent + first child only), child content is exactly the first
  attachment, no temp dirs remain.
- This cap is enforced workflow-side (`ingest_workflow.py:363-371`) and was
  never broken by R1; the test correctly guards the required "still works"
  contract through the production wiring.

### 6. Regression test covers the production wiring — ✅ Verified

- All four tests build the workflow via `IngestionWorkflow.create_default(settings)`
  — the exact entry-point path used by CLI and queue worker. Only
  network-dependent collaborators (`_processor`, chunker, embedding, vector
  store, KG builder) are swapped for fakes after construction.
- The net has real discriminating power: two tests fail under the pre-fix
  wiring (settings-wire and size-limit), and the `email_attachments=false` case
  is caught by its temp-dir-leak assertion (probe-confirmed). The
  `max_attachments` test passes under both wirings by design (never broken).

### 7. Implementation report matches reality — ✅ Verified

- Amended sections (limits, files-modified, test results, remaining risks,
  milestone readiness) match the code and re-run gates exactly:
  unit **605 passed**, integration **14 passed / 7 deselected**, AC test
  **1 passed**, ruff **64 (pre-existing baseline)**, mypy **4 (pre-existing
  baseline)**.
- The remediation report (`P2-208_REMEDIATION_REPORT.md`) accurately
  describes the fix, the regression net, gate results, and files changed.

### Remediation discipline — ✅ Verified

- Only the required files were touched by the remediation: the one-line
  `from_runtime` change, the integration test file (regression net + removal of
  a dead `email.policy` import), and the implementation report. No unrelated
  modules, no new functionality, backward compatible (additive optional
  parameter).

## Non-blocking observations (informational)

- O1–O5 from the original review are unchanged and remain non-blocking. O1
  (temp leak if the parent's own processing raises before `_ingest_children`)
  is adjacent to but distinct from the R1 leak and was explicitly out of
  remediation scope; the regression net covers the R1 scenario exactly.
- `test_create_default_wires_metadata_settings_to_service` reads private
  members (`_ingestion_service._metadata()`); acceptable for an internal
  regression test and consistent with the existing AC test's style.

## Verdict

✅ **Approved**

R1 is fully resolved: runtime settings reach `DocumentIngestionService` through
both production entry points, `email_attachments=false` disables extraction,
no temporary directories leak, `max_file_size_mb` and `max_attachments` are
enforced, the regression net exercises the production wiring and demonstrably
fails on the pre-fix wiring, and the implementation report matches reality.
Observations O1–O5 remain informational and do not affect approval.
