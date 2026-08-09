# P4-102 Engineering Review — Entity Extraction

**Task:** P4-102 — Entity Extraction
**Phase:** Phase 4 (entity extraction capability; no graph storage/retrieval)
**Date:** 2026-08-08
**Verdict:** **APPROVED**

---

## 1. Deliverable

New entity-extraction capability in `app/infrastructure/document_intelligence/entities/`:

| Artifact | Purpose |
|----------|---------|
| `extractor.py` | Deterministic rule-based `EntityExtractor` with `extract()` (flat or `DocumentStructure`-aware), `get_default_entity_extractor()` (composition root), and `analyze_document_entities()` (public API) |
| `__init__.py` | Package exports (`EntityExtractor`, `analyze_document_entities`, `get_default_entity_extractor`) |

The extractor reuses existing types and structures rather than duplicating them: the `EntityType` vocabulary from `app.domain.analysis` (9 types), the P4-101 `Entity`/`SourceReference` models from `app.domain.entity_relationship`, and `DocumentStructure`/`DocumentBlock`/`DocumentSection` from `app.domain.document_intelligence` (produced by the M2.3 `StructureAnalyzer`).

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| 1. Identify entities explicitly required by the existing specification | DONE | The Phase-4 spec defines entity extraction over the existing pipeline. Extraction produces `Entity` objects typed against the existing `EntityType` (`person`, `organization`, `technology`, `place`, `paper`, `concept`, …). No new type vocabulary invented. |
| 2. Reuse existing parsing/document structures | DONE | Consumes `DocumentStructure`/`DocumentBlock` from `app.domain.document_intelligence`; reuses block offsets instead of re-splitting text. No new document model, no duplicated parser. |
| 3. Extract entities deterministically | DONE | Pure function of input: pre-compiled regex rules, fixed precedence (first rule wins), sorted output; proven by `test_deterministic_across_calls` and `test_same_input_identical_ids_across_instances` (byte-stable `to_json` equality). |
| 4. Preserve entity text / type / source / offset / metadata | DONE | `Entity` carries `label`, `entity_type`, and `sources: list[SourceReference]` with `source`, `source_type`, `section_id`, and exact `start_char`/`end_char` plus `snippet`. Offsets always satisfy `text[start_char:end_char] == label` (label capture group per rule). |
| 5. Handle duplicate entities consistently | DONE | Repeated/case-variant mentions collapse via `Entity.make_id` (lowercase, spaces→underscores) into one entity with multiple `SourceReference`s; first-seen casing preserved as label. |
| 6. Empty/malformed input handled safely | DONE | Non-string, empty, and whitespace-only input returns `[]` without raising; Unicode and dangling-markdown-fence inputs never raise; oversize-structure path excluded (`code` blocks skipped). |
| 7. Extraction never crashes the ingestion pipeline | DONE | `extract()` is a pure, contained function with no I/O, no external calls, and a never-raise contract for non-string/empty input. The structure path is fed a validated `DocumentStructure` (pydantic). |
| 8. Feature isolated from unrelated Phase 1–3 functionality | DONE | Self-contained package; no Phase 1–3 module modified; changes are additive-only. Phase 1–3 behavior verified unchanged by the full regression suite. |
| 9. No external ML/NLP dependencies | DONE | `re` (stdlib) only; no spaCy/NLTK/transformers added. The existing LLM-based `ImportantEntity` extraction (M3) is untouched and remains separate. |

## 3. Design Notes

- **Label-group offsets.** Each rule declares which capture group is the canonical entity label (`0` = whole match). Offsets and `snippet` use exactly that group's span, so the invariant `text[start:end] == label` holds for every rule — the person title ("Dr."), place preposition ("in"), and paper quote delimiters are never part of the label, and the offsets point at the label itself.
- **Precedence.** Rules run in fixed order (`technology`, `person`, `organization`, `place`, `paper`, `concept`); the first rule claims a span, later rules skip overlapping spans, so a name like "Jane Smith" is not double-typed by the concept rule.
- **Structure reuse.** When a `DocumentStructure` is supplied, extraction runs per text-bearing block (`paragraph`, `list`, `blockquote`, `table`) and stitches block-relative offsets onto the global coordinate space via `block.start_char` (frozen §5.2). Code blocks are excluded. Empty structure falls back to the flat scan.
- **Dedup.** `by_id` keyed on `Entity.make_id` merges duplicates across the whole document in both flat and structure paths; case variations ("Python 3.12" / "PYTHON 3.12") normalize to the same id.

## 4. Testing

**32 focused tests** across `tests/unit/test_entity_extractor.py` (30) and `tests/integration/test_entity_pipeline.py` (2), covering every mandated category:

- Normal extraction: person (with title), organization (with suffix), technology (with version), place (after preposition), paper (quoted title), concept (title-case run).
- Multiple entities: distinct types in one document; document-order output.
- Duplicates: repeated mention merges sources (flat and structure modes).
- Case variations: merge to one entity with both sources.
- Empty input: empty string, whitespace-only.
- Unicode: non-crashing; entities extracted from Unicode-sentence text.
- Long input: 10k-word text extracts without raising.
- Malformed: `None`/`int`/`bytes`/`list`/`dict` return `[]`; dangling markdown fences.
- Offset/source mapping: exact `text[start:end] == snippet == label`; end-exclusive offsets; `source`/`source_type` preserved.
- Determinism: byte-stable `to_json` across calls and instances.
- Structure reuse: section ids attached, offsets point at the original text, code blocks excluded, empty structure falls back.
- Public API: `EntityExtractor`, `get_default_entity_extractor`, `analyze_document_entities`.
- **Pipeline wiring (integration):** real `StructureAnalyzer().analyze()` → `EntityExtractor().extract()` — entities found inside paragraph blocks carry offsets into the *original* document and section ids; code-block content is excluded.

## 5. Verification (commands re-run this session)

| Gate | Result |
|------|--------|
| Focused tests | **32 passed** (30 unit + 2 integration) |
| Full regression suite | **1204 passed / 0 failed / 39 deselected** (baseline 1172 + 32 new; 0 regressions) |
| Ruff | **All checks passed** (changed files: entities package + both test files) |
| Mypy (`--ignore-missing-imports`) | **Success: no issues found** |
| Coverage (`entities` package) | **100%** (72 stmts, 0 miss; repo floor 80%) |
| Rollback | Additive-only: revert/remove the `entities/` package, its tests, and the review doc; no Phase 1–3 file touched. Worktree uncommitted (per-task atomic commits pending), consistent with the M2.1–M4 convention. |

## 6. Files Changed

| File | Action |
|------|--------|
| `app/infrastructure/document_intelligence/entities/extractor.py` | **Created** — rules, `_scan`, `EntityExtractor`, public helpers |
| `app/infrastructure/document_intelligence/entities/__init__.py` | **Created** — package exports |
| `tests/unit/test_entity_extractor.py` | **Created** — 30 focused tests |
| `tests/integration/test_entity_pipeline.py` | **Created** — 2 pipeline-wiring tests |

## 7. Findings

**Blocking:** None.

**Non-blocking:**
- Rule set is heuristic by design (documented in the module docstring): e.g. a capitalized word run directly before an org suffix ("Hello Acme Corporation") is absorbed into the org label. Deterministic and internally consistent (`text[start:end] == label` still holds); a statistical NER backend is out of scope (requirement 9 forbids ML/NLP deps).
- Per-task atomic commits pending (worktree uncommitted; consistent with M2.1–M3.2 convention).
- Phase 4 milestones ship additive-only; no MEDD version bump until Phase 4 is released as a whole.

## 8. Conclusion

P4-102 delivers deterministic, dependency-free entity extraction that reuses the existing `EntityType` vocabulary, the P4-101 `Entity`/`SourceReference` models, and the M2.3 `DocumentStructure` offsets — with exact label-group offset mapping, consistent duplicate/case handling, safe empty/malformed/Unicode behavior, and isolation from Phase 1–3. All gates pass (1204 passed, 0 regressions; ruff/mypy clean; 100% package coverage).

**Verdict:** **APPROVED**
