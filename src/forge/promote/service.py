from __future__ import annotations

from pathlib import Path
from typing import Any

from xenibe.artifacts.store import utc_now, write_yaml
from xenibe.metrics.summary import METRIC_NET_PROFIT, METRIC_TOTAL_TRADES, METRIC_WIN_RATE

from forge.common import select_metrics
from forge.run_consumer import completed_run


PROMOTION_METRICS = (METRIC_WIN_RATE, METRIC_NET_PROFIT, METRIC_TOTAL_TRADES, "winning-candidate")


def promote_run(root: Path, experiment: str, run_id: str, reason: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    loaded = completed_run(root, experiment, run_id)
    if "error" in loaded:
        loaded["message"] = "run must be valid before promotion"
        return loaded
    target = root / "promoted" / experiment / run_id
    selected_metrics = select_metrics(loaded["metrics"], PROMOTION_METRICS)
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
