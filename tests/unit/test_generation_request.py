"""Tests for the V2 generation-request domain abstraction."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.generation import GenerationRequest, GenerationTaskType, ProvenanceLevel
from app.domain.scopes import MemoryScope


def _request(**overrides: object) -> GenerationRequest:
    values: dict[str, object] = {"task_type": "ask", "memory_scope": MemoryScope.all()}
    values.update(overrides)
    return GenerationRequest(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("task", list(GenerationTaskType))
def test_every_supported_task_type(task: GenerationTaskType) -> None:
    request = _request(task_type=task.value)

    assert request.task_type is task
    assert request.memory_scope == MemoryScope.all()


def test_invalid_task_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _request(task_type="teleport")


def test_memory_scope_is_required() -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(task_type="ask")  # type: ignore[call-arg]


def test_config_accepts_scalar_values() -> None:
    request = _request(config={"count": 10, "difficulty": "hard", "flag": True, "ratio": 0.5})

    assert request.config == {"count": 10, "difficulty": "hard", "flag": True, "ratio": 0.5}


def test_config_rejects_blank_keys_and_complex_values() -> None:
    with pytest.raises(ValidationError):
        _request(config={"  ": 1})
    with pytest.raises(ValidationError):
        _request(config={"nested": {"a": 1}})
    with pytest.raises(ValidationError):
        _request(config={"items": [1, 2]})


def test_model_role_defaults_and_validation() -> None:
    assert _request().model_role == "general_text"
    assert _request(model_role="  vision  ").model_role == "vision"
    with pytest.raises(ValidationError):
        _request(model_role="   ")


def test_provenance_defaults_and_validation() -> None:
    assert _request().provenance is ProvenanceLevel.STANDARD
    assert _request(provenance="strict").provenance is ProvenanceLevel.STRICT
    with pytest.raises(ValidationError):
        _request(provenance="maximum")


def test_metadata_must_be_string_to_string() -> None:
    request = _request(metadata={" request_id ": "abc", "client": "cli"})

    assert request.metadata == {"request_id": "abc", "client": "cli"}
    with pytest.raises(ValidationError):
        _request(metadata={"  ": "x"})
    with pytest.raises(ValidationError):
        _request(metadata={"key": 42})


def test_serialization_round_trip() -> None:
    request = _request(
        task_type="flashcards",
        memory_scope=MemoryScope.documents(["b.md", "a.md"]),
        config={"count": 5},
        provenance="strict",
    )

    restored = GenerationRequest.model_validate_json(request.model_dump_json())

    assert restored == request


def test_equal_requests_are_deterministic() -> None:
    first = _request(memory_scope=MemoryScope.documents(["b.md", "a.md"]))
    second = _request(memory_scope=MemoryScope.documents(["a.md", "b.md"]))

    assert first == second
