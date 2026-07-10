"""In-memory runtime statistics for watcher mode."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RuntimeStats:
    """Runtime-only processing counters."""

    processed: int = 0
    skipped_duplicates: int = 0
    failed: int = 0
    total_processing_seconds: float = 0.0
    total_queue_latency_seconds: float = 0.0
    detection_events: int = 0

    def record_processed(self, *, processing_seconds: float, queue_latency_seconds: float) -> None:
        self.processed += 1
        self.total_processing_seconds += processing_seconds
        self.total_queue_latency_seconds += queue_latency_seconds

    def record_duplicate(self) -> None:
        self.skipped_duplicates += 1

    def record_failed(self) -> None:
        self.failed += 1

    def record_detection(self) -> None:
        self.detection_events += 1

    @property
    def average_processing_seconds(self) -> float:
        if self.processed == 0:
            return 0.0
        return self.total_processing_seconds / self.processed

    @property
    def average_queue_latency_seconds(self) -> float:
        completed = self.processed + self.skipped_duplicates + self.failed
        if completed == 0:
            return 0.0
        return self.total_queue_latency_seconds / completed
