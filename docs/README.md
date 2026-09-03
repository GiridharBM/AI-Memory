# LLM-Wiki (Personal AI Memory) — Documentation

This directory is the consolidated documentation for **LLM-Wiki / Personal AI Memory (PAM)** — a local-first, offline AI system that turns documents, code, audio, images, and web content into a connected Obsidian knowledge base with semantic and hybrid search.

**Current published release:** ✅ **V1.1.0** is the current release. Earlier V1.0.0 status records are preserved below but should not be interpreted as the current system state.

---

## Documentation structure

- [`phases/`](./phases/) — historical phase engineering records (numbered `NN_*.md`), including investigation, experiment, audit, and sign-off reports. Preserved for provenance; they reflect the state of the project when each phase was written, not the current release.
- [`releases/`](./releases/) — release / sign-off / provenance records (e.g. `PLAN.md`, `VERSION_1_COMPLETE_FINAL_REPORT.md`, `POST_V1_VERIFICATION.md`).
- Top-level files below — current canonical architecture / development / testing documentation.

> **Note:** Historical phase and release reports are preserved for provenance. They record intermediate state and SHAs and should not be read as describing the current V1.1.0 system. See the root `README.md` and the current canonical docs in this directory for current state.

---

## Navigate the documentation

**START HERE**
- [Project `README.md`](../README.md) — entry point: what PAM is, install, quick start
- [Getting Started](./GETTING_STARTED.md) — set up PAM from zero
- [How to Use](./HOW_TO_USE.md) — command-by-command usage

**UNDERSTAND THE SYSTEM**
- [Architecture](./architecture.md) — system architecture with Mermaid diagrams
- [Implementation Guide](./IMPLEMENTATION_GUIDE.md) — how PAM is implemented
- [Project Status](./PROJECT_STATUS.md) — canonical current-state document

**FOR FACULTY / EVALUATORS**
- [Faculty Presentation Guide](./FACULTY_PRESENTATION_GUIDE.md) — how to explain the project
- [Final Project Report](./FINAL_PROJECT_REPORT.md) — end-to-end overview
- [Testing & Verification](./TESTING_AND_VERIFICATION.md) — how it was verified

**FOR DEVELOPERS**
- [Implementation Guide](./IMPLEMENTATION_GUIDE.md)
- [Implementation History](./IMPLEMENTATION_HISTORY.md)
- [Development Roadmap](./DEVELOPMENT_ROADMAP.md)
- [Implementation Specification](./IMPLEMENTATION_SPECIFICATION.md)

**EVALUATION**
- [Evaluation dataset contract tests](./TESTING_AND_VERIFICATION.md) (`test_eval_dataset.py`, 32 passed)
- Evaluation tooling: `eval/scripts/run_eval.py`, `eval/scripts/ground_truth_audit.py`
- Historical experiment reports: `docs/archive/`, `docs/phases/`

**RELEASES**
- [Release Notes](./RELEASE_NOTES.md)
- Release records: `docs/releases/`

**HISTORICAL**
- `docs/phases/` — numbered phase engineering records
- `docs/archive/` — consolidated historical files
- `docs/releases/` — release/sign-off provenance (e.g. `POST_V1_VERIFICATION.md`)

---

## Documentation index

| Document | What it is | Start here if you want to… |
|----------|------------|----------------------------|
| [**PROJECT_STATUS.md**](./PROJECT_STATUS.md) | **Current canonical status** — V1.1.0 release, production configuration & limitations, testing snapshot, next work | Know the real state of the project today |
| [**GETTING_STARTED.md**](./GETTING_STARTED.md) | Set up PAM from zero (prerequisites → install → run → first ingest) | Get PAM running for the first time |
| [**HOW_TO_USE.md**](./HOW_TO_USE.md) | Practical command-by-command usage guide | Use `pam` day to day |
| [**FINAL_PROJECT_REPORT.md**](./FINAL_PROJECT_REPORT.md) | One clean end-to-end report of the whole project | Understand the project in 10 minutes |
| [**architecture.md**](./architecture.md) | Authoritative system architecture (with Mermaid diagrams) | Understand how the system is built |
| [**IMPLEMENTATION_GUIDE.md**](./IMPLEMENTATION_GUIDE.md) | How PAM is implemented, layer by layer | Understand the codebase / contribute |
| [**IMPLEMENTATION_SPECIFICATION.md**](./IMPLEMENTATION_SPECIFICATION.md) | Technical contracts and data schemas | Build on or modify the pipeline |
| [**DEVELOPMENT_ROADMAP.md**](./DEVELOPMENT_ROADMAP.md) | What was delivered vs. what was deferred | Know what exists and what doesn't |
| [**IMPLEMENTATION_HISTORY.md**](./IMPLEMENTATION_HISTORY.md) | Chronological phase/milestone history | Trace how the project evolved |
| [**TESTING_AND_VERIFICATION.md**](./TESTING_AND_VERIFICATION.md) | Test results, coverage, verification evidence | See how it was verified |
| [**KNOWN_LIMITATIONS.md**](./KNOWN_LIMITATIONS.md) | Verified limitations, mitigations, future directions | Understand honest limits |
| [**RELEASE_NOTES.md**](./RELEASE_NOTES.md) | Version-by-version release history | See what changed in each release |
| [**DOCUMENTATION_GUIDE.md**](./DOCUMENTATION_GUIDE.md) | What documentation exists, why, and what an academic project needs | Navigate/audit the documentation set |
| [**FACULTY_PRESENTATION_GUIDE.md**](./FACULTY_PRESENTATION_GUIDE.md) | How to explain PAM to faculty (30s/2min/5min) | Prepare a project presentation |
| [**README.md**](./README.md) | This file | Navigate the documentation |

## Authoritative reference documents (kept in full)

| Document | Why it is kept |
|----------|----------------|
| [**MASTER_ENGINEERING_DESIGN_DOCUMENT.md**](./MASTER_ENGINEERING_DESIGN_DOCUMENT.md) | The master engineering design document (MEDD): full architecture, module specifications, gap analysis, technical debt, roadmap, risk register, and v1.0 checklist. Too detailed and authoritative to compress. |
| [**01_Current_Implementation_Report.md**](./01_Current_Implementation_Report.md) | Current implementation report: what is implemented vs. deferred, module inventory, and stated limitations. |
| [**PHASE_6_FINAL_APPROVAL.md**](./PHASE_6_FINAL_APPROVAL.md) | The authoritative completion evidence: acceptance gates, negative checklist, and the **APPROVED / PROJECT COMPLETE** verdict. |

## Historical documentation

All phase-, milestone-, engineering-review-, remediation-, and synchronization-related files that were consolidated are preserved in **[`docs/archive/`](./archive/)** for traceability. If you need to look up an individual task review (e.g. `P2-405`), release note, or milestone approval, the original file is there.

## Repository quick map

```
app/            Application source (cli, core, domain, infrastructure, pipelines,
                prompts, queue, templates, watcher)
config/         YAML configuration (default / development / production)
docs/           This documentation
tests/          Unit (~71 files) and integration (18 files) tests
vault/          Generated Obsidian vault
README.md       Project-level README (usage, install, CLI)
requirements.txt / pyproject.toml
```

## Quick facts

- **Version:** V1.1.0 (current release; see `PROJECT_STATUS.md` for the canonical status — V1.1 focus is reliability, source management, ingestion safety, CLI usability, truthful status, local-first)
- **Runtime:** Python 3.11–3.13 (validated in CI), Ollama, local-first
- **Suite:** 1688 unit tests passed / 1 deselected (integration-marker) / 1 known logging-isolation flake (`test_cli_remove.py`, passes in isolation); evaluation dataset-contract tests (`test_eval_dataset.py`) pass (32)
- **Search:** hybrid (dense cosine + BM25) fused with RRF (k=60), via `pam search`
- **Ask:** RAG question answering with `[SOURCE N]` citations, via `pam ask`
- **Completion evidence:** `PROJECT_STATUS.md` (current state) + `PHASE_6_FINAL_APPROVAL.md` (Phase-6 record)
