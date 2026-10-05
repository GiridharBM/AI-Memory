"""Tests for V2-H image domain models (plan + spec validation)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.image import (
    ALLOWED_IMAGE_SIZES,
    MAX_IMAGE_STEPS,
    ImagePlan,
    ImageSpec,
)


def _spec(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "model_id": "stabilityai/stable-diffusion-xl-base-1.0",
        "model_revision": "462165984030",
        "width": 768,
        "height": 768,
        "steps": 20,
        "guidance_scale": 7.5,
        "seed": 7,
    }
    values.update(overrides)
    return values


def test_valid_plan_and_spec() -> None:
    plan = ImagePlan(prompt="A misty forest.", negative_prompt="blurry", title="Forest")
    spec = ImageSpec(**_spec())  # type: ignore[arg-type]

    assert plan.prompt == "A misty forest."
    assert (spec.width, spec.height) == (768, 768)


def test_plan_prompt_normalized_and_required() -> None:
    plan = ImagePlan(prompt="  A   forest\nscene.  ")

    assert plan.prompt == "A forest scene."
    with pytest.raises(ValidationError):
        ImagePlan(prompt="   ")


def test_plan_prompt_length_capped() -> None:
    with pytest.raises(ValidationError):
        ImagePlan(prompt="x" * 1001)


def test_plan_text_fields_must_be_strings() -> None:
    with pytest.raises(ValidationError):
        ImagePlan(prompt="ok", negative_prompt=5)  # type: ignore[arg-type]


@pytest.mark.parametrize("size", list(ALLOWED_IMAGE_SIZES))
def test_allowed_sizes_accepted(size: tuple[int, int]) -> None:
    spec = ImageSpec(**_spec(width=size[0], height=size[1]))  # type: ignore[arg-type]

    assert (spec.width, spec.height) == size


@pytest.mark.parametrize(
    "size", [(800, 600), (1024, 768), (768, 1024), (0, 0), (256, 256)]
)
def test_disallowed_sizes_rejected(size: tuple[int, int]) -> None:
    with pytest.raises(ValidationError):
        ImageSpec(**_spec(width=size[0], height=size[1]))  # type: ignore[arg-type]


def test_steps_bounds() -> None:
    ImageSpec(**_spec(steps=1))  # type: ignore[arg-type]
    ImageSpec(**_spec(steps=MAX_IMAGE_STEPS))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ImageSpec(**_spec(steps=0))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ImageSpec(**_spec(steps=MAX_IMAGE_STEPS + 1))  # type: ignore[arg-type]


def test_guidance_and_seed_bounds() -> None:
    ImageSpec(**_spec(guidance_scale=0.0))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ImageSpec(**_spec(guidance_scale=-0.1))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ImageSpec(**_spec(seed=-1))  # type: ignore[arg-type]


def test_empty_model_refs_rejected() -> None:
    with pytest.raises(ValidationError):
        ImageSpec(**_spec(model_id="  "))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ImageSpec(**_spec(model_revision=""))  # type: ignore[arg-type]


def test_extra_forbidden_and_frozen() -> None:
    with pytest.raises(ValidationError):
        ImagePlan(prompt="ok", unknown="x")  # type: ignore[call-arg]
    plan = ImagePlan(prompt="ok")
    with pytest.raises(ValidationError):
        plan.prompt = "changed"  # type: ignore[misc]


def test_json_round_trip() -> None:
    spec = ImageSpec(**_spec())  # type: ignore[arg-type]
    plan = ImagePlan(prompt="ok")

    assert ImageSpec.model_validate_json(spec.model_dump_json()) == spec
    assert ImagePlan.model_validate_json(plan.model_dump_json()) == plan
