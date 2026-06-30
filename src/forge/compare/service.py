from __future__ import annotations

from pathlib import Path
from typing import Any

from xenibe.metrics.summary import METRIC_NET_PROFIT, METRIC_TOTAL_TRADES, METRIC_WIN_RATE, metrics_to_public

from forge.common import load_metrics, metrics_path, run_dir


COMPARISON_METRICS = (METRIC_WIN_RATE, METRIC_NET_PROFIT, METRIC_TOTAL_TRADES)


def compare_runs(root: Path, experiment: str, run_ids: list[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for run_id in run_ids:
        directory = run_dir(root, experiment, run_id)
        if not metrics_path(directory).exists():
            missing.append(run_id)
            continue
        rows.append({"runId": run_id, **metrics_to_public(load_metrics(directory), COMPARISON_METRICS)})
    if missing:
        return {"error": "missing-artifact", "message": "one or more runs are missing metrics", "missingRuns": missing}
    rows.sort(key=lambda row: (float(row.get("netProfit") or 0.0), float(row.get("winRate") or 0.0)), reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return {"experiment": experiment, "runs": rows, "bestRunId": rows[0]["runId"] if rows else None}
