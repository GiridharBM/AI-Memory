# Milestone 2.3 — P2-301 Implementation Specification: Structure Domain Models

**Milestone:** 2.3 — Document Structure Analysis
**Task:** P2-301 — Structure domain models
**Status:** Implementation specification (no code implemented by this document)
**Governing contract:** `docs/PHASE_2_MILESTONE_2_3_ENGINEERING_SPECIFICATION.md` v1.1 (🔒 FROZEN 2026-08-01) — §4.2 (normative models), §5.4 (R-1 channel), §11.1 (task row P2-301).
**Freeze record:** `docs/PHASE_2_MILESTONE_2_3_SPECIFICATION_FREEZE.md`

---

## 1. Objective

Define the three structure domain models — `DocumentStructure`, `DocumentSection`, `DocumentBlock` — in `app/domain/document_intelligence.py`, exactly as frozen in the engineering spec §4.2, with IDs, levels, parent IDs, and char offsets, plus validation that protects the offset-integrity contract (R-2).

**This task defines data only. No analysis logic, no enrichment wiring, and no `ProcessedDocument` change.** The models are pure pydantic data holders consumed by P2-302/303/304 (detectors + tree builder) and serialized by P2-305 via the R-1 channel (`document.metadata.extra["structure"]`).

> **Note on stale roadmap text:** `docs/PHASE_2_MILESTONE_2_3_IMPLEMENTATION_ROADMAP.md` §4 P2-301 still says "add additive `structure` field to `ProcessedDocument`" and "expose composition-root stubs". That predates the R-1 remediation. The frozen engineering spec governs: **`ProcessedDocument` is NOT modified** (spec §5.4 deviation) and **P2-301 touches only `domain/document_intelligence.py`** (spec §11.1 P2-301 row). The composition-root functions `analyze_document_structure` / `get_default_structure_analyzer` (spec §4.1/§4.3) are exposed by the detector/enrichment tasks, not P2-301.

## 2. Dependencies

| Dependency | Type | Detail |
|------------|------|--------|
| `pydantic` (v2) | Required, existing | `BaseModel`, `ConfigDict`, `Field`, `Literal`, `field_validator`, `model_validator` — already a project dependency |
| `app/domain/document_intelligence.py` | Existing file | Contains `MetadataExtraction` (M2.2, `document_intelligence.py:10`); new models are appended alongside it (frozen §7.2 placement precedent) |
| Intra-milestone | **None** | P2-301 is wave 1 (spec §11.2) — foundation, nothing consumes it this task |
| New dependencies | **None** | No new packages; no wheel verification needed |

## 3. Architecture

- **Layer:** domain models (`app/domain/`), consistent with the frozen §7.2 placement of `MetadataExtraction` — infrastructure stays out of this file.
- **Shape:** three pydantic `BaseModel` classes, flat containment `DocumentStructure → DocumentSection[] → DocumentBlock[]` (no bidirectional references — parent/child is expressed as scalar `parent_id`, never object links).
- **Behavior:** models are pure data — no methods, no parsing, no imports from `app/infrastructure/`. This keeps them trivially serializable (JSON mode), which is the R-1 channel requirement (`model_dump(mode="json")` → `metadata.extra["structure"]` → `model_validate`).
- **No wiring:** nothing instantiates these models in production code this task; the detector (P2-302/303), tree builder (P2-304), and enrichment hook (P2-305) consume them in later waves.
- **ID conventions (frozen D4/D5):** section IDs `s-1` / `s-1-1` (deterministic from heading order, R-8); block IDs `b-<section_id>-<n>` (e.g. `b-s-1-1-1`). The model carries these as plain strings — the *schemes* are owned by the builder, the *fields* by this task.

## 4. Files to Modify

| File | Change |
|------|--------|
| `app/domain/document_intelligence.py` | **Add** `DocumentStructure`, `DocumentSection`, `DocumentBlock`. `MetadataExtraction` untouched. |

No other file changes. Explicitly **not** modified: `app/domain/processed_document.py` (R-1 — see Objective note), `app/infrastructure/document_intelligence/__init__.py`, `app/core/config.py`, `config/default.yaml`, any test baseline file.

## 5. Public Interfaces

```python
class DocumentBlock(BaseModel): ...
class DocumentSection(BaseModel): ...
class DocumentStructure(BaseModel): ...
```

- **Import path:** `from app.domain.document_intelligence import DocumentStructure, DocumentSection, DocumentBlock`.
- **Module-level only:** the three classes become public module attributes; existing public name `MetadataExtraction` unchanged.
- **Construction contract (frozen §4.2, normative):**

```python
structure = DocumentStructure(
    sections=[
        DocumentSection(
            id="s-1",
            title="Introduction",
            level=1,
            parent_id=None,
            start_char=0,
            end_char=120,
            blocks=[
                DocumentBlock(
                    block_id="b-s-1-1",
                    type="paragraph",
                    text="First paragraph.",
                    start_char=0,
                    end_char=120,
                )
            ],
        )
    ]
)
```

- **Serialization contract (R-1 channel):** `structure.model_dump(mode="json")` must produce a JSON-native dict (`{"sections": [...]}`); `DocumentStructure.model_validate(dumped)` must reproduce an equal model. An empty structure is legal and dumps to `{"sections": []}`.
- **Deferred to later tasks:** `analyze_document_structure(text, source)`, `StructureAnalyzer`, `get_default_structure_analyzer()` are NOT introduced by P2-301 (frozen §11.1 file ownership).

## 6. Data Models

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BlockType = Literal["paragraph", "list", "code", "blockquote", "table"]


class DocumentBlock(BaseModel):
    """A typed block within a document section (frozen spec §4.2)."""

    model_config = ConfigDict(extra="forbid")

    block_id: str          # e.g. "b-s-1-1" — scheme owned by the tree builder (D5)
    type: BlockType        # paragraph | list | code | blockquote | table
    text: str
    start_char: int        # inclusive, relative to the analyzed text
    end_char: int          # exclusive, relative to the analyzed text


class DocumentSection(BaseModel):
    """A heading-delimited section of the document (frozen spec §4.2)."""

    model_config = ConfigDict(extra="forbid")

    id: str                # e.g. "s-1" / "s-1-1" — scheme owned by the tree builder (D4)
    title: str
    level: int             # 1..6, from ATX heading depth
    parent_id: str | None  # None for root sections
    start_char: int
    end_char: int
    blocks: list[DocumentBlock]


class DocumentStructure(BaseModel):
    """The nested structure of a document (frozen spec §4.2)."""

    model_config = ConfigDict(extra="forbid")

    sections: list[DocumentSection]
```

**Fidelity rule:** the three classes above are the frozen §4.2 interface verbatim. No field added, removed, re-typed, or given a default that changes the interface (e.g. `sections` stays required; the analyzer's degenerate path passes `sections=[]` explicitly).

## 7. Validation Rules

| Field | Rule | Mechanism |
|-------|------|-----------|
| `DocumentBlock.type` | Must be one of `paragraph`, `list`, `code`, `blockquote`, `table` | `Literal` (pydantic rejects others at construction) |
| `DocumentSection.level` | `1 <= level <= 6` (frozen `MAX_HEADING_LEVEL`) | `Field(ge=1, le=6)` — levels deeper than 6 are normalized by P2-302, never stored as >6 |
| `start_char` / `end_char` | Non-negative | `Field(ge=0)` |
| Offsets ordering | `end_char >= start_char` | `model_validator(mode="after")` raising `ValueError` |
| Slice self-consistency | When `text` is non-empty, `text[start_char:end_char] == text` | `model_validator(mode="after")` raising `ValueError` — enforces the offset-integrity contract (R-2, AC3) at the boundary |
| `block_id` / `id` | Non-empty | `Field(min_length=1)` |
| `parent_id` | `None` for roots; non-empty string otherwise | Empty string rejected via `Field(min_length=1)` when not `None` |
| Unknown keys | Rejected (no silent field creep) | `ConfigDict(extra="forbid")` on all three models |

**Semantics pinned (R-2 risk mitigation):** `start_char` is **inclusive**, `end_char` is **exclusive**, both relative to the exact analyzed text string (frozen spec §4.2 "Offsets are relative to the exact text string passed to `analyze`"). This task establishes the convention; P2-303/304 offset-accuracy tests assert it.

## 8. Rollback Strategy

| Level | Mechanism | Detail |
|-------|-----------|--------|
| Per-task | Git revert of the single atomic P2-301 commit | Task is additive-only; nothing else references the models yet, so a revert is a clean removal with zero blast radius |
| Data | No persistence touched | Models are not serialized to any store by this task; no migration |
| Code | No legacy branch | No behavioral change to any existing component; `MetadataExtraction` byte-identical |
| Dependency | None | No new packages |
| Process | Frozen spec §14 | Follows the milestone rollback contract; `enabled: false` semantics are unaffected (no wiring yet) |

## 9. Acceptance Criteria

| # | Criterion |
|---|-----------|
| AC1 | `DocumentStructure.sections` is a `list[DocumentSection]`. |
| AC2 | `DocumentSection` carries `id`, `title`, `level`, `parent_id`, `start_char`, `end_char`, `blocks` with the frozen types. |
| AC3 | `DocumentBlock` carries `block_id`, `type` restricted to `paragraph`/`list`/`code`/`blockquote`/`table`, `text`, `start_char`, `end_char`. |
| AC4 | `ProcessedDocument` is **not** modified (R-1): no `structure` field is added to any model outside `document_intelligence.py`. |
| AC5 | JSON round-trip: `DocumentStructure.model_validate(ds.model_dump(mode="json")) == ds`, including the empty case `DocumentStructure(sections=[])` → `{"sections": []}`. |
| AC6 | Validation: `level` outside 1..6, negative offsets, `end_char < start_char`, a text/slice mismatch, an unknown `type`, and empty IDs are all rejected with `ValidationError`. |
| AC7 | Existing `MetadataExtraction` and the 605 unit + 14 integration baseline remain green (additive-file regression). |

## 10. Definition of Done

- [ ] `DocumentStructure`, `DocumentSection`, `DocumentBlock` added to `app/domain/document_intelligence.py` matching the frozen §4.2 interface exactly.
- [ ] Validation rules (§7) implemented and covered by unit tests.
- [ ] No change to `ProcessedDocument` or any other file (R-1 compliance).
- [ ] Placement matches the M2.2 precedent (`MetadataExtraction` at `document_intelligence.py:10`).
- [ ] Models **not** wired into ingestion (spec §11.1 P2-301 DoD).
- [ ] Unit tests added to `tests/unit/test_structure_analysis.py` (per frozen spec §13); all existing tests pass unchanged; `ruff` zero new errors; `mypy` zero new type errors.
- [ ] Single atomic commit per the milestone rollback contract (frozen spec §14).

## 11. Test Plan

| Layer | Scope | Details |
|-------|-------|---------|
| Unit — construction | Build a 2-section, 3-block sample; assert every field value | `tests/unit/test_structure_analysis.py` (new file per frozen spec §13) |
| Unit — ID/type | Section IDs and block IDs accepted as non-empty strings; block `type` Literal rejects `"heading"`/`"image"` | same file |
| Unit — validation | `level` 0 and 7 rejected; `level` 1 and 6 accepted; negative offsets rejected; `end < start` rejected; empty-string `id`/`block_id` rejected; `extra` key rejected (extra="forbid") | same file |
| Unit — slice integrity | Text/slice mismatch (`text[start:end] != text`) rejected; exact-slice model accepted | same file |
| Unit — round-trip (R-1) | `model_validate(model_dump(mode="json"))` preserves equality on the sample and on `DocumentStructure(sections=[])` → `{"sections": []}` | same file |
| Unit — parent semantics | `parent_id=None` for root; nested section carries `"s-1"` parent reference | same file |
| Regression | `MetadataExtraction` unchanged; full `tests/unit` + `tests/integration` suite | `python -m pytest tests -q -p no:cacheprovider --cov=app --cov-report=term` |

**Fixtures:** none committed this task (detector fixtures arrive with P2-302/303); the test sample is inline.

## 12. Risks

| # | Risk | L/I | Mitigation |
|---|------|-----|------------|
| 1 | Offset semantics (inclusive/exclusive) ambiguity causes P2-303/304 off-by-one bugs | M/M | Convention pinned in §7 now; slice self-consistency validator enforces it at the model boundary; offset-accuracy tests arrive with the detectors |
| 2 | `type` string drift beyond the frozen five kinds | M/L | `Literal` restricts at construction; changing the set later requires a frozen-spec deviation |
| 3 | Model surface creep (defaults/extra fields) deviating from the frozen §4.2 interface | L/M | `extra="forbid"` + §6 fidelity rule; engineering-review gate checks the diff against §4.2 verbatim |
| 4 | R-1 regression — someone adds the `structure` field to `ProcessedDocument` under the stale roadmap text | L/M | Objective note + AC4 make the negative criterion explicit; review gate verifies only `document_intelligence.py` changed |
| 5 | Future non-JSON-native fields break the R-1 serialization channel | L/L | All fields are `str`/`int`/`Literal`/`None` — JSON-native by construction; round-trip test guards it |

## 13. Complexity Estimate

**Low — 0.5 dev-day** (frozen spec §11.1 P2-301 row). Three small pydantic models + validators + one new unit-test file; no infrastructure, no wiring, no dependency changes. Estimated split: ~0.25 d models + validators, ~0.25 d tests.

---

*End of P2-301 Implementation Specification. No code implemented by this document.*
