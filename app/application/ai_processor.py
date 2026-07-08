"""AI processing use case for source documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.logging import get_logger
from app.domain.analysis import DocumentAnalysis
from app.domain.documents import SourceDocument
from app.infrastructure.llm import OllamaRequest, OllamaResponseError
from app.prompts.document_analysis import (
    DOCUMENT_ANALYSIS_SYSTEM_PROMPT,
    build_document_analysis_user_prompt,
)

logger = get_logger(__name__)


class AIProcessingError(RuntimeError):
    """Raised when document analysis cannot be produced."""


class JsonGeneratingClient(Protocol):
    """Protocol for clients that can return validated JSON model output."""

    def generate_json(
        self,
        request: OllamaRequest,
        *,
        response_model: type[DocumentAnalysis] | None = None,
    ) -> object:
        """Generate a structured analysis object from a model request."""


@dataclass(slots=True)
class AIProcessingResult:
    """Successful AI processing result."""

    document: SourceDocument
    analysis: DocumentAnalysis
    attempts: int


class DocumentAIProcessor:
    """Send source documents to Ollama and return validated Python objects."""

    def __init__(
        self,
        ollama_client: JsonGeneratingClient,
        *,
        validation_retries: int = 2,
    ) -> None:
        self._ollama_client = ollama_client
        self._validation_retries = validation_retries

    def process(self, document: SourceDocument) -> AIProcessingResult:
        """Analyze a source document with Ollama and validate the JSON response."""

        max_attempts = self._validation_retries + 1
        last_error: OllamaResponseError | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                analysis = self._request_analysis(document, attempt=attempt)
                logger.info(
                    "AI document analysis completed.",
                    extra={
                        "source": document.source,
                        "source_type": document.source_type,
                        "attempt": attempt,
                    },
                )
                return AIProcessingResult(document=document, analysis=analysis, attempts=attempt)
            except OllamaResponseError as exc:
                last_error = exc
                logger.warning(
                    "AI document analysis returned malformed or invalid JSON.",
                    extra={
                        "source": document.source,
                        "source_type": document.source_type,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "reason": str(exc),
                    },
                )

        raise AIProcessingError(
            f"Unable to produce valid document analysis after {max_attempts} attempts."
        ) from last_error

    def _request_analysis(self, document: SourceDocument, *, attempt: int) -> DocumentAnalysis:
        prompt = build_document_analysis_user_prompt(document)
        if attempt > 1:
            prompt = _add_retry_instruction(prompt)

        request = OllamaRequest(
            system_prompt=DOCUMENT_ANALYSIS_SYSTEM_PROMPT,
            prompt=prompt,
        )
        response = self._ollama_client.generate_json(request, response_model=DocumentAnalysis)

        if not isinstance(response, DocumentAnalysis):
            raise AIProcessingError("Ollama client returned an unexpected response type.")

        return response


def _add_retry_instruction(prompt: str) -> str:
    return (
        f"{prompt}\n\n"
        "The previous response was not valid JSON for the required schema. "
        "Return only corrected JSON with all required fields."
    )
