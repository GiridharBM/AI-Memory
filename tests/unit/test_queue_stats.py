"""Tests for RuntimeStats queue latency calculation."""

from __future__ import annotations

from app.queue.stats import RuntimeStats


def test_average_latency_excludes_duplicates() -> None:
    stats = RuntimeStats()
    stats.record_processed(processing_seconds=1.0, queue_latency_seconds=10.0)
    stats.record_duplicate()
    assert stats.average_queue_latency_seconds == 10.0


def test_average_latency_excludes_failed() -> None:
    stats = RuntimeStats()
    stats.record_processed(processing_seconds=1.0, queue_latency_seconds=10.0)
    stats.record_failed()
    assert stats.average_queue_latency_seconds == 10.0


def test_average_latency_all_processed() -> None:
    stats = RuntimeStats()
    for latency in (5.0, 10.0, 15.0):
        stats.record_processed(processing_seconds=1.0, queue_latency_seconds=latency)
    assert stats.average_queue_latency_seconds == 10.0


def test_average_latency_zero_processed() -> None:
    stats = RuntimeStats()
    stats.record_duplicate()
    stats.record_failed()
    assert stats.average_queue_latency_seconds == 0.0
