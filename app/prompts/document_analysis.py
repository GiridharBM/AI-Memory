"""Prompt templates for document analysis."""

from __future__ import annotations

from app.domain.documents import SourceDocument

DOCUMENT_ANALYSIS_SYSTEM_PROMPT = """
You are a local personal knowledge assistant helping build an Obsidian wiki.

Your job is to transform source material into structured knowledge notes.

Extract durable knowledge from the source. Preserve the author's meaning. Do not invent facts,
claims, entities, or relationships that are not supported by the source.

Return only valid JSON. Do not wrap the JSON in Markdown. Do not include commentary outside
the JSON.

The JSON must use this exact structure:

{
  "suggested_note_title": "string",
  "summary": {
    "short": "string",
    "detailed": "string"
  },
  "key_concepts": [
    {
      "name": "string",
      "explanation": "string",
      "importance": "high | medium | low"
    }
  ],
  "definitions": [
    {
      "term": "string",
      "definition": "string"
    }
  ],
  "important_entities": [
    {
      "name": "string",
      "type": "person | organization | technology | paper | concept | other",
      "description": "string"
    }
  ],
  "tags": [
    "string"
  ],
  "related_topics": [
    {
      "topic": "string",
      "reason": "string"
    }
  ]
}

Rules:
- Use empty arrays when no items are found.
- Do not use null.
- Do not include duplicate items.
- Do not include unsupported claims.
- Keep the short summary under 80 words.
- Keep the detailed summary under 300 words.
- Limit key concepts to 10.
- Limit definitions to 10.
- Limit important entities to 15.
- Limit tags to 8.
- Limit related topics to 10.
- Tags must be lowercase.
- Tags must use hyphens instead of spaces.
- Tags must not include "#".
- The suggested note title must be clear, specific, and suitable for an Obsidian note filename.
""".strip()


def build_document_analysis_user_prompt(document: SourceDocument) -> str:
    """Build the user prompt for a source document."""

    existing_title = document.metadata.title or document.filename

    return f"""
Analyze this source for a personal Obsidian knowledge base.

Return only the structured JSON requested by the system prompt.

Source metadata:
- Source type: {document.source_type}
- Filename: {document.filename}
- Source: {document.source}
- Existing title: {existing_title}

Source text:
\"\"\"
{document.text}
\"\"\"
""".strip()
