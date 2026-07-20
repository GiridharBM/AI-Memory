# Milestone 4 Audit — Knowledge Engine

**Date:** 2026-07-20
**Status:** 5/13 features implemented, 8 missing
**Tests:** 205 passing
**Ghost pyc files:** 11 deleted source modules found as compiled bytecode only

---

## Feature Matrix

| # | Feature | Status | Location |
|---|---------|--------|----------|
| 1 | Semantic Chunking | **MISSING** | Ghost pyc only |
| 2 | Embedding Generation | **MISSING** | Config field + ghost pyc |
| 3 | Vector Database Storage | **MISSING** | Ghost pyc only |
| 4 | Duplicate Detection | **DONE** | `app/infrastructure/state/hashing.py`, `manifest.py`, `app/queue/worker.py` |
| 5 | Automatic Wiki Links | **DONE** | `app/templates/obsidian_note.py`, `app/infrastructure/vault/wiki_manager.py` |
| 6 | Automatic Backlinks | **PARTIAL** | LLM-suggested, not written back to other notes |
| 7 | Placeholder Note Creation | **MISSING** | Does not exist |
| 8 | Knowledge Graph | **MISSING** | Ghost pyc only |
| 9 | Entity Extraction | **PARTIAL** | LLM-driven via prompt, no dedicated NER |
| 10 | Relationship Extraction | **PARTIAL** | LLM-driven via prompt, no dedicated RE |
| 11 | Semantic Search | **MISSING** | Ghost pyc only |
| 12 | Hybrid Search | **MISSING** | Ghost pyc only |
| 13 | Version History | **MISSING** | Does not exist |

---

## Detailed Findings

### Duplicate Detection — DONE
- `app/infrastructure/state/hashing.py` (27 lines): SHA-256 streaming hash for `.md`, `.pdf`, `.txt` files
- `app/infrastructure/state/manifest.py` (175 lines): JSON manifest at `data/manifests/processed_files.json`, tracks `contains_hash()`, `contains_path()`, `add_processed_file()`
- `app/queue/worker.py` lines 160-174: worker skips re-processing on duplicate hash
- `tests/unit/test_duplicate_detection.py`: 1 test covering duplicate skip
- **Scope:** file-level dedup only. No content-level or note-level dedup.

### Automatic Wiki Links — DONE
- `app/templates/obsidian_note.py` line 346-349: `_wiki_link(value)` generates `[[escaped_label]]`
- Used for: key concepts, definitions, important entities, related topics, suggested related notes, suggested backlinks
- `app/infrastructure/vault/wiki_manager.py`: index, overview, log pages all use `[[stem|title]]` links; `_with_navigation()` adds nav links to every note
- **Scope:** LLM-generated suggestions only. No code writes reverse links into existing notes.

### Automatic Backlinks — PARTIAL
- `app/prompts/document_analysis.py` lines 58, 129: prompt asks LLM for `suggested_backlinks`
- `app/domain/analysis.py` line 144: `suggested_backlinks: list[str]`
- `app/templates/obsidian_note.py` lines 84-86, 232-235: renders "Suggested Backlinks" section
- **Gap:** No code writes backlinks INTO existing notes. Only generates a section in the current note.

### Entity Extraction — PARTIAL
- `app/prompts/document_analysis.py` lines 43-50: prompt requests `important_entities` with `name`, `type`, `description`
- `app/domain/analysis.py` lines 52-59: `ImportantEntity` model (person, organization, product, project, technology, place, paper, concept, other)
- **No spaCy, NLTK, or dedicated NER library.** Pure LLM extraction.

### Relationship Extraction — PARTIAL
- `app/prompts/document_analysis.py` lines 51-56: prompt requests `related_topics` with `topic`, `reason`
- `app/domain/analysis.py` lines 62-68: `RelatedTopic` model
- **No dedicated RE pipeline.** Pure LLM extraction.

### Semantic Chunking — MISSING
- Ghost pyc: `semantic_chunking.cpython-314.pyc` contained `DocumentChunk`, `SemanticChunker`
- No source, no imports, no tests in committed code
- README roadmap lists under **v3** (future)

### Embedding Generation — MISSING
- Config field: `app/core/config.py` line 197: `embeddings: str = "nomic-embed-text"` — placeholder, never consumed
- Ghost pyc: `embeddings.cpython-314.pyc` contained `EmbeddingResult`, `EmbeddingService`
- No `sentence-transformers`, `openai`, or embedding library in dependencies
- **Note:** User has `nomic-embed-text:latest` installed in Ollama — infrastructure ready, code missing

### Vector Database Storage — MISSING
- Ghost pyc: `vector_store.cpython-314.pyc` contained `VectorEntry`, `SearchResult`, `VectorStore` (in-memory + JSON persistence)
- No chromadb, faiss, qdrant, or any vector DB dependency
- README roadmap lists ChromaDB/FAISS/Qdrant under **v3**

### Knowledge Graph — MISSING
- Ghost pyc (two modules):
  - `app/domain/knowledge_graph.cpython-314.pyc`: `KnowledgeNode`, `KnowledgeEdge`, `KnowledgeGraph`, `GraphBuildResult`
  - `app/infrastructure/knowledge_graph.cpython-314.pyc`: `KnowledgeGraphBuilder`
- Ghost tests: `test_knowledge_graph`, `test_knowledge_engine_m4`, `test_multi_model_knowledge_engine`
- No networkx, neo4j, or graph library in dependencies

### Semantic Search — MISSING
- Ghost pyc: `search.cpython-314.pyc` contained `SearchHit`, `SemanticSearch`, `HybridSearch`
- No search code in committed files

### Hybrid Search — MISSING
- Same ghost pyc as semantic search

### Placeholder Note Creation — MISSING
- No stub/placeholder note creation code anywhere
- README roadmap lists under **v2** (current milestone scope)

### Version History — MISSING
- `app/infrastructure/state/models.py` line 52: `ManifestEntry.version: int = 1` — this is manifest schema version, not note versioning
- No diff tracking, no history system, no git-like version control for notes
- One orphan file in `vault/Versions/` (no code creates it)

---

## Ghost Modules (Deleted Source)

These `.py` files existed locally but were deleted before the latest commit. Their `.pyc` bytecode remains in `__pycache__`:

| Module | Classes |
|--------|---------|
| `app/infrastructure/semantic_chunking` | `DocumentChunk`, `SemanticChunker` |
| `app/infrastructure/embeddings` | `EmbeddingResult`, `EmbeddingService` |
| `app/infrastructure/vector_store` | `VectorEntry`, `SearchResult`, `VectorStore` |
| `app/infrastructure/duplicate_detection` | `DuplicateMatch`, `DuplicateDetector` |
| `app/infrastructure/search` | `SearchHit`, `SemanticSearch`, `HybridSearch` |
| `app/infrastructure/knowledge_graph` | `KnowledgeGraphBuilder` |
| `app/domain/knowledge_graph` | `KnowledgeNode`, `KnowledgeEdge`, `KnowledgeGraph`, `GraphBuildResult` |
| `app/infrastructure/content_intelligence` | `ContentIntelligenceResult`, `ContentIntelligenceBuilder` |
| `app/infrastructure/study_features` | `StudyQuestion`, `StudyPack`, `StudyFeatureBuilder` |
| `app/infrastructure/language_detection` | (shared language detection utilities) |
| `app/infrastructure/ocr_engine` | `OCRResult`, `HybridOCR` |

---

## What Works End-to-End

1. File ingested → SHA-256 hash checked → skip if duplicate
2. File classified by `DocumentClassifier` → routed to processor
3. Routed processor extracts text (OCR/vision/whisper/text)
4. `DocumentAIProcessor` sends text to LLM → gets `DocumentAnalysis`
5. `ObsidianMarkdownGenerator` renders note with:
   - Table of Contents (dynamic, Obsidian `[[#anchor]]` links)
   - Keywords, Categories, Reading Time, Difficulty
   - Key Concepts, Definitions, Important Entities (all `[[wiki linked]]`)
   - Related Topics (`[[wiki linked]]`)
   - Suggested Related Notes, Suggested Backlinks (`[[wiki linked]]`)
   - Questions & Answers, Flashcards, MCQs, Short/Long Answer, Revision Notes
   - Tags, References
6. WikiManager writes note to vault, maintains index/overview/log pages with `[[wiki links]]`

---

## Gaps Summary

| Gap | Impact |
|-----|--------|
| No embeddings | Cannot do semantic search, no vector storage |
| No vector store | Cannot persist or query embeddings |
| No semantic chunking | Documents processed as single blobs, no retrieval |
| No knowledge graph | No entity/relationship graph, no graph queries |
| No placeholder notes | Unlinked references silently fail |
| No backlink writing | Backlinks are suggestions only, not bidirectional |
| No version history | No audit trail for note changes |
| No semantic/hybrid search | Only file-level duplicate check exists |

---

## Recommendation

Milestone 4 scope is significantly larger than what exists. The ghost modules indicate prior prototyping that was rolled back (likely during the Ponytail cleanup). Before implementing, decide:

1. **Embeddings + Vector Store + Semantic Search** — these are tightly coupled; implement together
2. **Knowledge Graph** — depends on entity extraction; currently LLM-only, may want dedicated NER
3. **Placeholder Notes + Backlink Writing** — depends on knowing which notes exist; needs vault scanning
4. **Version History** — independent, can be done anytime
