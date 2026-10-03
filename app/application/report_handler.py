"""V2 report generation handler.

Renders a structured prompt from the ``GenerationContext`` hits, calls the
injected structured-output client (one correction retry on malformed
output), validates the report, and returns a ``GenerationResult`` with
rendered Markdown. Persistence belongs to the executor.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import ValidationError

from app.application.generation_errors import HandlerError
from app.domain.artifacts import ArtifactKind, ProvenanceRecord, ProvenanceRole
from app.domain.generation import GenerationTaskType
from app.domain.generation_context import GenerationContext
from app.domain.generation_documents import Report
from app.domain.generation_result import GenerationResult
from app.prompts.generation import (
    GENERATION_SYSTEM_PROMPT,
    add_generation_retry_instruction,
    build_report_user_prompt,
)
from app.templates.report import render_report_markdown

MAX_REPORT_SECTIONS = 12
DEFAULT_REPORT_SECTIONS = 5
DETAIL_LEVELS = ("brief", "standard", "detailed")

# (system prompt, user prompt, response model) -> parsed report. A thin lambda
# over OllamaClient.generate_json binds the real client without the handler
# importing provider code.
GenerateReport = Callable[[str, str, "type[Report]"], Report]


@dataclass(slots=True, frozen=True)
class _ReportConfig:
    title: str | None
    section_count: int
    detail_level: str


def _parse_config(config: dict[str, object]) -> _ReportConfig:
    title = config.get("title")
    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise HandlerError("Report 'title' must be a non-empty string.")
    section_count = config.get("section_count", DEFAULT_REPORT_SECTIONS)
    if isinstance(section_count, bool) or not isinstance(section_count, int):
        raise HandlerError("Report 'section_count' must be an integer.")
    if not 1 <= section_count <= MAX_REPORT_SECTIONS:
        raise HandlerError(
            f"Report 'section_count' must be between 1 and {MAX_REPORT_SECTIONS}."
        )
    detail_level = config.get("detail_level", "standard")
    if detail_level not in DETAIL_LEVELS:
        raise HandlerError("Report 'detail_level' must be brief, standard, or detailed.")
    return _ReportConfig(
        title=title.strip() if isinstance(title, str) else None,
        section_count=section_count,
        detail_level=detail_level,  # type: ignore[arg-type]
    )


def _validate_report(report: Report, count: int) -> None:
    if len(report.sections) != count:
        raise HandlerError(
            f"Expected exactly {count} report sections, got {len(report.sections)}."
        )
    seen: set[str] = set()
    for section in report.sections:
        key = section.heading.casefold()
        if key in seen:
            raise HandlerError(f"Duplicate report section heading: {section.heading!r}.")
        seen.add(key)


def _provenance(context: GenerationContext) -> tuple[ProvenanceRecord, ...]:
    """One candidate per retrieved hit (set-level attribution).

    The model generates from the whole context, so per-section records
    reference every retrieved chunk rather than fabricating section-to-chunk
    mapping. The caller repeats these per generated section.
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


class ReportTaskHandler:
    """Generate a structured report from retrieved memory context."""

    task_type = GenerationTaskType.REPORT

    def __init__(self, generate_json: GenerateReport) -> None:
        self._generate_json = generate_json

    def handle(self, context: GenerationContext) -> GenerationResult:
        config = _parse_config(dict(context.request.config))
        prompt = build_report_user_prompt(
            context,
            title=config.title,
            section_count=config.section_count,
            detail_level=config.detail_level,
        )
        report = self._generate_with_retry(prompt, config)
        per_hit = _provenance(context)
        return GenerationResult(
            kind=ArtifactKind.REPORT,
            title=report.title,
            content=render_report_markdown(report),
            metadata={"sections": str(len(report.sections))},
            provenance=tuple(
                record for _ in report.sections for record in per_hit
            ),
        )

    def _generate_with_retry(self, prompt: str, config: _ReportConfig) -> Report:
        last_error: Exception | None = None
        current = prompt
        for _ in range(2):
            try:
                report = self._generate_json(GENERATION_SYSTEM_PROMPT, current, Report)
            except ValidationError as exc:
                last_error = exc
            except Exception as exc:
                raise HandlerError(f"Report generation failed: {exc}") from exc
            else:
                try:
                    _validate_report(report, config.section_count)
                except HandlerError as exc:
                    last_error = exc
                else:
                    return report
            current = add_generation_retry_instruction(prompt)
        raise HandlerError(f"Report generation failed after retry: {last_error}")
