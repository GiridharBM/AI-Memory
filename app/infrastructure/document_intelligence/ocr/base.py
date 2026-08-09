"""OCR engine protocol and registry service."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core.logging import get_logger
from app.domain.documents import SourceDocument
from app.infrastructure.document_intelligence.ocr.models import OcrResult

logger = get_logger(__name__)


class OCRSelectionError(RuntimeError):
    """Raised when no registered OCR engine can handle the requested kind."""


@runtime_checkable
class OcrEngine(Protocol):
    """Contract implemented by every OCR engine."""

    name: str
    supported_kinds: set[str]

    def run(self, source: Path, *, prompt: str, preprocess: bool = False) -> OcrResult:
        """Extract text from a rendered PDF or image path."""
        ...


class DocumentOcrService:
    """Registry that selects an OCR engine for a document and runs it."""

    def __init__(self, engines: list[OcrEngine] | None = None) -> None:
        self._engines: list[OcrEngine] = list(engines or [])

    def register(self, engine: OcrEngine) -> None:
        """Register an OCR engine."""
        self._engines.append(engine)

    @property
    def engines(self) -> list[OcrEngine]:
        """Return a snapshot of registered engines in registration order."""
        return list(self._engines)

    def select(self, kind: str, *, engine: str = "auto") -> OcrEngine:
        """Select the first registered engine matching the requested kind.

        ``engine="auto"`` returns the first engine (registration order) that
        supports the kind; an explicit engine name requires both the name and
        the kind to match.
        """
        candidates = self._engines
        if engine != "auto":
            candidates = [e for e in self._engines if e.name == engine]

        for candidate in candidates:
            if kind in candidate.supported_kinds:
                return candidate

        raise OCRSelectionError(
            f"No OCR engine available for kind '{kind}'"
            + (f" with engine '{engine}'" if engine != "auto" else "")
            + ". Register an OcrEngine or disable OCR."
        )

    def extract(
        self,
        document: SourceDocument,
        *,
        prompt: str,
        engine: str = "auto",
        preprocess: bool = False,
    ) -> OcrResult:
        """Run OCR on a document's source file via the selected engine."""
        source_path = document.source_path
        if source_path is None or not source_path.exists():
            raise ValueError(
                f"Cannot OCR '{document.source}': source path is missing."
            )

        selected = self.select(document.source_type, engine=engine)
        logger.debug(
            "Running OCR engine.",
            extra={"engine": selected.name, "kind": document.source_type},
        )
        return selected.run(source_path, prompt=prompt, preprocess=preprocess)
