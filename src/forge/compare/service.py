from __future__ import annotations

from pathlib import Path
from typing import Any

from xenibe.metrics.summary import METRIC_NET_PROFIT, METRIC_TOTAL_TRADES, METRIC_WIN_RATE

from forge.common import select_metrics
from forge.run_consumer import completed_run


COMPARISON_METRICS = (METRIC_WIN_RATE, METRIC_NET_PROFIT, METRIC_TOTAL_TRADES)


def compare_runs(root: Path, experiment: str, run_ids: list[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for run_id in run_ids:
        loaded = completed_run(root, experiment, run_id)
        if "error" in loaded:
            loaded["runId"] = run_id
            return loaded
        rows.append({"runId": run_id, **select_metrics(loaded["metrics"], COMPARISON_METRICS)})
    rows.sort(key=lambda row: (float(row.get(METRIC_NET_PROFIT) or 0.0), float(row.get(METRIC_WIN_RATE) or 0.0)), reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return {"experiment": experiment, "runs": rows, "bestRunId": rows[0]["runId"] if rows else None}
