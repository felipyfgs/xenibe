from __future__ import annotations

from pathlib import Path
from typing import Any

from xenibe.artifacts.store import load_json

from forge.common import load_metrics


def _run_dir(root: Path, experiment: str, run_id: str) -> Path:
    return root / experiment / "runs" / run_id


def generate(root: Path, experiment: str, run_id: str, dry_run: bool = False) -> dict[str, Any]:
    run_dir = _run_dir(root, experiment, run_id)
    metrics_path = run_dir / "metrics.json"
    if not metrics_path.exists():
        return {"error": "missing-artifact", "message": "metrics not found"}
    metrics = load_metrics(run_dir)
    report = "\n".join(
        [
            f"# Run {run_id}",
            "",
            f"- Experiment: `{experiment}`",
            f"- Total trades: {metrics.get('total-trades', 0)}",
            f"- Win rate: {float(metrics.get('win-rate', 0.0)):.4f}",
            f"- Net profit: {float(metrics.get('net-profit', 0.0)):.2f}",
            "",
        ]
    )
    path = run_dir / "report.md"
    payload: dict[str, Any] = {"experiment": experiment, "runId": run_id, "reportPath": str(path)}
    if dry_run:
        payload["plannedActions"] = ["write report.md"]
        payload["report"] = report
        return payload
    path.write_text(report, encoding="utf-8")
    return payload


def show(root: Path, experiment: str, run_id: str) -> dict[str, Any]:
    report_path = _run_dir(root, experiment, run_id) / "report.md"
    if not report_path.exists():
        return {"error": "missing-artifact", "message": "report not found"}
    manifest = _run_dir(root, experiment, run_id) / "manifest.json"
    mode = None
    if manifest.exists():
        mode = load_json(manifest).get("mode")
    return {"experiment": experiment, "runId": run_id, "mode": mode, "reportPath": str(report_path), "report": report_path.read_text(encoding="utf-8")}
