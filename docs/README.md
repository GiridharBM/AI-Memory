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

## Documentation index

| Document | What it is | Start here if you want to… |
|----------|------------|----------------------------|
| [**PROJECT_STATUS.md**](./PROJECT_STATUS.md) | **Current canonical status** — V1.1.0 release, production configuration & limitations, testing snapshot, next work | Know the real state of the project today |
| [**FINAL_PROJECT_REPORT.md**](./FINAL_PROJECT_REPORT.md) | One clean end-to-end report of the whole project | Understand the project in 10 minutes |
| [**architecture.md**](./architecture.md) | Authoritative system architecture | Understand how the system is built |
| [**IMPLEMENTATION_SPECIFICATION.md**](./IMPLEMENTATION_SPECIFICATION.md) | Technical contracts and data schemas | Build on or modify the pipeline |
| [**DEVELOPMENT_ROADMAP.md**](./DEVELOPMENT_ROADMAP.md) | What was delivered vs. what was deferred | Know what exists and what doesn't |
| [**IMPLEMENTATION_HISTORY.md**](./IMPLEMENTATION_HISTORY.md) | Chronological phase/milestone history | Trace how the project evolved |
| [**TESTING_AND_VERIFICATION.md**](./TESTING_AND_VERIFICATION.md) | Test results, coverage, verification evidence | See how it was verified |
| [**RELEASE_NOTES.md**](./RELEASE_NOTES.md) | Version-by-version release history | See what changed in each release |
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
tests/          Unit (56 files) and integration (16 files) tests
vault/          Generated Obsidian vault
README.md       Project-level README (usage, install, CLI)
requirements.txt / pyproject.toml
```

## Quick facts

- **Version:** V1.1.0 (current release; see `PROJECT_STATUS.md` for the canonical status — V1.1 focus is reliability, source management, ingestion safety, CLI usability, truthful status, local-first)
- **Runtime:** Python 3.11–3.13 (validated in CI), Ollama, local-first
- **Suite:** 1375 tests passing / 57 deselected / 0 failed; coverage **89.80%** (floor 80); 56 unit + 16 integration files
- **Search:** hybrid (dense cosine + BM25) fused with RRF (k=60), via `pam search`
- **Ask:** RAG question answering with `[SOURCE N]` citations, via `pam ask`
- **Completion evidence:** `PROJECT_STATUS.md` (current state) + `PHASE_6_FINAL_APPROVAL.md` (Phase-6 record)
