# Documentation Guide

What documentation exists, why, how to keep it consistent, and what an **academic project** like PAM needs. This is the map for navigating and auditing the documentation set — and the checklist evaluators rely on.

## Documentation map

For navigation entry points, see the **docs hub**: [`docs/README.md`](./README.md).

**Canonical / current-state docs (read these first):**
- [`PROJECT_STATUS.md`](./PROJECT_STATUS.md) — canonical current state (release, production config, testing snapshot, next work).
- [`architecture.md`](./architecture.md) — system architecture with Mermaid diagrams.
- [`TESTING_AND_VERIFICATION.md`](./TESTING_AND_VERIFICATION.md) — test results and verification evidence.

**User-facing:**
- [`GETTING_STARTED.md`](./GETTING_STARTED.md) — set up from zero.
- [`HOW_TO_USE.md`](./HOW_TO_USE.md) — command-by-command usage.
- Root [`README.md`](../README.md) — project overview / entry point.

**Developer-facing:**
- [`IMPLEMENTATION_GUIDE.md`](./IMPLEMENTATION_GUIDE.md) — the codebase, layer by layer.
- [`IMPLEMENTATION_HISTORY.md`](./IMPLEMENTATION_HISTORY.md) — chronological build record.
- [`DEVELOPMENT_ROADMAP.md`](./DEVELOPMENT_ROADMAP.md) — delivered vs. deferred.
- [`IMPLEMENTATION_SPECIFICATION.md`](./IMPLEMENTATION_SPECIFICATION.md) — technical contracts and schemas.

**Assessment / faculty-facing:**
- [`FACULTY_PRESENTATION_GUIDE.md`](./FACULTY_PRESENTATION_GUIDE.md) — how to explain the project.
- [`FINAL_PROJECT_REPORT.md`](./FINAL_PROJECT_REPORT.md) — end-to-end overview.
- [`KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md) — honest limits.

**Release / history:**
- [`RELEASE_NOTES.md`](./RELEASE_NOTES.md) — version-by-version history.

**Historical / provenance (do NOT rewrite):**
- `docs/phases/` — numbered phase engineering records.
- `docs/archive/` — consolidated historical files.
- `docs/releases/` — release / sign-off records (e.g. `POST_V1_VERIFICATION.md`).
- `docs/01_Current_Implementation_Report.md` — preserved as-is.

## Documentation rules

1. **Version accuracy** — the current release is **V1.1.0**. Never describe it as V1.0.0 or claim the `~1703 passed / 57 deselected` (stale) numbers; use the current snapshot in [`TESTING_AND_VERIFICATION.md`](./TESTING_AND_VERIFICATION.md).
2. **Production vs. experimental** — never present disabled research features (reranking, HyDE, answerability, banded verification) as production capabilities.
3. **Don't invent capabilities** — only claim what the source proves (see the ingestion-status discipline and [`KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md)). Library existence ≠ product support.
4. **Real CLI syntax** — use the actual commands verified from `app/cli/entry.py` (see [`HOW_TO_USE.md`](./HOW_TO_USE.md)).
5. **Cross-link** — docs link to each other and to the hub instead of duplicating content.
6. **Preserve history** — keep historical phase/release reports as historical; don't rewrite them to look current. The current release docs are the canonical source.
7. **Mermaid** — use `flowchart` (preferred `TD`) for diagrams, as in `architecture.md`.

## Academic Documentation Checklist

An academic-project documentation set should cover all of the following. PAM's set is mapped to each item.

- **Overview / abstract** — root [`README.md`](../README.md), [`FINAL_PROJECT_REPORT.md`](./FINAL_PROJECT_REPORT.md).
- **Problem statement & motivation** — [`FINAL_PROJECT_REPORT.md`](./FINAL_PROJECT_REPORT.md).
- **Architecture** — [`architecture.md`](./architecture.md) (with Mermaid diagrams).
- **Implementation details** — [`IMPLEMENTATION_GUIDE.md`](./IMPLEMENTATION_GUIDE.md), [`IMPLEMENTATION_SPECIFICATION.md`](./IMPLEMENTATION_SPECIFICATION.md).
- **Design decisions / rationale** — ADRs and archived phase records (`docs/archive/`, `docs/phases/`).
- **Methodology / how it was built** — [`IMPLEMENTATION_HISTORY.md`](./IMPLEMENTATION_HISTORY.md).
- **Results & evaluation** — [`TESTING_AND_VERIFICATION.md`](./TESTING_AND_VERIFICATION.md), evaluation reports, [`PROJECT_STATUS.md`](./PROJECT_STATUS.md).
- **Limitations & honest assessment** — [`KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md).
- **Future work** — [`DEVELOPMENT_ROADMAP.md`](./DEVELOPMENT_ROADMAP.md).
- **How to run / reproduce** — [`GETTING_STARTED.md`](./GETTING_STARTED.md), [`HOW_TO_USE.md`](./HOW_TO_USE.md).
- **Release history** — [`RELEASE_NOTES.md`](./RELEASE_NOTES.md).
- **Versioned / dated records** — release notes and archived reports carry dates and version tags.
- **Provenance & traceability** — git tags (v1.0.0, v1.1.0, v2.0.0) and the archived engineering records.

If your evaluator asks "is the documentation complete and accurate for an academic project?", walk them through this checklist and cross-link each item from the docs hub.
