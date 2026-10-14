"""Observational QA measurement harness (Phase 6C).

MEASUREMENT ONLY — never changes production QA decisions.

Runs the existing production QA pipeline (``QAWorkflow``) over a sample of
questions and emits one observational JSONL record per attempt plus a terminal
summary.  It:

- never alters the ANSWERED / ABSTAINED / FAILED outcome,
- adds no LLM judge and performs no additional model calls,
- reads (never writes) the evaluation dataset and the knowledge base,
- records the insufficiency-language flag as a *heuristic* only.

Requires a live Ollama server and an indexed knowledge base.  Run:

        python -m app.application.qa_measurement_harness --limit 30
            --out eval/results/qa_measurement.jsonl

Example output row (observational telemetry):

    {"query": "...", "outcome": "answered", "failure_category": "none",
     "answer_length": 42, "retrieved_source_count": 5,
     "citation_count": 1, "valid_citation_count": 1,
     "invalid_citation_count": 0, "duplicate_citation_count": 0,
     "has_insufficiency_language": false, "latency_ms": 3831.7}

If the model is unreachable every row records a ``failure_category`` and the
run still completes, so the corpus of rows is usable as-is.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import cast

from app.application.qa_workflow import (
    QAEmptyAnswerError,
    QAError,
    QATimeoutError,
    QAWorkflow,
    extract_citations,
    has_insufficiency_language,
)
from app.core.config import load_settings

FAILURE_NONE = "none"
FAILURE_TIMEOUT = "timeout"
FAILURE_EMPTY_ANSWER = "empty_answer"
FAILURE_GENERATION = "generation_error"
FAILURE_UNEXPECTED = "unexpected"


def record_row(
    query: str,
    *,
    result: object | None = None,
    failure: str = FAILURE_NONE,
    latency_s: float = 0.0,
) -> dict[str, object]:
    """Flatten a QA attempt into one observational JSONL row.

    ``result`` is a ``QAAnswer`` (answered or abstained); when it is ``None``
    the row records a failure category instead.  Purely observational.
    """

    base = {
        "query": query,
        "outcome": "failed" if result is None else getattr(result, "outcome", "answered"),
        "failure_category": failure,
        "latency_ms": round(latency_s * 1000.0, 1),
    }
    if result is None:
        return {
            **base,
            "answer_length": None,
            "retrieved_source_count": None,
            "citation_count": None,
            "valid_citation_count": None,
            "invalid_citation_count": None,
            "duplicate_citation_count": None,
            "has_insufficiency_language": None,
        }

    answer = getattr(result, "answer", "") or ""
    citations = getattr(result, "citations", None) or []
    invalid = getattr(result, "invalid_citations", None) or []
    duplicates = getattr(result, "duplicate_citations", 0) or 0
    return {
        **base,
        "answer_length": len(answer),
        "retrieved_source_count": len(getattr(result, "sources", None) or []),
        "citation_count": len(extract_citations(answer)),
        "valid_citation_count": len(citations),
        "invalid_citation_count": len(invalid),
        "duplicate_citation_count": duplicates,
        "has_insufficiency_language": has_insufficiency_language(answer),
    }


def _classify(exc: Exception) -> str:
    if isinstance(exc, QATimeoutError):
        return FAILURE_TIMEOUT
    if isinstance(exc, QAEmptyAnswerError):
        return FAILURE_EMPTY_ANSWER
    if isinstance(exc, QAError):
        return FAILURE_GENERATION
    return FAILURE_UNEXPECTED


def _print_summary(rows: list[dict[str, object]]) -> None:
    by_outcome = Counter(str(row["outcome"]) for row in rows)
    by_failure = Counter(
        str(row["failure_category"]) for row in rows if str(row["failure_category"]) != FAILURE_NONE
    )
    answered = [row for row in rows if str(row["outcome"]) == "answered"]
    insufficiency = sum(
        1
        for row in answered
        if bool(cast(bool | None, row["has_insufficiency_language"]))
    )
    cited = sum(
        1
        for row in answered
        if int(cast(int | None, row["citation_count"]) or 0) > 0
    )
    latencies: list[float] = []
    for row in rows:
        latency = row["latency_ms"]
        if latency is not None:
            latencies.append(float(cast(float | int, latency)))

    print(f"Queries run: {len(rows)}")
    print(f"  outcomes: {dict(by_outcome)}")
    print(f"  failures: {dict(by_failure)}")
    if answered:
        print(
            f"  answered: n={len(answered)}, cited={cited}, "
            f"insufficiency_language={insufficiency}",
        )
    if latencies:
        print(
            f"  latency ms: mean={sum(latencies) / len(latencies):.0f} "
            f"max={max(latencies):.0f}",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("eval/datasets/dataset.json"))
    parser.add_argument(
        "--limit", type=int, default=None, help="Max queries to run (default: all)."
    )
    parser.add_argument("--category", default=None, help="Only run queries of this category.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("eval/results/qa_measurement.jsonl"),
        help="Append-mode JSONL output (default: eval/results/qa_measurement.jsonl).",
    )
    args = parser.parse_args(argv)

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    queries = [q["query"] for q in dataset["queries"]]
    if args.category:
        queries = [q["query"] for q in dataset["queries"] if q.get("category") == args.category]
    if args.limit:
        queries = queries[: args.limit]

    workflow = QAWorkflow.create_default(load_settings())
    args.out.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    with args.out.open("a", encoding="utf-8") as fh:
        for query in queries:
            start = time.perf_counter()
            try:
                result = workflow.ask(query)
                row = record_row(query, result=result, latency_s=time.perf_counter() - start)
            except Exception as exc:
                row = record_row(
                    query,
                    failure=_classify(exc),
                    latency_s=time.perf_counter() - start,
                )
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            rows.append(row)

    _print_summary(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())