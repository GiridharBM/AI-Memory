# Milestone 2.5 Specification Review — Remediation Verification Report

**Milestone:** 2.5 — Image Intelligence
**Spec Updated:** `docs/PHASE_2_IMPLEMENTATION_SPECIFICATION.md` (§3.5, §4.5, §14), version 1.1 → 1.3
**Scope of this document:** verify every Required remediation from the Milestone 2.5 Specification Review is resolved in the spec, dependency graphs remain valid, and Acceptance Criteria / Definition of Done are internally consistent.
**Constraint honored:** no code modified — specification text only.

---

## 1. Required findings — resolution check

| # | Finding | Resolved? | Where |
|---|---------|-----------|-------|
| F-1 | P2-506 trigger/gate condition undefined ("PDF-with-images" with no classifier condition; risk of invented routing conditions) | ✅ | §3.5 Scope; §4.5 P2-506 row; §14.6 |
| F-2 | P2-505 Deps omit P2-205 (language slot), inconsistent with §5 and §6.3 | ✅ | §4.5 P2-505 row; §3.5 AC4; §14.6 |

### F-1 verification
- §3.5 Scope now states: multi-image handling **gated on the existing classifier condition `kind == "pdf"`** via a self-contained `_enrich_images` helper at the shared P2-305 call site, **no invented routing conditions (M2.4 R2 precedent)**.
- §4.5 P2-506 row: AC explicitly names the trigger (`kind == "pdf"`), the attachment point (shared call site), coexistence with the `kind == "pdf"` table gate, and adds `ingest_workflow.py` to the files list (matching the actual shared call site verified at `app/pipelines/ingest_workflow.py:492-505`).
- Deps unchanged (P2-305, P2-503) — consistent with §5 edge "2.3 → 2.4/2.5/2.6 (hard, R-2)".

### F-2 verification
- §4.5 P2-505 Deps column now reads `P2-205, P2-502, P2-107` — P2-205 (language slot, landed in M2.2) added.
- §3.5 AC4 and the P2-505 AC now state the R-6 prompt-from-config base is already landed in M2.1 and the M2.5 delta is the `{language}` call-site wiring (P2-205). This matches the verified code state: `_resolve_prompt(...)` at `processor_impls.py:291/373/416` is called without `language`.

---

## 2. Recommended findings — clarity fixes applied (no implementation-intent change)

| # | Finding | Where |
|---|---------|-------|
| R-a | Preprocess toggle ownership — `intelligence.images.preprocess` (image path) vs `intelligence.ocr.preprocess` (OCR path), one shared module, two toggles (R-3) | §3.5 Configuration Changes |
| R-b | `max_dimensions`/`max_bytes` are the single source of truth for P2-503 dimension/size guards, superseding the module's fixed `MAX_EDGE = 8000` | §3.5 Configuration Changes; §4.5 P2-503 AC |
| R-c | Public API delegation stated: `analyze_image` → `ImageAnalyzer.analyze`, `preprocess_image` → shared `Preprocessor`, `drawio_to_mermaid` → `DiagramParser.parse` (M2.4 C2 precedent) | §3.5 Public APIs |
| R-d | AC4 wording reflects prompt-from-config already green; delta is `{language}` substitution | §3.5 AC4; §4.5 P2-505 AC |

None of R-a…R-d alter scope, interfaces, or execution order; they remove ambiguity only.

---

## 3. Dependency graph validity

Re-checked against the updated spec:

- **§5 edge definitions** — unchanged, still valid: Foundation→all; 2.1→2.5 (P2-104); 2.2→2.5 (P2-205, `{language}` slot); 2.3→2.4/2.5/2.6 (P2-305 hard). The P2-205 edge now matches the P2-505 task row.
- **§4.5 M2.5 task deps** — each resolves to an existing task in the graph:
  - P2-501: (foundation, no dep)
  - P2-502 → P2-501
  - P2-503 → P2-104 (landed M2.1)
  - P2-504 → P2-501
  - P2-505 → **P2-205** (landed M2.2), P2-502, P2-107 (landed M2.1)
  - P2-506 → P2-305 (landed M2.3), P2-503
- **§6.3 blocking tasks** — consistent: P2-104 blocks P2-503; P2-205 blocks P2-505; P2-305 blocks P2-506. All blocking predecessors shipped in M2.1–M2.3; no cycles introduced.
- **Wave schedule (§6.1)** — M2.5 remains wave 5 (last, pure consumer); unaffected.

---

## 4. Acceptance Criteria / Definition of Done internal consistency

- **DoD** (`ImageAnalyzer`, shared `Preprocessor`, `DiagramParser`, prompt config, wiring, tests, lint) aligns with the **Interfaces** block (three classes) and the **Public APIs** block (three delegating functions + `ImageInfo`). R-c makes the class↔function mapping explicit.
- **AC4** now ties directly to **Required Unit Tests** ("prompt templating with `{language}`") and the **P2-505 AC** — the R-6 base vs P2-205 delta split is stated once and referenced consistently.
- **AC2** (preprocessing toggle → different bytes to mocked vision) is consistent with **P2-503 AC** and the R-a/R-b config notes (two toggles, one shared module, config-sourced bounds).
- **P2-506 AC** (trigger = `kind == "pdf"`, shared call site) is consistent with **§3.5 Scope** and **§10 Rollback** (per-feature toggles restore Phase-1 behavior — image PDFs default to the existing passthrough/table path).

No contradictions found between milestones 2.1–2.4 artifacts and the updated M2.5 sections.

---

## 5. Conclusion

- **F-1, F-2 (Required):** resolved.
- **R-a…R-d (Recommended):** applied as clarity fixes; implementation intent preserved.
- Dependency graph: valid, cycle-free, consistent with landed M2.1–M2.4 work.
- AC/DoD: internally consistent.

The Milestone 2.5 Engineering Specification (v1.3) is ready for re-approval.
