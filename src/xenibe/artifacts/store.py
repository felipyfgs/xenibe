from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from xenibe.artifacts.naming import find_non_kebab_keys, is_kebab, is_run_id
from xenibe.artifacts.schemas import (
    DEFAULT_EXPERIMENT,
    DEFAULT_INGEST,
    DEFAULT_PROVIDER,
    DEFAULT_REPORT,
    DEFAULT_RISK,
    DEFAULT_SEARCHSCOPE,
    DETAIL_JSONL_FILES,
    EXPERIMENT_FILES,
    EXPERIMENT_REQUIRED_KEYS,
    RUN_ARTIFACTS,
    RUN_JSON_REQUIRED_KEYS,
    RUN_JSONL_FILES,
)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: str
    message: str


class ImmutableRunError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def make_run_id(prefix: str = "bt") -> str:
    return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("yaml-root-must-be-object")
    return data


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("json-root-must-be-object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def init_artifact_root(root: Path) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for name in ("promoted", "archived", "exports", "assets"):
        path = root / name
        missing = not path.exists()
        path.mkdir(exist_ok=True)
        if missing:
            created.append(path)
    config = root / "config.yml"
    if not config.exists():
        write_yaml(
            config,
            {
                "schema-version": 1,
                "artifact": {"root": str(root)},
                "contexts": {
                    "promoted": {"path": "promoted"},
                    "archived": {"path": "archived"},
                    "exports": {"path": "exports"},
                    "assets": {"path": "assets"},
                },
            },
        )
        created.append(config)
    return created


def create_experiment(root: Path, name: str) -> Path:
    if not is_kebab(name):
        raise ValueError("experiment-name-must-be-kebab-case")
    experiment = root / name
    if experiment.exists():
        raise FileExistsError(name)
    experiment.mkdir(parents=True)
    defaults = {
        "experiment.yml": {**DEFAULT_EXPERIMENT, "name": name},
        "ingest.yml": DEFAULT_INGEST,
        "searchscope.yml": DEFAULT_SEARCHSCOPE,
        "risk.yml": DEFAULT_RISK,
        "provider.yml": DEFAULT_PROVIDER,
        "report.yml": DEFAULT_REPORT,
    }
    for filename, data in defaults.items():
        write_yaml(experiment / filename, data)
    (experiment / "runs").mkdir()
    return experiment


def list_experiments(root: Path) -> list[str]:
    if not root.exists():
        return []
    reserved = {"promoted", "archived", "exports", "assets"}
    names = []
    for child in root.iterdir():
        if child.is_dir() and child.name not in reserved and (child / "experiment.yml").exists():
            names.append(child.name)
    return sorted(names)


def load_experiment(root: Path, name: str) -> dict[str, dict[str, Any]]:
    base = root / name
    return {filename: load_yaml(base / filename) for filename in EXPERIMENT_FILES}


def validate_experiment_dir(path: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not is_kebab(path.name):
        issues.append(ValidationIssue("invalid-name", str(path), "experiment directory must use kebab-case"))
    loaded: dict[str, dict[str, Any]] = {}
    for filename in EXPERIMENT_FILES:
        file_path = path / filename
        if not file_path.exists():
            issues.append(ValidationIssue("missing-artifact", str(file_path), f"missing {filename}"))
            continue
        try:
            data = load_yaml(file_path)
        except Exception as exc:
            issues.append(ValidationIssue("invalid-yaml", str(file_path), str(exc)))
            continue
        loaded[filename] = data
        for key in EXPERIMENT_REQUIRED_KEYS[filename]:
            if key not in data:
                issues.append(ValidationIssue("invalid-artifact", str(file_path), f"missing key {key}"))
        for key_path in find_non_kebab_keys(data):
            issues.append(ValidationIssue("invalid-name", f"{file_path}:{key_path}", "YAML keys must use kebab-case"))
    experiment = loaded.get("experiment.yml", {})
    target = experiment.get("target")
    if not isinstance(target, dict) or set(target) != {"metric", "operator", "value"}:
        issues.append(ValidationIssue("invalid-artifact", str(path / "experiment.yml"), "target must contain exactly metric, operator, and value"))
    searchscope = loaded.get("searchscope.yml", {})
    components = searchscope.get("components", {})
    if not isinstance(components, dict) or not components:
        issues.append(ValidationIssue("invalid-artifact", str(path / "searchscope.yml"), "components must be a non-empty object"))
    else:
        for group, items in components.items():
            if not isinstance(items, list):
                issues.append(ValidationIssue("invalid-artifact", f"{path / 'searchscope.yml'}:{group}", "component group must be a list"))
                continue
            for index, item in enumerate(items):
                if not isinstance(item, dict) or not (item.get("type") or item.get("role")):
                    issues.append(ValidationIssue("invalid-artifact", f"{path / 'searchscope.yml'}:{group}[{index}]", "component must include type or role"))
    return issues


def validate_jsonl(path: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                issues.append(ValidationIssue("invalid-jsonl", f"{path}:{index}", str(exc)))
                continue
            if not isinstance(data, dict):
                issues.append(ValidationIssue("invalid-jsonl", f"{path}:{index}", "record must be an object"))
    return issues


def validate_candidate_record(record: dict[str, Any], path: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    required = ("candidateId", "components", "parameters", "classification", "status", "metrics")
    for key in required:
        if key not in record:
            issues.append(ValidationIssue("invalid-artifact", path, f"candidate missing key {key}"))
    classification = record.get("classification")
    if classification is not None and classification not in {"rejected", "approved", "winner"}:
        issues.append(ValidationIssue("invalid-artifact", path, "candidate classification must be rejected, approved, or winner"))
    return issues


def validate_candidates_jsonl(path: Path) -> list[ValidationIssue]:
    issues = validate_jsonl(path)
    if issues:
        return issues
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            issues.extend(validate_candidate_record(json.loads(line), f"{path}:{index}"))
    return issues


def validate_run_dir(path: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not is_run_id(path.name):
        issues.append(ValidationIssue("invalid-name", str(path), "run id must use bt-YYYYMMDD-HHMMSS or sim-YYYYMMDD-HHMMSS"))
    for filename in RUN_ARTIFACTS:
        file_path = path / filename
        if not file_path.exists():
            issues.append(ValidationIssue("missing-artifact", str(file_path), f"missing {filename}"))
            continue
        if filename in RUN_JSON_REQUIRED_KEYS:
            try:
                data = load_json(file_path)
            except Exception as exc:
                issues.append(ValidationIssue("invalid-json", str(file_path), str(exc)))
                continue
            for key in RUN_JSON_REQUIRED_KEYS[filename]:
                if key not in data:
                    issues.append(ValidationIssue("invalid-artifact", str(file_path), f"missing key {key}"))
        elif filename == "config-snapshot.yml":
            try:
                data = load_yaml(file_path)
            except Exception as exc:
                issues.append(ValidationIssue("invalid-yaml", str(file_path), str(exc)))
                continue
            for key_path in find_non_kebab_keys(data):
                issues.append(ValidationIssue("invalid-name", f"{file_path}:{key_path}", "snapshot YAML keys must use kebab-case"))
        elif filename == "candidates.jsonl":
            issues.extend(validate_candidates_jsonl(file_path))
        elif filename in RUN_JSONL_FILES:
            issues.extend(validate_jsonl(file_path))
    for filename in DETAIL_JSONL_FILES:
        file_path = path / filename
        if file_path.exists():
            issues.extend(validate_jsonl(file_path))
    return issues


def assert_run_writable(run_dir: Path) -> None:
    manifest = run_dir / "manifest.json"
    if not manifest.exists():
        return
    try:
        data = load_json(manifest)
    except Exception:
        return
    if data.get("status") == "completed":
        raise ImmutableRunError(f"{run_dir.name} is completed; create a new run-id or audit artifact")


def ensure_run_artifacts(run_dir: Path, run_id: str, experiment: str, mode: str, snapshot: dict[str, Any], inputs: dict[str, Any]) -> None:
    assert_run_writable(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "manifest.json", {"runId": run_id, "experiment": experiment, "mode": mode, "status": "running", "createdAt": utc_now()})
    write_yaml(run_dir / "config-snapshot.yml", snapshot)
    write_json(run_dir / "inputs.json", {"runId": run_id, **inputs})
    write_json(run_dir / "scoreboard.json", {"runId": run_id, "rankings": {"candidates": []}, "components": []})
    for filename in RUN_JSONL_FILES:
        (run_dir / filename).touch()


def complete_run(run_dir: Path, metrics: dict[str, Any], report: str) -> None:
    manifest = load_json(run_dir / "manifest.json")
    run_id = manifest["runId"]
    write_json(run_dir / "metrics.json", {"runId": run_id, "status": "completed", "metrics": metrics})
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    manifest["status"] = "completed"
    manifest["completedAt"] = utc_now()
    write_json(run_dir / "manifest.json", manifest)
