"""V2 presentation generation handler.

Renders a structured prompt from the ``GenerationContext`` hits, calls the
injected structured-output client (one correction retry on malformed
output), validates the presentation, renders it to PPTX beneath the
configured artifact root, and returns a ``GenerationResult`` whose
``content_ref`` is project-relative. The intermediate ``Presentation``
model is never persisted. Persistence belongs to the executor.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from app.application.generation_errors import HandlerError
from app.domain.artifacts import ArtifactKind, ProvenanceRecord, ProvenanceRole
from app.domain.generation import GenerationTaskType
from app.domain.generation_context import GenerationContext
from app.domain.generation_documents import Presentation
from app.domain.generation_result import GenerationResult
from app.infrastructure.pptx_renderer import (
    PptxRendererError,
    render_presentation_pptx,
    slug_filename,
)
from app.prompts.generation import (
    GENERATION_SYSTEM_PROMPT,
    add_generation_retry_instruction,
    build_presentation_user_prompt,
)

MAX_SLIDE_COUNT = 20
DEFAULT_SLIDE_COUNT = 5
DETAIL_LEVELS = ("brief", "standard", "detailed")

# (system prompt, user prompt, response model) -> parsed presentation. A thin
# lambda over OllamaClient.generate_json binds the real client without the
# handler importing provider code.
GeneratePresentation = Callable[[str, str, "type[Presentation]"], Presentation]


@dataclass(slots=True, frozen=True)
class _PresentationConfig:
    title: str | None
    slide_count: int
    detail_level: str
    theme: str
    speaker_notes: bool


def _parse_config(config: dict[str, object]) -> _PresentationConfig:
    title = config.get("title")
    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise HandlerError("Presentation 'title' must be a non-empty string.")
    slide_count = config.get("slide_count", DEFAULT_SLIDE_COUNT)
    if isinstance(slide_count, bool) or not isinstance(slide_count, int):
        raise HandlerError("Presentation 'slide_count' must be an integer.")
    if not 1 <= slide_count <= MAX_SLIDE_COUNT:
        raise HandlerError(
            f"Presentation 'slide_count' must be between 1 and {MAX_SLIDE_COUNT}."
        )
    detail_level = config.get("detail_level", "standard")
    if detail_level not in DETAIL_LEVELS:
        raise HandlerError(
            "Presentation 'detail_level' must be brief, standard, or detailed."
        )
    theme = config.get("theme", "default")
    if not isinstance(theme, str) or not theme.strip():
        raise HandlerError("Presentation 'theme' must be a non-empty string.")
    if theme.strip() != "default":
        raise HandlerError("Only the 'default' presentation theme is supported in V2-D.")
    speaker_notes = config.get("speaker_notes", True)
    if not isinstance(speaker_notes, bool):
        raise HandlerError("Presentation 'speaker_notes' must be a boolean.")
    return _PresentationConfig(
        title=title.strip() if isinstance(title, str) else None,
        slide_count=slide_count,
        detail_level=detail_level,  # type: ignore[arg-type]
        theme="default",
        speaker_notes=speaker_notes,
    )


def _validate_presentation(presentation: Presentation, count: int) -> None:
    if len(presentation.slides) != count:
        raise HandlerError(
            f"Expected exactly {count} slides, got {len(presentation.slides)}."
        )
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for slide in presentation.slides:
        key = (slide.title.casefold(), tuple(bullet.casefold() for bullet in slide.bullets))
        if key in seen:
            raise HandlerError(f"Duplicate slide: {slide.title!r}.")
        seen.add(key)


def _provenance(context: GenerationContext) -> tuple[ProvenanceRecord, ...]:
    """One candidate per retrieved hit (set-level attribution).

    The model generates from the whole context, so per-slide records
    reference every retrieved chunk rather than fabricating slide-to-chunk
    mapping. The caller repeats these per generated slide.
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


class PresentationTaskHandler:
    """Generate a PPTX presentation from retrieved memory context."""

    task_type = GenerationTaskType.PPT

    def __init__(
        self,
        generate_json: GeneratePresentation,
        *,
        artifact_root: Path,
        project_root: Path,
    ) -> None:
        self._generate_json = generate_json
        # Resolve once at construction. Configured defaults like
        # "./data/artifacts" are relative to the project root (like every
        # other ./data/* default), while renderer resolution is CWD-anchored.
        # Anchoring here keeps the write location and the project-relative
        # content_ref consistent regardless of launch CWD.
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
        config = _parse_config(dict(context.request.config))
        prompt = build_presentation_user_prompt(
            context,
            title=config.title,
            slide_count=config.slide_count,
            detail_level=config.detail_level,
            speaker_notes=config.speaker_notes,
        )
        presentation = self._generate_with_retry(prompt, config)
        filename = f"{slug_filename(presentation.title)}-{uuid4().hex[:8]}.pptx"
        destination = self._artifact_root / filename
        try:
            rendered = render_presentation_pptx(
                presentation,
                destination,
                artifact_root=self._artifact_root,
                include_notes=config.speaker_notes,
            )
        except PptxRendererError:
            raise
        except Exception as exc:
            raise HandlerError(f"Presentation rendering failed: {exc}") from exc
        try:
            content_ref = rendered.relative_to(self._project_root).as_posix()
        except ValueError as exc:
            raise HandlerError(
                "Artifact root escapes the project root; cannot form content_ref."
            ) from exc
        per_hit = _provenance(context)
        return GenerationResult(
            kind=ArtifactKind.PPT,
            title=presentation.title,
            content_ref=content_ref,
            metadata={"slides": str(len(presentation.slides)), "theme": "default"},
            provenance=tuple(
                record for _ in presentation.slides for record in per_hit
            ),
        )

    def _generate_with_retry(
        self, prompt: str, config: _PresentationConfig
    ) -> Presentation:
        last_error: Exception | None = None
        current = prompt
        for _ in range(2):
            try:
                presentation = self._generate_json(
                    GENERATION_SYSTEM_PROMPT, current, Presentation
                )
            except ValidationError as exc:
                last_error = exc
            except Exception as exc:
                raise HandlerError(f"Presentation generation failed: {exc}") from exc
            else:
                try:
                    _validate_presentation(presentation, config.slide_count)
                except HandlerError as exc:
                    last_error = exc
                else:
                    return presentation
            current = add_generation_retry_instruction(prompt)
        raise HandlerError(f"Presentation generation failed after retry: {last_error}")
