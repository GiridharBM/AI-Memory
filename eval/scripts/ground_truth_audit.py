"""Ground-truth audit for the PAM V1 evaluation dataset.

Checks for:
- Missing expected sources on positive queries
- Positive queries with empty expected_sources
- Negative queries with non-empty expected_sources
- Duplicate query IDs
- Duplicate query text
- Unreliable ground truth flags
- Source keys not in the known source document mapping
- Malformed category values
- Missing required fields

The valid category and source-key sets are derived from the dataset's own
metadata (``metadata.categories`` and ``metadata.source_documents``) when
present, falling back to the static defaults below for older datasets that
predate that metadata.
"""

from __future__ import annotations

import json
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent
DATASET_PATH = EVAL_DIR / "datasets" / "dataset.json"

VALID_CATEGORIES = {"factoid", "comparison", "negative", "cross_document", "tricky"}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}

KNOWN_SOURCE_KEYS = {
    "neural_networks", "daa_assignment", "jharkhand_protest", "gpt56_demo",
    "openhands", "utthunga", "pcb_design", "leetcode", "tihan", "b_md",
    "pam_smoke_test", "sigmamusicart",
}

REQUIRED_FIELDS = {"id", "query", "expected_sources", "category", "difficulty", "ground_truth_reliable"}


def audit(dataset_path: Path = DATASET_PATH) -> dict:
    with open(dataset_path, encoding="utf-8") as f:
        ds = json.load(f)

    queries = ds["queries"]
    issues: list[dict] = []
    warnings: list[dict] = []

    # Derive the valid category / source-key sets from the dataset's metadata
    # when present, falling back to the static defaults for older datasets.
    metadata = ds.get("metadata", {})
    valid_categories = set(metadata.get("categories", [])) or VALID_CATEGORIES
    known_source_keys = set(metadata.get("source_documents", {}).keys()) or KNOWN_SOURCE_KEYS

    # Duplicate detection
    seen_ids: dict[str, int] = {}
    seen_texts: dict[str, int] = {}

    for i, q in enumerate(queries):
        qid = q.get("id", f"MISSING_ID_{i}")

        # Missing ID
        if "id" not in q:
            issues.append({"type": "missing_id", "index": i, "query": q.get("query", "?")})

        # Duplicate ID
        if qid in seen_ids:
            issues.append({"type": "duplicate_id", "id": qid, "indices": [seen_ids[qid], i]})
        seen_ids[qid] = i

        # Duplicate query text
        text = q.get("query", "")
        if text in seen_texts:
            warnings.append({"type": "duplicate_query_text", "query": text, "indices": [seen_texts[text], i]})
        seen_texts[text] = i

        # Missing required fields
        missing = REQUIRED_FIELDS - set(q.keys())
        if missing:
            issues.append({"type": "missing_fields", "id": qid, "fields": sorted(missing)})

        # Category validation
        cat = q.get("category", "")
        if cat not in valid_categories:
            issues.append({"type": "invalid_category", "id": qid, "category": cat})

        # Difficulty validation
        diff = q.get("difficulty", "")
        if diff not in VALID_DIFFICULTIES:
            issues.append({"type": "invalid_difficulty", "id": qid, "difficulty": diff})

        # Source key validation
        sources = q.get("expected_sources", [])
        for s in sources:
            if s not in known_source_keys:
                issues.append({"type": "unknown_source_key", "id": qid, "source": s})

        # Positive/negative consistency
        if q.get("category") == "negative":
            if sources:
                issues.append({"type": "negative_has_sources", "id": qid, "sources": sources})
        elif q.get("category") != "negative":
            if not sources:
                issues.append({"type": "positive_missing_sources", "id": qid})

        # Ground truth reliability
        if not q.get("ground_truth_reliable", True):
            warnings.append({
                "type": "unreliable_ground_truth",
                "id": qid,
                "query": text,
                "notes": q.get("notes", ""),
            })

    # Summary
    total = len(queries)
    pos = [q for q in queries if q.get("expected_sources")]
    neg = [q for q in queries if not q.get("expected_sources")]
    cats = {}
    for q in queries:
        c = q.get("category", "UNKNOWN")
        cats[c] = cats.get(c, 0) + 1

    result = {
        "summary": {
            "total_queries": total,
            "positive_queries": len(pos),
            "negative_queries": len(neg),
            "categories": cats,
        },
        "issues": issues,
        "warnings": warnings,
        "issue_count": len(issues),
        "warning_count": len(warnings),
        "passed": len(issues) == 0,
    }

    # Print report
    print(f"\nGround-Truth Audit Report")
    print(f"{'=' * 60}")
    print(f"Total queries:  {total}")
    print(f"Positive:       {len(pos)}")
    print(f"Negative:       {len(neg)}")
    print(f"Categories:     {cats}")
    print()

    if issues:
        print(f"ISSUES ({len(issues)}):")
        for iss in issues:
            print(f"  [{iss['type']}] {iss}")
    else:
        print("ISSUES: None")

    print()

    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  [{w['type']}] {w.get('id', '')}: {w.get('query', '')[:60]}")
            if w.get("notes"):
                print(f"    Note: {w['notes']}")
    else:
        print("WARNINGS: None")

    print(f"\nResult: {'PASS' if result['passed'] else 'FAIL'}")

    # Save report
    report_path = EVAL_DIR / "reports" / "ground_truth_audit_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nReport saved to: {report_path}")

    return result


if __name__ == "__main__":
    audit()
