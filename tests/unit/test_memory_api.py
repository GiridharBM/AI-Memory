"""Tests for the V2.1-B memory HTTP API (fake LLM, tmp stores)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.application.conversation_service import ConversationService
from app.core.config import Settings
from app.domain.conversation import EvidenceSnapshot, Message, MessageRole
from app.infrastructure.conversations import ConversationStore
from app.interfaces.web import deps
from app.interfaces.web.server import create_app


class ScriptedGenerate:
    """Fake structured model with a mutable script."""

    def __init__(self, responses: list[object] | None = None) -> None:
        self.responses: list[object] = list(responses or [])
        self.calls = 0

    def __call__(
        self, system_prompt: str, user_prompt: str, model: type[BaseModel]
    ) -> Any:
        self.calls += 1
        if not self.responses:
            raise AssertionError("Fake model called more times than scripted.")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return model.model_validate(response)


class FakeOllamaClient:
    """OllamaClient stand-in routing generate_json to the scripted fake."""

    fake: ScriptedGenerate | None = None

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def generate_json(self, request: object, response_model: type) -> Any:
        assert FakeOllamaClient.fake is not None
        return FakeOllamaClient.fake("system", "prompt", response_model)


@pytest.fixture()
def client(
    tmp_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """A TestClient with isolated settings and a scripted extraction model."""

    cached = (
        deps.get_settings,
        deps.get_search_service,
        deps.get_qa_workflow,
        deps.get_vector_store,
    )

    def _clear() -> None:
        for fn in cached:
            fn.cache_clear()
        monkeypatch.setattr(deps, "_health_cache", None)

    _clear()
    monkeypatch.setattr(deps, "get_settings", lambda: tmp_settings)
    monkeypatch.setattr(
        deps,
        "ollama_health",
        lambda **_kwargs: {
            "reachable": True,
            "model_present": True,
            "model": tmp_settings.ollama.model,
            "detail": str(tmp_settings.ollama.host),
        },
    )
    import app.interfaces.web.routes.memories as memory_routes

    monkeypatch.setattr(memory_routes, "OllamaClient", FakeOllamaClient)
    FakeOllamaClient.fake = ScriptedGenerate([])
    yield TestClient(create_app())
    _clear()
    FakeOllamaClient.fake = None


def _seed_user(
    tmp_settings: Settings, content: str = "I prefer dark mode."
) -> tuple[str, Message]:
    service = ConversationService(ConversationStore(tmp_settings.paths.manifest_root))
    conversation = service.create_conversation("t")
    user: Message = service._store.append_message(
        conversation.id, MessageRole.USER, content
    )
    return conversation.id, user


def _proposal(
    message_id: str, seq: int, text: str = "User prefers dark mode."
) -> dict[str, object]:
    return {
        "text": text,
        "category": "preference",
        "confidence": 0.9,
        "message_id": message_id,
        "seq": seq,
        "quoted_text": "I prefer dark mode.",
    }


def _extract(client: TestClient, conversation_id: str) -> dict[str, Any]:
    response = client.post("/api/memories/extract", json={"conversation_id": conversation_id})
    assert response.status_code == 201, response.text
    return response.json()


def test_extract_creates_pending_candidates(
    client: TestClient, tmp_settings: Settings
) -> None:
    conversation_id, user = _seed_user(tmp_settings)
    assert FakeOllamaClient.fake is not None
    FakeOllamaClient.fake.responses = [
        {"candidates": [_proposal(user.id, user.seq)]}
    ]

    body = _extract(client, conversation_id)

    assert body["total"] == 1
    candidate = body["candidates"][0]
    assert candidate["status"] == "pending"
    assert candidate["text"] == "User prefers dark mode."
    assert candidate["grounding"]["message_id"] == user.id
    assert candidate["conversation_id"] == conversation_id
    assert candidate["id"] != user.id


def test_extract_unknown_conversation_is_404(client: TestClient) -> None:
    response = client.post("/api/memories/extract", json={"conversation_id": "ghost"})

    assert response.status_code == 404


def test_extract_transport_failure_is_502(
    client: TestClient, tmp_settings: Settings
) -> None:
    conversation_id, _ = _seed_user(tmp_settings)
    assert FakeOllamaClient.fake is not None
    FakeOllamaClient.fake.responses = [RuntimeError("ollama down")]

    response = client.post("/api/memories/extract", json={"conversation_id": conversation_id})

    assert response.status_code == 502


def test_extract_empty_body_is_422(client: TestClient) -> None:
    assert client.post("/api/memories/extract", json={}).status_code == 422
    assert (
        client.post(
            "/api/memories/extract", json={"conversation_id": "x", "extra": 1}
        ).status_code
        == 422
    )


def test_list_and_get_candidate(client: TestClient, tmp_settings: Settings) -> None:
    conversation_id, user = _seed_user(tmp_settings)
    assert FakeOllamaClient.fake is not None
    FakeOllamaClient.fake.responses = [
        {"candidates": [_proposal(user.id, user.seq)]}
    ]
    created = _extract(client, conversation_id)["candidates"][0]

    listed = client.get("/api/memories/candidates").json()
    assert listed["total"] == 1
    assert listed["candidates"][0]["id"] == created["id"]
    fetched = client.get(f"/api/memories/candidates/{created['id']}").json()
    assert fetched == created
    assert client.get("/api/memories/candidates/ghost").status_code == 404


def test_approve_creates_memory(client: TestClient, tmp_settings: Settings) -> None:
    conversation_id, user = _seed_user(tmp_settings)
    assert FakeOllamaClient.fake is not None
    FakeOllamaClient.fake.responses = [
        {"candidates": [_proposal(user.id, user.seq)]}
    ]
    created = _extract(client, conversation_id)["candidates"][0]

    response = client.post(f"/api/memories/candidates/{created['id']}/approve", json={})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["memory"]["version"] == 1
    assert body["memory"]["text"] == "User prefers dark mode."
    assert body["memory"]["source"]["message_id"] == user.id
    assert body["candidate"]["status"] == "approved"


def test_approve_twice_is_409(client: TestClient, tmp_settings: Settings) -> None:
    conversation_id, user = _seed_user(tmp_settings)
    assert FakeOllamaClient.fake is not None
    FakeOllamaClient.fake.responses = [
        {"candidates": [_proposal(user.id, user.seq)]}
    ]
    created = _extract(client, conversation_id)["candidates"][0]
    client.post(f"/api/memories/candidates/{created['id']}/approve", json={})

    assert (
        client.post(f"/api/memories/candidates/{created['id']}/approve", json={}).status_code
        == 409
    )
    assert client.post("/api/memories/candidates/ghost/approve", json={}).status_code == 404


def test_approve_with_edit(client: TestClient, tmp_settings: Settings) -> None:
    conversation_id, user = _seed_user(tmp_settings)
    assert FakeOllamaClient.fake is not None
    FakeOllamaClient.fake.responses = [
        {"candidates": [_proposal(user.id, user.seq)]}
    ]
    created = _extract(client, conversation_id)["candidates"][0]

    body = client.post(
        f"/api/memories/candidates/{created['id']}/approve",
        json={"edited_text": "User loves dark mode."},
    ).json()

    assert body["memory"]["text"] == "User loves dark mode."
    assert body["candidate"]["review"]["edited"] is True


def test_approve_privileged_fields_rejected(client: TestClient, tmp_settings: Settings) -> None:
    conversation_id, user = _seed_user(tmp_settings)
    assert FakeOllamaClient.fake is not None
    FakeOllamaClient.fake.responses = [
        {"candidates": [_proposal(user.id, user.seq)]}
    ]
    created = _extract(client, conversation_id)["candidates"][0]

    assert (
        client.post(
            f"/api/memories/candidates/{created['id']}/approve",
            json={"edited_text": "x", "status": "approved"},
        ).status_code
        == 422
    )


def test_reject_requires_reason_and_stays_auditable(
    client: TestClient, tmp_settings: Settings
) -> None:
    conversation_id, user = _seed_user(tmp_settings)
    assert FakeOllamaClient.fake is not None
    FakeOllamaClient.fake.responses = [
        {"candidates": [_proposal(user.id, user.seq)]}
    ]
    created = _extract(client, conversation_id)["candidates"][0]

    assert (
        client.post(
            f"/api/memories/candidates/{created['id']}/reject", json={}
        ).status_code
        == 422
    )
    rejected = client.post(
        f"/api/memories/candidates/{created['id']}/reject", json={"reason": "transient"}
    ).json()

    assert rejected["status"] == "rejected"
    assert rejected["review"]["reason"] == "transient"
    assert (
        client.post(
            f"/api/memories/candidates/{created['id']}/approve", json={}
        ).status_code
        == 409
    )


def test_edit_keeps_pending(client: TestClient, tmp_settings: Settings) -> None:
    conversation_id, user = _seed_user(tmp_settings)
    assert FakeOllamaClient.fake is not None
    FakeOllamaClient.fake.responses = [
        {"candidates": [_proposal(user.id, user.seq)]}
    ]
    created = _extract(client, conversation_id)["candidates"][0]

    edited = client.post(
        f"/api/memories/candidates/{created['id']}/edit",
        json={"edited_text": "User adores dark mode."},
    ).json()

    assert edited["status"] == "pending"
    assert edited["edited_text"] == "User adores dark mode."
    assert (
        client.post(
            f"/api/memories/candidates/{created['id']}/edit",
            json={"edited_text": "x" * 2001},
        ).status_code
        == 422
    )


def test_supersede_versions(client: TestClient, tmp_settings: Settings) -> None:
    conversation_id, user = _seed_user(tmp_settings)
    assert FakeOllamaClient.fake is not None
    FakeOllamaClient.fake.responses = [
        {"candidates": [_proposal(user.id, user.seq)]}
    ]
    created = _extract(client, conversation_id)["candidates"][0]
    first = client.post(
        f"/api/memories/candidates/{created['id']}/approve", json={}
    ).json()["memory"]

    second = client.post(
        f"/api/memories/{first['logical_id']}/supersede",
        json={"text": "User loves dark mode.", "category": "preference", "confidence": 0.95},
    ).json()

    assert second["version"] == 2
    assert second["logical_id"] == first["logical_id"]
    assert client.get(f"/api/memories/{first['id']}").json()["status"] == "superseded"
    versions = client.get(
        "/api/memories", params={"logical_id": first["logical_id"]}
    ).json()
    assert [row["version"] for row in versions["memories"]] == [1, 2]
    assert (
        client.post("/api/memories/ghost/supersede", json={
            "text": "x", "category": "fact", "confidence": 0.5}).status_code == 404
    )


def test_memories_list_get_provenance(client: TestClient, tmp_settings: Settings) -> None:
    conversation_id, user = _seed_user(tmp_settings)
    assert FakeOllamaClient.fake is not None
    FakeOllamaClient.fake.responses = [
        {"candidates": [_proposal(user.id, user.seq)]}
    ]
    created = _extract(client, conversation_id)["candidates"][0]
    memory = client.post(
        f"/api/memories/candidates/{created['id']}/approve", json={}
    ).json()["memory"]

    listed = client.get("/api/memories").json()
    assert listed["total"] == 1
    fetched = client.get(f"/api/memories/{memory['id']}").json()
    assert fetched["id"] == memory["id"]
    assert client.get("/api/memories/ghost").status_code == 404

    provenance = client.get(f"/api/memories/{memory['id']}/provenance").json()
    assert provenance["memory_id"] == memory["id"]
    assert provenance["source"]["message_id"] == user.id
    assert provenance["source"]["quoted_text"] == "I prefer dark mode."
    assert provenance["conversation"]["id"] == conversation_id
    assert client.get("/api/memories/ghost/provenance").status_code == 404


def test_failed_message_excluded_via_api(client: TestClient, tmp_settings: Settings) -> None:
    service = ConversationService(ConversationStore(tmp_settings.paths.manifest_root))
    conversation = service.create_conversation("t")
    service._store.append_message(conversation.id, MessageRole.USER, "answer me")
    failed = service._store.append_message(
        conversation.id,
        MessageRole.ASSISTANT,
        "[assistant generation failed]",
        evidence=EvidenceSnapshot(error="RuntimeError: down"),
    )
    assert FakeOllamaClient.fake is not None
    FakeOllamaClient.fake.responses = [
        {"candidates": [
            {
                "text": "Bogus.",
                "category": "fact",
                "confidence": 0.9,
                "message_id": failed.id,
                "seq": failed.seq,
                "quoted_text": "x",
            }
        ]}
    ]

    body = _extract(client, conversation.id)

    assert body["total"] == 0
