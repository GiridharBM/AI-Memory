"""Memory routes: extraction, candidates, lifecycle, and provenance.

Thin HTTP over ``MemoryService``: request validation here, state
transitions and extraction in the service. Extraction is explicitly
triggered per conversation — there is no background or automatic path.
Human approval (via these routes) is the only route from candidate to
durable memory.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.application.conversation_service import (
    ConversationService,
    UnknownConversationError,
)
from app.application.memory_service import (
    ExtractionError,
    InvalidCandidateStateError,
    MemoryService,
    UnknownCandidateError,
    UnknownMemoryError,
)
from app.core.config import Settings
from app.domain.memory import Memory, MemoryCandidate, MemoryCategory
from app.infrastructure.conversations import ConversationStore
from app.infrastructure.llm import OllamaClient, OllamaRequest
from app.infrastructure.memories import CandidateStore, MemoryStore
from app.interfaces.web import deps

router = APIRouter()


class ExtractRequest(BaseModel):
    """Trigger extraction for one conversation."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1)


class ApproveRequest(BaseModel):
    """Approve a pending candidate; optional pre-approval edit."""

    model_config = ConfigDict(extra="forbid")

    edited_text: str | None = Field(default=None, max_length=2000)


class RejectRequest(BaseModel):
    """Reject a pending candidate; reason is required and retained."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1)


class EditRequest(BaseModel):
    """Set pending-edit text; the candidate stays pending."""

    model_config = ConfigDict(extra="forbid")

    edited_text: str = Field(min_length=1, max_length=2000)


class SupersedeRequest(BaseModel):
    """Create the next version reusing the latest version's source."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    category: MemoryCategory
    confidence: float = Field(ge=0.0, le=1.0)


def _service(settings: Settings) -> MemoryService:
    """Build the memory service over the manifest root plus the LLM seam."""

    root = settings.paths.manifest_root
    client = OllamaClient(settings.ollama)
    model = settings.models.model_for("general_text")

    def generate_json(system_prompt: str, user_prompt: str, response_model: type) -> Any:
        return client.generate_json(
            OllamaRequest(prompt=user_prompt, system_prompt=system_prompt, model=model),
            response_model=response_model,
        )

    return MemoryService(
        CandidateStore(root),
        MemoryStore(root),
        ConversationService(ConversationStore(root)),
        generate_json,
    )


def _candidate_payload(candidate: MemoryCandidate) -> dict[str, Any]:
    return candidate.model_dump(mode="json")


def _memory_payload(memory: Memory) -> dict[str, Any]:
    return memory.model_dump(mode="json")


def _require_settings() -> Settings:
    error = deps.settings_error()
    if error is not None:
        raise HTTPException(status_code=503, detail=error)
    return deps.get_settings()


@router.post("/memories/extract", status_code=201)
def extract_memories(request: ExtractRequest) -> dict[str, Any]:
    """Run explicit extraction for one conversation; returns new candidates."""

    settings = _require_settings()
    try:
        candidates = _service(settings).extract(request.conversation_id)
    except UnknownConversationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}") from exc
    return {
        "candidates": [_candidate_payload(candidate) for candidate in candidates],
        "total": len(candidates),
    }


@router.get("/memories/candidates")
def list_candidates(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Candidates in deterministic extraction order (paginated)."""

    settings = _require_settings()
    candidates = _service(settings).list_candidates(limit=10000, offset=0)
    return {
        "candidates": [
            _candidate_payload(candidate)
            for candidate in candidates[offset : offset + limit]
        ],
        "total": len(candidates),
    }


@router.get("/memories/candidates/{candidate_id}")
def get_candidate(candidate_id: str) -> dict[str, Any]:
    """One candidate, or 404 when unknown."""

    settings = _require_settings()
    try:
        return _candidate_payload(_service(settings).get_candidate(candidate_id))
    except UnknownCandidateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/memories/candidates/{candidate_id}/approve")
def approve_candidate(
    candidate_id: str, request: ApproveRequest
) -> dict[str, Any]:
    """Approve a pending candidate, creating Memory v1 (or its next version)."""

    settings = _require_settings()
    try:
        memory = _service(settings).approve(candidate_id, edited_text=request.edited_text)
    except UnknownCandidateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidCandidateStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    service = _service(settings)
    return {
        "memory": _memory_payload(memory),
        "candidate": _candidate_payload(service.get_candidate(candidate_id)),
    }


@router.post("/memories/candidates/{candidate_id}/reject")
def reject_candidate(candidate_id: str, request: RejectRequest) -> dict[str, Any]:
    """Reject a pending candidate with a required reason; stays auditable."""

    settings = _require_settings()
    try:
        rejected = _service(settings).reject(candidate_id, request.reason)
    except UnknownCandidateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidCandidateStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _candidate_payload(rejected)


@router.post("/memories/candidates/{candidate_id}/edit")
def edit_candidate(candidate_id: str, request: EditRequest) -> dict[str, Any]:
    """Set pending-edit text; the candidate stays pending."""

    settings = _require_settings()
    try:
        edited = _service(settings).edit_candidate(candidate_id, request.edited_text)
    except UnknownCandidateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidCandidateStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _candidate_payload(edited)


@router.get("/memories")
def list_memories(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    logical_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Memory versions in approval order, or one logical memory's versions."""

    settings = _require_settings()
    service = _service(settings)
    if logical_id is not None:
        versions = service.memory_versions(logical_id)
        return {
            "memories": [_memory_payload(memory) for memory in versions],
            "total": len(versions),
        }
    memories = service.list_memories(limit=10000, offset=0)
    return {
        "memories": [
            _memory_payload(memory) for memory in memories[offset : offset + limit]
        ],
        "total": len(memories),
    }


@router.get("/memories/{memory_id}")
def get_memory(memory_id: str) -> dict[str, Any]:
    """One memory version, or 404 when unknown."""

    settings = _require_settings()
    try:
        return _memory_payload(_service(settings).get_memory(memory_id))
    except UnknownMemoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/memories/{logical_id}/supersede")
def supersede_memory(logical_id: str, request: SupersedeRequest) -> dict[str, Any]:
    """Create the next version reusing the latest version's source."""

    settings = _require_settings()
    service = _service(settings)
    try:
        memory = service.supersede_latest(
            logical_id,
            request.text,
            category=request.category,
            confidence=request.confidence,
        )
    except UnknownMemoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidCandidateStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _memory_payload(memory)


@router.get("/memories/{memory_id}/provenance")
def memory_provenance(memory_id: str) -> dict[str, Any]:
    """Resolved provenance chain for one memory version.

    Only the linked conversation is exposed — never unrelated threads.
    """

    settings = _require_settings()
    service = _service(settings)
    try:
        memory = service.get_memory(memory_id)
    except UnknownMemoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    source = memory.source
    conversation = ConversationService(
        ConversationStore(settings.paths.manifest_root)
    ).get_conversation(source.conversation_id)
    return {
        "memory_id": memory.id,
        "memory": _memory_payload(memory),
        "source": {
            "conversation_id": source.conversation_id,
            "message_id": source.message_id,
            "seq": source.seq,
            "quoted_text": source.grounding.quoted_text,
            "evidence": (
                source.evidence.model_dump(mode="json") if source.evidence else None
            ),
        },
        "conversation": (
            {
                "id": conversation.id,
                "title": conversation.title,
                "status": conversation.status.value,
            }
            if conversation is not None
            else None
        ),
    }
