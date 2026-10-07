"""Storage tests for V2.1-A conversations (ordering, recovery, isolation)."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from app.domain.conversation import ConversationStatus, MessageRole
from app.infrastructure.conversations import ConversationStore


def _store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(tmp_path / "manifests")


def test_create_and_get_conversation(tmp_path: Path) -> None:
    store = _store(tmp_path)

    created = store.create_conversation("hello")

    assert store.get_conversation(created.id) == created
    assert store.get_conversation("missing") is None
    assert store.list_conversations() == [created]


def test_missing_files_bootstrap_empty(tmp_path: Path) -> None:
    store = _store(tmp_path)

    assert store.list_conversations() == []
    assert store.get_messages("anything") == []
    assert store.count_messages("anything") == 0


def test_append_assigns_sequence_and_counts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    conversation = store.create_conversation("t")

    first = store.append_message(conversation.id, MessageRole.USER, "one")
    second = store.append_message(conversation.id, MessageRole.ASSISTANT, "two")

    assert (first.seq, second.seq) == (1, 2)
    assert store.count_messages(conversation.id) == 2
    assert store.get_conversation(conversation.id) is not None
    assert store.get_conversation(conversation.id).message_count == 2  # type: ignore[union-attr]


def test_messages_read_chronologically(tmp_path: Path) -> None:
    store = _store(tmp_path)
    conversation = store.create_conversation("t")
    for index in range(5):
        store.append_message(conversation.id, MessageRole.USER, f"m{index}")

    messages = store.get_messages(conversation.id, limit=10)

    assert [message.content for message in messages] == [f"m{i}" for i in range(5)]
    assert store.get_messages(conversation.id, limit=2, offset=1)[0].content == "m1"
    assert store.get_messages(conversation.id, limit=2, offset=4)[0].content == "m4"
    assert store.get_messages(conversation.id, limit=2, offset=9) == []


def test_append_unknown_conversation_raises(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with pytest.raises(KeyError):
        store.append_message("ghost", MessageRole.USER, "hi")


def test_restart_persistence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    conversation = store.create_conversation("t")
    store.append_message(conversation.id, MessageRole.USER, "one")
    store.append_message(conversation.id, MessageRole.ASSISTANT, "two")

    reloaded = ConversationStore(tmp_path / "manifests")

    assert reloaded.get_conversation(conversation.id) == store.get_conversation(
        conversation.id
    )
    assert [m.content for m in reloaded.get_messages(conversation.id)] == ["one", "two"]
    third = reloaded.append_message(conversation.id, MessageRole.USER, "three")
    assert third.seq == 3


def test_concurrent_appends_keep_unique_sequences(tmp_path: Path) -> None:
    store = _store(tmp_path)
    conversation = store.create_conversation("t")

    def worker(n: int) -> None:
        for i in range(10):
            store.append_message(conversation.id, MessageRole.USER, f"w{n}-{i}")

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    messages = store.get_messages(conversation.id, limit=100)
    assert len(messages) == 50
    assert sorted(message.seq for message in messages) == list(range(1, 51))


def test_corrupt_jsonl_lines_are_skipped(tmp_path: Path) -> None:
    store = _store(tmp_path)
    conversation = store.create_conversation("t")
    store.append_message(conversation.id, MessageRole.USER, "good")
    path = tmp_path / "manifests" / "conversation_messages.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write("not json{{{\n")
        handle.write("\n")
        handle.write('["not", "a", "message"]\n')

    reloaded = ConversationStore(tmp_path / "manifests")
    messages = reloaded.get_messages(conversation.id)

    assert [message.content for message in messages] == ["good"]


def test_partial_final_line_recovered(tmp_path: Path) -> None:
    store = _store(tmp_path)
    conversation = store.create_conversation("t")
    store.append_message(conversation.id, MessageRole.USER, "good")
    path = tmp_path / "manifests" / "conversation_messages.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"id": "torn", "conversation_id": ')

    reloaded = ConversationStore(tmp_path / "manifests")

    assert [m.content for m in reloaded.get_messages(conversation.id)] == ["good"]
    assert reloaded.append_message(conversation.id, MessageRole.USER, "next").seq == 2


def test_archive_persistence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    conversation = store.create_conversation("t")
    archived = conversation.model_copy(update={"status": ConversationStatus.ARCHIVED})
    store.update_conversation(archived)

    assert ConversationStore(tmp_path / "manifests").get_conversation(
        conversation.id
    ).status is ConversationStatus.ARCHIVED  # type: ignore[union-attr]
    with pytest.raises(KeyError):
        store.update_conversation(archived.model_copy(update={"id": "ghost"}))


def test_cross_conversation_isolation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.create_conversation("one")
    second = store.create_conversation("two")
    store.append_message(first.id, MessageRole.USER, "for-one")
    store.append_message(second.id, MessageRole.USER, "for-two")

    assert [m.content for m in store.get_messages(first.id)] == ["for-one"]
    assert [m.content for m in store.get_messages(second.id)] == ["for-two"]
    assert store.count_messages(first.id) == 1


def test_large_history_filtering_is_deterministic(tmp_path: Path) -> None:
    store = _store(tmp_path)
    conversation = store.create_conversation("t")
    for index in range(1000):
        store.append_message(conversation.id, MessageRole.USER, f"m{index:04d}")

    page = store.get_messages(conversation.id, limit=50, offset=900)

    assert len(page) == 50
    assert page[0].content == "m0900"
    assert page[-1].content == "m0949"
    again = ConversationStore(tmp_path / "manifests").get_messages(
        conversation.id, limit=50, offset=900
    )
    assert [m.id for m in page] == [m.id for m in again]
