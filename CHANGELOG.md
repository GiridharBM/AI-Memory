# Changelog

All notable changes to Personal AI Memory are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.0.0] - Unreleased

V2.0 adds an async generation system on top of the V1.1 foundation: scoped
generation jobs with persisted artifacts and evidence-set provenance, plus
multimodal ingestion and local SDXL image generation.

### Added

- Generation jobs and executor (`GenerationExecutor`): async submit/poll/
  cancel lifecycle with PENDING / PROCESSING / VALIDATING / DONE / FAILED /
  CANCELLED states (`POST /generation`, `GET /jobs`, `POST /jobs/{id}/cancel`).
- Versioned artifacts with inline or traversal-safe file-backed content, plus
  artifact APIs (`GET /artifacts`, versions, provenance, content download).
- Per-chunk evidence-set provenance for every generation (`ProvenanceStore`,
  GUI Library rendering).
- Memory scopes: `all` / `documents` / `topics` / `nodes` (`MemoryScope`,
  `ResolvedScope`); topics/nodes resolve through the knowledge graph and
  unknown scopes fail closed instead of widening to whole-corpus retrieval.
- Flashcards generation (`flashcards` task).
- Multiple-choice quiz generation (`quiz` task, MCQ only).
- Structured Markdown report generation (`report` task).
- PPTX presentation generation (`ppt` task, default theme, speaker notes).
- AI-enriched mind-map generation (`mindmap_enrich` task; derived artifact,
  knowledge graph itself untouched).
- SDXL image generation (`image` task): prompt planning over retrieved
  evidence via the existing structured-output seam, local Diffusers runtime
  (768×768 default; 512 fallback; 1024 opt-in; 20-step standard and 4-step
  Turbo fast mode), PNG artifacts with full generation metadata.
- Image/OCR/vision ingestion (Tesseract + vision-model OCR, EXIF, diagrams).
- Audio transcription and video ingestion.
- GUI Generate page (all generation tasks with scope/config controls,
  progress, cancellation, structured result rendering) and Library/Provenance
  views; generation/artifacts/provenance/mindmap API routes.
- `image_generation` configuration section (`config/default.yaml`):
  pinned SDXL model IDs/revisions, defaults, output byte cap.

### Configuration

- New `image_generation` settings (`ImageGenerationSettings`): standard/fast
  model IDs and pinned revisions, default dimensions/steps, max output bytes.
- New dependencies: `diffusers>=0.35.0`, `accelerate>=1.0.0`, `Pillow>=10.0.0`.
- **CUDA-enabled PyTorch (cu128+) is required for actual SDXL execution**
  (Blackwell GPUs); CPU-only installs fail fast with a clear error instead
  of generating. Install torch separately per
  https://pytorch.org/get-started/locally/.

### Known limitations

- `projects` memory scopes are representable but unsupported (fail closed).
- Topic/node scopes resolve each KG node to its single persisted source.
- SDXL in-image text is weak/unreliable; CPU-only environments cannot generate.
- `video` generation task is declared but has no handler (rejected at submit).
- Reranker, HyDE, and answerability remain implemented but disabled by default.

## [1.1.0]

Reliability, source management, ingestion safety, CLI usability, and truthful
status. Hybrid retrieval + grounded QA with citations, system-facts fast path,
vault notes with manifest ledger, deduplication and safe re-ingestion,
secret-bearing source blocking, bounded QA timeout, watcher/queue services.
Retrieval pipeline intentionally frozen. Tag `v1.1.0` (`e5d9129`).

## [1.0.0]

Initial PAM application layer release. Tag `v1.0.0`.
