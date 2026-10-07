"""Tests for the V2.1-A conversation HTTP API (fake QA, tmp stores)."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.application.qa_workflow import OUTCOME_ANSWERED, QAAnswer, SourceCitation
from app.core.config import Settings
from app.domain.conversation import Message
from app.infrastructure.search import SearchHit
from app.interfaces.web import deps
from app.interfaces.web.server import create_app


class ScriptedQA:
    """Fake QA workflow: scripted answers, history-accepting signature."""

    def __init__(self, answer: QAAnswer | Exception) -> None:
        self._answer = answer

    def ask(
        self,
        question: str,
        *,
        top_k: int = 5,
        history: Sequence[Message] = (),
    ) -> QAAnswer:
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer


def _answer() -> QAAnswer:
    hit = SearchHit(text="body", source="a.md", score=0.9, entry_id="a.md::0")
    return QAAnswer(
        answer="grounded answer",
        sources=[hit],
        model="qwen3:8b",
        citations=[SourceCitation(number=1, hit=hit)],
    )


@pytest.fixture()
def client(tmp_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A TestClient with isolated settings and a scripted QA workflow."""

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
    monkeypatch.setattr(deps, "get_qa_workflow", lambda: ScriptedQA(_answer()))
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
    yield TestClient(create_app())
    _clear()


def _create(client: TestClient, title: str | None = None) -> dict[str, Any]:
    body: dict[str, object] = {}
    if title is not None:
        body["title"] = title
    response = client.post("/api/conversations", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_get_conversation(client: TestClient) -> None:
    created = _create(client, "hello")

    assert created["title"] == "hello"
    assert created["status"] == "active"
    assert created["message_count"] == 0
    fetched = client.get(f"/api/conversations/{created['id']}").json()

    assert fetched == created


def test_create_default_title(client: TestClient) -> None:
    created = _create(client)

    assert created["title"] == "New conversation"


def test_get_unknown_is_404(client: TestClient) -> None:
    assert client.get("/api/conversations/ghost").status_code == 404


def test_list_pagination(client: TestClient) -> None:
    first = _create(client, "one")
    _create(client, "two")

    body = client.get("/api/conversations", params={"limit": 1}).json()

    assert body["total"] == 2
    assert [row["id"] for row in body["conversations"]] == [first["id"]]
    second_page = client.get(
        "/api/conversations", params={"limit": 1, "offset": 1}
    ).json()
    assert [row["id"] for row in second_page["conversations"]] != [first["id"]]
    assert client.get("/api/conversations", params={"limit": 101}).status_code == 422


def test_append_and_list_messages(client: TestClient) -> None:
    created = _create(client)

    first = client.post(
        f"/api/conversations/{created['id']}/messages",
        json={"role": "user", "content": "hi"},
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"/api/conversations/{created['id']}/messages",
        json={"role": "user", "content": "there"},
    )

    assert second.json()["seq"] == first.json()["seq"] + 1
    body = client.get(f"/api/conversations/{created['id']}/messages").json()
    assert body["total"] == 2
    assert [row["content"] for row in body["messages"]] == ["hi", "there"]


def test_forged_assistant_message_rejected(client: TestClient) -> None:
    created = _create(client)

    for role in ("assistant", "system", "tool"):
        response = client.post(
            f"/api/conversations/{created['id']}/messages",
            json={"role": role, "content": "forged"},
        )
        assert response.status_code == 422, role


def test_message_validation(client: TestClient) -> None:
    created = _create(client)

    assert (
        client.post(
            f"/api/conversations/{created['id']}/messages",
            json={"role": "user", "content": "   "},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/conversations/{created['id']}/messages",
            json={"role": "user", "content": "x" * 8001},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/conversations/ghost/messages",
            json={"role": "user", "content": "hi"},
        ).status_code
        == 404
    )


def test_archive_blocks_writes(client: TestClient) -> None:
    created = _create(client)

    archived = client.post(f"/api/conversations/{created['id']}/archive").json()
    assert archived["status"] == "archived"
    again = client.post(f"/api/conversations/{created['id']}/archive")
    assert again.status_code == 200
    assert (
        client.post(
            f"/api/conversations/{created['id']}/messages",
            json={"role": "user", "content": "hi"},
        ).status_code
        == 409
    )
    assert client.post("/api/conversations/ghost/archive").status_code == 404


def test_ask_persists_both_messages(client: TestClient) -> None:
    created = _create(client)

    response = client.post(
        f"/api/conversations/{created['id']}/ask",
        json={"question": "what is this?"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user_message"]["content"] == "what is this?"
    assert body["assistant_message"]["content"] == "grounded answer"
    assert body["assistant_message"]["evidence"]["outcome"] == OUTCOME_ANSWERED
    assert body["assistant_message"]["evidence"]["citations"][0]["source"] == "a.md"
    history = client.get(f"/api/conversations/{created['id']}/messages").json()
    assert history["total"] == 2


def test_ask_archived_is_409(client: TestClient) -> None:
    created = _create(client)
    client.post(f"/api/conversations/{created['id']}/archive")

    response = client.post(
        f"/api/conversations/{created['id']}/ask", json={"question": "what?"}
    )

    assert response.status_code == 409


def test_ask_unknown_is_404(client: TestClient) -> None:
    response = client.post("/api/conversations/ghost/ask", json={"question": "what?"})

    assert response.status_code == 404
