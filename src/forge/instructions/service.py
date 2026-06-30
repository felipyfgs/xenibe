from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from forge.common import issues_payload, relative_files
from forge.status.service import run_summary
from xenibe.artifacts.schemas import DETAIL_JSONL_FILES, RUN_ARTIFACTS
from xenibe.artifacts.store import ValidationIssue, experiment_dir, experiments_root, load_experiment, load_json, load_yaml, validate_config, validate_experiment_dir
from xenibe.metrics.summary import METRIC_NET_PROFIT
from xenibe.strategy import candidate_allows_target_hit, rank_candidates, resolve_limits, target_satisfied


TERMINAL_LIMIT_STATES = {"limits-exhausted", "max-rounds", "stagnation"}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except Exception:
        return {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
    return records


def _artifact_key(filename: str) -> str:
    stem = filename.removesuffix(".json").removesuffix(".jsonl").removesuffix(".yml").removesuffix(".md")
    parts = stem.split("-")
    return parts[0] + "".join(part.title() for part in parts[1:])


def _artifact_paths(base: Path, latest_run: Path | None = None) -> dict[str, str]:
    paths: dict[str, Path] = {
        "root": base.parent.parent,
        "experiment": base,
        "experimentYaml": base / "experiment.yml",
        "ingestYaml": base / "ingest.yml",
        "candidateSearchYaml": base / "search-scope.yml",
        "data": base / "data",
        "runs": base / "runs",
        "scopeRevisions": base / "scope-revisions.jsonl",
    }
    if latest_run is not None:
        paths["latestRun"] = latest_run
        for filename in (*RUN_ARTIFACTS, *DETAIL_JSONL_FILES):
            paths[_artifact_key(filename)] = latest_run / filename
    return {name: str(path) for name, path in paths.items() if path.exists()}


def _context_files(base: Path, latest_run: Path | None = None) -> dict[str, list[str]]:
    files = {
        "experiment": [
            base / "experiment.yml",
            base / "ingest.yml",
            base / "search-scope.yml",
            base / "risk.yml",
            base / "provider.yml",
            base / "report.yml",
        ],
        "data": [base / "data" / name for name in relative_files(base / "data")],
        "revisions": [base / "scope-revisions.jsonl"],
    }
    if latest_run is not None:
        files["latestRun"] = [latest_run / name for name in (*RUN_ARTIFACTS, *DETAIL_JSONL_FILES)]
    return {key: [str(path) for path in paths if path.exists()] for key, paths in files.items() if any(path.exists() for path in paths)}


def _latest_run_dirs(base: Path) -> list[Path]:
    runs = base / "runs"
    if not runs.exists():
        return []
    return sorted((path for path in runs.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True)


def _latest_completed_run(base: Path) -> Path | None:
    for path in _latest_run_dirs(base):
        manifest = _load_json(path / "manifest.json")
        if manifest.get("status") == "completed":
            return path
    return None


def _candidate_summary(record: dict[str, Any], target_metric: str, run_id: str) -> dict[str, Any]:
    metrics = record.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    selected_metrics = {
        target_metric: metrics.get(target_metric),
        METRIC_NET_PROFIT: metrics.get(METRIC_NET_PROFIT),
    }
    return {
        "runId": run_id,
        "candidateId": record.get("candidateId"),
        "classification": record.get("classification"),
        "status": record.get("status"),
        "targetMetric": target_metric,
        "metrics": {key: value for key, value in selected_metrics.items() if value is not None},
        "horizonValidation": record.get("horizonValidation"),
        "candidateFingerprint": record.get("candidateFingerprint"),
        "evaluationFingerprint": record.get("evaluationFingerprint"),
    }


def _best_candidate(run_directory: Path, target_metric: str) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    scoreboard = _load_json(run_directory / "scoreboard.json")
    ranked = scoreboard.get("rankings", {}).get("candidates", [])
    if isinstance(ranked, list):
        candidates = [record for record in ranked if isinstance(record, dict)]
    if not candidates:
        candidates = rank_candidates(_read_jsonl(run_directory / "candidates.jsonl"), target_metric)
    if not candidates:
        return None
    best = candidates[0]
    return _candidate_summary(best, target_metric, run_directory.name)


def _revision_context(base: Path) -> dict[str, Any] | None:
    path = base / "scope-revisions.jsonl"
    records = _read_jsonl(path)
    if not path.exists():
        return None
    context: dict[str, Any] = {"path": str(path), "count": len(records)}
    if records:
        context["latest"] = records[-1]
    return context


def _blocked_data(root: Path, experiment: str, state: str, issues: list[ValidationIssue], message: str) -> dict[str, Any]:
    base = experiment_dir(root, experiment)
    return {
        "error": "missing-artifact" if any(issue.code == "missing-artifact" for issue in issues) else "invalid-artifact",
        "message": message,
        "state": state,
        "experiment": experiment,
        "artifactPaths": _artifact_paths(base),
        "contextFiles": _context_files(base),
        "blockedReasons": issues_payload(issues),
    }


def _next_actions(root: Path, experiment: str, state: str, run_id: str | None = None) -> list[str]:
    if state == "missing-root":
        return [f"forge status --root {root} --json", f"forge init --root {root} --json"]
    if state == "no-experiments":
        return [f"forge status --root {root} --json", f"forge experiment new <name> --root {root} --json"]
    if state == "blocked":
        return [f"repair reported artifacts under {experiment_dir(root, experiment)}", f"forge validate --root {root} --json"]
    if state == "target-hit":
        selected = run_id or "<run-id>"
        return [f"forge run promote {experiment} {selected} --root {root} --json", f"forge report show {experiment} {selected} --root {root} --json"]
    if state == "limits-exhausted":
        return [f"revise {experiment_dir(root, experiment) / 'search-scope.yml'} or archive the experiment", f"forge run compare {experiment} <run-id-a> <run-id-b> --root {root} --json"]
    return [f"forge run backtest {experiment} --root {root} --json", f"forge validate --root {root} --json"]


def _state_from_run(latest_run: dict[str, Any] | None, best_candidate: dict[str, Any] | None, target: dict[str, Any]) -> str:
    if latest_run is None:
        return "ready"
    search_state = latest_run.get("searchState")
    if search_state == "target-hit" and candidate_allows_target_hit(best_candidate):
        return "target-hit"
    if best_candidate is not None and candidate_allows_target_hit(best_candidate) and target_satisfied(best_candidate.get("metrics", {}), target):
        return "target-hit"
    if search_state in TERMINAL_LIMIT_STATES:
        return "limits-exhausted"
    return "ready"


def orchestrate(root: Path, experiment: str) -> tuple[dict[str, Any], list[str], bool]:
    if not root.exists():
        issue = ValidationIssue("missing-artifact", str(root), "artifact root does not exist")
        data = _blocked_data(root, experiment, "missing-root", [issue], "artifact root does not exist")
        return data, _next_actions(root, experiment, "missing-root"), False

    root_issues = validate_config(root)
    names = sorted(path.name for path in experiments_root(root).iterdir() if path.is_dir()) if experiments_root(root).exists() else []
    if not names:
        issue = ValidationIssue("missing-artifact", str(experiments_root(root)), "no experiments found")
        data = _blocked_data(root, experiment, "no-experiments", [*root_issues, issue], "no experiments found")
        return data, _next_actions(root, experiment, "no-experiments"), False

    base = experiment_dir(root, experiment)
    if not base.exists():
        issue = ValidationIssue("missing-artifact", str(base), "experiment not found")
        data = _blocked_data(root, experiment, "blocked", [*root_issues, issue], "experiment not found")
        return data, _next_actions(root, experiment, "blocked"), False

    experiment_issues = validate_experiment_dir(base)
    if root_issues or experiment_issues:
        data = _blocked_data(root, experiment, "blocked", [*root_issues, *experiment_issues], "experiment validation failed")
        return data, _next_actions(root, experiment, "blocked"), False

    configs = load_experiment(root, experiment)
    search_scope = configs["search-scope.yml"]
    target = configs["experiment.yml"]["target"]
    latest_run_dir = _latest_completed_run(base)
    latest_run = run_summary(latest_run_dir) if latest_run_dir is not None else None
    latest_runs = [run_summary(path) for path in _latest_run_dirs(base)[:3]]
    target_metric = str(target["metric"])
    best_candidate = _best_candidate(latest_run_dir, target_metric) if latest_run_dir is not None else None
    state = _state_from_run(latest_run, best_candidate, target)
    data = {
        "state": state,
        "experiment": experiment,
        "target": target,
        "loopLimits": resolve_limits(search_scope),
        "blockedReasons": [],
        "contextFiles": _context_files(base, latest_run_dir),
        "artifactPaths": _artifact_paths(base, latest_run_dir),
        "latestRuns": latest_runs,
        "bestCandidate": best_candidate,
        "revisionContext": _revision_context(base),
        "candidateSearch": {
            "path": str(base / "search-scope.yml"),
            "flow": search_scope.get("flow", []),
        },
    }
    return data, _next_actions(root, experiment, state, latest_run_dir.name if latest_run_dir is not None else None), True


def read_search_scope(path: Path) -> dict[str, Any]:
    return load_yaml(path)
