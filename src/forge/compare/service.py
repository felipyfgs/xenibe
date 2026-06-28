from __future__ import annotations

from pathlib import Path
from typing import Any

from xenibe.artifacts.store import experiment_dir

from forge.common import load_metrics


def compare_runs(root: Path, experiment: str, run_ids: list[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for run_id in run_ids:
        run_dir = experiment_dir(root, experiment) / "runs" / run_id
        metrics_path = run_dir / "metrics.json"
        if not metrics_path.exists():
            missing.append(run_id)
            continue
        metrics = load_metrics(run_dir)
        rows.append(
            {
                "runId": run_id,
                "winRate": metrics.get("win-rate"),
                "netProfit": metrics.get("net-profit"),
                "totalTrades": metrics.get("total-trades"),
            }
        )
    if missing:
        return {"error": "missing-artifact", "message": "one or more runs are missing metrics", "missingRuns": missing}
    rows.sort(key=lambda row: (float(row.get("netProfit") or 0.0), float(row.get("winRate") or 0.0)), reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return {"experiment": experiment, "runs": rows, "bestRunId": rows[0]["runId"] if rows else None}
