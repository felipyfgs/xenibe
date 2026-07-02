from __future__ import annotations

from pathlib import Path
from typing import Any

from forge.common import issues_payload, run_dir
from xenibe.artifacts.store import ValidationIssue, load_run_view


def completed_run(root: Path, experiment: str, run_id: str) -> dict[str, Any]:
    directory = run_dir(root, experiment, run_id)
    if not directory.exists():
        return {"error": "missing-artifact", "message": "run not found", "issues": []}
    loaded = load_run_view(directory, expected_experiment=experiment)
    if loaded["issues"]:
        return {"error": "invalid-artifact", "message": "run validation failed", "issues": issues_payload(loaded["issues"])}
    manifest = loaded["manifest"]
    if manifest.get("status") != "completed":
        status_path = directory / ("run.json" if loaded["layout"] == "compact" else "manifest.json")
        issue = ValidationIssue("invalid-artifact", f"{status_path}:status", "run must be completed")
        return {"error": "invalid-artifact", "message": "run must be completed", "issues": issues_payload([issue])}
    if not isinstance(loaded["metrics"], dict):
        metrics_path = directory / ("run.json" if loaded["layout"] == "compact" else "metrics.json")
        issue = ValidationIssue("invalid-artifact", f"{metrics_path}:metrics", "must be an object")
        return {"error": "invalid-artifact", "message": "run validation failed", "issues": issues_payload([issue])}
    return {
        "experiment": experiment,
        "runId": run_id,
        "path": str(directory),
        "directory": directory,
        "layout": loaded["layout"],
        "manifest": manifest,
        "inputs": loaded["inputs"],
        "configSnapshot": loaded["configSnapshot"],
        "metrics": loaded["metrics"],
        "scoreboard": loaded["scoreboard"],
        "recordsByKind": loaded["recordsByKind"],
        "artifactPaths": loaded["artifactPaths"],
        "duplicateOnly": loaded["duplicateOnly"],
        "bestEligible": loaded["bestEligible"],
        "promotionEligible": loaded["promotionEligible"],
        "winnerCandidate": loaded["winnerCandidate"],
        "recordCounts": loaded["recordCounts"],
    }
