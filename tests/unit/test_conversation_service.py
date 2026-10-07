"""Service tests for V2.1-A conversations (rules, history, QA coordination)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from app.application.conversation_service import (
    ArchivedConversationError,
    ConversationService,
    InvalidMessageError,
    UnknownConversationError,
)
from app.application.qa_workflow import OUTCOME_ABSTAINED, QAAnswer, SourceCitation
from app.domain.conversation import (
    ConversationStatus,
    Message,
    MessageRole,
)
from app.infrastructure.conversations import ConversationStore
from app.infrastructure.search import SearchHit


def _service(tmp_path: Path) -> ConversationService:
    return ConversationService(ConversationStore(tmp_path / "manifests"))


def _hit(source: str = "a.md") -> SearchHit:
    return SearchHit(text="body", source=source, score=0.9, entry_id=f"{source}::0")


def _answer(text: str = "answer text") -> QAAnswer:
    return QAAnswer(
        answer=text,
        sources=[_hit("a.md")],
        model="qwen3:8b",
        citations=[SourceCitation(number=1, hit=_hit("a.md"))],
    )


class ScriptedQA:
    """Fake QA port recording history it receives."""

    def __init__(self, answer: QAAnswer | Exception) -> None:
        self._answer = answer
        self.histories: list[tuple[Message, ...]] = []
        self.questions: list[str] = []

    def ask(
        self,
        question: str,
        *,
        top_k: int = 5,
        history: Sequence[Message] = (),
    ) -> QAAnswer:
        self.questions.append(question)
        self.histories.append(tuple(history))
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer


def test_create_list_get_conversation(tmp_path: Path) -> None:
    service = _service(tmp_path)

    created = service.create_conversation("  hello ")
    assert created.title == "hello"
    assert service.get_conversation(created.id) == created
    assert [c.id for c in service.list_conversations()] == [created.id]
    assert service.create_conversation().title == "New conversation"
    with pytest.raises(UnknownConversationError):
        service.get_conversation("ghost")


def test_append_user_message_rules(tmp_path: Path) -> None:
    service = _service(tmp_path)
    conversation = service.create_conversation("t")

    message = service.append_user_message(conversation.id, "  hi ")
    assert message.role is MessageRole.USER
    assert message.content == "hi"
    assert message.seq == 1
    with pytest.raises(InvalidMessageError):
        service.append_user_message(conversation.id, "   ")
    with pytest.raises(UnknownConversationError):
        service.append_user_message("ghost", "hi")


def test_archive_blocks_writes_but_is_idempotent(tmp_path: Path) -> None:
    service = _service(tmp_path)
    conversation = service.create_conversation("t")

    archived = service.archive_conversation(conversation.id)
    assert archived.status is ConversationStatus.ARCHIVED
    assert service.archive_conversation(conversation.id).status is ConversationStatus.ARCHIVED
    with pytest.raises(ArchivedConversationError):
        service.append_user_message(conversation.id, "hi")
    with pytest.raises(UnknownConversationError):
        service.archive_conversation("ghost")


def test_recent_messages_bounded_and_ordered(tmp_path: Path) -> None:
    service = _service(tmp_path)
    conversation = service.create_conversation("t")
    for index in range(6):
        service.append_user_message(conversation.id, f"m{index}")

    recent = service.recent_messages(conversation.id, max_messages=3, max_chars=1000)
    assert [m.content for m in recent] == ["m3", "m4", "m5"]
    tiny = service.recent_messages(conversation.id, max_messages=10, max_chars=3)
    assert [m.content for m in tiny] == ["m5"]
    with pytest.raises(UnknownConversationError):
        service.recent_messages("ghost")


def test_ask_persists_both_messages_with_snapshot(tmp_path: Path) -> None:
    service = _service(tmp_path)
    conversation = service.create_conversation("t")
    qa = ScriptedQA(_answer())

    user_message, assistant_message = service.ask(conversation.id, "what?", qa)

    assert user_message.role is MessageRole.USER
    assert assistant_message.role is MessageRole.ASSISTANT
    assert assistant_message.content == "answer text"
    assert assistant_message.model == "qwen3:8b"
    assert assistant_message.evidence is not None
    assert assistant_message.evidence.outcome == "answered"
    assert assistant_message.evidence.citations[0].source == "a.md"
    assert assistant_message.seq == user_message.seq + 1
    # QA saw the just-written user message as history.
    assert [m.content for m in qa.histories[0]] == ["what?"]


def test_ask_failure_marks_assistant_not_silent(tmp_path: Path) -> None:
    service = _service(tmp_path)
    conversation = service.create_conversation("t")
    qa = ScriptedQA(RuntimeError("ollama down"))

    user_message, assistant_message = service.ask(conversation.id, "what?", qa)

    assert user_message.content == "what?"
    assert assistant_message.role is MessageRole.ASSISTANT
    assert assistant_message.evidence is not None
    assert assistant_message.evidence.error is not None
    assert "RuntimeError" in assistant_message.evidence.error
    stored = service.recent_messages(conversation.id)
    assert [m.content for m in stored] == ["what?", "[assistant generation failed]"]


def test_ask_validates_and_respects_archive(tmp_path: Path) -> None:
    service = _service(tmp_path)
    conversation = service.create_conversation("t")
    qa = ScriptedQA(_answer())

    with pytest.raises(InvalidMessageError):
        service.ask(conversation.id, "   ", qa)
    service.archive_conversation(conversation.id)
    with pytest.raises(ArchivedConversationError):
        service.ask(conversation.id, "what?", qa)
    with pytest.raises(UnknownConversationError):
        service.ask("ghost", "what?", qa)
    assert qa.questions == []


def test_ask_abstention_still_persisted(tmp_path: Path) -> None:
    service = _service(tmp_path)
    conversation = service.create_conversation("t")
    abstained = QAAnswer(answer="I don't know.", sources=[], model="qwen3:8b")
    abstained.outcome = OUTCOME_ABSTAINED
    qa = ScriptedQA(abstained)

    _, assistant_message = service.ask(conversation.id, "what?", qa)

    assert assistant_message.content == "I don't know."
    assert assistant_message.evidence is not None
    assert assistant_message.evidence.outcome == OUTCOME_ABSTAINED
    assert assistant_message.evidence.citations == ()
