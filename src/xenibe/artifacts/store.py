from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from xenibe.artifacts.naming import find_non_kebab_keys, is_experiment_name, is_run_id
from xenibe.artifacts.schemas import (
    CANONICAL_SEARCH_FLOW,
    COMPONENT_PARAMETER_RULES,
    COMPONENT_TYPE_REGISTRY,
    DEFAULT_EXPERIMENT,
    DEFAULT_INGEST,
    DEFAULT_SEARCHSCOPE,
    DETAIL_JSONL_FILES,
    EXPERIMENT_FILES,
    EXPERIMENT_REQUIRED_KEYS,
    LOOP_LIMIT_KEYS,
    REQUIRED_SEARCH_STAGES,
    RUN_ARTIFACTS,
    RUN_JSON_REQUIRED_KEYS,
    RUN_JSONL_FILES,
    VALID_FORMATS,
    VALID_PROVIDERS,
    VALID_SOURCES,
    VALID_TARGET_METRICS,
    VALID_TARGET_OPERATORS,
    VALID_TIMEFRAMES,
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


def scope_hash(scope: dict[str, Any]) -> str:
    payload = json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append_scope_revision(
    experiment_path: Path,
    decision: str,
    reason: str,
    source_run: str | None,
    previous_scope: dict[str, Any],
    new_scope: dict[str, Any],
) -> dict[str, Any]:
    record = {
        "timestamp": utc_now(),
        "decision": decision,
        "reason": reason,
        "sourceRun": source_run,
        "previousScopeHash": scope_hash(previous_scope),
        "newScopeHash": scope_hash(new_scope),
    }
    append_jsonl(experiment_path / "scope-revisions.jsonl", record)
    return record


def experiments_root(root: Path) -> Path:
    return root / "experiment"


def experiment_dir(root: Path, name: str) -> Path:
    return experiments_root(root) / name


def init_artifact_root(root: Path) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for name in ("promoted", "archived", "experiment"):
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
                    "experiment": {"path": "experiment"},
                },
            },
        )
        created.append(config)
    return created


def create_experiment(root: Path, name: str) -> Path:
    if not is_experiment_name(name):
        raise ValueError("experiment-name-must-be-label")
    experiment = experiment_dir(root, name)
    if experiment.exists():
        raise FileExistsError(name)
    experiment.mkdir(parents=True)
    defaults = {
        "experiment.yml": {**DEFAULT_EXPERIMENT, "name": name},
        "ingest.yml": DEFAULT_INGEST,
        "search-scope.yml": DEFAULT_SEARCHSCOPE,
    }
    for filename, data in defaults.items():
        write_yaml(experiment / filename, data)
    (experiment / "data").mkdir()
    return experiment


def list_experiments(root: Path) -> list[str]:
    base = experiments_root(root)
    if not base.exists():
        return []
    names = []
    for child in base.iterdir():
        if child.is_dir() and (child / "experiment.yml").exists():
            names.append(child.name)
    return sorted(names)


def load_experiment(root: Path, name: str) -> dict[str, dict[str, Any]]:
    base = experiment_dir(root, name)
    return {filename: load_yaml(base / filename) for filename in EXPERIMENT_FILES}


def _issue(path: Path, field: str, message: str, code: str = "invalid-artifact") -> ValidationIssue:
    return ValidationIssue(code, f"{path}:{field}" if field else str(path), message)


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_date(value: Any) -> datetime | None:
    if hasattr(value, "isoformat") and not isinstance(value, str):
        value = value.isoformat()
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromisoformat(f"{value}T00:00:00")
        except ValueError:
            return None


def _safe_relative_path(base: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    configured = Path(value)
    if configured.is_absolute():
        return None
    resolved_base = base.resolve()
    resolved = (base / configured).resolve()
    try:
        resolved.relative_to(resolved_base)
    except ValueError:
        return None
    return resolved


def _check_enum(issues: list[ValidationIssue], path: Path, field: str, value: Any, allowed: tuple[str, ...]) -> None:
    if not isinstance(value, str) or value not in allowed:
        issues.append(_issue(path, field, f"must be one of {', '.join(allowed)}"))


def _check_bool(issues: list[ValidationIssue], path: Path, field: str, value: Any) -> None:
    if not _is_bool(value):
        issues.append(_issue(path, field, "must be a boolean"))


def _check_component_value(value: Any, rule: dict[str, Any]) -> bool:
    allowed = rule.get("allowed")
    if allowed is not None:
        return value in allowed
    value_type = rule.get("type")
    if value_type == "bool":
        return _is_bool(value)
    if value_type == "positive-int":
        return _is_int(value) and value > 0
    if value_type == "number":
        return _is_number(value)
    if value_type == "positive-number":
        return _is_number(value) and float(value) > 0.0
    if value_type == "nonnegative-number":
        return _is_number(value) and float(value) >= 0.0
    return True


def _check_limit_value(issues: list[ValidationIssue], path: Path, field: str, value: Any) -> None:
    if value == "dynamic":
        return
    if not _is_int(value) or value <= 0:
        issues.append(_issue(path, field, "must be dynamic or a positive integer"))


def validate_config(root: Path) -> list[ValidationIssue]:
    path = root / "config.yml"
    if not path.exists():
        return [ValidationIssue("missing-artifact", str(path), "missing config.yml")]
    try:
        config = load_yaml(path)
    except Exception as exc:
        return [ValidationIssue("invalid-yaml", str(path), str(exc))]

    issues: list[ValidationIssue] = []
    if config.get("schema-version") != 1:
        issues.append(_issue(path, "schema-version", "must equal 1"))
    artifact = config.get("artifact")
    if not isinstance(artifact, dict):
        issues.append(_issue(path, "artifact", "must be an object"))
    elif not isinstance(artifact.get("root"), str) or not artifact.get("root"):
        issues.append(_issue(path, "artifact.root", "must be a non-empty string"))

    contexts = config.get("contexts")
    if not isinstance(contexts, dict):
        issues.append(_issue(path, "contexts", "must be an object"))
        return issues
    for name in ("promoted", "archived", "experiment"):
        context = contexts.get(name)
        field = f"contexts.{name}"
        if not isinstance(context, dict):
            issues.append(_issue(path, field, "must be an object"))
            continue
        resolved = _safe_relative_path(root, context.get("path"))
        if resolved is None:
            issues.append(_issue(path, f"{field}.path", "must be a safe relative path inside the artifact root"))
            continue
        if not resolved.exists() or not resolved.is_dir():
            issues.append(_issue(path, f"{field}.path", "directory does not exist inside the artifact root"))
    return issues


def _validate_experiment_yaml(path: Path, data: dict[str, Any], expected_name: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if data.get("name") != expected_name:
        issues.append(_issue(path, "name", "must match the experiment directory name"))
    if not isinstance(data.get("hypothesis"), str) or not data.get("hypothesis"):
        issues.append(_issue(path, "hypothesis", "must be a non-empty string"))
    target = data.get("target")
    if not isinstance(target, dict) or set(target) != {"metric", "operator", "value"}:
        issues.append(_issue(path, "target", "must contain exactly metric, operator, and value"))
    else:
        _check_enum(issues, path, "target.metric", target.get("metric"), VALID_TARGET_METRICS)
        _check_enum(issues, path, "target.operator", target.get("operator"), VALID_TARGET_OPERATORS)
        if not _is_number(target.get("value")):
            issues.append(_issue(path, "target.value", "must be a number"))
    _check_bool(issues, path, "stop-on-target", data.get("stop-on-target"))
    return issues


def _validate_ingest_yaml(path: Path, data: dict[str, Any], experiment_path: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    ingest_data = data.get("data")
    if not isinstance(ingest_data, dict):
        issues.append(_issue(path, "data", "must be an object"))
        return issues
    for key in ("provider", "asset", "timeframe", "from", "to", "source", "format", "path"):
        if key not in ingest_data:
            issues.append(_issue(path, "data", f"missing key {key}"))
    _check_enum(issues, path, "data.provider", ingest_data.get("provider"), VALID_PROVIDERS)
    asset = ingest_data.get("asset")
    if not isinstance(asset, str) or re.fullmatch(r"[A-Z0-9._-]{3,32}", asset) is None:
        issues.append(_issue(path, "data.asset", "must be 3-32 uppercase asset characters"))
    _check_enum(issues, path, "data.timeframe", ingest_data.get("timeframe"), VALID_TIMEFRAMES)
    _check_enum(issues, path, "data.source", ingest_data.get("source"), VALID_SOURCES)
    _check_enum(issues, path, "data.format", ingest_data.get("format"), VALID_FORMATS)

    start = _parse_date(ingest_data.get("from"))
    end = _parse_date(ingest_data.get("to"))
    if start is None:
        issues.append(_issue(path, "data.from", "must be an ISO date or datetime"))
    if end is None:
        issues.append(_issue(path, "data.to", "must be an ISO date or datetime"))
    if start is not None and end is not None and start >= end:
        issues.append(_issue(path, "data.to", "must be after data.from"))

    resolved = _safe_relative_path(experiment_path, ingest_data.get("path"))
    if resolved is None:
        issues.append(_issue(path, "data.path", "must be a safe relative path inside the experiment directory"))
    elif not resolved.exists() or not resolved.is_dir():
        issues.append(_issue(path, "data.path", "directory does not exist inside the experiment directory"))

    validation = data.get("validation")
    if not isinstance(validation, dict):
        issues.append(_issue(path, "validation", "must be an object"))
        return issues
    for key in ("require-complete-candles", "reject-gaps"):
        _check_bool(issues, path, f"validation.{key}", validation.get(key))
    if validation.get("timezone") != "UTC":
        issues.append(_issue(path, "validation.timezone", "must equal UTC"))
    return issues


def _validate_search_scope_yaml(path: Path, data: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if data.get("schema-version") != 1:
        issues.append(_issue(path, "schema-version", "must equal 1"))

    flow = data.get("flow")
    if flow != list(CANONICAL_SEARCH_FLOW):
        issues.append(_issue(path, "flow", f"must exactly match {', '.join(CANONICAL_SEARCH_FLOW)}"))

    limits = data.get("limits")
    if not isinstance(limits, dict):
        issues.append(_issue(path, "limits", "must be an object"))
    else:
        for key in LOOP_LIMIT_KEYS:
            if key not in limits:
                issues.append(_issue(path, f"limits.{key}", "missing loop limit"))
        for key, value in limits.items():
            if key not in LOOP_LIMIT_KEYS:
                issues.append(_issue(path, f"limits.{key}", "unknown loop limit"))
                continue
            _check_limit_value(issues, path, f"limits.{key}", value)

    components = data.get("components")
    if not isinstance(components, dict):
        issues.append(_issue(path, "components", "must be an object"))
        return issues
    for stage in CANONICAL_SEARCH_FLOW:
        if stage not in components:
            issues.append(_issue(path, f"components.{stage}", "missing canonical stage key"))
            continue
        items = components.get(stage)
        if not isinstance(items, list):
            issues.append(_issue(path, f"components.{stage}", "stage must be a list"))
            continue
        if stage in REQUIRED_SEARCH_STAGES and not items:
            issues.append(_issue(path, f"components.{stage}", "required stage must contain at least one component"))
        for index, item in enumerate(items):
            item_field = f"components.{stage}[{index}]"
            if not isinstance(item, dict):
                issues.append(_issue(path, item_field, "component must be an object"))
                continue
            component_type = item.get("type")
            if not isinstance(component_type, str) or not component_type:
                issues.append(_issue(path, f"{item_field}.type", "component type is required"))
                continue
            if component_type not in COMPONENT_TYPE_REGISTRY.get(stage, ()):
                issues.append(_issue(path, f"{item_field}.type", f"unknown component type for {stage}"))
                continue
            parameters = item.get("parameters")
            if not isinstance(parameters, dict):
                issues.append(_issue(path, f"{item_field}.parameters", "parameters must be an object"))
                continue
            rules = COMPONENT_PARAMETER_RULES[stage][component_type]
            for parameter_name, values in parameters.items():
                parameter_field = f"{item_field}.parameters.{parameter_name}"
                if parameter_name not in rules:
                    issues.append(_issue(path, parameter_field, "unknown parameter"))
                    continue
                if not isinstance(values, list) or not values:
                    issues.append(_issue(path, parameter_field, "parameter value must be a non-empty list"))
                    continue
                for value_index, value in enumerate(values):
                    if not _check_component_value(value, rules[parameter_name]):
                        issues.append(_issue(path, f"{parameter_field}[{value_index}]", "invalid parameter value"))
            for parameter_name in rules:
                if parameter_name not in parameters:
                    issues.append(_issue(path, f"{item_field}.parameters.{parameter_name}", "missing parameter"))
    for stage in components:
        if stage not in CANONICAL_SEARCH_FLOW:
            issues.append(_issue(path, f"components.{stage}", "unknown canonical stage"))
    return issues


def validate_experiment_dir(path: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not is_experiment_name(path.name):
        issues.append(ValidationIssue("invalid-name", str(path), "experiment directory must use letters, numbers, and hyphens"))
    loaded: dict[str, dict[str, Any]] = {}
    for filename in EXPERIMENT_FILES:
        file_path = path / filename
        if not file_path.exists():
            message = f"missing {filename}"
            if filename == "search-scope.yml" and (path / "searchscope.yml").exists():
                message = "missing search-scope.yml; legacy searchscope.yml is unsupported, migrate to search-scope.yml"
            issues.append(ValidationIssue("missing-artifact", str(file_path), message))
            continue
        try:
            data = load_yaml(file_path)
        except Exception as exc:
            issues.append(ValidationIssue("invalid-yaml", str(file_path), str(exc)))
            continue
        loaded[filename] = data
        for key in EXPERIMENT_REQUIRED_KEYS[filename]:
            if key not in data:
                issues.append(_issue(file_path, key, f"missing key {key}"))
        for key_path in find_non_kebab_keys(data):
            issues.append(ValidationIssue("invalid-name", f"{file_path}:{key_path}", "YAML keys must use kebab-case"))
    if "experiment.yml" in loaded:
        issues.extend(_validate_experiment_yaml(path / "experiment.yml", loaded["experiment.yml"], path.name))
    if "ingest.yml" in loaded:
        issues.extend(_validate_ingest_yaml(path / "ingest.yml", loaded["ingest.yml"], path))
    if "search-scope.yml" in loaded:
        issues.extend(_validate_search_scope_yaml(path / "search-scope.yml", loaded["search-scope.yml"]))
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
    required = ("candidateId", "components", "parameters", "classification", "status", "metrics", "candidateFingerprint", "evaluationFingerprint")
    for key in required:
        if key not in record:
            issues.append(ValidationIssue("invalid-artifact", path, f"candidate missing key {key}"))
    classification = record.get("classification")
    if classification is not None and classification not in {"rejected", "approved", "winner", "skipped"}:
        issues.append(ValidationIssue("invalid-artifact", path, "candidate classification must be rejected, approved, winner, or skipped"))
    if classification == "skipped" and record.get("status") != "skipped-duplicate":
        issues.append(ValidationIssue("invalid-artifact", path, "skipped candidates must use status skipped-duplicate"))
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
