"""Persistence for V2.1-A conversations and messages.

Conversations live in one atomic-JSON store; messages live in one
append-only JSONL file. Both follow the repository's tmp-file +
``os.replace`` / lock conventions: best-effort writes (logged, never
raised), corrupt content degrades to skips with a warning rather than
destroying the store. A torn final JSONL line (crash mid-append) reads as
one skipped corrupt line on the next load.
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.core.logging import get_logger
from app.domain.conversation import (
    Conversation,
    EvidenceSnapshot,
    Message,
    MessageRole,
)

logger = get_logger(__name__)


class ConversationStore:
    """Thread-safe store for conversations plus their message history."""

    def __init__(self, manifest_root: Path) -> None:
        self._conversations_path = manifest_root / "conversations.json"
        self._messages_path = manifest_root / "conversation_messages.jsonl"
        self._lock = threading.Lock()
        self._conversations: dict[str, Conversation] = {}
        self._messages: list[Message] = []
        self._loaded = False

    def _load_once(self) -> None:
        if self._loaded:
            return
        self._conversations = self._read_conversations()
        self._messages = self._read_messages()
        self._loaded = True

    def _read_conversations(self) -> dict[str, Conversation]:
        if not self._conversations_path.exists():
            return {}
        try:
            payload = json.loads(self._conversations_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError):
            logger.warning(
                "Conversation store unreadable; starting empty: %s",
                self._conversations_path,
            )
            return {}
        raw_items = payload.get("conversations", []) if isinstance(payload, dict) else []
        if not isinstance(raw_items, list):
            return {}
        conversations: dict[str, Conversation] = {}
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            try:
                conversation = Conversation.model_validate(raw)
            except ValidationError:
                logger.warning("Skipping unparseable conversation entry.")
                continue
            conversations[conversation.id] = conversation
        return conversations

    def _read_messages(self) -> list[Message]:
        if not self._messages_path.exists():
            return []
        messages: list[Message] = []
        try:
            text = self._messages_path.read_text(encoding="utf-8")
        except OSError:
            logger.warning(
                "Conversation messages unreadable; starting empty: %s", self._messages_path
            )
            return []
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                logger.warning(
                    "Skipping unparseable conversation message line.",
                    extra={"line": line_number},
                )
                continue
            if not isinstance(raw, dict):
                continue
            try:
                messages.append(Message.model_validate(raw))
            except ValidationError:
                logger.warning(
                    "Skipping unparseable conversation message entry.",
                    extra={"line": line_number},
                )
        return messages

    def _persist_conversations(self) -> None:
        payload: dict[str, Any] = {
            "version": 1,
            "conversations": [
                conversation.model_dump(mode="json")
                for _, conversation in sorted(
                    self._conversations.items(),
                    key=lambda item: (item[1].created_at, item[0]),
                )
            ],
        }
        try:
            self._conversations_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self._conversations_path.with_suffix(
                f"{self._conversations_path.suffix}.tmp"
            )
            try:
                temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                os.replace(temporary_path, self._conversations_path)
            finally:
                with suppress(FileNotFoundError):
                    temporary_path.unlink()
        except OSError:
            logger.warning("Failed to persist conversation store.", exc_info=True)

    def _append_message_line(self, message: Message) -> None:
        try:
            self._messages_path.parent.mkdir(parents=True, exist_ok=True)
            with self._messages_path.open("a", encoding="utf-8") as handle:
                handle.write(message.model_dump_json() + "\n")
                handle.flush()
        except OSError:
            logger.warning("Failed to persist conversation message.", exc_info=True)

    def create_conversation(self, title: str) -> Conversation:
        """Create, persist, and return a new active conversation."""

        with self._lock:
            self._load_once()
            conversation = Conversation.create(title)
            self._conversations[conversation.id] = conversation
            self._persist_conversations()
            return conversation

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Return one conversation, or ``None`` when unknown."""

        with self._lock:
            self._load_once()
            return self._conversations.get(conversation_id)

    def list_conversations(self) -> list[Conversation]:
        """All conversations in deterministic creation order."""

        with self._lock:
            self._load_once()
            return sorted(
                self._conversations.values(),
                key=lambda item: (item.created_at, item.id),
            )

    def update_conversation(self, conversation: Conversation) -> None:
        """Persist a changed conversation row; raises ``KeyError`` when unknown."""

        with self._lock:
            self._load_once()
            if conversation.id not in self._conversations:
                raise KeyError(f"Unknown conversation: {conversation.id}")
            self._conversations[conversation.id] = conversation
            self._persist_conversations()

    def append_message(
        self,
        conversation_id: str,
        role: MessageRole,
        content: str,
        *,
        model: str | None = None,
        evidence: EvidenceSnapshot | dict[str, Any] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Message:
        """Append a message with the next sequence number; raises ``KeyError``."""

        with self._lock:
            self._load_once()
            conversation = self._conversations.get(conversation_id)
            if conversation is None:
                raise KeyError(f"Unknown conversation: {conversation_id}")
            parsed_evidence = None
            if evidence is not None:
                parsed_evidence = (
                    evidence
                    if isinstance(evidence, EvidenceSnapshot)
                    else EvidenceSnapshot.model_validate(evidence)
                )
            seq = (
                max(
                    (message.seq for message in self._messages
                     if message.conversation_id == conversation_id),
                    default=0,
                )
                + 1
            )
            message = Message.create(
                conversation_id,
                role,
                content,
                seq,
                model=model,
                evidence=parsed_evidence,
                metadata=metadata,
            )
            self._messages.append(message)
            self._append_message_line(message)
            self._conversations[conversation_id] = conversation.model_copy(
                update={
                    "updated_at": datetime.now(UTC),
                    "message_count": conversation.message_count + 1,
                }
            )
            self._persist_conversations()
            return message

    def get_messages(
        self, conversation_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[Message]:
        """Chronological messages for one conversation (unknown id yields [])."""

        with self._lock:
            self._load_once()
            selected = [
                message
                for message in self._messages
                if message.conversation_id == conversation_id
            ]
            selected.sort(key=lambda message: (message.seq, message.id))
            return selected[offset : offset + limit]

    def count_messages(self, conversation_id: str) -> int:
        """Number of stored messages for one conversation."""

        with self._lock:
            self._load_once()
            return sum(
                1 for message in self._messages if message.conversation_id == conversation_id
            )
