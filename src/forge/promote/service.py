from __future__ import annotations

from pathlib import Path
from typing import Any

from xenibe.artifacts.store import utc_now, validate_run_dir, write_yaml

from forge.common import issues_payload, load_metrics


def promote_run(root: Path, experiment: str, run_id: str, reason: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    run_dir = root / experiment / "runs" / run_id
    issues = validate_run_dir(run_dir)
    if issues:
        return {"error": "invalid-artifact", "message": "run must be valid before promotion", "issues": issues_payload(issues)}
    target = root / "promoted" / experiment / run_id
    metrics = load_metrics(run_dir)
    selected_metrics = {key: metrics.get(key) for key in ("win-rate", "net-profit", "total-trades", "winning-candidate") if key in metrics}
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
