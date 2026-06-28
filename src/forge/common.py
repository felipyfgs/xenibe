from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from xenibe.artifacts.store import ValidationIssue, load_json


def issues_payload(issues: list[ValidationIssue]) -> list[dict[str, str]]:
    return [{"code": issue.code, "path": issue.path, "message": issue.message} for issue in issues]


def option_value(args: list[str], name: str, default: str | None = None) -> str | None:
    if name not in args:
        return default
    index = args.index(name)
    if index + 1 >= len(args):
        return default
    return args[index + 1]


def strip_option(args: list[str], name: str) -> list[str]:
    cleaned: list[str] = []
    index = 0
    while index < len(args):
        if args[index] == name:
            index += 2
            continue
        cleaned.append(args[index])
        index += 1
    return cleaned


def load_metrics(run_dir: Path) -> dict[str, Any]:
    metrics_path = run_dir / "metrics.json"
    if not metrics_path.exists():
        return {}
    data = load_json(metrics_path)
    metrics = data.get("metrics", {})
    return metrics if isinstance(metrics, dict) else {}


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


def read_json_text(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("json-root-must-be-object")
    return data
