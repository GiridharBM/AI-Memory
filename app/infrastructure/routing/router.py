"""Strategy-based processor router."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import ModelRoutingSettings
from app.core.logging import get_logger
from app.domain.routing import DocumentClassification, ProcessorSelection

logger = get_logger(__name__)


@dataclass(slots=True)
class RoutedProcessor:
    """Registered processor and its selection logic."""

    name: str
    kinds: set[str]
    model_key: str

    def matches(self, classification: DocumentClassification) -> bool:
        return classification.kind in self.kinds

    @property
    def supported_kinds(self) -> set[str]:
        return self.kinds


class ProcessorRouter:
    """Select processors without hard-coded if/else chains."""

    def __init__(self, routing: ModelRoutingSettings) -> None:
        self._routing = routing
        self._processors: list[RoutedProcessor] = []

    def register(self, processor: RoutedProcessor) -> None:
        self._processors.append(processor)

    def select(self, classification: DocumentClassification) -> ProcessorSelection:
        for processor in self._processors:
            if processor.matches(classification):
                return ProcessorSelection(
                    processor_name=processor.name,
                    model_name=self._routing.model_for(processor.model_key),
                )

        return ProcessorSelection(
            processor_name="TextProcessor",
            model_name=self._routing.model_for("general_text"),
        )
