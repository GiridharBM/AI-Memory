"""End-to-end V2.1-A lifecycle: create → ask → restart → history → archive."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.application.conversation_service import (
    ArchivedConversationError,
    ConversationService,
)
from app.application.qa_workflow import QAAnswer, SourceCitation
from app.domain.conversation import ConversationStatus, Message, MessageRole
from app.infrastructure.conversations import ConversationStore
from app.infrastructure.search import SearchHit


def _hit(source: str = "a.md") -> SearchHit:
    return SearchHit(text="body", source=source, score=0.9, entry_id=f"{source}::0")


class ScriptedQA:
    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)
        self.seen_histories: list[tuple[Message, ...]] = []

    def ask(
        self,
        question: str,
        *,
        top_k: int = 5,
        history: Sequence[Message] = (),
    ) -> QAAnswer:
        self.seen_histories.append(tuple(history))
        text = self._texts.pop(0)
        return QAAnswer(
            answer=text,
            sources=[_hit()],
            model="qwen3:8b",
            citations=[SourceCitation(number=1, hit=_hit())],
        )


def test_full_lifecycle_with_restart(tmp_path: Path) -> None:
    service = ConversationService(ConversationStore(tmp_path / "manifests"))
    qa = ScriptedQA(["first answer", "second answer"])

    conversation = service.create_conversation("deep dive")
    user_one, assistant_one = service.ask(conversation.id, "first question?", qa)
    assert (user_one.seq, assistant_one.seq) == (1, 2)
    assert assistant_one.evidence is not None
    assert assistant_one.evidence.citations[0].source == "a.md"

    # Second turn sees the first turn as history.
    _, assistant_two = service.ask(conversation.id, "follow-up?", qa)
    assert assistant_two.seq == 4
    assert [m.content for m in qa.seen_histories[1]] == [
        "first question?",
        "first answer",
        "follow-up?",
    ]

    # Restart: a fresh store/service over the same directory keeps everything.
    restarted = ConversationService(ConversationStore(tmp_path / "manifests"))
    reloaded = restarted.get_conversation(conversation.id)
    assert reloaded.message_count == 4
    history = restarted.recent_messages(conversation.id)
    assert [m.content for m in history] == [
        "first question?",
        "first answer",
        "follow-up?",
        "second answer",
    ]
    assert [m.seq for m in history] == [1, 2, 3, 4]

    # Archive closes the thread but preserves readable history.
    restarted.archive_conversation(conversation.id)
    assert (
        restarted.get_conversation(conversation.id).status
        is ConversationStatus.ARCHIVED
    )
    assert len(restarted.recent_messages(conversation.id)) == 4
    try:
        restarted.ask(conversation.id, "another?", qa)
    except ArchivedConversationError:
        pass
    else:
        raise AssertionError("ask on archived conversation must fail")
    assert len(restarted.recent_messages(conversation.id)) == 4


def test_message_roles_cover_user_assistant_system(tmp_path: Path) -> None:
    service = ConversationService(ConversationStore(tmp_path / "manifests"))
    conversation = service.create_conversation("t")
    qa = ScriptedQA(["answer"])

    service.ask(conversation.id, "q?", qa)
    store = ConversationStore(tmp_path / "manifests")
    store.append_message(conversation.id, MessageRole.SYSTEM, "boundary marker")

    roles = [m.role for m in store.get_messages(conversation.id, limit=10)]
    assert roles == [MessageRole.USER, MessageRole.ASSISTANT, MessageRole.SYSTEM]
