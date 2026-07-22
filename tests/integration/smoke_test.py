"""Quick pipeline smoke test."""
from app.infrastructure.llm import OllamaClient
from app.core.config import OllamaSettings
from app.domain.analysis import DocumentAnalysis
from app.infrastructure.llm.ollama_client import OllamaRequest
from app.prompts.document_analysis import DOCUMENT_ANALYSIS_SYSTEM_PROMPT
from app.domain.documents import DocumentMetadata, SourceDocument
from app.templates.obsidian_note import ObsidianMarkdownGenerator
from pathlib import Path

settings = OllamaSettings(timeout_seconds=300)
client = OllamaClient(settings)

doc = SourceDocument(
    source="test.py",
    source_path=Path("test.py"),
    source_type="code",
    filename="test.py",
    text="def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)\n\n# Classic recursive fibonacci implementation",
    metadata=DocumentMetadata(title="Fibonacci"),
)

prompt = f"""Analyze this source for a personal Obsidian knowledge base.
Return only the structured JSON requested by the system prompt.

Source metadata:
- Source type: {doc.source_type}
- Filename: {doc.filename}
- Existing title: {doc.metadata.title}

Source text:
\"\"\"
{doc.text}
\"\"\"
"""

request = OllamaRequest(
    system_prompt=DOCUMENT_ANALYSIS_SYSTEM_PROMPT,
    prompt=prompt,
    model="llama3.1:8b",
)

print("Generating analysis...")
response = client.generate_json(request, response_model=DocumentAnalysis)
analysis = response
print(f"Title: {analysis.suggested_note_title}")
print(f"Short summary: {analysis.summary.short[:100]}")
print(f"Keywords: {analysis.keywords[:5]}")
print(f"Tags: {analysis.tags[:5]}")
print(f"Difficulty: {analysis.difficulty}")
print(f"Reading time: {analysis.reading_time_minutes} min")
print(f"Key concepts: {len(analysis.key_concepts)}")
print(f"Definitions: {len(analysis.definitions)}")
print(f"FAQ: {len(analysis.questions_and_answers)}")
print(f"Flashcards: {len(analysis.flashcards)}")
print(f"MCQs: {len(analysis.multiple_choice_questions)}")
print(f"Short answer: {len(analysis.short_answer_questions)}")
print(f"Long answer: {len(analysis.long_answer_questions)}")
print(f"Revision notes: {len(analysis.revision_notes)}")
print(f"Related notes: {len(analysis.suggested_related_notes)}")
print(f"Backlinks: {len(analysis.suggested_backlinks)}")

gen = ObsidianMarkdownGenerator()
note = gen.generate(document=doc, analysis=analysis, processing_confidence=0.92)
print(f"\nNote filename: {note.filename}")
print(f"Note size: {len(note.markdown)} chars")

# Check all sections present
required = [
    "## Summary", "## Table of Contents", "## Reading Time", "## Difficulty Level",
    "## Keywords", "## Categories", "## Key Concepts", "## Definitions",
    "## Important Entities", "## Related Topics", "## Suggested Related Notes",
    "## Suggested Backlinks", "## Frequently Asked Questions", "## Flashcards",
    "## Multiple Choice Questions", "## Short Answer Questions", "## Long Answer Questions",
    "## Revision Notes", "## Tags", "## Metadata", "## References",
]
found = [s for s in required if s in note.markdown]
missing = [s for s in required if s not in note.markdown]
print(f"\nSections: {len(found)}/{len(required)}")
if missing:
    print(f"Missing: {missing}")

# Save sample note
Path("tests/integration/sample_note.md").write_text(note.markdown, encoding="utf-8")
print("Saved sample_note.md")
