"""Tests for AI document processing."""

from __future__ import annotations

from typing import Any

import pytest

from app.application.ai_processor import AIProcessingError, DocumentAIProcessor
from app.domain.analysis import DocumentAnalysis
from app.domain.documents import DocumentMetadata, SourceDocument
from app.infrastructure.llm import OllamaRequest, OllamaResponseError


class FakeOllamaClient:
    """Small fake that mimics the Ollama client JSON API."""

    def __init__(self, responses: list[DocumentAnalysis | Exception]) -> None:
        self.responses = responses
        self.requests: list[OllamaRequest] = []

    def generate_json(
        self,
        request: OllamaRequest,
        *,
        response_model: type[DocumentAnalysis] | None = None,
    ) -> DocumentAnalysis:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_document_ai_processor_returns_validated_analysis() -> None:
    analysis = _analysis()
    processor = DocumentAIProcessor(FakeOllamaClient([analysis]))

    result = processor.process(_document())

    assert result.analysis == analysis
    assert result.attempts == 1


def test_document_ai_processor_retries_malformed_json() -> None:
    analysis = _analysis()
    client = FakeOllamaClient([OllamaResponseError("invalid json"), analysis])
    processor = DocumentAIProcessor(client, validation_retries=1)

    result = processor.process(_document())

    assert result.analysis == analysis
    assert result.attempts == 2
    assert "previous response was not valid JSON" in client.requests[1].prompt


def test_document_ai_processor_fails_after_retry_budget() -> None:
    client = FakeOllamaClient(
        [
            OllamaResponseError("invalid json"),
            OllamaResponseError("schema mismatch"),
        ]
    )
    processor = DocumentAIProcessor(client, validation_retries=1)

    with pytest.raises(AIProcessingError):
        processor.process(_document())


def _document() -> SourceDocument:
    return SourceDocument(
        source="memory.md",
        source_type="markdown",
        filename="memory.md",
        text="# Local Memory\n\nA local AI memory system.",
        metadata=DocumentMetadata(title="Local Memory"),
    )


def _analysis() -> DocumentAnalysis:
    payload: dict[str, Any] = {
        "suggested_note_title": "Local AI Memory",
        "summary": {
            "short": "A local AI memory system.",
            "detailed": "The source describes a local AI memory system for durable notes.",
        },
        "key_concepts": [
            {
                "name": "Local AI memory",
                "explanation": "A local system for building durable personal knowledge.",
                "importance": "high",
            }
        ],
        "definitions": [],
        "important_entities": [],
        "tags": ["Local AI", "#memory"],
        "related_topics": [],
    }
    return DocumentAnalysis.model_validate(payload)
