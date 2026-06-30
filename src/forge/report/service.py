from __future__ import annotations

from pathlib import Path
from typing import Any

from xenibe.artifacts.store import load_json

from forge.common import load_metrics, metrics_path, render_run_report, run_dir


def generate(root: Path, experiment: str, run_id: str, dry_run: bool = False) -> dict[str, Any]:
    directory = run_dir(root, experiment, run_id)
    if not metrics_path(directory).exists():
        return {"error": "missing-artifact", "message": "metrics not found"}
    manifest_path = directory / "manifest.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {}
    report = render_run_report(experiment, run_id, load_metrics(directory), manifest)
    path = directory / "report.md"
    payload: dict[str, Any] = {"experiment": experiment, "runId": run_id, "reportPath": str(path)}
    if dry_run:
        payload["plannedActions"] = ["write report.md"]
        payload["report"] = report
        return payload
    path.write_text(report, encoding="utf-8")
    return payload


def show(root: Path, experiment: str, run_id: str) -> dict[str, Any]:
    directory = run_dir(root, experiment, run_id)
    report_path = directory / "report.md"
    if not report_path.exists():
        return {"error": "missing-artifact", "message": "report not found"}
    manifest = directory / "manifest.json"
    mode = None
    if manifest.exists():
        mode = load_json(manifest).get("mode")
    return {"experiment": experiment, "runId": run_id, "mode": mode, "reportPath": str(report_path), "report": report_path.read_text(encoding="utf-8")}
