"""Conversation routes: threads, messages, archive, and conversation QA.

Conversations are the V2.1-A session foundation: synchronous request/response
like ``POST /ask`` (no background jobs), with history persisted per message.
Assistant messages are server-created after real QA runs — clients can only
submit ``user`` messages, so history cannot be forged.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.application.conversation_service import (
    ArchivedConversationError,
    ConversationService,
    InvalidMessageError,
    UnknownConversationError,
)
from app.application.qa_workflow import QAError
from app.core.config import Settings
from app.domain.conversation import Conversation, Message, MessageRole
from app.infrastructure.conversations import ConversationStore
from app.interfaces.web import deps

router = APIRouter()


class CreateConversationRequest(BaseModel):
    """Create a conversation; title is optional."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)


class AppendMessageRequest(BaseModel):
    """Append a message; only ``user`` role is accepted from clients."""

    model_config = ConfigDict(extra="forbid")

    role: str
    content: str = Field(min_length=1, max_length=8000)


class ConversationAskRequest(BaseModel):
    """Ask within a conversation; mirrors ``AskRequest`` bounds."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=8000)
    top_k: int = Field(default=5, ge=1, le=50)


def _service(settings: Settings) -> ConversationService:
    """Build the conversation service over the manifest root."""

    return ConversationService(ConversationStore(settings.paths.manifest_root))


def _conversation_payload(conversation: Conversation) -> dict[str, Any]:
    return conversation.model_dump(mode="json")


def _message_payload(message: Message) -> dict[str, Any]:
    return message.model_dump(mode="json")


def _require_settings() -> Settings:
    error = deps.settings_error()
    if error is not None:
        raise HTTPException(status_code=503, detail=error)
    return deps.get_settings()


@router.post("/conversations", status_code=201)
def create_conversation(request: CreateConversationRequest) -> dict[str, Any]:
    """Create a new active conversation."""

    settings = _require_settings()
    return _conversation_payload(_service(settings).create_conversation(request.title))


@router.get("/conversations")
def list_conversations(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """All conversations in deterministic creation order (paginated)."""

    settings = _require_settings()
    conversations = _service(settings).list_conversations()
    return {
        "conversations": [
            _conversation_payload(conversation)
            for conversation in conversations[offset : offset + limit]
        ],
        "total": len(conversations),
    }


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict[str, Any]:
    """One conversation, or 404 when unknown."""

    settings = _require_settings()
    try:
        return _conversation_payload(
            _service(settings).get_conversation(conversation_id)
        )
    except UnknownConversationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/conversations/{conversation_id}/messages", status_code=201)
def append_message(
    conversation_id: str, request: AppendMessageRequest
) -> dict[str, Any]:
    """Append a user message; assistant history cannot be forged (422)."""

    settings = _require_settings()
    if request.role != MessageRole.USER.value:
        raise HTTPException(
            status_code=422,
            detail="Only 'user' messages may be submitted; "
            "assistant messages are created by PAM after QA runs.",
        )
    service = _service(settings)
    try:
        message = service.append_user_message(conversation_id, request.content)
    except UnknownConversationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArchivedConversationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidMessageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _message_payload(message)


@router.get("/conversations/{conversation_id}/messages")
def list_messages(
    conversation_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Chronological messages for one conversation (paginated)."""

    settings = _require_settings()
    service = _service(settings)
    try:
        messages = service.get_messages(conversation_id, limit=limit, offset=offset)
        total = service.count_messages(conversation_id)
    except UnknownConversationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "messages": [_message_payload(message) for message in messages],
        "total": total,
    }


@router.post("/conversations/{conversation_id}/archive")
def archive_conversation(conversation_id: str) -> dict[str, Any]:
    """Archive a conversation; already-archived is a no-op success."""

    settings = _require_settings()
    try:
        archived = _service(settings).archive_conversation(conversation_id)
    except UnknownConversationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _conversation_payload(archived)


@router.post("/conversations/{conversation_id}/ask")
def ask_in_conversation(
    conversation_id: str, request: ConversationAskRequest
) -> dict[str, Any]:
    """Ask within a conversation and persist both messages.

    Synchronous like ``POST /ask``: the request blocks until the QA answer
    is stored. QA failures keep the established 502/500 mapping.
    """

    settings = _require_settings()
    service = _service(settings)
    try:
        user_message, assistant_message = service.ask(
            conversation_id,
            request.question,
            deps.get_qa_workflow(),
            top_k=request.top_k,
        )
    except UnknownConversationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArchivedConversationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidMessageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except QAError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Conversation ask failed: {exc}") from exc
    return {
        "user_message": _message_payload(user_message),
        "assistant_message": _message_payload(assistant_message),
    }
