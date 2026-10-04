"""V2-F AI-enriched mind map generation handler.

Renders a structured prompt from the ``GenerationContext`` hits, calls the
injected structured-output client (one correction retry on malformed
output), validates the map, and returns a ``GenerationResult`` with
serialized JSON. Persistence belongs to the executor.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import ValidationError

from app.application.generation_errors import HandlerError
from app.domain.artifacts import ArtifactKind, ProvenanceRecord, ProvenanceRole
from app.domain.generation import GenerationTaskType
from app.domain.generation_context import GenerationContext
from app.domain.generation_result import GenerationResult
from app.domain.mindmap import EnrichedMindMap
from app.prompts.generation import (
    GENERATION_SYSTEM_PROMPT,
    add_generation_retry_instruction,
    build_mindmap_user_prompt,
)

MAX_MINDMAP_NODES = 60
MAX_MINDMAP_EDGES = 120
DEFAULT_MINDMAP_NODES = 20
DETAIL_LEVELS = ("brief", "standard", "detailed")

# (system prompt, user prompt, response model) -> parsed map. A thin lambda
# over OllamaClient.generate_json binds the real client without the handler
# importing provider code.
GenerateMindMap = Callable[[str, str, "type[EnrichedMindMap]"], EnrichedMindMap]


@dataclass(slots=True, frozen=True)
class _MindMapConfig:
    title: str | None
    node_limit: int
    detail: str


def _parse_config(config: dict[str, object]) -> _MindMapConfig:
    title = config.get("title")
    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise HandlerError("Mind map 'title' must be a non-empty string.")
    node_limit = config.get("node_limit", DEFAULT_MINDMAP_NODES)
    if isinstance(node_limit, bool) or not isinstance(node_limit, int):
        raise HandlerError("Mind map 'node_limit' must be an integer.")
    if not 1 <= node_limit <= MAX_MINDMAP_NODES:
        raise HandlerError(f"Mind map 'node_limit' must be between 1 and {MAX_MINDMAP_NODES}.")
    detail = config.get("detail", "standard")
    if detail not in DETAIL_LEVELS:
        raise HandlerError("Mind map 'detail' must be brief, standard, or detailed.")
    for key in ("query", "topic"):
        value = config.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise HandlerError(f"Mind map '{key}' must be a non-empty string.")
    return _MindMapConfig(
        title=title.strip() if isinstance(title, str) else None,
        node_limit=node_limit,
        detail=detail,  # type: ignore[arg-type]
    )


def _validate_mindmap(mindmap: EnrichedMindMap, node_limit: int) -> None:
    """Enforce the requested node budget; the schema enforces graph structure."""

    if len(mindmap.nodes) > node_limit:
        raise HandlerError(
            f"Expected at most {node_limit} mind map nodes, got {len(mindmap.nodes)}."
        )


def _provenance(context: GenerationContext) -> tuple[ProvenanceRecord, ...]:
    """One candidate per retrieved hit (set-level attribution).

    The model generates from the whole context, so per-node records
    reference every retrieved chunk rather than fabricating node-to-chunk
    mapping. The records represent evidence-set membership rather than
    claiming that a particular chunk semantically generated a particular
    node. The caller repeats these per generated node, attaching a
    structurally known knowledge-graph node id only when the enriched
    node id matches a retrieved graph node id.
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


class MindMapEnrichTaskHandler:
    """Generate an AI-enriched mind map from retrieved memory context."""

    task_type = GenerationTaskType.MINDMAP_ENRICH

    def __init__(self, generate_json: GenerateMindMap) -> None:
        self._generate_json = generate_json

    def handle(self, context: GenerationContext) -> GenerationResult:
        config = _parse_config(dict(context.request.config))
        prompt = build_mindmap_user_prompt(
            context,
            title=config.title,
            node_limit=config.node_limit,
            detail=config.detail,
        )
        mindmap = self._generate_with_retry(prompt, config)
        per_hit = _provenance(context)
        known_ids = {node.id for node in context.nodes}
        provenance: list[ProvenanceRecord] = []
        for node in mindmap.nodes:
            kg_node_id = node.id if node.id in known_ids else None
            for record in per_hit:
                if kg_node_id is None:
                    provenance.append(record)
                else:
                    provenance.append(record.model_copy(update={"kg_node_id": kg_node_id}))
        return GenerationResult(
            kind=ArtifactKind.MINDMAP,
            title=mindmap.title,
            content=mindmap.model_dump_json(),
            metadata={
                "nodes": str(len(mindmap.nodes)),
                "edges": str(len(mindmap.edges)),
            },
            provenance=tuple(provenance),
        )

    def _generate_with_retry(self, prompt: str, config: _MindMapConfig) -> EnrichedMindMap:
        last_error: Exception | None = None
        current = prompt
        for _ in range(2):
            try:
                mindmap = self._generate_json(GENERATION_SYSTEM_PROMPT, current, EnrichedMindMap)
            except ValidationError as exc:
                last_error = exc
            except Exception as exc:
                raise HandlerError(f"Mind map generation failed: {exc}") from exc
            else:
                try:
                    _validate_mindmap(mindmap, config.node_limit)
                except HandlerError as exc:
                    last_error = exc
                else:
                    return mindmap
            current = add_generation_retry_instruction(prompt)
        raise HandlerError(f"Mind map generation failed after retry: {last_error}")
