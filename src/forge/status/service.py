from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from forge.common import issues_payload, load_metrics, select_metrics
from xenibe.artifacts.store import ValidationIssue, experiment_dir, experiments_root, load_json, validate_config, validate_experiment_dir


SUMMARY_METRICS = ("win-rate", "net-profit", "total-trades", "winning-candidate", "best-candidate")
RUN_ARTIFACTS = ("manifest.json", "scoreboard.json", "candidates.jsonl", "metrics.json", "report.md")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except Exception:
        return {}


def _artifact_paths(paths: dict[str, Path]) -> dict[str, str]:
    return {name: str(path) for name, path in paths.items() if path.exists()}


def _experiment_names(root: Path) -> list[str]:
    base = experiments_root(root)
    if not base.exists():
        return []
    return sorted(path.name for path in base.iterdir() if path.is_dir())


def _latest_run_dirs(base: Path) -> list[Path]:
    runs = base / "runs"
    if not runs.exists():
        return []
    return sorted((path for path in runs.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True)


def _scoreboard_summary(path: Path) -> dict[str, Any]:
    scoreboard = _load_json(path)
    candidates = scoreboard.get("rankings", {}).get("candidates", [])
    if not isinstance(candidates, list):
        candidates = []
    top = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
    summary: dict[str, Any] = {
        "candidateCount": len(candidates),
    }
    if scoreboard.get("targetMetric") is not None:
        summary["targetMetric"] = scoreboard["targetMetric"]
    if top:
        summary["topCandidate"] = {
            "candidateId": top.get("candidateId"),
            "classification": top.get("classification"),
            "status": top.get("status"),
            "metrics": top.get("metrics", {}),
        }
    return summary


def run_summary(run_directory: Path) -> dict[str, Any]:
    manifest = _load_json(run_directory / "manifest.json")
    metrics = load_metrics(run_directory)
    summary: dict[str, Any] = {
        "runId": str(manifest.get("runId") or run_directory.name),
        "path": str(run_directory),
        "artifactPaths": _artifact_paths({name.removesuffix(".json").removesuffix(".jsonl").removesuffix(".md"): run_directory / name for name in RUN_ARTIFACTS}),
    }
    for key in ("mode", "status", "createdAt", "completedAt", "searchState", "winnerCandidate", "bestCandidate"):
        if manifest.get(key) is not None:
            summary[key] = manifest[key]
    if metrics:
        summary["metrics"] = select_metrics(metrics, SUMMARY_METRICS)
    scoreboard_path = run_directory / "scoreboard.json"
    if scoreboard_path.exists():
        summary["scoreboard"] = _scoreboard_summary(scoreboard_path)
    return summary


def _experiment_artifact_paths(base: Path) -> dict[str, str]:
    paths = {
        "experiment": base,
        "experimentYaml": base / "experiment.yml",
        "ingestYaml": base / "ingest.yml",
        "searchScopeYaml": base / "search-scope.yml",
        "data": base / "data",
        "runs": base / "runs",
        "scopeRevisions": base / "scope-revisions.jsonl",
    }
    return _artifact_paths(paths)


def _experiment_summary(root: Path, name: str) -> dict[str, Any]:
    base = experiment_dir(root, name)
    issues = validate_experiment_dir(base)
    latest_runs = [run_summary(path) for path in _latest_run_dirs(base)[:3]]
    return {
        "name": name,
        "path": str(base),
        "valid": not issues,
        "issues": issues_payload(issues),
        "artifactPaths": _experiment_artifact_paths(base),
        "latestRunIds": [run["runId"] for run in latest_runs],
        "latestRuns": latest_runs,
    }


def _issue(code: str, path: Path, message: str) -> ValidationIssue:
    return ValidationIssue(code, str(path), message)


def inspect_root(root: Path) -> dict[str, Any]:
    artifact_paths = {
        "root": str(root),
        "config": str(root / "config.yml"),
        "experimentsRoot": str(experiments_root(root)),
    }
    if not root.exists():
        issue = _issue("missing-artifact", root, "artifact root does not exist")
        return {
            "state": "missing-root",
            "artifactRoot": str(root),
            "rootValid": False,
            "rootIssues": issues_payload([issue]),
            "blockedReasons": issues_payload([issue]),
            "experiments": [],
            "artifactPaths": artifact_paths,
        }

    root_issues = validate_config(root)
    experiments = [_experiment_summary(root, name) for name in _experiment_names(root)]
    experiment_issues = [
        ValidationIssue(str(issue["code"]), str(issue.get("path") or issue.get("target") or summary["path"]), str(issue["message"]))
        for summary in experiments
        for issue in summary["issues"]
    ]
    blocked_reasons = issues_payload([*root_issues, *experiment_issues])
    if blocked_reasons:
        state = "blocked"
    elif not experiments:
        state = "no-experiments"
    else:
        state = "ready"
    return {
        "state": state,
        "artifactRoot": str(root),
        "rootValid": not root_issues,
        "rootIssues": issues_payload(root_issues),
        "blockedReasons": blocked_reasons,
        "experiments": experiments,
        "artifactPaths": artifact_paths,
    }


def next_actions(root: Path, data: dict[str, Any]) -> list[str]:
    state = data.get("state")
    if state == "missing-root":
        return [f"forge init --root {root} --json"]
    if state == "no-experiments":
        return [f"forge experiment new <name> --root {root} --json"]
    if state == "blocked":
        return [f"repair reported artifacts under {root}", f"forge validate --root {root} --json", f"forge status --root {root} --json"]
    experiments = data.get("experiments", [])
    first = experiments[0]["name"] if experiments else "<experiment>"
    return [f"forge instructions orchestrate {first} --root {root} --json", f"forge run backtest {first} --root {root} --json"]


def json_fingerprint(root: Path) -> str:
    data = inspect_root(root)
    return json.dumps(data, ensure_ascii=False, sort_keys=True)
