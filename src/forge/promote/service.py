from __future__ import annotations

from pathlib import Path
from typing import Any

from xenibe.artifacts.store import utc_now, validate_run_dir, write_yaml
from xenibe.metrics.summary import METRIC_NET_PROFIT, METRIC_TOTAL_TRADES, METRIC_WIN_RATE

from forge.common import issues_payload, load_metrics, run_dir, select_metrics


PROMOTION_METRICS = (METRIC_WIN_RATE, METRIC_NET_PROFIT, METRIC_TOTAL_TRADES, "winning-candidate")


def promote_run(root: Path, experiment: str, run_id: str, reason: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    directory = run_dir(root, experiment, run_id)
    issues = validate_run_dir(directory)
    if issues:
        return {"error": "invalid-artifact", "message": "run must be valid before promotion", "issues": issues_payload(issues)}
    target = root / "promoted" / experiment / run_id
    selected_metrics = select_metrics(load_metrics(directory), PROMOTION_METRICS)
    metadata = {
        "source-experiment": experiment,
        "source-run-id": run_id,
        "reason": reason or "target metric satisfied",
        "timestamp": utc_now(),
        "metrics": selected_metrics,
    }
    path = target / "promotion.yml"
    payload: dict[str, Any] = {"experiment": experiment, "runId": run_id, "promotion": str(path), "metadata": metadata}
    if dry_run:
        payload["plannedActions"] = ["write promotion metadata"]
        return payload
    write_yaml(path, metadata)
    return payload
