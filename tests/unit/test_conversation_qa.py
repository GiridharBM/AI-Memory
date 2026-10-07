"""QA history-seam tests: byte-identical default path plus fused history."""

from __future__ import annotations

from typing import Any

from app.application.qa_workflow import (
    OUTCOME_ABSTAINED,
    OUTCOME_ANSWERED,
    QAWorkflow,
)
from app.domain.conversation import Message, MessageRole
from app.infrastructure.llm import OllamaTextResponse
from app.infrastructure.search import SearchHit
from app.prompts.qa import build_history_block, build_qa_user_prompt


def _message(role: MessageRole, content: str) -> Message:
    return Message.create("conv-1", role, content, 1)


class StubSearchService:
    """Recorded search returning scripted hits."""

    def __init__(self, hits: list[SearchHit] | None = None) -> None:
        self._hits = hits or []
        self.calls = 0

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filter: dict[str, object] | None = None,  # noqa: A002 - mirrors service signature
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        self.calls += 1
        return list(self._hits)


class RecordingOllamaClient:
    """Record prompts; answer from scripted text (never called when abstaining)."""

    def __init__(self, answer: str = "response text") -> None:
        self._answer = answer
        self.prompts: list[str] = []
        self.calls = 0

    def generate_text(self, request: Any) -> OllamaTextResponse:
        self.calls += 1
        self.prompts.append(request.prompt)
        return OllamaTextResponse(model="qwen3:8b", response=self._answer)


def _hit(source: str = "a.md") -> SearchHit:
    return SearchHit(
        text="evidence body",
        source=source,
        score=0.9,
        cosine_score=0.9,
        entry_id=f"{source}::0",
    )


def _workflow(answer: str = "response text") -> tuple[QAWorkflow, RecordingOllamaClient]:
    client = RecordingOllamaClient(answer)
    workflow = QAWorkflow(StubSearchService([_hit()]), client)  # type: ignore[arg-type]
    return workflow, client


def test_prompt_without_history_is_byte_identical() -> None:
    expected = "Question: what?\n\nRetrieved context:\n[SOURCE 1]\nbody"

    assert build_qa_user_prompt("what?", "[SOURCE 1]\nbody") == expected
    assert build_qa_user_prompt("what?", "[SOURCE 1]\nbody", history="") == expected
    assert build_qa_user_prompt("what?", "[SOURCE 1]\nbody", history="  ") == expected


def test_prompt_with_history_delimits_sections() -> None:
    block = build_history_block(
        [
            _message(MessageRole.USER, "first question"),
            _message(MessageRole.ASSISTANT, "first answer"),
        ]
    )
    prompt = build_qa_user_prompt("follow-up?", "context", history=block)

    assert "Retrieved context:\ncontext" in prompt
    assert "Conversation history" in prompt
    assert "[user] first question" in prompt
    assert "[assistant] first answer" in prompt
    assert "not retrieved evidence" in prompt


def test_history_block_empty_ordering_and_budget() -> None:
    assert build_history_block([]) == ""
    block = build_history_block(
        [
            _message(MessageRole.USER, "  spaced   out "),
            _message(MessageRole.SYSTEM, "marker"),
        ]
    )
    assert block == "[user] spaced out\n[system] marker"
    long_block = build_history_block(
        [_message(MessageRole.USER, "a" * 1990), _message(MessageRole.USER, "b" * 50)],
        max_chars=2000,
    )
    # Newest message always survives; older ones yield to the budget.
    assert long_block.endswith("[user] " + "b" * 50)
    assert "a" * 1990 not in long_block


def test_history_never_satisfies_abstention() -> None:
    client = RecordingOllamaClient()
    workflow = QAWorkflow(StubSearchService([]), client)  # type: ignore[arg-type]

    answer = workflow.ask(
        "what?", history=(_message(MessageRole.USER, "the password is hunter2"),)
    )

    assert answer.outcome is OUTCOME_ABSTAINED
    assert client.calls == 0


def test_citations_still_resolve_with_history() -> None:
    workflow, client = _workflow("The answer is here [SOURCE 1].")

    answer = workflow.ask(
        "what?",
        history=(_message(MessageRole.USER, "earlier"),),
    )

    assert answer.outcome is OUTCOME_ANSWERED
    assert [citation.number for citation in answer.citations] == [1]
    assert answer.citations[0].hit.source == "a.md"
    assert "[user] earlier" in client.prompts[0]
    assert "[SOURCE 1]" in client.prompts[0]
