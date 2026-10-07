"""Thin orchestration for V2.1-A conversations.

Owns user-facing conversation rules (unknown/archived/invalid handling,
server-assigned sequencing, failure markers) on top of ``ConversationStore``.
History formatting for prompts lives in ``qa_workflow``; retrieval itself is
untouched. No long-term memory is created here.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.application.qa_workflow import QAAnswer
from app.domain.conversation import (
    Conversation,
    ConversationStatus,
    EvidenceCitation,
    EvidenceSnapshot,
    Message,
    MessageRole,
)
from app.infrastructure.conversations import ConversationStore

MAX_HISTORY_MESSAGES = 10
MAX_HISTORY_CHARS = 2000
DEFAULT_TITLE = "New conversation"


class ConversationError(ValueError):
    """Base class for conversation failures."""


class UnknownConversationError(ConversationError):
    """No conversation exists for the requested id."""


class ArchivedConversationError(ConversationError):
    """The conversation is archived and rejects new writes."""


class InvalidMessageError(ConversationError):
    """A message payload or question failed validation."""


class QAConversationPort(Protocol):
    """Structural interface for asking with conversation history."""

    def ask(
        self,
        question: str,
        *,
        top_k: int = 5,
        history: Sequence[Message] = (),
    ) -> QAAnswer: ...


def _failure_snapshot(exc: Exception) -> EvidenceSnapshot:
    return EvidenceSnapshot(error=f"{type(exc).__name__}: {exc}")


class ConversationService:
    """Coordinate conversations, messages, and conversation QA."""

    def __init__(self, store: ConversationStore) -> None:
        self._store = store

    def create_conversation(self, title: str | None = None) -> Conversation:
        """Create a new active conversation."""

        cleaned = title.strip() if isinstance(title, str) else ""
        return self._store.create_conversation(cleaned or DEFAULT_TITLE)

    def get_conversation(self, conversation_id: str) -> Conversation:
        """Return one conversation; raises when unknown."""

        conversation = self._store.get_conversation(conversation_id)
        if conversation is None:
            raise UnknownConversationError(
                f"Unknown conversation: {conversation_id}."
            )
        return conversation

    def list_conversations(self) -> list[Conversation]:
        """All conversations in deterministic creation order."""

        return self._store.list_conversations()

    def archive_conversation(self, conversation_id: str) -> Conversation:
        """Archive a conversation; already-archived is a no-op success."""

        conversation = self.get_conversation(conversation_id)
        if conversation.status is ConversationStatus.ARCHIVED:
            return conversation
        archived = conversation.model_copy(
            update={"status": ConversationStatus.ARCHIVED}
        )
        self._store.update_conversation(archived)
        return archived

    def _require_writable(self, conversation_id: str) -> Conversation:
        conversation = self.get_conversation(conversation_id)
        if conversation.status is ConversationStatus.ARCHIVED:
            raise ArchivedConversationError(
                f"Conversation is archived: {conversation_id}."
            )
        return conversation

    def append_user_message(self, conversation_id: str, content: str) -> Message:
        """Append a validated user message; rejects archived/unknown."""

        if not isinstance(content, str) or not content.strip():
            raise InvalidMessageError("Message content must not be empty.")
        self._require_writable(conversation_id)
        try:
            return self._store.append_message(
                conversation_id, MessageRole.USER, content
            )
        except KeyError as exc:
            raise UnknownConversationError(str(exc)) from exc

    def recent_messages(
        self,
        conversation_id: str,
        *,
        max_messages: int = MAX_HISTORY_MESSAGES,
        max_chars: int = MAX_HISTORY_CHARS,
    ) -> tuple[Message, ...]:
        """Newest bounded slice of history, oldest-first, within char budget."""

        self.get_conversation(conversation_id)
        messages = self._store.get_messages(conversation_id, limit=max_messages * 4)
        recent = messages[-max_messages:] if max_messages >= 0 else []
        kept: list[Message] = []
        used = 0
        for message in reversed(recent):
            if used + len(message.content) > max_chars and kept:
                break
            kept.append(message)
            used += len(message.content)
        return tuple(reversed(kept))

    def get_messages(
        self, conversation_id: str, *, limit: int = 50, offset: int = 0
    ) -> tuple[Message, ...]:
        """Paginated history for one conversation; raises when unknown."""

        self.get_conversation(conversation_id)
        return tuple(self._store.get_messages(conversation_id, limit=limit, offset=offset))

    def count_messages(self, conversation_id: str) -> int:
        """Stored message count; raises when unknown."""

        self.get_conversation(conversation_id)
        return self._store.count_messages(conversation_id)

    def ask(
        self,
        conversation_id: str,
        question: str,
        qa: QAConversationPort,
        *,
        top_k: int = 5,
    ) -> tuple[Message, Message]:
        """Ask within a conversation: persist user + assistant messages.

        The assistant message carries the QA evidence snapshot on success or
        a failure marker (never a silent loss) when generation raises.
        """

        if not isinstance(question, str) or not question.strip():
            raise InvalidMessageError("Question must not be empty.")
        self._require_writable(conversation_id)
        user_message = self.append_user_message(conversation_id, question)
        history = self.recent_messages(conversation_id)
        try:
            answer = qa.ask(question.strip(), top_k=top_k, history=history)
        except Exception as exc:
            failure = self._store.append_message(
                conversation_id,
                MessageRole.ASSISTANT,
                "[assistant generation failed]",
                metadata={"error": f"{type(exc).__name__}: {exc}"[:500]},
                evidence=_failure_snapshot(exc),
            )
            return user_message, failure
        snapshot = EvidenceSnapshot(
            model=answer.model or "",
            outcome=answer.outcome,
            citations=tuple(
                EvidenceCitation(
                    number=citation.number,
                    source=citation.hit.source,
                    chunk_id=citation.hit.entry_id or None,
                    chunk_index=citation.hit.chunk_index,
                )
                for citation in answer.citations
            ),
        )
        assistant_message = self._store.append_message(
            conversation_id,
            MessageRole.ASSISTANT,
            answer.answer,
            model=answer.model or None,
            evidence=snapshot,
        )
        return user_message, assistant_message
