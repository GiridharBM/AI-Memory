"""Application service for V2.1-B memory extraction and lifecycle.

Explicit per-conversation extraction only: no daemon, no background watcher,
no automatic runs. The model proposes content; the service assigns every
privileged field (identifiers, timestamps, status, provenance links) after
validation. Human approval is the only path from candidate to memory, and
approved memories stay durable records — retrieval integration is deferred.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from pydantic import ValidationError

from app.application.conversation_service import ConversationService
from app.domain.conversation import Message, MessageRole
from app.domain.memory import (
    MAX_MEMORY_CHARS,
    CandidateStatus,
    Memory,
    MemoryCandidate,
    MemoryCategory,
    MemoryGrounding,
    MemoryReview,
    MemorySource,
    MemoryStatus,
    ReviewDecision,
)
from app.infrastructure.memories import CandidateStore, MemoryStore
from app.prompts.generation import add_generation_retry_instruction
from app.prompts.memory import (
    EXTRACTION_SYSTEM_PROMPT,
    ProposedMemorySet,
    build_extraction_user_prompt,
)

# (system prompt, user prompt, response model) -> parsed proposals. Same seam
# shape as every generation handler: a thin lambda over
# OllamaClient.generate_json binds the real client without this service
# importing provider code.
GenerateProposals = Callable[[str, str, "type[ProposedMemorySet]"], ProposedMemorySet]

MAX_EXTRACTION_CANDIDATES = 10


class MemoryServiceError(ValueError):
    """Base class for memory service failures."""


class UnknownCandidateError(MemoryServiceError):
    """No candidate exists for the requested id."""


class InvalidCandidateStateError(MemoryServiceError):
    """The candidate is not in a state allowing the requested transition."""


class UnknownMemoryError(MemoryServiceError):
    """No memory exists for the requested id or logical id."""


class ExtractionError(MemoryServiceError):
    """Conversation memory extraction failed."""


def _transcript(messages: Sequence[Message]) -> str:
    lines = []
    for message in messages:
        text = " ".join(message.content.split())
        lines.append(f"[{message.role.value} seq={message.seq} id={message.id}] {text}")
    return "\n".join(lines)


class MemoryService:
    """Extract candidates from conversations; steward their lifecycle."""

    def __init__(
        self,
        candidates: CandidateStore,
        memories: MemoryStore,
        conversations: ConversationService,
        generate_json: GenerateProposals,
        *,
        max_candidates: int = MAX_EXTRACTION_CANDIDATES,
    ) -> None:
        self._candidates = candidates
        self._memories = memories
        self._conversations = conversations
        self._generate_json = generate_json
        self._max_candidates = max_candidates
        self._lock = threading.Lock()

    def extract(self, conversation_id: str) -> list[MemoryCandidate]:
        """Propose candidates from one conversation's eligible user messages.

        Unknown conversations raise; conversations with no eligible content
        return []. Failed assistant generations are skipped via their
        structured evidence flag, never by matching visible prose.
        """

        history = self._conversations.recent_messages(conversation_id)
        if not any(message.role is MessageRole.USER for message in history):
            return []
        # Failed assistant generations carry a structured evidence flag;
        # they are skipped here explicitly, never by matching visible prose.
        failed_ids = {
            message.id
            for message in history
            if message.evidence is not None and message.evidence.error is not None
        }
        by_id = {message.id: message for message in history}
        prompt = build_extraction_user_prompt(
            conversation_id,
            _transcript(history),
            max_candidates=self._max_candidates,
        )
        proposals = self._propose_with_retry(prompt)
        created: list[MemoryCandidate] = []
        seen_texts: set[str] = set()
        for proposal in proposals.candidates[: self._max_candidates]:
            if proposal.message_id in failed_ids:
                continue
            message = by_id.get(proposal.message_id)
            if message is None or message.role is not MessageRole.USER:
                continue
            if message.seq != proposal.seq:
                continue
            try:
                grounding = MemoryGrounding(
                    conversation_id=conversation_id,
                    message_id=message.id,
                    seq=message.seq,
                    quoted_text=proposal.quoted_text,
                )
                candidate = MemoryCandidate.propose(
                    proposal.text,
                    proposal.category,
                    proposal.confidence,
                    grounding,
                )
            except Exception:
                continue
            if candidate.text in seen_texts:
                continue
            seen_texts.add(candidate.text)
            created.append(self._candidates.save(candidate))
        return created

    def _propose_with_retry(self, prompt: str) -> ProposedMemorySet:
        last_error: Exception | None = None
        current = prompt
        for _ in range(2):
            try:
                return self._generate_json(
                    EXTRACTION_SYSTEM_PROMPT, current, ProposedMemorySet
                )
            except ValidationError as exc:
                last_error = exc
            except Exception as exc:
                raise ExtractionError(f"Memory extraction failed: {exc}") from exc
            current = add_generation_retry_instruction(prompt)
        raise ExtractionError(f"Memory extraction failed after retry: {last_error}")

    def get_candidate(self, candidate_id: str) -> MemoryCandidate:
        """Return one candidate; raises when unknown."""

        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise UnknownCandidateError(f"Unknown memory candidate: {candidate_id}.")
        return candidate

    def list_candidates(self, limit: int = 50, offset: int = 0) -> list[MemoryCandidate]:
        """Candidates in deterministic extraction order (paginated)."""

        return self._candidates.list(limit=limit, offset=offset)

    def approve(
        self, candidate_id: str, *, edited_text: str | None = None
    ) -> Memory:
        """Approve a pending candidate, creating Memory v1. Rejects otherwise."""

        with self._lock:
            candidate = self.get_candidate(candidate_id)
            if candidate.status is not CandidateStatus.PENDING:
                raise InvalidCandidateStateError(
                    f"Candidate is {candidate.status.value}, not pending."
                )
            text = candidate.text
            edited = False
            if edited_text is not None:
                cleaned = " ".join(edited_text.split())
                if not cleaned:
                    raise InvalidCandidateStateError(
                        "Edited candidate text must not be empty."
                    )
                if len(cleaned) > MAX_MEMORY_CHARS:
                    raise InvalidCandidateStateError(
                        f"Edited text must be at most {MAX_MEMORY_CHARS} characters."
                    )
                text, edited = cleaned, True
            review = MemoryReview(
                decision=ReviewDecision.APPROVED,
                reviewed_at=datetime.now(UTC),
                edited=edited,
                edited_text=text if edited else None,
            )
            decided = MemoryCandidate.model_validate(
                {**candidate.model_dump(), "status": CandidateStatus.APPROVED,
                 "review": review.model_dump()}
            )
            memory = Memory.create(
                text,
                candidate.category,
                candidate.confidence,
                MemorySource(
                    conversation_id=candidate.conversation_id,
                    message_id=candidate.message_id,
                    seq=candidate.seq,
                    grounding=candidate.grounding,
                    evidence=candidate.evidence,
                ),
            )
            self._memories.save(memory)
            self._candidates.save(decided)
            return memory

    def reject(self, candidate_id: str, reason: str) -> MemoryCandidate:
        """Reject a pending candidate with a required reason; stays auditable."""

        if not isinstance(reason, str) or not reason.strip():
            raise InvalidCandidateStateError("Rejection requires a reason.")
        with self._lock:
            candidate = self.get_candidate(candidate_id)
            if candidate.status is not CandidateStatus.PENDING:
                raise InvalidCandidateStateError(
                    f"Candidate is {candidate.status.value}, not pending."
                )
            rejected = MemoryCandidate.model_validate(
                {
                    **candidate.model_dump(),
                    "status": CandidateStatus.REJECTED,
                    "review": MemoryReview(
                        decision=ReviewDecision.REJECTED,
                        reviewed_at=datetime.now(UTC),
                        reason=reason.strip(),
                    ).model_dump(),
                }
            )
            return self._candidates.save(rejected)

    def edit_candidate(self, candidate_id: str, edited_text: str) -> MemoryCandidate:
        """Set pending-edit text on a pending candidate; stays pending."""

        with self._lock:
            candidate = self.get_candidate(candidate_id)
            if candidate.status is not CandidateStatus.PENDING:
                raise InvalidCandidateStateError(
                    f"Candidate is {candidate.status.value}, not pending."
                )
            if not isinstance(edited_text, str) or not edited_text.strip():
                raise InvalidCandidateStateError("Edited candidate text must not be empty.")
            cleaned = " ".join(edited_text.split())
            if len(cleaned) > MAX_MEMORY_CHARS:
                raise InvalidCandidateStateError(
                    f"Edited text must be at most {MAX_MEMORY_CHARS} characters."
                )
            return self._candidates.save(
                MemoryCandidate.model_validate(
                    {**candidate.model_dump(), "edited_text": cleaned}
                )
            )

    def get_memory(self, memory_id: str) -> Memory:
        """Return one memory version; raises when unknown."""

        memory = self._memories.get(memory_id)
        if memory is None:
            raise UnknownMemoryError(f"Unknown memory: {memory_id}.")
        return memory

    def list_memories(self, limit: int = 50, offset: int = 0) -> list[Memory]:
        """Memory versions in deterministic approval order (paginated)."""

        return self._memories.list(limit=limit, offset=offset)

    def active_memories(self) -> Sequence[Memory]:
        """Every ACTIVE approved memory, oldest approval first.

        Read-only lifecycle view for runtime memory context: superseded
        versions are excluded here, never mutated. Delegates to the store
        like the other list methods.
        """

        return self._memories.active_memories()

    def memory_versions(self, logical_id: str) -> list[Memory]:
        """Every stored version of one logical memory, oldest version first."""

        return self._memories.versions(logical_id)

    def supersede(
        self,
        logical_id: str,
        text: str,
        *,
        category: MemoryCategory,
        confidence: float,
        source: MemorySource,
    ) -> Memory:
        """Create the next version; the previous active version is preserved."""

        with self._lock:
            versions = self._memories.versions(logical_id)
            if not versions:
                raise UnknownMemoryError(f"Unknown logical memory: {logical_id}.")
            previous = max(versions, key=lambda item: item.version)
            if previous.status is not MemoryStatus.ACTIVE:
                raise InvalidCandidateStateError(
                    "Only the active memory version can be superseded."
                )
            cleaned = " ".join(text.split()) if isinstance(text, str) else ""
            if not cleaned:
                raise InvalidCandidateStateError("Superseding text must not be empty.")
            if len(cleaned) > MAX_MEMORY_CHARS:
                raise InvalidCandidateStateError(
                    f"Superseding text must be at most {MAX_MEMORY_CHARS} characters."
                )
            current = Memory.create(
                cleaned,
                category,
                confidence,
                source,
                logical_id=logical_id,
                version=previous.version + 1,
                supersedes_id=previous.id,
            )
            retired = Memory.model_validate(
                {**previous.model_dump(), "status": MemoryStatus.SUPERSEDED}
            )
            self._memories.save(current)
            self._memories.save(retired)
            return current

    def supersede_latest(
        self,
        logical_id: str,
        text: str,
        *,
        category: MemoryCategory,
        confidence: float,
    ) -> Memory:
        """Supersede reusing the latest version's source (review-UI path)."""

        versions = self._memories.versions(logical_id)
        if not versions:
            raise UnknownMemoryError(f"Unknown logical memory: {logical_id}.")
        latest = max(versions, key=lambda item: item.version)
        return self.supersede(
            logical_id,
            text,
            category=category,
            confidence=confidence,
            source=latest.source,
        )
