# Architecture

This document describes the architecture of the Personal AI Memory System.

## Architectural Goals

The system is designed to be:

- Local-first
- File-based
- Obsidian-compatible
- Incremental
- Testable
- Extensible

Version 1 avoids vector databases, RAG, graph databases, and a web UI. The focus is a reliable document-to-wiki pipeline.

## End-To-End Workflow

```text
Input
  -> Read document
  -> Clean text
  -> Send to Ollama
  -> Receive structured JSON
  -> Validate JSON
  -> Generate Markdown
  -> Update wiki files
  -> Save into Obsidian vault
```

The workflow is implemented in:

```text
app/pipelines/ingest_workflow.py
```

## Layers

### CLI

Location:

```text
app/cli/
```

Responsibilities:

- Expose user commands
- Render Rich terminal output
- Load configuration
- Trigger the ingestion workflow
- Show status and health checks

### Core

Location:

```text
app/core/
```

Responsibilities:

- YAML configuration
- Environment variable overrides
- Logging setup
- Shared technical foundations

### Domain

Location:

```text
app/domain/
```

Responsibilities:

- Source document models
- AI analysis models
- Generated note models
- Typed contracts shared across layers

Domain objects are intentionally independent of storage and transport details.

### Infrastructure

Location:

```text
app/infrastructure/
```

Responsibilities:

- File ingestion
- GitHub README ingestion
- YouTube transcript ingestion
- Ollama client integration
- Obsidian vault writing
- Wiki management

Infrastructure modules hide external libraries and filesystem behavior from the rest of the system.

### Application

Location:

```text
app/application/
```

Responsibilities:

- Coordinate domain operations
- Send source documents to Ollama
- Validate structured AI responses
- Retry malformed model responses

### Pipelines

Location:

```text
app/pipelines/
```

Responsibilities:

- Connect ingestion, AI processing, Markdown generation, and vault writing
- Provide one reusable end-to-end workflow for the CLI and tests

### Prompts

Location:

```text
app/prompts/
```

Responsibilities:

- Store system prompts
- Build document-specific user prompts
- Keep prompt text separate from application logic

### Templates

Location:

```text
app/templates/
```

Responsibilities:

- Generate Obsidian-compatible Markdown
- Format YAML frontmatter
- Render wiki links, tags, references, and sections

## Main Data Objects

### SourceDocument

Represents clean ingested source content.

Key fields:

- `source`
- `source_path`
- `source_type`
- `filename`
- `text`
- `metadata`

### DocumentAnalysis

Represents validated model output.

Key fields:

- `suggested_note_title`
- `summary`
- `key_concepts`
- `definitions`
- `important_entities`
- `tags`
- `related_topics`

### ObsidianNote

Represents a generated note ready for vault persistence.

Key fields:

- `title`
- `filename`
- `markdown`
- `generated_at`
- `tags`
- `source`
- `source_type`

## Ingestion Architecture

All ingestors implement the same base contract.

Current ingestors:

- PDF
- Markdown
- TXT
- GitHub README
- YouTube transcript

The ingestion service chooses the correct adapter and returns a normalized `SourceDocument`.

Adding a new source type requires:

1. Implementing a new ingestor.
2. Registering it with `DocumentIngestionService`.
3. Adding focused tests.

## AI Processing Architecture

AI processing lives behind:

```text
app/application/ai_processor.py
```

The processor:

- Builds prompts
- Sends the document to Ollama
- Requests JSON output
- Validates the response with Pydantic
- Retries malformed or schema-invalid responses
- Returns a typed `DocumentAnalysis`

The rest of the app does not call Ollama directly.

## Vault Architecture

Vault writing is handled by:

```text
app/infrastructure/vault/
```

The vault manager:

- Creates missing folders
- Writes generated notes
- Prevents filename conflicts
- Avoids duplicate notes by matching `source`
- Maintains `index.md`
- Maintains `overview.md`
- Appends to `log.md`
- Preserves user-written content

Generated content is wrapped in managed markers:

```markdown
<!-- PAM:BEGIN MANAGED -->
Generated content
<!-- PAM:END MANAGED -->
```

Only this managed block is replaced during updates.

## Configuration Architecture

Configuration is layered:

```text
config/default.yaml
config/<environment>.yaml
PAM_* environment variables
```

Configuration is validated with typed settings models before the application runs.

## Logging Architecture

Logging supports:

- Rich console output
- Rotating file logs
- JSON file logs
- Development mode
- Production mode

All major operations log their start, result, and failures.

## Testing Architecture

The test suite uses pytest.

External model behavior is mocked so tests are deterministic.

Coverage includes:

- Unit tests for each major module
- Integration tests for the complete workflow
- CLI tests with Typer's test runner

## Extensibility

Future features can be added through existing boundaries:

- New source types: add ingestion adapters.
- New model providers: replace or extend the LLM client.
- New note formats: add templates.
- New storage behavior: extend the vault writer or state layer.
- RAG or search: add indexing and retrieval without changing ingestion.
- Graph features: derive relationships from Obsidian links and generated metadata.
