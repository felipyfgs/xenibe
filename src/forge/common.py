from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xenibe.artifacts.store import ValidationIssue, experiment_dir, load_json


@dataclass(frozen=True)
class ParsedOptions:
    positionals: list[str]
    options: dict[str, str]
    missing_value: str | None = None


def issue_fix(issue: ValidationIssue) -> str:
    if issue.code == "missing-artifact":
        return f"create or restore {issue.path}"
    if issue.code in {"invalid-yaml", "invalid-json", "invalid-jsonl"}:
        return f"fix syntax at {issue.path}"
    if issue.code == "invalid-name":
        return f"rename or update {issue.path} to use the required naming convention"
    return f"update {issue.path} so it satisfies validation: {issue.message}"


def issues_payload(issues: list[ValidationIssue]) -> list[dict[str, str]]:
    return [
        {
            "code": issue.code,
            "path": issue.path,
            "message": issue.message,
            "target": issue.path,
            "fix": issue_fix(issue),
        }
        for issue in issues
    ]


def parse_options(args: list[str], option_names: set[str]) -> ParsedOptions:
    positionals: list[str] = []
    options: dict[str, str] = {}
    index = 0
    while index < len(args):
        value = args[index]
        if value in option_names:
            if index + 1 >= len(args) or args[index + 1].startswith("--"):
                return ParsedOptions(positionals, options, value)
            options[value] = args[index + 1]
            index += 2
            continue
        positionals.append(value)
        index += 1
    return ParsedOptions(positionals, options)


def dry_status(dry_run: bool, success: str = "created") -> str:
    return "dry-run" if dry_run else success


def result_error(result: dict[str, Any]) -> tuple[str, str] | None:
    if "error" not in result:
        return None
    return str(result["error"]), str(result.get("message", result["error"]))


def run_dir(root: Path, experiment: str, run_id: str) -> Path:
    return experiment_dir(root, experiment) / "runs" / run_id


def metrics_path(run_directory: Path) -> Path:
    return run_directory / "metrics.json"


def load_metrics(run_dir: Path) -> dict[str, Any]:
    path = metrics_path(run_dir)
    if not path.exists():
        return {}
    data = load_json(path)
    metrics = data.get("metrics", {})
    return metrics if isinstance(metrics, dict) else {}


def select_metrics(metrics: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: metrics.get(key) for key in keys if key in metrics}


def relative_files(source: Path) -> list[str]:
    if source.is_file():
        return [source.name]
    if not source.exists():
        return []
    return sorted(str(path.relative_to(source)) for path in source.rglob("*") if path.is_file())


def normalize_record(value: Any) -> dict[str, Any]:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if isinstance(value, dict):
        return value
    data: dict[str, Any] = {}
    for key in ("time", "timestamp", "open", "high", "low", "close", "volume"):
        if hasattr(value, key):
            data[key] = getattr(value, key)
    if data:
        return data
    return {"value": str(value)}


def safe_provider_message(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()
    for marker in ("password", "token", "secret", "key="):
        if marker in lowered:
            return "provider operation failed"
    return message


def provider_error_payload(exc: Exception) -> dict[str, str]:
    code = str(getattr(exc, "code", "provider-error"))
    return {"error": code if code.startswith("provider-") else "provider-error", "message": safe_provider_message(exc)}


def provider_metadata(provider: Any) -> dict[str, str]:
    return {"provider": str(getattr(provider, "name", "ebinex")), "mode": str(getattr(provider, "mode", "live"))}


def render_run_report(experiment: str, run_id: str, metrics: dict[str, Any], manifest: dict[str, Any] | None = None) -> str:
    manifest = manifest or {}
    lines = [
        f"# Run {run_id}",
        "",
        f"- Experiment: `{experiment}`",
        f"- Total trades: {metrics.get('total-trades', 0)}",
        f"- Win rate: {float(metrics.get('win-rate', 0.0)):.4f}",
        f"- Net profit: {float(metrics.get('net-profit', 0.0)):.2f}",
    ]
    winning_candidate = metrics.get("winning-candidate", manifest.get("winnerCandidate"))
    best_candidate = metrics.get("best-candidate", manifest.get("bestCandidate"))
    search_state = manifest.get("searchState")
    if winning_candidate is not None:
        lines.append(f"- Winning candidate: `{winning_candidate}`")
    if best_candidate is not None:
        lines.append(f"- Best candidate: `{best_candidate}`")
    if search_state is not None:
        lines.append(f"- Search state: `{search_state}`")
    horizon = metrics.get("horizonValidation")
    if isinstance(horizon, dict):
        lines.append(f"- Horizon validation: `{horizon.get('status', 'unknown')}`")
    lines.append("")
    return "\n".join(lines)
