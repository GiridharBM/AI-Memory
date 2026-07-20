"""Audio transcription via faster-whisper."""

from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


class WhisperTranscriber:
    """Transcribe audio files using faster-whisper."""

    def __init__(self, *, model_size: str = "base", device: str = "cpu") -> None:
        self._model_size = model_size
        self._device = device
        self._model = None

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self._model_size, device=self._device)
        except ImportError:
            raise RuntimeError("faster-whisper is not installed.")

    def transcribe(self, audio_path: Path) -> str:
        """Transcribe an audio file and return the text."""
        self._ensure_model()
        segments, info = self._model.transcribe(str(audio_path), beam_size=5)
        parts = [segment.text for segment in segments]
        text = " ".join(parts).strip()
        logger.info(
            "Audio transcription complete.",
            extra={"path": str(audio_path), "language": info.language, "duration": info.duration},
        )
        return text
