from __future__ import annotations

from pathlib import Path
from typing import Any

from forge.common import issues_payload, run_dir
from xenibe.artifacts.store import ValidationIssue, load_json, validate_run_dir


def completed_run(root: Path, experiment: str, run_id: str) -> dict[str, Any]:
    directory = run_dir(root, experiment, run_id)
    if not directory.exists():
        return {"error": "missing-artifact", "message": "run not found", "issues": []}
    issues = validate_run_dir(directory, expected_experiment=experiment)
    if issues:
        return {"error": "invalid-artifact", "message": "run validation failed", "issues": issues_payload(issues)}
    manifest = load_json(directory / "manifest.json")
    if manifest.get("status") != "completed":
        issue = ValidationIssue("invalid-artifact", f"{directory / 'manifest.json'}:status", "run must be completed")
        return {"error": "invalid-artifact", "message": "run must be completed", "issues": issues_payload([issue])}
    metrics_envelope = load_json(directory / "metrics.json")
    metrics = metrics_envelope.get("metrics", {})
    if not isinstance(metrics, dict):
        issue = ValidationIssue("invalid-artifact", f"{directory / 'metrics.json'}:metrics", "must be an object")
        return {"error": "invalid-artifact", "message": "run validation failed", "issues": issues_payload([issue])}
    return {
        "experiment": experiment,
        "runId": run_id,
        "path": str(directory),
        "directory": directory,
        "manifest": manifest,
        "metrics": metrics,
        "scoreboard": load_json(directory / "scoreboard.json"),
    }
