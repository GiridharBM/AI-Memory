"""Deterministic PPTX rendering for generated presentations.

Pure file rendering over the structured ``Presentation`` model: title slide
plus one title-and-content slide per ``Slide``, optional speaker notes. No
LLM calls, no store access, no diagrams/images/tables. Uses the already
vendored ``python-pptx`` dependency (also used read-only by ingestion).
"""

from __future__ import annotations

import re
from pathlib import Path

from app.domain.generation_documents import Presentation

_FILENAME_UNSAFE_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class PptxRendererError(ValueError):
    """The presentation could not be rendered to a valid PPTX file."""


def slug_filename(title: str) -> str:
    """Return a filesystem-safe slug for an artifact title."""

    cleaned = _FILENAME_UNSAFE_PATTERN.sub("", title).strip()
    cleaned = re.sub(r"\s+", "-", cleaned).strip("-")
    return cleaned[:80] or "presentation"


def render_presentation_pptx(
    presentation: Presentation,
    destination: Path,
    *,
    artifact_root: Path,
    include_notes: bool = True,
) -> Path:
    """Render ``presentation`` to ``destination`` and validate by reopening.

    ``destination`` must resolve beneath ``artifact_root``; anything else is
    rejected rather than written. Returns ``destination`` on success.
    """

    try:
        resolved = destination.resolve()
        resolved.relative_to(artifact_root.resolve())
    except (OSError, ValueError) as exc:
        raise PptxRendererError(
            f"PPTX destination must be beneath the artifact root: {exc}"
        ) from exc

    try:
        from pptx import Presentation as PptxPresentation

        deck = PptxPresentation()
        title_slide = deck.slides.add_slide(deck.slide_layouts[5])
        title_slide.shapes.title.text = presentation.title
        for slide in presentation.slides:
            content_slide = deck.slides.add_slide(deck.slide_layouts[1])
            content_slide.shapes.title.text = slide.title
            text_frame = content_slide.placeholders[1].text_frame
            text_frame.clear()
            for index, bullet in enumerate(slide.bullets):
                paragraph = text_frame.paragraphs[0] if index == 0 else text_frame.add_paragraph()
                paragraph.text = bullet
                paragraph.level = 0
            if include_notes and slide.speaker_notes:
                content_slide.notes_slide.notes_text_frame.text = slide.speaker_notes
        resolved.parent.mkdir(parents=True, exist_ok=True)
        deck.save(str(resolved))
    except PptxRendererError:
        raise
    except Exception as exc:
        raise PptxRendererError(f"PPTX rendering failed: {exc}") from exc

    try:
        from pptx import Presentation as PptxReopen

        check = PptxReopen(str(resolved))
        rendered_titles: list[str] = []
        for slide in check.slides:
            title_shape = slide.shapes.title
            rendered_titles.append(
                title_shape.text.strip() if title_shape is not None else ""
            )
    except Exception as exc:
        raise PptxRendererError(f"Generated PPTX failed validation: {exc}") from exc
    expected = [presentation.title] + [slide.title for slide in presentation.slides]
    if len(check.slides) != len(expected) or rendered_titles != expected:
        raise PptxRendererError("Generated PPTX failed validation: title mismatch.")
    return resolved
