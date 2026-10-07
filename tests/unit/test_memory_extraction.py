"""Extraction tests: user-origin rules, failure exclusion, model distrust."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.application.conversation_service import ConversationService
from app.application.memory_service import (
    ExtractionError,
    MemoryService,
    UnknownCandidateError,
)
from app.domain.conversation import EvidenceSnapshot, MessageRole
from app.domain.memory import CandidateStatus, MemoryReview, ReviewDecision
from app.infrastructure.conversations import ConversationStore
from app.infrastructure.memories import CandidateStore, MemoryStore
from app.prompts.memory import ProposedMemorySet


class ScriptedGenerate:
    """Fake structured model: each call consumes the next scripted response."""

    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self, system_prompt: str, user_prompt: str, model: type[ProposedMemorySet]
    ) -> Any:
        self.calls.append((system_prompt, user_prompt))
        if not self._responses:
            raise AssertionError("Fake model called more times than scripted.")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return model.model_validate(response)


def _proposal(
    message_id: str = "msg-1",
    seq: int = 1,
    text: str = "User prefers dark mode.",
    category: str = "preference",
) -> dict[str, object]:
    return {
        "text": text,
        "category": category,
        "confidence": 0.9,
        "message_id": message_id,
        "seq": seq,
        "quoted_text": "I prefer dark mode.",
    }


def _service(
    tmp_path: Path, responses: list[object]
) -> tuple[MemoryService, ConversationService, ScriptedGenerate]:
    root = tmp_path / "manifests"
    conversations = ConversationService(ConversationStore(root))
    fake = ScriptedGenerate(responses)
    service = MemoryService(
        CandidateStore(root), MemoryStore(root), conversations, fake
    )
    return service, conversations, fake


def test_eligible_categories_become_candidates(tmp_path: Path) -> None:
    categories = ["fact", "preference", "goal", "decision", "constraint", "project", "correction"]
    service, conversations, fake = _service(tmp_path, [{"candidates": "placeholder"}])
    conversation = conversations.create_conversation("t")
    user = conversations._store.append_message(
        conversation.id, MessageRole.USER, "durable content"
    )
    fake._responses = [  # type: ignore[union-attr]
        {
            "candidates": [
                _proposal(user.id, user.seq, f"claim {i}", category)
                for i, category in enumerate(categories)
            ]
        }
    ]
    created = service.extract(conversation.id)

    assert len(created) == 7
    assert all(c.status is CandidateStatus.PENDING for c in created)


def test_empty_model_response_yields_nothing(tmp_path: Path) -> None:
    service, conversations, fake = _service(tmp_path, [{"candidates": []}])
    conversation = conversations.create_conversation("t")
    conversations._store.append_message(conversation.id, MessageRole.USER, "hi there")

    assert service.extract(conversation.id) == []


def test_question_small_talk_transient_excluded(tmp_path: Path) -> None:
    # A well-behaved model proposes nothing for non-durable content; the
    # service persists exactly what the model proposes — no more.
    service, conversations, fake = _service(tmp_path, [{"candidates": []}])
    conversation = conversations.create_conversation("t")
    conversations._store.append_message(
        conversation.id, MessageRole.USER, "remind me in five minutes?"
    )

    assert service.extract(conversation.id) == []
    prompt = fake.calls[0][1]
    assert "transient" in prompt and "small talk" in prompt


def test_assistant_only_claim_excluded(tmp_path: Path) -> None:
    service, conversations, fake = _service(
        tmp_path,
        [
            {
                "candidates": [
                    _proposal("assistant-msg", 2, text="Assistant claim here.")
                ]
            }
        ],
    )
    conversation = conversations.create_conversation("t")
    store = conversations._store
    user = store.append_message(conversation.id, MessageRole.USER, "tell me stuff")
    store.append_message(conversation.id, MessageRole.ASSISTANT, "stuff is great")

    created = service.extract(conversation.id)

    assert created == []
    assert user.content == "tell me stuff"


def test_user_confirmed_assistant_claim_eligible(tmp_path: Path) -> None:
    service, conversations, fake = _service(tmp_path, [{"candidates": "placeholder"}])
    conversation = conversations.create_conversation("t")
    store = conversations._store
    store.append_message(conversation.id, MessageRole.USER, "what should I drink?")
    store.append_message(conversation.id, MessageRole.ASSISTANT, "try tea")
    confirmed = store.append_message(conversation.id, MessageRole.USER, "yes, tea daily")

    fake._responses = [  # type: ignore[union-attr]
        {
            "candidates": [
                _proposal(
                    confirmed.id, confirmed.seq, text="User drinks tea daily."
                )
            ]
        }
    ]
    created = service.extract(conversation.id)

    assert len(created) == 1
    assert created[0].grounding.message_id == confirmed.id
    assert created[0].text == "User drinks tea daily."


def test_failed_assistant_message_yields_zero_candidates(tmp_path: Path) -> None:
    service, conversations, fake = _service(
        tmp_path,
        [{"candidates": [_proposal("failed-id", 2, text="Bogus claim.")]}],
    )
    conversation = conversations.create_conversation("t")
    store = conversations._store
    store.append_message(conversation.id, MessageRole.USER, "answer me")
    failed = store.append_message(
        conversation.id,
        MessageRole.ASSISTANT,
        "[assistant generation failed]",
        evidence=EvidenceSnapshot(error="RuntimeError: down"),
    )
    assert failed.evidence is not None and failed.evidence.error is not None
    # Repair the scripted id to the real failed message id.
    fake._responses = [  # type: ignore[union-attr]
        {
            "candidates": [
                _proposal(failed.id, failed.seq, text="Bogus claim.")
            ]
        }
    ]

    assert service.extract(conversation.id) == []


def test_grounding_must_point_at_user_message(tmp_path: Path) -> None:
    service, conversations, fake = _service(
        tmp_path,
        [
            {
                "candidates": [
                    _proposal("ghost-id", 99, text="Invented claim."),
                    _proposal("assistant-mid", 2, text="Assistant claim."),
                ]
            }
        ],
    )
    conversation = conversations.create_conversation("t")
    store = conversations._store
    store.append_message(conversation.id, MessageRole.USER, "real user fact here")
    assistant = store.append_message(conversation.id, MessageRole.ASSISTANT, "ok")
    assert assistant.id != "assistant-mid"

    assert service.extract(conversation.id) == []


def test_evidence_does_not_substitute_for_grounding(tmp_path: Path) -> None:
    service, conversations, fake = _service(
        tmp_path, [{"candidates": [_proposal("msg-x", 1)]}]
    )
    conversation = conversations.create_conversation("t")
    user = conversations._store.append_message(
        conversation.id, MessageRole.USER, "I prefer dark mode."
    )

    created = service.extract(conversation.id)

    # The fake grounded on an unknown id: dropped despite quoted text.
    assert created == []
    assert user.content == "I prefer dark mode."


def test_multiple_candidates_and_within_run_dedup(tmp_path: Path) -> None:
    service, conversations, fake = _service(
        tmp_path,
        [
            {
                "candidates": [
                    _proposal("m1", 1, text="Same claim."),
                    _proposal("m1", 1, text="Same claim."),
                    _proposal("m2", 2, text="Other claim."),
                ]
            }
        ],
    )
    conversation = conversations.create_conversation("t")
    store = conversations._store
    first = store.append_message(conversation.id, MessageRole.USER, "first fact")
    second = store.append_message(conversation.id, MessageRole.USER, "second fact")
    fake._responses = [  # type: ignore[union-attr]
        {
            "candidates": [
                _proposal(first.id, first.seq, text="Same claim."),
                _proposal(first.id, first.seq, text="Same claim."),
                _proposal(second.id, second.seq, text="Other claim."),
            ]
        }
    ]

    created = service.extract(conversation.id)

    assert [c.text for c in created] == ["Same claim.", "Other claim."]


def test_rejected_candidate_reconsidered_with_new_evidence(tmp_path: Path) -> None:
    service, conversations, fake = _service(tmp_path, [{"candidates": []}])
    conversation = conversations.create_conversation("t")
    first = conversations._store.append_message(
        conversation.id, MessageRole.USER, "I like tea."
    )
    fake._responses = [  # type: ignore[union-attr]
        {"candidates": [_proposal(first.id, first.seq, text="User likes tea.")]}
    ]
    [old] = service.extract(conversation.id)
    rejected = type(old).model_validate(
        {
            **old.model_dump(),
            "status": CandidateStatus.REJECTED,
            "review": MemoryReview(
                decision=ReviewDecision.REJECTED,
                reviewed_at=datetime.now(UTC),
                reason="too vague",
            ).model_dump(),
        }
    )
    service._candidates.save(rejected)

    # Genuinely new user evidence re-proposes the same claim: allowed.
    second = conversations._store.append_message(
        conversation.id, MessageRole.USER, "I drink tea every single morning."
    )
    fake._responses = [  # type: ignore[union-attr]
        {"candidates": [_proposal(second.id, second.seq, text="User likes tea.")]}
    ]
    created = service.extract(conversation.id)

    assert len(created) == 1
    assert created[0].id != old.id
    assert created[0].grounding.message_id == second.id


def test_extraction_is_conversation_scoped(tmp_path: Path) -> None:
    service, conversations, fake = _service(
        tmp_path, [{"candidates": [_proposal("other-id", 1, text="Other claim.")]}]
    )
    mine = conversations.create_conversation("mine")
    conversations._store.append_message(mine.id, MessageRole.USER, "my fact")
    other = conversations.create_conversation("other")
    conversations._store.append_message(other.id, MessageRole.USER, "other fact")

    assert service.extract(mine.id) == []


def test_retrieved_context_not_supplied(tmp_path: Path) -> None:
    service, conversations, fake = _service(tmp_path, [{"candidates": []}])
    conversation = conversations.create_conversation("t")
    conversations._store.append_message(conversation.id, MessageRole.USER, "a fact")

    service.extract(conversation.id)

    prompt = fake.calls[0][1]
    assert "[SOURCE" not in prompt
    assert "chunk" not in prompt.lower()
    assert "a fact" in prompt


def test_model_cannot_assign_status_or_ids(tmp_path: Path) -> None:
    service, conversations, fake = _service(
        tmp_path,
        [
            {
                "candidates": [
                    {
                        "text": "User likes tea.",
                        "category": "preference",
                        "confidence": 0.9,
                        "message_id": "mid",
                        "seq": 1,
                        "quoted_text": "tea please",
                        "status": "approved",
                        "id": "hacked",
                    }
                ]
            },
            {"candidates": [_proposal("mid", 1, text="User likes tea.")]},
        ],
    )
    conversation = conversations.create_conversation("t")
    user = conversations._store.append_message(conversation.id, MessageRole.USER, "tea")

    # First response carries privileged fields: schema rejects, retry succeeds.
    fake._responses[1]["candidates"][0]["message_id"] = user.id  # type: ignore[index]
    created = service.extract(conversation.id)

    assert len(created) == 1
    assert created[0].id != "hacked"
    assert created[0].status.value == "pending"
    assert len(fake.calls) == 2


def test_candidate_ids_are_server_assigned(tmp_path: Path) -> None:
    service, conversations, fake = _service(
        tmp_path, [{"candidates": [_proposal("m", 1)]}]
    )
    conversation = conversations.create_conversation("t")
    user = conversations._store.append_message(conversation.id, MessageRole.USER, "x")
    fake._responses = [  # type: ignore[union-attr]
        {"candidates": [_proposal(user.id, user.seq)]}
    ]

    [created] = service.extract(conversation.id)

    assert created.id != user.id
    assert created.conversation_id == conversation.id
    assert created.extracted_at is not None


def test_transport_failure_fails_immediately(tmp_path: Path) -> None:
    service, conversations, fake = _service(tmp_path, [RuntimeError("ollama down")])
    conversation = conversations.create_conversation("t")
    conversations._store.append_message(conversation.id, MessageRole.USER, "fact")

    with pytest.raises(ExtractionError):
        service.extract(conversation.id)

    assert len(fake.calls) == 1


def test_malformed_twice_fails(tmp_path: Path) -> None:
    bad = {"candidates": [{"text": "", "category": "fact"}]}
    service, conversations, fake = _service(tmp_path, [bad, bad])
    conversation = conversations.create_conversation("t")
    conversations._store.append_message(conversation.id, MessageRole.USER, "fact")

    with pytest.raises(ExtractionError):
        service.extract(conversation.id)

    assert len(fake.calls) == 2


def test_unknown_conversation_raises(tmp_path: Path) -> None:
    from app.application.conversation_service import UnknownConversationError

    service, _, fake = _service(tmp_path, [])

    with pytest.raises(UnknownConversationError):
        service.extract("ghost")


def test_empty_conversation_extracts_nothing(tmp_path: Path) -> None:
    service, conversations, fake = _service(tmp_path, [])
    conversation = conversations.create_conversation("t")

    assert service.extract(conversation.id) == []
    assert fake.calls == []


def test_only_assistant_messages_extract_nothing(tmp_path: Path) -> None:
    service, conversations, fake = _service(tmp_path, [])
    conversation = conversations.create_conversation("t")
    conversations._store.append_message(conversation.id, MessageRole.ASSISTANT, "hi")

    assert service.extract(conversation.id) == []
    assert fake.calls == []


def test_get_unknown_candidate_raises(tmp_path: Path) -> None:
    service, _, fake = _service(tmp_path, [])

    with pytest.raises(UnknownCandidateError):
        service.get_candidate("ghost")
