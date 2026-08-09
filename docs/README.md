# LLM-Wiki (Personal AI Memory) — Documentation

This directory is the consolidated documentation for **LLM-Wiki / Personal AI Memory (PAM)** — a local-first, offline AI system that turns documents, code, audio, images, and web content into a connected Obsidian knowledge base with semantic and hybrid search.

**Project status:** ✅ **COMPLETE** — v0.12.0, approved at Phase 6 (`PHASE_6_FINAL_APPROVAL.md`). No further phases are planned.

---

## Documentation index

| Document | What it is | Start here if you want to… |
|----------|------------|----------------------------|
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
tests/          Unit (56 files) and integration (18 files) tests
vault/          Generated Obsidian vault
README.md       Project-level README (usage, install, CLI)
requirements.txt / pyproject.toml
```

## Quick facts

- **Version:** 0.12.0 (pre-1.0, maturity ≈ 80%)
- **Runtime:** Python 3.11+ (tested on 3.14), Ollama, local-first
- **Final suite:** 1359 tests passing (coverage 90.04% was measured at the Phase 6 gate — not re-measured after cleanup)
- **Search:** hybrid (dense cosine + BM25) fused with RRF (k=60), via `pam search`
- **Completion evidence:** `PHASE_6_FINAL_APPROVAL.md`
