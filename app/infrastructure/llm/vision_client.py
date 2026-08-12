"""Vision client for sending images to Ollama vision models."""

from __future__ import annotations

import base64
from pathlib import Path

import ollama

from app.core.config import OllamaSettings
from app.core.logging import get_logger

logger = get_logger(__name__)


class OllamaVisionClient:
    """Send images to Ollama vision models for OCR and description."""

    def __init__(self, settings: OllamaSettings, *, vision_model: str | None = None) -> None:
        self._settings = settings
        self._vision_model = vision_model or "qwen2.5vl:7b"
        self._client = ollama.Client(
            host=str(settings.host),
            timeout=settings.timeout_seconds,
        )

    def _ensure_vision_model(self) -> None:
        """Check that the vision model is available, log warning if not."""
        try:
            models = self._client.list()
            model_names = []
            for m in (models.models if hasattr(models, "models") else []):
                name = m.model if isinstance(m.model, str) else str(m)
                model_names.append(name)
            if not any(self._vision_model in name for name in model_names):
                logger.warning(
                    "Vision model '%s' not found. Available: %s. "
                    "Image processing will fail. Pull it with: ollama pull %s",
                    self._vision_model,
                    ", ".join(model_names[:10]),
                    self._vision_model,
                )
        except Exception:
            pass

    def describe_image(
        self,
        image_path: Path,
        *,
        model: str | None = None,
        prompt: str = (
            "Extract all text from this image. "
            "Return only the extracted text, nothing else."
        ),
    ) -> str:
        """Send an image to a vision model and return the extracted text."""
        image_b64 = base64.b64encode(image_path.read_bytes()).decode()
        return self._generate_with_image(
            model=model or self._vision_model,
            prompt=prompt,
            image_b64=image_b64,
        )

    def describe_image_bytes(
        self,
        image_bytes: bytes,
        *,
        model: str | None = None,
        prompt: str = (
            "Extract all text from this image. "
            "Return only the extracted text, nothing else."
        ),
    ) -> str:
        """Send raw image bytes to a vision model."""
        image_b64 = base64.b64encode(image_bytes).decode()
        return self._generate_with_image(
            model=model or self._vision_model,
            prompt=prompt,
            image_b64=image_b64,
        )

    def _generate_with_image(
        self,
        *,
        model: str,
        prompt: str,
        image_b64: str,
    ) -> str:
        response = self._client.generate(
            model=model,
            prompt=prompt,
            images=[image_b64],
            stream=False,
        )
        if isinstance(response, dict):
            text = response.get("response", "")
        else:
            text = getattr(response, "response", "")
        if not text:
            logger.warning("Vision model returned empty response.", extra={"model": model})
        return text.strip()
