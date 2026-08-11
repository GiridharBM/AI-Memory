"""RAG question-answering use case over the knowledge base."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.core.config import Settings
from app.core.logging import get_logger
from app.infrastructure.llm import OllamaClient, OllamaClientError, OllamaRequest
from app.infrastructure.search import SearchHit, SearchService
from app.prompts.qa import QA_SYSTEM_PROMPT, build_qa_user_prompt

logger = get_logger(__name__)

MAX_CONTEXT_CHUNKS = 8
MAX_CONTEXT_CHARS = 12_000


class QAError(RuntimeError):
    """Raised when the QA workflow cannot produce an answer."""


@dataclass(slots=True)
class QAAnswer:
    """A generated answer together with the retrieved sources it is grounded on."""

    answer: str
    sources: list[SearchHit] = field(default_factory=list)
    model: str = ""


def build_context(hits: Sequence[SearchHit]) -> str:
    """Build a bounded, deterministic context block from ranked hits.

    Chunks are bounded by ``MAX_CONTEXT_CHUNKS`` and a total character budget
    so excessive retrieval results cannot create an uncontrolled prompt.
    """

    blocks: list[str] = []
    used = 0
    for index, hit in enumerate(hits[:MAX_CONTEXT_CHUNKS], start=1):
        remaining = MAX_CONTEXT_CHARS - used
        if remaining <= 0:
            break
        text = " ".join(hit.text.split())
        if len(text) > remaining:
            text = text[:remaining]

        section = hit.metadata.get("heading") or hit.metadata.get("parent_heading")
        block = f"[SOURCE {index}]\nSource: {hit.source}\n"
        if section:
            block += f"Section: {section}\n"
        block += f"Score: {hit.score:.4f}\nContent:\n{text}"

        blocks.append(block)
        used += len(text)
    return "\n\n".join(blocks)


class QAWorkflow:
    """Answer a question grounded in retrieved knowledge base context.

    Retrieval goes through the existing ``SearchService`` hybrid pipeline;
    generation goes through the existing ``OllamaClient``. Neither the vector
    store nor the retrieved documents are ever modified.
    """

    def __init__(
        self,
        search_service: SearchService,
        ollama_client: OllamaClient,
        *,
        model: str | None = None,
    ) -> None:
        self._search_service = search_service
        self._ollama_client = ollama_client
        self._model = model

    @classmethod
    def create_default(cls, settings: Settings, *, model: str | None = None) -> QAWorkflow:
        """Build the production workflow from application settings."""

        search_service = SearchService.create_default(settings)
        ollama_client = OllamaClient(settings.ollama)
        return cls(search_service, ollama_client, model=model)

    def ask(
        self,
        question: str,
        *,
        top_k: int = 5,
        min_score: float = 0.0,
        filter: dict[str, object] | None = None,
    ) -> QAAnswer:
        """Answer ``question`` using the top retrieved sources."""

        question = question.strip() if question else ""
        if not question:
            raise QAError("Question must not be empty.")

        hits = self._search_service.search(
            question, top_k=top_k, min_score=min_score, filter=filter,
        )
        logger.info(
            "QA retrieval completed.",
            extra={"question": question, "hits": len(hits), "top_k": top_k},
        )

        context = build_context(hits)
        prompt = build_qa_user_prompt(question, context)
        try:
            response = self._ollama_client.generate_text(
                OllamaRequest(
                    system_prompt=QA_SYSTEM_PROMPT,
                    prompt=prompt,
                    model=self._model,
                )
            )
        except OllamaClientError as exc:
            logger.warning("QA generation failed: Ollama unavailable or errored.", exc_info=True)
            raise QAError(
                "Unable to generate an answer because the Ollama server is "
                "unavailable or returned an error."
            ) from exc

        return QAAnswer(answer=response.response, sources=list(hits), model=response.model)
