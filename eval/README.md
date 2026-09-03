# PAM Evaluation — Index

This directory holds the evaluation artifacts for **Personal AI Memory (PAM)**.

## Structure

- [`datasets/`](./datasets/) — evaluation datasets
- [`scripts/`](./scripts/) — reusable evaluation and experiment scripts
- [`results/`](./results/) — generated evaluation outputs
- [`reports/`](./reports/) — evaluation / audit reports

## `datasets/`

| File | Status | Notes |
|------|--------|-------|
| `dataset.json` | **Canonical (frozen)** | V3.0 freeze from Phase 5D. Current authoritative reference dataset. |
| `dataset_v1_frozen.json` | **Frozen (historical)** | V1.0 50-query frozen dataset; immutability/back-compat reference. |
| `dataset_v3_proposed.json` | **Proposed** | Candidate proposed dataset, not canonical. |
| `dataset_backup_20260827.json` | **Backup** | Point-in-time snapshot of a prior dataset for recovery/repro. |

Only `dataset.json` (canonical) and `dataset_v1_frozen.json` (frozen) should be treated as authoritative. The proposed and backup files are not canonical.

## `scripts/`

- `run_eval.py` — canonical evaluation runner (baseline + abstention measurement).
- `backward_compat_check.py` — verifies results on the frozen v1 dataset are unchanged.
- `ground_truth_audit.py` — audits dataset ground-truth integrity; writes `reports/ground_truth_audit_report.json`.
- `analyze_reranker.py` — inspects reranker results.
- `sweep_3f.py`, `sweep_combined.py`, `sweep_reranker.py`, `sweep_thresholds.py` — historical threshold/abstention experiment sweeps.

These are experiment/evaluation tooling; they do not alter application or retrieval behavior.

## `results/`

Generated evaluation outputs (e.g. `phase_5d_frozen_baseline.json`, `phase_5f_experiment_*.json`, `threshold_sweep.json`, `qa_measurement.jsonl`). Historical and reproducible from the scripts + datasets. `backup_20260827/` holds a preserved prior snapshot of results.

## `reports/`

- `EVALUATION_AUDIT.md` — evaluation audit write-up.
- `ground_truth_audit_report.json` — output of `scripts/ground_truth_audit.py`.