"""QA history-seam tests: byte-identical default path plus fused history."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.application.conversation_service import ConversationService
from app.application.memory_service import MemoryService
from app.application.qa_workflow import (
    OUTCOME_ABSTAINED,
    OUTCOME_ANSWERED,
    QAWorkflow,
)
from app.core.config import Settings
from app.domain.conversation import Message, MessageRole
from app.domain.memory import MemoryCandidate, MemoryCategory, MemoryGrounding
from app.infrastructure.conversations import ConversationStore
from app.infrastructure.llm import OllamaTextResponse
from app.infrastructure.memories import CandidateStore, MemoryStore
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


def _never_generate(*args: object) -> object:
    raise AssertionError("runtime memory context must not call the model")


def _approve_memory(
    tmp_settings: Settings,
    text: str = "User prefers dark mode.",
    quoted: str = "I prefer dark mode.",
) -> str:
    """Approve one memory through the real lifecycle; return its logical id."""

    root = tmp_settings.paths.manifest_root
    conversations = ConversationService(ConversationStore(root))
    conversation = conversations.create_conversation("t")
    user = conversations.append_user_message(conversation.id, quoted)
    service = MemoryService(
        CandidateStore(root), MemoryStore(root), conversations, _never_generate  # type: ignore[arg-type]
    )
    candidate = MemoryCandidate.propose(
        text,
        MemoryCategory.PREFERENCE,
        0.9,
        MemoryGrounding(
            conversation_id=conversation.id,
            message_id=user.id,
            seq=user.seq,
            quoted_text=quoted,
        ),
    )
    service._candidates.save(candidate)
    return service.approve(candidate.id).logical_id


def _memory_workflow(
    answer: str,
    tmp_settings: Settings,
    hits: list[SearchHit] | None = None,
) -> tuple[QAWorkflow, RecordingOllamaClient]:
    client = RecordingOllamaClient(answer)
    workflow = QAWorkflow(
        StubSearchService(hits if hits is not None else []),  # type: ignore[arg-type]
        client,
        manifest_root=tmp_settings.paths.manifest_root,
    )
    return workflow, client


def test_no_memory_path_is_byte_identical(tmp_path: Path) -> None:
    plain_client = RecordingOllamaClient("response text")
    plain = QAWorkflow(StubSearchService([_hit()]), plain_client)  # type: ignore[arg-type]
    mem_client = RecordingOllamaClient("response text")
    mem = QAWorkflow(
        StubSearchService([_hit()]),  # type: ignore[arg-type]
        mem_client,
        manifest_root=tmp_path / "manifests",
    )

    plain.ask("what?")
    mem.ask("what?")

    assert mem_client.prompts == plain_client.prompts


def test_memory_appended_after_documents(tmp_settings: Settings) -> None:
    _approve_memory(tmp_settings)
    workflow, client = _memory_workflow(
        "See [SOURCE 1] and [SOURCE 2].", tmp_settings, [_hit()]
    )

    answer = workflow.ask("Does the user prefers dark mode?")

    assert answer.outcome is OUTCOME_ANSWERED
    prompt = client.prompts[0]
    assert prompt.index("[SOURCE 1]\nSource: a.md") < prompt.index("[SOURCE 2]")
    assert "Source: memory:" in prompt
    assert [citation.number for citation in answer.citations] == [1, 2]
    assert answer.citations[0].hit.source == "a.md"
    assert answer.citations[1].hit.source.startswith("memory:")


def test_memory_rescues_abstaining_query(tmp_settings: Settings) -> None:
    _approve_memory(tmp_settings)
    workflow, client = _memory_workflow(
        "Dark mode it is [SOURCE 1].", tmp_settings
    )

    answer = workflow.ask("Does the user prefers dark mode?")

    assert answer.outcome is OUTCOME_ANSWERED
    assert client.calls == 1
    assert len(answer.citations) == 1
    assert answer.citations[0].hit.source.startswith("memory:")
    assert "USER-CONFIRMED PERSONAL FACTS" in client.prompts[0]


def test_no_memory_match_does_not_rescue_abstention(tmp_settings: Settings) -> None:
    _approve_memory(tmp_settings)
    workflow, client = _memory_workflow("unused", tmp_settings)

    answer = workflow.ask("What is the capital of France?")

    assert answer.outcome is OUTCOME_ABSTAINED
    assert client.calls == 0


def test_abstention_without_memories_makes_no_llm_call(tmp_settings: Settings) -> None:
    workflow, client = _memory_workflow("unused", tmp_settings)

    answer = workflow.ask("What is the capital of France?")

    assert answer.outcome is OUTCOME_ABSTAINED
    assert client.calls == 0


def test_multiple_memories_cited(tmp_settings: Settings) -> None:
    _approve_memory(tmp_settings, "User prefers dark mode.")
    _approve_memory(tmp_settings, "User prefers light mode at night.")
    workflow, client = _memory_workflow(
        "Both hold [SOURCE 1] [SOURCE 2].", tmp_settings
    )

    answer = workflow.ask("Does the user prefers dark mode or light mode?")

    assert answer.outcome is OUTCOME_ANSWERED
    assert [citation.number for citation in answer.citations] == [1, 2]
    assert answer.citations[0].hit.source != answer.citations[1].hit.source
    assert all(
        citation.hit.source.startswith("memory:") for citation in answer.citations
    )


def test_superseded_memory_cannot_appear(tmp_settings: Settings) -> None:
    root = tmp_settings.paths.manifest_root
    logical_id = _approve_memory(tmp_settings, "User prefers dark mode.")
    conversations = ConversationService(ConversationStore(root))
    service = MemoryService(
        CandidateStore(root), MemoryStore(root), conversations, _never_generate  # type: ignore[arg-type]
    )
    service.supersede_latest(
        logical_id,
        "User wake-up time is 6am.",
        category=MemoryCategory.FACT,
        confidence=0.8,
    )
    workflow, client = _memory_workflow("unused", tmp_settings)

    answer = workflow.ask("Does the user prefers dark mode?")

    assert answer.outcome is OUTCOME_ABSTAINED
    assert client.calls == 0


def test_memory_evidence_snapshot_flows_to_conversation(tmp_settings: Settings) -> None:
    logical_id = _approve_memory(tmp_settings)
    workflow, _ = _memory_workflow("Dark mode it is [SOURCE 1].", tmp_settings)
    conversations = ConversationService(
        ConversationStore(tmp_settings.paths.manifest_root)
    )
    conversation = conversations.create_conversation("t")

    _, assistant = conversations.ask(
        conversation.id, "Does the user prefers dark mode?", workflow
    )

    assert assistant.evidence is not None
    assert assistant.evidence.error is None
    (citation,) = assistant.evidence.citations
    assert citation.source == f"memory:{logical_id}@v1"
    assert assistant.evidence.citations[0].chunk_id is not None


def test_workflow_sees_newly_approved_memories(tmp_settings: Settings) -> None:
    root = tmp_settings.paths.manifest_root
    logical_id = _approve_memory(tmp_settings, "User prefers dark mode.")
    workflow, client = _memory_workflow("Dark mode it is [SOURCE 1].", tmp_settings)

    first = workflow.ask("Does the user prefers dark mode?")

    assert first.outcome is OUTCOME_ANSWERED
    assert "User prefers dark mode." in client.prompts[0]

    conversations = ConversationService(ConversationStore(root))
    service = MemoryService(
        CandidateStore(root), MemoryStore(root), conversations, _never_generate  # type: ignore[arg-type]
    )
    service.supersede_latest(
        logical_id,
        "User wake-up time is 6am.",
        category=MemoryCategory.FACT,
        confidence=0.8,
    )

    second = workflow.ask("Does the user prefers dark mode?")

    # The same workflow instance must see the current ACTIVE state: the old
    # version is superseded (excluded) and the new text does not match, so
    # the query abstains and the LLM is never called again.
    assert second.outcome is OUTCOME_ABSTAINED
    assert client.calls == 1
