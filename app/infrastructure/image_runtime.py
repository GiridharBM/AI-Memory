"""Local image-generation runtime behind a minimal protocol (V2-H).

``ImageRuntime`` is the only seam between the task handler and diffusion
machinery: model loading, pipeline creation, and GPU execution live here;
request interpretation, planning, validation, and provenance live in the
handler. ``torch``/``diffusers`` are imported lazily so this module (and
everything importing it) loads on machines without GPU dependencies —
generation fails fast with a clear error only when actually invoked.

Loaded pipelines are cached process-wide per (model, revision): model
weights load once, subsequent jobs reuse them. One lock serializes GPU
access; concurrent image jobs queue behind it rather than contending for
8 GB of VRAM.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


class ImageRuntimeError(RuntimeError):
    """Image generation failed (model, CUDA, OOM, or output defect)."""


@dataclass(slots=True, frozen=True)
class ImageResult:
    """One rendered image plus the parameters that produced it."""

    image: PILImage
    width: int
    height: int
    seed: int
    model_id: str
    model_revision: str
    scheduler: str
    elapsed_seconds: float


class ImageRuntime(Protocol):
    """Generate one image from a distilled visual prompt."""

    def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        model_id: str,
        model_revision: str,
        width: int,
        height: int,
        steps: int,
        guidance_scale: float,
        seed: int,
    ) -> ImageResult:
        """Render ``prompt`` to an image; raises ``ImageRuntimeError`` on failure."""
        ...


_PIPELINE_CACHE: dict[tuple[str, str], Any] = {}
_PIPELINE_LOCK = threading.Lock()

# Refuse fast when clearly below the measured 768px working set (~5.8 GB
# reserved). OOM during generation is still caught and mapped below; this
# is only an early, legible failure for obviously starved GPUs.
MIN_FREE_BYTES = 5_000_000_000


def _require_cuda() -> Any:
    try:
        import torch
    except ImportError as exc:
        raise ImageRuntimeError(
            "Image generation needs PyTorch with CUDA; torch is not installed."
        ) from exc
    if not torch.cuda.is_available():
        raise ImageRuntimeError(
            "Image generation needs a CUDA GPU; none is available. "
            "Install a CUDA-enabled torch build (cu128+ for Blackwell GPUs)."
        )
    return torch


def _load_pipeline(model_id: str, model_revision: str) -> Any:
    # NOTE: diffusers is an optional V2-H dependency (CPU-only environments
    # run the stub path in tests); it is imported lazily at first use.
    from diffusers import AutoPipelineForText2Image  # type: ignore[import-not-found]

    torch = _require_cuda()
    key = (model_id, model_revision)
    with _PIPELINE_LOCK:
        cached = _PIPELINE_CACHE.get(key)
        if cached is not None:
            return cached
        try:
            pipe = AutoPipelineForText2Image.from_pretrained(
                model_id,
                revision=model_revision,
                torch_dtype=torch.float16,
                use_safetensors=True,
            )
            pipe.enable_model_cpu_offload()
        except Exception as exc:
            raise ImageRuntimeError(
                f"Image model loading failed for '{model_id}': {exc}"
            ) from exc
        _PIPELINE_CACHE[key] = pipe
        return pipe


class DiffusersImageRuntime:
    """SDXL-family image generation via Diffusers (V2-G benchmark winner)."""

    def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        model_id: str,
        model_revision: str,
        width: int,
        height: int,
        steps: int,
        guidance_scale: float,
        seed: int,
    ) -> ImageResult:
        torch = _require_cuda()
        free_bytes, _ = torch.cuda.mem_get_info()
        if free_bytes < MIN_FREE_BYTES:
            raise ImageRuntimeError(
                f"Insufficient GPU memory for image generation "
                f"({free_bytes / 1e9:.1f} GB free)."
            )
        pipe = _load_pipeline(model_id, model_revision)
        generator = torch.Generator(device="cuda").manual_seed(seed)
        call: dict[str, object] = {
            "prompt": prompt,
            "height": height,
            "width": width,
            "num_inference_steps": steps,
            "guidance_scale": guidance_scale,
            "generator": generator,
        }
        if negative_prompt:
            call["negative_prompt"] = negative_prompt
        torch.cuda.synchronize()
        started = time.perf_counter()
        try:
            with _PIPELINE_LOCK:
                images = pipe(**call).images  # type: ignore[operator]
        except torch.cuda.OutOfMemoryError as exc:
            torch.cuda.empty_cache()
            raise ImageRuntimeError(f"Image generation ran out of GPU memory: {exc}") from exc
        except Exception as exc:
            raise ImageRuntimeError(f"Image generation failed: {exc}") from exc
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        if not images:
            raise ImageRuntimeError("Image generation produced no output.")
        return ImageResult(
            image=images[0],
            width=width,
            height=height,
            seed=seed,
            model_id=model_id,
            model_revision=model_revision,
            scheduler=type(pipe.scheduler).__name__,
            elapsed_seconds=elapsed,
        )
