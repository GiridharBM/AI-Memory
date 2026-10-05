"""V2-H image generation handler.

Plans a visual prompt from the ``GenerationContext`` hits with the injected
structured-output client (one correction retry on malformed output), renders
exactly one image through the injected ``ImageRuntime``, writes the PNG
beneath the configured artifact root, and returns a ``GenerationResult``
whose ``content_ref`` is project-relative. The intermediate ``ImagePlan``
is never persisted. Persistence belongs to the executor.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL.Image import Image as PILImage
from pydantic import ValidationError

from app.application.generation_errors import HandlerError
from app.core.config import ImageGenerationSettings
from app.domain.artifacts import ArtifactKind, ProvenanceRecord, ProvenanceRole
from app.domain.generation import GenerationTaskType
from app.domain.generation_context import GenerationContext
from app.domain.generation_result import GenerationResult
from app.domain.image import ALLOWED_IMAGE_SIZES, MAX_IMAGE_STEPS, ImagePlan, ImageSpec
from app.infrastructure.image_runtime import ImageRuntime
from app.infrastructure.pptx_renderer import slug_filename
from app.prompts.generation import (
    GENERATION_SYSTEM_PROMPT,
    add_generation_retry_instruction,
)
from app.prompts.image import build_image_plan_user_prompt

MODES = ("standard", "fast")

# (system prompt, user prompt, response model) -> parsed plan. A thin lambda
# over OllamaClient.generate_json binds the real client without the handler
# importing provider code.
GenerateImagePlan = Callable[[str, str, "type[ImagePlan]"], ImagePlan]


@dataclass(slots=True, frozen=True)
class _ImageConfig:
    mode: str
    title: str | None
    prompt: str | None
    negative_prompt: str
    width: int
    height: int
    steps: int
    guidance_scale: float
    seed: int


def _parse_config(
    config: dict[str, object], defaults: ImageGenerationSettings
) -> _ImageConfig:
    mode = config.get("mode", "standard")
    if mode not in MODES:
        raise HandlerError("Image 'mode' must be 'standard' or 'fast'.")
    title = config.get("title")
    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise HandlerError("Image 'title' must be a non-empty string.")
    prompt = config.get("prompt")
    if prompt is not None and (not isinstance(prompt, str) or not prompt.strip()):
        raise HandlerError("Image 'prompt' must be a non-empty string.")
    negative_prompt = config.get("negative_prompt", "")
    if not isinstance(negative_prompt, str):
        raise HandlerError("Image 'negative_prompt' must be a string.")
    default_steps = (
        defaults.default_steps_standard
        if mode == "standard"
        else defaults.default_steps_fast
    )
    steps = config.get("steps", default_steps)
    if isinstance(steps, bool) or not isinstance(steps, int):
        raise HandlerError("Image 'steps' must be an integer.")
    if not 1 <= steps <= MAX_IMAGE_STEPS:
        raise HandlerError(f"Image 'steps' must be between 1 and {MAX_IMAGE_STEPS}.")
    width = config.get("width", defaults.default_width)
    height = config.get("height", defaults.default_height)
    for name, value in (("width", width), ("height", height)):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise HandlerError(f"Image '{name}' must be a positive integer.")
    if (width, height) not in ALLOWED_IMAGE_SIZES:
        allowed = ", ".join(f"{w}x{h}" for w, h in ALLOWED_IMAGE_SIZES)
        raise HandlerError(f"Image dimensions must be one of: {allowed}.")
    default_guidance = 7.5 if mode == "standard" else 0.0
    guidance_scale = config.get("guidance_scale", default_guidance)
    if isinstance(guidance_scale, bool) or not isinstance(guidance_scale, (int, float)):
        raise HandlerError("Image 'guidance_scale' must be a number.")
    if not 0.0 <= float(guidance_scale) <= 30.0:
        raise HandlerError("Image 'guidance_scale' must be between 0.0 and 30.0.")
    seed = config.get("seed", 0)
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise HandlerError("Image 'seed' must be a non-negative integer (0 = random).")
    for key in ("query", "topic"):
        value = config.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise HandlerError(f"Image '{key}' must be a non-empty string.")
    return _ImageConfig(
        mode=mode,  # type: ignore[arg-type]
        title=title.strip() if isinstance(title, str) else None,
        prompt=prompt.strip() if isinstance(prompt, str) else None,
        negative_prompt=" ".join(negative_prompt.split()),
        width=width,  # type: ignore[arg-type]
        height=height,  # type: ignore[arg-type]
        steps=steps,
        guidance_scale=float(guidance_scale),
        seed=seed,
    )


def _provenance(context: GenerationContext) -> tuple[ProvenanceRecord, ...]:
    """One candidate per retrieved hit (set-level attribution).

    A render has no addressable sub-items, so records reference every
    retrieved chunk exactly once rather than fabricating element-level
    visual attribution. The records represent evidence-set membership.
    """

    return tuple(
        ProvenanceRecord(
            artifact_id="pending",
            source_id=hit.source,
            role=ProvenanceRole.EVIDENCE_CHUNK,
            source_type=hit.source_type or None,
            chunk_id=hit.entry_id or None,
            chunk_index=hit.chunk_index,
            start_char=hit.start_char,
            end_char=hit.end_char,
        )
        for hit in context.hits
    )


def _validate_png(path: Path, width: int, height: int, max_bytes: int) -> None:
    from PIL import Image as PILModule

    size = path.stat().st_size
    if size == 0:
        raise HandlerError("Image generation produced an empty file.")
    if size > max_bytes:
        raise HandlerError(
            f"Generated image exceeds the {max_bytes} byte limit."
        )
    try:
        with PILModule.open(path) as image:
            image.load()
            if image.size != (width, height):
                raise HandlerError(
                    f"Generated image has wrong dimensions: {image.size[0]}x{image.size[1]}."
                )
    except HandlerError:
        raise
    except Exception as exc:
        raise HandlerError(f"Generated image is not a valid PNG: {exc}") from exc


class ImageTaskHandler:
    """Generate one PNG illustration from retrieved memory context."""

    task_type = GenerationTaskType.IMAGE

    def __init__(
        self,
        generate_json: GenerateImagePlan,
        image_runtime: ImageRuntime,
        image_config: ImageGenerationSettings,
        *,
        artifact_root: Path,
        project_root: Path,
    ) -> None:
        self._generate_json = generate_json
        self._image_runtime = image_runtime
        self._image_config = image_config
        try:
            project_root = project_root.resolve()
            if artifact_root.is_absolute():
                resolved_root = artifact_root.resolve()
            else:
                resolved_root = (project_root / artifact_root).resolve()
            self._artifact_root = resolved_root
            self._project_root = project_root
        except OSError as exc:
            raise HandlerError(f"Cannot resolve artifact paths: {exc}") from exc

    def handle(self, context: GenerationContext) -> GenerationResult:
        config = _parse_config(dict(context.request.config), self._image_config)
        if config.prompt is not None:
            plan = ImagePlan(
                prompt=config.prompt,
                negative_prompt=config.negative_prompt,
                title=config.title or "",
            )
        else:
            plan = self._plan_with_retry(context, config)
        if config.mode == "standard":
            model_id = self._image_config.model_id_standard
            model_revision = self._image_config.model_revision_standard
        else:
            model_id = self._image_config.model_id_fast
            model_revision = self._image_config.model_revision_fast
        seed = config.seed if config.seed else secrets.randbelow(2**31)
        spec = ImageSpec(
            model_id=model_id,
            model_revision=model_revision,
            width=config.width,
            height=config.height,
            steps=config.steps,
            guidance_scale=config.guidance_scale,
            seed=seed,
        )
        try:
            result = self._image_runtime.generate(
                prompt=plan.prompt,
                negative_prompt=plan.negative_prompt,
                model_id=spec.model_id,
                model_revision=spec.model_revision,
                width=spec.width,
                height=spec.height,
                steps=spec.steps,
                guidance_scale=spec.guidance_scale,
                seed=spec.seed,
            )
        except Exception as exc:
            raise HandlerError(f"Image rendering failed: {exc}") from exc
        title = plan.title or config.title or f"Image ({spec.width}x{spec.height})"
        filename = f"{slug_filename(title)}-{uuid4().hex[:8]}.png"
        destination = self._artifact_root / filename
        try:
            self._write_png(result.image, destination)
        except Exception as exc:
            raise HandlerError(f"Image file write failed: {exc}") from exc
        _validate_png(destination, spec.width, spec.height, self._image_config.max_output_bytes)
        try:
            content_ref = destination.relative_to(self._project_root).as_posix()
        except ValueError as exc:
            raise HandlerError(
                "Artifact root escapes the project root; cannot form content_ref."
            ) from exc
        prompt_hash = hashlib.sha256(plan.prompt.encode("utf-8")).hexdigest()
        metadata = {
            "mode": config.mode,
            "model_id": result.model_id,
            "model_revision": result.model_revision,
            "runtime": "diffusers",
            "scheduler": result.scheduler,
            "seed": str(result.seed),
            "width": str(result.width),
            "height": str(result.height),
            "steps": str(spec.steps),
            "guidance_scale": str(spec.guidance_scale),
            "precision": "float16",
            "prompt_sha256": prompt_hash,
            "evidence_chunks": str(len(context.hits)),
        }
        if plan.negative_prompt:
            metadata["negative_prompt"] = plan.negative_prompt
        return GenerationResult(
            kind=ArtifactKind.IMAGE,
            title=title,
            content_ref=content_ref,
            metadata=metadata,
            provenance=_provenance(context),
        )

    def _plan_with_retry(
        self, context: GenerationContext, config: _ImageConfig
    ) -> ImagePlan:
        prompt = build_image_plan_user_prompt(
            context, title=config.title, detail="standard"
        )
        last_error: Exception | None = None
        current = prompt
        for _ in range(2):
            try:
                return self._generate_json(GENERATION_SYSTEM_PROMPT, current, ImagePlan)
            except ValidationError as exc:
                last_error = exc
            except Exception as exc:
                raise HandlerError(f"Image prompt planning failed: {exc}") from exc
            current = add_generation_retry_instruction(prompt)
        raise HandlerError(f"Image prompt planning failed after retry: {last_error}")

    def _write_png(self, image: PILImage, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, "PNG")
