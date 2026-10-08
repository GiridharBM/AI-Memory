# PAM V2.1.0 Final Report

## 1. Release Identity

- **Version:** V2.1.0 (released)
- **Release tag:** `v2.1.0` (annotated, pushed and verified)
- **Release commit:** `be3a7ae` (`be3a7aeb154ff507151952938aefc6e0ea387e70`)
- **Release state:** RELEASED — `HEAD == origin/main == be3a7ae`
- **Previous release:** V2.0.0 (tag `v2.0.0`)
- **V2.1 commit chain:**
  - `d02077d` (`d02077d7ae3d93cc1f8089e74e3d8aaf0f06c269`) — feat: add conversation session foundation (V2.1-A)
  - `3f0c0d6` (`3f0c0d6ce532cb68db0906d50530953f6676f069`) — feat: add memory domain foundation
  - `6240234` (`624023473dcaf5e318c710e9bd30ef2c4d088f4f`) — feat: add memory persistence and extraction lifecycle
  - `c23f65e` (`c23f65e04cadde6025db198d4bd9dd34da43e027`) — feat: add memory review API and UI
  - `be3a7ae` (`be3a7aeb154ff507151952938aefc6e0ea387e70`) — feat: integrate approved memories into conversation QA (V2.1-C)

## 2. Implementation Scope

V2.1 adds conversation sessions and a human-approved personal-memory
lifecycle over the frozen document-RAG foundation without modifying it:

- **V2.1-A conversation/session foundation** (`d02077d`): persistent
  conversations, immutable server-sequenced messages (clients submit `user`
  messages only), per-conversation isolation, `EvidenceSnapshot` /
  `EvidenceCitation` on assistant messages, failure markers, bounded history.
- **V2.1-B memory domain/persistence/extraction/approval** (`3f0c0d6`,
  `6240234`): `MemoryCandidate` / `Memory` domain with pending/approved/
  rejected and active/superseded states, explicit per-conversation extraction
  (USER-grounded, failed generations excluded, privileged fields
  server-assigned), approve/reject/edit/supersede lifecycle, atomic local
  JSON persistence.
- **Memory REST API** (`c23f65e`): 10 endpoints — extract, candidate
  list/get/approve/reject/edit, memory list/get, version filtering,
  supersede, provenance — with server-owned IDs/timestamps and
  404/409/422 mappings.
- **Memory Review UI** (`c23f65e`): `/memory-review` route with review queue,
  approve/edit/reject actions, version history, and provenance display.
- **V2.1-C approved-memory QA integration** (`be3a7ae`): ACTIVE-only
  deterministic lexical retrieval inside `QAWorkflow.ask`, memory context
  appended after document evidence, positional citations, memory-based
  abstention rescue, per-call store freshness.

## 3. V2.1 Feature Inventory

Conversation/session foundation; immutable server-sequenced messages;
`EvidenceSnapshot`; `EvidenceCitation`; explicit conversation-scoped
extraction; USER grounding; failed-assistant exclusion; candidate lifecycle;
mandatory human approval; durable memories; versioning; stable logical IDs;
supersession (no tombstones, no deletion); atomic JSON persistence; memory
REST API (10 endpoints); Memory Review UI; provenance
(`memory:<logical_id>@v<n>`); ACTIVE-only retrieval; deterministic lexical
scoring (threshold 0.5, top 3); memory-backed QA; memory evidence citations;
abstention rescue; per-call `MemoryStore` freshness.

## 4. Architecture Status

Dual evidence path inside the single `QAWorkflow.ask` seam (shared by
`POST /ask`, `POST /conversations/{id}/ask`, and `pam ask`):

Document path (frozen):
Search → Rerank → Abstention → Answerability → Context → LLM

Memory path (additive):
Approved Memory → lexical retrieval → memory context → QA

Document gates evaluate document hits only; a usable memory section is a
separate downstream sufficiency signal. With no matching memories the
document-only flow is byte-identical (tested). Frozen components
(embeddings, search, BM25, RRF, reranker, HyDE, answerability, citation
resolution, domains, ingestion) are unchanged through V2.1.

## 5. Testing and Validation

Full regression: **2337 passed / 2 skipped / 57 deselected / 0 failed**
(the 2 skips are pre-existing platform skips for URL-shaped directory
names; the 57 deselected are `integration`-marked).

E2E: **16/16 scenarios passed** (personal fact → extraction → approval →
persistence → memory-backed question → provenance → rejection safety →
supersession → cache freshness → no-memory regression → abstention rescue
→ irrelevant-memory abstention → document+memory → conflicting actives).

Static quality: **Ruff clean**; **mypy: zero V2.1 errors** (five known
pre-existing `reranker.py` errors only).

## 6. Migration Requirements

V2.1 does not introduce a database migration. Memory JSON stores
(`memory_candidates.json`, `memories.json`) are created on demand under
the configured manifest root; no data migration, re-ingest, or
configuration change is required. No automatic migration mechanism exists
or is claimed.

## 7. Known Limitations

Lexical memory retrieval (lowercase alphanumeric tokens, no stemming, no
semantic matching); threshold 0.5; top 3 memories per answer; ACTIVE
versions only (superseded/rejected excluded); one `memories.json` read per
QA call; no automatic extraction (explicit per-conversation trigger only);
no tombstones; conflicting ACTIVE memories are surfaced side-by-side with
no automatic resolution; memory retrieval is not semantic.

## 8. Deferred Capabilities

Memory embeddings; semantic memory retrieval; memory BM25/RRF; memory
reranking; advanced conflict resolution; knowledge-graph runtime retrieval
integration; tombstones; database/vector-database migration;
automatic/background memory extraction; daemon/agent-based memory
extraction; cloud memory storage. None are partially implemented; none
block this release.

## 9. Release Checklist

- [x] V2.1 implementation complete (V2.1-A/B/C, audited PASS)
- [x] Full suite green (2337/2/57), Ruff/mypy clean (5 pre-existing reranker notes only)
- [x] 16/16 E2E scenarios passed against the release tree
- [x] Worktree protection verified (30 unrelated entries preserved at every gate)
- [x] Annotated `v2.1.0` tag created, pushed, and verified against `be3a7ae`
- [x] `HEAD == origin/main == be3a7ae`
- [x] Release documentation updated (README V2.1.0 + this report)

## 10. Current Release Status

**PAM V2.1.0 is released.**

Release tag: `v2.1.0`

Release commit: `be3a7ae` (`be3a7aeb154ff507151952938aefc6e0ea387e70`)
