from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from xenibe.artifacts.history import (
    canonical_history_path,
    canonical_history_relative_path,
    canonical_manifest_path,
    manifest_range,
    parse_datetime,
    relative_posix,
    request_range,
    validate_canonical_manifest,
)
from xenibe.artifacts.naming import find_non_kebab_keys, is_experiment_name, is_run_id
from xenibe.artifacts.schemas import (
    CANONICAL_CONTEXT_PATHS,
    CANONICAL_SEARCH_FLOW,
    COMPACT_RECORD_KINDS,
    COMPACT_RUN_ARTIFACTS,
    COMPACT_RUN_JSON_REQUIRED_KEYS,
    COMPONENT_PARAMETER_RULES,
    COMPONENT_TYPE_REGISTRY,
    DEFAULT_EXPERIMENT,
    DEFAULT_INGEST,
    DEFAULT_SEARCH_SCOPE,
    DETAIL_JSONL_FILES,
    EXPERIMENT_FILES,
    EXPERIMENT_REQUIRED_KEYS,
    LOOP_LIMIT_KEYS,
    REQUIRED_SEARCH_STAGES,
    RUN_FORMAT_MARKER_KEYS,
    RUN_ARTIFACTS,
    RUN_ID_MODE_PREFIXES,
    RUN_JSON_REQUIRED_KEYS,
    RUN_JSONL_FILES,
    RUN_MODES,
    RUN_SUBJECT_VALUES,
    RUN_STATUS_VALUES,
    SCENARIO_DERIVED_SIDE_TRIGGERS,
    PROMOTED_ROBOT_REQUIRED_SECTIONS,
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
    if prefix not in {"bt", "sim"}:
        raise ValueError("run-id-prefix-must-be-bt-or-sim")
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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            data = json.loads(line)
            if not isinstance(data, dict):
                raise ValueError(f"jsonl-record-{index}-must-be-object")
            records.append(data)
    return records


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
        "search-scope.yml": DEFAULT_SEARCH_SCOPE,
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


def list_experiment_dirs(root: Path) -> list[str]:
    base = experiments_root(root)
    if not base.exists():
        return []
    return sorted(child.name for child in base.iterdir() if child.is_dir())


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
    return parse_datetime(value)


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


def _check_positive_number(issues: list[ValidationIssue], path: Path, field: str, value: Any) -> None:
    if not _is_number(value) or float(value) <= 0.0:
        issues.append(_issue(path, field, "must be a positive number"))


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


def _validate_horizon_validation(path: Path, value: Any) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if value is None:
        return issues
    if not isinstance(value, dict):
        return [_issue(path, "horizon-validation", "must be an object")]
    _check_bool(issues, path, "horizon-validation.enabled", value.get("enabled"))
    if value.get("enabled") is not True:
        return issues
    days = value.get("days")
    if not isinstance(days, list) or not days:
        issues.append(_issue(path, "horizon-validation.days", "must be a non-empty list of positive integers"))
    else:
        for index, day in enumerate(days):
            if not _is_int(day) or int(day) <= 0:
                issues.append(_issue(path, f"horizon-validation.days[{index}]", "must be a positive integer"))
    primary = value.get("primary-window-days")
    if not _is_int(primary) or int(primary) <= 0:
        issues.append(_issue(path, "horizon-validation.primary-window-days", "must be a positive integer"))
    _check_positive_number(issues, path, "horizon-validation.min-trades-per-hour", value.get("min-trades-per-hour"))
    min_sufficient = value.get("min-sufficient-horizons")
    if not _is_int(min_sufficient) or int(min_sufficient) <= 0:
        issues.append(_issue(path, "horizon-validation.min-sufficient-horizons", "must be a positive integer"))
    elif isinstance(days, list) and int(min_sufficient) > len(days):
        issues.append(_issue(path, "horizon-validation.min-sufficient-horizons", "must not exceed the number of configured days"))
    gate = value.get("gate")
    if not isinstance(gate, dict):
        issues.append(_issue(path, "horizon-validation.gate", "must be an object"))
        return issues
    if gate.get("mode") != "min-sufficient":
        issues.append(_issue(path, "horizon-validation.gate.mode", "must equal min-sufficient"))
    if gate.get("target-source") != "experiment-target":
        issues.append(_issue(path, "horizon-validation.gate.target-source", "must equal experiment-target"))
    if "require-positive-net-profit" in gate:
        _check_bool(issues, path, "horizon-validation.gate.require-positive-net-profit", gate.get("require-positive-net-profit"))
    return issues


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
    for name in sorted(set(contexts) - set(CANONICAL_CONTEXT_PATHS)):
        issues.append(_issue(path, f"contexts.{name}", "unsupported context; canonical contexts are promoted, archived, and experiment"))
    for name, canonical_path in CANONICAL_CONTEXT_PATHS.items():
        context = contexts.get(name)
        field = f"contexts.{name}"
        if not isinstance(context, dict):
            issues.append(_issue(path, field, "must be an object"))
            continue
        configured_path = context.get("path")
        if configured_path != canonical_path:
            issues.append(_issue(path, f"{field}.path", f"must equal canonical path {canonical_path}"))
            continue
        resolved = _safe_relative_path(root, configured_path)
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


def _validate_history_manifest(path: Path, experiment_path: Path, ingest_data: dict[str, Any], csv_path: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not path.exists():
        issues.append(ValidationIssue("missing-artifact", str(path), "missing paired canonical history manifest"))
        return issues
    try:
        manifest = load_json(path)
    except Exception as exc:
        issues.append(ValidationIssue("invalid-json", str(path), str(exc)))
        return issues

    asset = str(ingest_data.get("asset", ""))
    timeframe = str(ingest_data.get("timeframe", ""))
    for field, message in validate_canonical_manifest(manifest, csv_path, asset, timeframe):
        issue_path = csv_path if field == "csv" else path
        issues.append(_issue(issue_path, "" if field == "csv" else field, message))

    coverage = manifest_range(manifest)
    if coverage is None:
        requested = None
    else:
        requested = request_range(ingest_data.get("from"), ingest_data.get("to"))
    if requested is not None and coverage is not None and not (coverage[0] <= requested[0] and requested[1] <= coverage[1]):
        issues.append(_issue(path, "coverageRange", "must cover ingest.yml:data.from through data.to as [from, to)"))
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
    elif not resolved.exists():
        issues.append(_issue(path, "data.path", "path does not exist inside the experiment directory"))
    elif not (resolved.is_dir() or resolved.is_file()):
        issues.append(_issue(path, "data.path", "must be a directory or CSV file inside the experiment directory"))
    elif resolved.is_file():
        if resolved.suffix.lower() != ".csv":
            issues.append(_issue(path, "data.path", "history file must be a CSV"))
        elif isinstance(asset, str) and isinstance(ingest_data.get("timeframe"), str):
            expected = canonical_history_path(experiment_path, asset, str(ingest_data.get("timeframe")))
            if resolved.resolve() != expected.resolve():
                issues.append(_issue(path, "data.path", f"active history CSV must be canonical path {relative_posix(canonical_history_relative_path(asset, str(ingest_data.get('timeframe'))))}"))
            else:
                issues.extend(_validate_history_manifest(canonical_manifest_path(experiment_path, asset, str(ingest_data.get("timeframe"))), experiment_path, ingest_data, resolved))

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

    issues.extend(_validate_horizon_validation(path, data.get("horizon-validation")))

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
                    if stage == "trigger" and component_type in SCENARIO_DERIVED_SIDE_TRIGGERS and parameter_name == "side":
                        issues.append(_issue(path, parameter_field, "remove side; directional triggers derive call or put from the scenario"))
                    else:
                        issues.append(_issue(path, parameter_field, "unknown parameter"))
                    continue
                if not isinstance(values, list) or not values:
                    issues.append(_issue(path, parameter_field, "parameter value must be a non-empty list"))
                    continue
                for value_index, value in enumerate(values):
                    if not _check_component_value(value, rules[parameter_name]):
                        issues.append(_issue(path, f"{parameter_field}[{value_index}]", "invalid parameter value"))
            for parameter_name in rules:
                if parameter_name not in parameters and rules[parameter_name].get("required", True):
                    issues.append(_issue(path, f"{item_field}.parameters.{parameter_name}", "missing parameter"))
    for stage in components:
        if stage not in CANONICAL_SEARCH_FLOW:
            issues.append(_issue(path, f"components.{stage}", "unknown canonical stage"))
    return issues


def _horizon_validation_enabled(search_scope: dict[str, Any]) -> bool:
    value = search_scope.get("horizon-validation")
    return isinstance(value, dict) and value.get("enabled") is True


def _validate_ebinex_contract_scope(experiment_path: Path, ingest: dict[str, Any], search_scope: dict[str, Any]) -> list[ValidationIssue]:
    ingest_data = ingest.get("data")
    if not isinstance(ingest_data, dict) or ingest_data.get("provider") != "ebinex":
        return []
    issues: list[ValidationIssue] = []
    components = search_scope.get("components")
    if not isinstance(components, dict):
        return issues
    decision_components = components.get("decision")
    if not isinstance(decision_components, list):
        return issues
    path = experiment_path / "search-scope.yml"
    message = "Ebinex expiry is controlled by the provider timeframe; remove expiration-candles from the search scope."
    for index, item in enumerate(decision_components):
        if not isinstance(item, dict):
            continue
        parameters = item.get("parameters")
        if isinstance(parameters, dict) and "expiration-candles" in parameters:
            issues.append(_issue(path, f"components.decision[{index}].parameters.expiration-candles", message))
    return issues


def _validate_horizon_coverage(experiment_path: Path, ingest: dict[str, Any], search_scope: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not _horizon_validation_enabled(search_scope):
        return issues
    ingest_data = ingest.get("data")
    horizon = search_scope.get("horizon-validation")
    if not isinstance(ingest_data, dict) or not isinstance(horizon, dict):
        return issues
    days = horizon.get("days")
    min_sufficient = horizon.get("min-sufficient-horizons")
    if not isinstance(days, list) or not _is_int(min_sufficient) or int(min_sufficient) <= 0:
        return issues
    positive_days = sorted(int(day) for day in days if _is_int(day) and int(day) > 0)
    if len(positive_days) < int(min_sufficient):
        return issues
    end = parse_datetime(ingest_data.get("to"))
    asset = ingest_data.get("asset")
    timeframe = ingest_data.get("timeframe")
    if end is None or not isinstance(asset, str) or not isinstance(timeframe, str):
        return issues
    required_days = positive_days[: int(min_sufficient)]
    required_start = end - timedelta(days=max(required_days))
    manifest_path = canonical_manifest_path(experiment_path, asset, timeframe)
    if not manifest_path.exists():
        issues.append(ValidationIssue("missing-artifact", str(manifest_path), "canonical history manifest is required for horizon validation coverage checks"))
        return issues
    try:
        manifest = load_json(manifest_path)
    except Exception as exc:
        issues.append(ValidationIssue("invalid-json", str(manifest_path), str(exc)))
        return issues
    coverage = manifest_range(manifest)
    if coverage is None or coverage[0] > required_start or coverage[1] < end:
        issues.append(
            _issue(
                manifest_path,
                "coverageRange",
                f"canonical history must cover the {len(required_days)} smallest horizons ({', '.join(str(day) for day in required_days)} days) ending at ingest.yml:data.to",
            )
        )
    return issues


def _validate_risk_yaml(path: Path, data: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for key in ("stop-loss", "stop-win", "balance", "max-open-risk"):
        if key in data:
            _check_positive_number(issues, path, key, data.get(key))
    if "min-payout" in data:
        min_payout = data.get("min-payout")
        if not _is_number(min_payout) or not 0.0 <= float(min_payout) <= 1.0:
            issues.append(_issue(path, "min-payout", "must be a number between 0 and 1"))

    stake = data.get("stake")
    if stake is not None:
        if not isinstance(stake, dict):
            issues.append(_issue(path, "stake", "must be an object"))
        else:
            for key in ("stop-loss-divisor", "min", "max"):
                if key in stake:
                    _check_positive_number(issues, path, f"stake.{key}", stake.get(key))
            if _is_number(stake.get("min")) and _is_number(stake.get("max")) and float(stake["min"]) > float(stake["max"]):
                issues.append(_issue(path, "stake.max", "must be greater than or equal to stake.min"))

    soros = data.get("soros")
    if soros is not None:
        if not isinstance(soros, dict):
            issues.append(_issue(path, "soros", "must be an object"))
        else:
            if "enabled" in soros:
                _check_bool(issues, path, "soros.enabled", soros.get("enabled"))
            if "levels" in soros and (not _is_int(soros.get("levels")) or int(soros["levels"]) <= 0):
                issues.append(_issue(path, "soros.levels", "must be a positive integer"))
            elif "levels" in soros and int(soros["levels"]) != 1:
                issues.append(_issue(path, "soros.levels", "only Soros level 1 is currently supported"))

    martingale = data.get("martingale")
    if martingale is not None:
        if not isinstance(martingale, dict):
            issues.append(_issue(path, "martingale", "must be an object"))
        else:
            if "enabled" in martingale:
                _check_bool(issues, path, "martingale.enabled", martingale.get("enabled"))
                if martingale.get("enabled") is True:
                    issues.append(_issue(path, "martingale.enabled", "martingale is declared but not currently implemented"))
            if "max-steps" in martingale and (not _is_int(martingale.get("max-steps")) or int(martingale["max-steps"]) < 0):
                issues.append(_issue(path, "martingale.max-steps", "must be a nonnegative integer"))
            elif "max-steps" in martingale and int(martingale["max-steps"]) > 0:
                issues.append(_issue(path, "martingale.max-steps", "martingale steps are declared but not currently implemented"))
            if "multiplier" in martingale:
                _check_positive_number(issues, path, "martingale.multiplier", martingale.get("multiplier"))
    return issues


def validate_experiment_dir(path: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not is_experiment_name(path.name):
        issues.append(ValidationIssue("invalid-name", str(path), "experiment directory must use lowercase kebab-case"))
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
                issues.append(_issue(file_path, key, f"missing key {key}"))
        for key_path in find_non_kebab_keys(data):
            issues.append(ValidationIssue("invalid-name", f"{file_path}:{key_path}", "YAML keys must use kebab-case"))
    if "experiment.yml" in loaded:
        issues.extend(_validate_experiment_yaml(path / "experiment.yml", loaded["experiment.yml"], path.name))
    if "ingest.yml" in loaded:
        issues.extend(_validate_ingest_yaml(path / "ingest.yml", loaded["ingest.yml"], path))
    if "search-scope.yml" in loaded:
        issues.extend(_validate_search_scope_yaml(path / "search-scope.yml", loaded["search-scope.yml"]))
    if "ingest.yml" in loaded and "search-scope.yml" in loaded:
        issues.extend(_validate_ebinex_contract_scope(path, loaded["ingest.yml"], loaded["search-scope.yml"]))
        issues.extend(_validate_horizon_coverage(path, loaded["ingest.yml"], loaded["search-scope.yml"]))
    risk_path = path / "risk.yml"
    if risk_path.exists():
        try:
            risk = load_yaml(risk_path)
        except Exception as exc:
            issues.append(ValidationIssue("invalid-yaml", str(risk_path), str(exc)))
        else:
            for key_path in find_non_kebab_keys(risk):
                issues.append(ValidationIssue("invalid-name", f"{risk_path}:{key_path}", "YAML keys must use kebab-case"))
            issues.extend(_validate_risk_yaml(risk_path, risk))
    for filename in ("provider.yml", "report.yml"):
        optional_path = path / filename
        if not optional_path.exists():
            continue
        try:
            data = load_yaml(optional_path)
        except Exception as exc:
            issues.append(ValidationIssue("invalid-yaml", str(optional_path), str(exc)))
            continue
        for key_path in find_non_kebab_keys(data):
            issues.append(ValidationIssue("invalid-name", f"{optional_path}:{key_path}", "YAML keys must use kebab-case"))
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
    status = record.get("status")
    if status is not None and status not in {"tested", "skipped-duplicate"}:
        issues.append(ValidationIssue("invalid-artifact", path, "candidate status must be a processing state: tested or skipped-duplicate"))
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


def _mode_for_run_id(run_id: str) -> str | None:
    if run_id.startswith("bt-"):
        return "backtest"
    if run_id.startswith("sim-"):
        return "simulate"
    return None


def _synthetic_history_issue(path: Path, field: str) -> ValidationIssue:
    return _issue(path, field, "synthetic history is no longer supported; recreate the run with configured real history")


def _validate_no_synthetic_run_history(path: Path, loaded_json: dict[str, dict[str, Any]]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    manifest = loaded_json.get("manifest.json")
    if manifest is not None:
        execution = manifest.get("execution")
        if isinstance(execution, dict) and execution.get("dataSource") == "synthetic-default":
            issues.append(_synthetic_history_issue(path / "manifest.json", "execution.dataSource"))

    inputs = loaded_json.get("inputs.json")
    if inputs is None:
        return issues
    execution = inputs.get("execution")
    if isinstance(execution, dict) and execution.get("dataSource") == "synthetic-default":
        issues.append(_synthetic_history_issue(path / "inputs.json", "execution.dataSource"))
    history = inputs.get("history")
    if isinstance(history, dict):
        if history.get("dataSource") == "synthetic-default":
            issues.append(_synthetic_history_issue(path / "inputs.json", "history.dataSource"))
        if history.get("synthetic") is True:
            issues.append(_synthetic_history_issue(path / "inputs.json", "history.synthetic"))
    limitations = inputs.get("limitations")
    if isinstance(limitations, list):
        for index, limitation in enumerate(limitations):
            if isinstance(limitation, dict) and limitation.get("code") == "synthetic-default-candles":
                issues.append(_synthetic_history_issue(path / "inputs.json", f"limitations[{index}].code"))
    return issues


def _validate_no_synthetic_compact_run(path: Path, run_doc: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    execution = run_doc.get("execution")
    if isinstance(execution, dict) and execution.get("dataSource") == "synthetic-default":
        issues.append(_synthetic_history_issue(path / "run.json", "execution.dataSource"))
    inputs = run_doc.get("inputs")
    if isinstance(inputs, dict):
        input_execution = inputs.get("execution")
        if isinstance(input_execution, dict) and input_execution.get("dataSource") == "synthetic-default":
            issues.append(_synthetic_history_issue(path / "run.json", "inputs.execution.dataSource"))
        history = inputs.get("history")
        if isinstance(history, dict):
            if history.get("dataSource") == "synthetic-default":
                issues.append(_synthetic_history_issue(path / "run.json", "inputs.history.dataSource"))
            if history.get("synthetic") is True:
                issues.append(_synthetic_history_issue(path / "run.json", "inputs.history.synthetic"))
        limitations = inputs.get("limitations")
        if isinstance(limitations, list):
            for index, limitation in enumerate(limitations):
                if isinstance(limitation, dict) and limitation.get("code") == "synthetic-default-candles":
                    issues.append(_synthetic_history_issue(path / "run.json", f"inputs.limitations[{index}].code"))
    limitations = run_doc.get("limitations")
    if isinstance(limitations, list):
        for index, limitation in enumerate(limitations):
            if isinstance(limitation, dict) and limitation.get("code") == "synthetic-default-candles":
                issues.append(_synthetic_history_issue(path / "run.json", f"limitations[{index}].code"))
    return issues


def is_compact_run_dir(path: Path) -> bool:
    return (path / "run.json").exists()


def compact_record_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = {kind: 0 for kind in COMPACT_RECORD_KINDS}
    for record in records:
        kind = record.get("kind")
        if isinstance(kind, str) and kind in counts:
            counts[kind] += 1
    return counts


def _load_compact_records(path: Path) -> tuple[list[dict[str, Any]], dict[str, int], list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    records: list[dict[str, Any]] = []
    counts = {kind: 0 for kind in COMPACT_RECORD_KINDS}
    previous_seq: int | None = None
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                issues.append(ValidationIssue("invalid-jsonl", f"{path}:{index}", str(exc)))
                continue
            if not isinstance(record, dict):
                issues.append(ValidationIssue("invalid-jsonl", f"{path}:{index}", "record must be an object"))
                continue
            seq = record.get("seq")
            if not _is_int(seq):
                issues.append(ValidationIssue("invalid-jsonl", f"{path}:{index}:seq", "seq must be an integer"))
            elif previous_seq is not None and int(seq) <= previous_seq:
                issues.append(ValidationIssue("invalid-jsonl", f"{path}:{index}:seq", "seq must be monotonically increasing"))
            if _is_int(seq):
                previous_seq = int(seq)
            kind = record.get("kind")
            if not isinstance(kind, str) or kind not in COMPACT_RECORD_KINDS:
                issues.append(ValidationIssue("invalid-jsonl", f"{path}:{index}:kind", f"kind must be one of {', '.join(COMPACT_RECORD_KINDS)}"))
            data = record.get("data")
            if not isinstance(data, dict):
                issues.append(ValidationIssue("invalid-jsonl", f"{path}:{index}:data", "data must be an object"))
            elif kind == "candidate":
                issues.extend(validate_candidate_record(data, f"{path}:{index}:data"))
            if isinstance(kind, str) and kind in counts:
                counts[kind] += 1
            records.append(record)
    return records, counts, issues


def _validate_record_counts(path: Path, run_doc: dict[str, Any], actual_counts: dict[str, int]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    declared = run_doc.get("recordCounts")
    if not isinstance(declared, dict):
        return [_issue(path / "run.json", "recordCounts", "must be an object")]
    for kind, value in declared.items():
        if kind not in COMPACT_RECORD_KINDS:
            issues.append(_issue(path / "run.json", f"recordCounts.{kind}", f"must be one of {', '.join(COMPACT_RECORD_KINDS)}"))
            continue
        if not _is_int(value) or int(value) < 0:
            issues.append(_issue(path / "run.json", f"recordCounts.{kind}", "must be a non-negative integer"))
    for kind in COMPACT_RECORD_KINDS:
        value = declared.get(kind, 0)
        if _is_int(value) and int(value) != int(actual_counts.get(kind, 0)):
            issues.append(_issue(path / "run.json", f"recordCounts.{kind}", f"must match records.jsonl count {actual_counts.get(kind, 0)}"))
    return issues


def _validate_compact_run_dir(path: Path, expected_experiment: str | None = None, expected_mode: str | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not is_run_id(path.name):
        issues.append(ValidationIssue("invalid-name", str(path), "run id must use bt-YYYYMMDD-HHMMSS or sim-YYYYMMDD-HHMMSS"))
    run_doc: dict[str, Any] | None = None
    records_counts = {kind: 0 for kind in COMPACT_RECORD_KINDS}
    for filename in COMPACT_RUN_ARTIFACTS:
        file_path = path / filename
        if not file_path.exists():
            issues.append(ValidationIssue("missing-artifact", str(file_path), f"missing {filename}"))
            continue
        if filename == "run.json":
            try:
                run_doc = load_json(file_path)
            except Exception as exc:
                issues.append(ValidationIssue("invalid-json", str(file_path), str(exc)))
                continue
            for marker in RUN_FORMAT_MARKER_KEYS:
                if marker in run_doc:
                    issues.append(_issue(file_path, marker, "compact run packages must not include a format version marker"))
            for key in COMPACT_RUN_JSON_REQUIRED_KEYS:
                if key not in run_doc:
                    issues.append(ValidationIssue("invalid-artifact", str(file_path), f"missing key {key}"))
        elif filename == "records.jsonl":
            _, records_counts, record_issues = _load_compact_records(file_path)
            issues.extend(record_issues)
    if run_doc is None:
        return issues

    run_id = run_doc.get("runId")
    if not isinstance(run_id, str) or not is_run_id(run_id):
        issues.append(_issue(path / "run.json", "runId", "must use bt-YYYYMMDD-HHMMSS or sim-YYYYMMDD-HHMMSS"))
    elif run_id != path.name:
        issues.append(_issue(path / "run.json", "runId", "must match the run directory name"))

    experiment = run_doc.get("experiment")
    mode = run_doc.get("mode")
    subject = run_doc.get("subject")
    status = run_doc.get("status")
    if expected_experiment is not None and experiment != expected_experiment:
        issues.append(_issue(path / "run.json", "experiment", "must match the expected experiment"))
    if not isinstance(mode, str) or mode not in RUN_MODES:
        issues.append(_issue(path / "run.json", "mode", f"must be one of {', '.join(RUN_MODES)}"))
    elif expected_mode is not None and mode != expected_mode:
        issues.append(_issue(path / "run.json", "mode", "must match the expected run mode"))
    elif is_run_id(path.name) and _mode_for_run_id(path.name) != mode:
        expected_prefix = RUN_ID_MODE_PREFIXES.get(mode)
        issues.append(_issue(path / "run.json", "mode", f"must match run id prefix {expected_prefix}-"))
    if not isinstance(subject, str) or subject not in RUN_SUBJECT_VALUES:
        issues.append(_issue(path / "run.json", "subject", f"must be one of {', '.join(RUN_SUBJECT_VALUES)}"))
    if not isinstance(status, str) or status not in RUN_STATUS_VALUES:
        issues.append(_issue(path / "run.json", "status", f"must be one of {', '.join(RUN_STATUS_VALUES)}"))
    elif status != "completed":
        issues.append(_issue(path / "run.json", "status", "must equal completed"))
    for key in ("configSnapshot", "inputs", "metrics", "scoreboard"):
        if key in run_doc and not isinstance(run_doc.get(key), dict):
            issues.append(_issue(path / "run.json", key, "must be an object"))
    inputs = run_doc.get("inputs")
    if isinstance(inputs, dict):
        input_run_id = inputs.get("runId")
        if input_run_id is not None and input_run_id != path.name:
            issues.append(_issue(path / "run.json", "inputs.runId", "must match the run directory name"))
    scoreboard = run_doc.get("scoreboard")
    if isinstance(scoreboard, dict):
        scoreboard_run_id = scoreboard.get("runId")
        if scoreboard_run_id is not None and scoreboard_run_id != path.name:
            issues.append(_issue(path / "run.json", "scoreboard.runId", "must match the run directory name"))
    issues.extend(_validate_record_counts(path, run_doc, records_counts))
    issues.extend(_validate_no_synthetic_compact_run(path, run_doc))
    return issues


def _validate_legacy_run_dir(path: Path, expected_experiment: str | None = None, expected_mode: str | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not is_run_id(path.name):
        issues.append(ValidationIssue("invalid-name", str(path), "run id must use bt-YYYYMMDD-HHMMSS or sim-YYYYMMDD-HHMMSS"))
    loaded_json: dict[str, dict[str, Any]] = {}
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
            loaded_json[filename] = data
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
    for filename, data in loaded_json.items():
        run_id = data.get("runId")
        if not isinstance(run_id, str) or not is_run_id(run_id):
            issues.append(_issue(path / filename, "runId", "must use bt-YYYYMMDD-HHMMSS or sim-YYYYMMDD-HHMMSS"))
        elif run_id != path.name:
            issues.append(_issue(path / filename, "runId", "must match the run directory name"))
    issues.extend(_validate_no_synthetic_run_history(path, loaded_json))
    manifest = loaded_json.get("manifest.json")
    if manifest is not None:
        experiment = manifest.get("experiment")
        mode = manifest.get("mode")
        subject = manifest.get("subject")
        status = manifest.get("status")
        if expected_experiment is not None and experiment != expected_experiment:
            issues.append(_issue(path / "manifest.json", "experiment", "must match the expected experiment"))
        if not isinstance(mode, str) or mode not in RUN_MODES:
            issues.append(_issue(path / "manifest.json", "mode", f"must be one of {', '.join(RUN_MODES)}"))
        elif expected_mode is not None and mode != expected_mode:
            issues.append(_issue(path / "manifest.json", "mode", "must match the expected run mode"))
        elif is_run_id(path.name) and _mode_for_run_id(path.name) != mode:
            expected_prefix = RUN_ID_MODE_PREFIXES.get(mode)
            issues.append(_issue(path / "manifest.json", "mode", f"must match run id prefix {expected_prefix}-"))
        if not isinstance(subject, str) or subject not in RUN_SUBJECT_VALUES:
            issues.append(_issue(path / "manifest.json", "subject", f"must be one of {', '.join(RUN_SUBJECT_VALUES)}"))
        if not isinstance(status, str) or status not in RUN_STATUS_VALUES:
            issues.append(_issue(path / "manifest.json", "status", f"must be one of {', '.join(RUN_STATUS_VALUES)}"))
    metrics = loaded_json.get("metrics.json")
    if metrics is not None and metrics.get("status") != "completed":
        issues.append(_issue(path / "metrics.json", "status", "must equal completed"))
    return issues


def validate_run_dir(path: Path, expected_experiment: str | None = None, expected_mode: str | None = None) -> list[ValidationIssue]:
    if is_compact_run_dir(path):
        return _validate_compact_run_dir(path, expected_experiment, expected_mode)
    return _validate_legacy_run_dir(path, expected_experiment, expected_mode)


def _artifact_key(filename: str) -> str:
    stem = filename.removesuffix(".json").removesuffix(".jsonl").removesuffix(".yml").removesuffix(".md")
    parts = stem.split("-")
    return parts[0] + "".join(part.title() for part in parts[1:])


def run_artifact_paths(path: Path) -> dict[str, str]:
    names: tuple[str, ...]
    if is_compact_run_dir(path):
        names = COMPACT_RUN_ARTIFACTS
    else:
        names = (*RUN_ARTIFACTS, *DETAIL_JSONL_FILES)
    return {_artifact_key(name): str(path / name) for name in names if (path / name).exists()}


def _safe_load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except Exception:
        return {}


def _safe_load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return load_yaml(path)
    except Exception:
        return {}


def _safe_load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return load_jsonl(path)
    except Exception:
        return []


def _records_by_kind_from_compact(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {kind: [] for kind in COMPACT_RECORD_KINDS}
    for record in records:
        kind = record.get("kind")
        data = record.get("data")
        if isinstance(kind, str) and kind in grouped and isinstance(data, dict):
            grouped[kind].append(data)
    return grouped


def _winner_candidate(candidates: list[dict[str, Any]], manifest: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any] | None:
    winner_id = manifest.get("winnerCandidate") or metrics.get("winning-candidate")
    if isinstance(winner_id, str):
        for candidate in candidates:
            if candidate.get("candidateId") == winner_id and candidate.get("classification") == "winner":
                return candidate
    for candidate in candidates:
        if candidate.get("classification") == "winner":
            return candidate
    return None


def _eligibility(candidates: list[dict[str, Any]], manifest: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    tested = [candidate for candidate in candidates if candidate.get("status") == "tested"]
    duplicate_only = bool(candidates) and not tested and all(candidate.get("status") == "skipped-duplicate" for candidate in candidates)
    winner = _winner_candidate(candidates, manifest, metrics)
    return {
        "duplicateOnly": duplicate_only,
        "evaluatedCandidateCount": len(tested),
        "bestEligible": bool(tested) and not duplicate_only,
        "promotionEligible": winner is not None and not duplicate_only,
        "winnerCandidate": winner,
    }


def _manifest_from_compact(run_doc: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "runId",
        "experiment",
        "mode",
        "subject",
        "status",
        "createdAt",
        "completedAt",
        "searchState",
        "search",
        "execution",
        "winnerCandidate",
        "bestCandidate",
        "skippedDuplicates",
    )
    return {key: run_doc[key] for key in keys if key in run_doc}


def load_run_view(path: Path, expected_experiment: str | None = None, expected_mode: str | None = None) -> dict[str, Any]:
    layout = "compact" if is_compact_run_dir(path) else "legacy"
    issues = validate_run_dir(path, expected_experiment=expected_experiment, expected_mode=expected_mode)
    if layout == "compact":
        run_doc = _safe_load_json(path / "run.json")
        try:
            records, _, _ = _load_compact_records(path / "records.jsonl") if (path / "records.jsonl").exists() else ([], {}, [])
        except Exception:
            records = []
        records_by_kind = _records_by_kind_from_compact(records)
        manifest = _manifest_from_compact(run_doc)
        metrics = run_doc.get("metrics", {}) if isinstance(run_doc.get("metrics"), dict) else {}
        scoreboard = run_doc.get("scoreboard", {}) if isinstance(run_doc.get("scoreboard"), dict) else {}
        inputs = run_doc.get("inputs", {}) if isinstance(run_doc.get("inputs"), dict) else {}
        config_snapshot = run_doc.get("configSnapshot", {}) if isinstance(run_doc.get("configSnapshot"), dict) else {}
        record_counts = run_doc.get("recordCounts", compact_record_counts(records)) if isinstance(run_doc.get("recordCounts"), dict) else compact_record_counts(records)
    else:
        manifest = _safe_load_json(path / "manifest.json")
        metrics_envelope = _safe_load_json(path / "metrics.json")
        metrics = metrics_envelope.get("metrics", {}) if isinstance(metrics_envelope.get("metrics"), dict) else {}
        scoreboard = _safe_load_json(path / "scoreboard.json")
        inputs = _safe_load_json(path / "inputs.json")
        config_snapshot = _safe_load_yaml(path / "config-snapshot.yml")
        records_by_kind = {
            "candidate": _safe_load_jsonl(path / "candidates.jsonl"),
            "round": _safe_load_jsonl(path / "rounds.jsonl"),
            "reflection": _safe_load_jsonl(path / "reflections.jsonl"),
            "signal": _safe_load_jsonl(path / "signals.jsonl"),
            "order": _safe_load_jsonl(path / "orders.jsonl"),
            "trade": _safe_load_jsonl(path / "trades.jsonl"),
            "block": _safe_load_jsonl(path / "blocks.jsonl"),
            "equity": _safe_load_jsonl(path / "equity.jsonl"),
            "horizon": _safe_load_jsonl(path / "horizons.jsonl"),
        }
        record_counts = {kind: len(records_by_kind.get(kind, [])) for kind in COMPACT_RECORD_KINDS}

    candidates = records_by_kind.get("candidate", [])
    eligibility = _eligibility(candidates, manifest, metrics)
    run_id = manifest.get("runId") or path.name
    experiment = manifest.get("experiment") or expected_experiment
    return {
        "layout": layout,
        "valid": not issues,
        "issues": issues,
        "runId": run_id,
        "experiment": experiment,
        "mode": manifest.get("mode"),
        "subject": manifest.get("subject"),
        "status": manifest.get("status"),
        "path": str(path),
        "directory": path,
        "manifest": manifest,
        "run": _safe_load_json(path / "run.json") if layout == "compact" else {},
        "inputs": inputs,
        "configSnapshot": config_snapshot,
        "metrics": metrics,
        "scoreboard": scoreboard,
        "recordsByKind": records_by_kind,
        "recordCounts": record_counts,
        "artifactPaths": run_artifact_paths(path),
        "duplicateOnly": eligibility["duplicateOnly"],
        "bestEligible": eligibility["bestEligible"],
        "promotionEligible": eligibility["promotionEligible"],
        "winnerCandidate": eligibility["winnerCandidate"],
        "evaluatedCandidateCount": eligibility["evaluatedCandidateCount"],
    }


def assert_run_writable(run_dir: Path) -> None:
    compact = run_dir / "run.json"
    if compact.exists():
        try:
            data = load_json(compact)
        except Exception:
            return
        if data.get("status") == "completed":
            raise ImmutableRunError(f"{run_dir.name} is completed; create a new run-id or audit artifact")
        return
    manifest = run_dir / "manifest.json"
    if not manifest.exists():
        return
    try:
        data = load_json(manifest)
    except Exception:
        return
    if data.get("status") == "completed":
        raise ImmutableRunError(f"{run_dir.name} is completed; create a new run-id or audit artifact")


def write_compact_run_artifacts(run_dir: Path, run_doc: dict[str, Any], records: list[dict[str, Any]], report: str) -> None:
    assert_run_writable(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    normalized = dict(run_doc)
    normalized["recordCounts"] = compact_record_counts(records)
    for marker in RUN_FORMAT_MARKER_KEYS:
        normalized.pop(marker, None)
    write_json(run_dir / "run.json", normalized)
    records_path = run_dir / "records.jsonl"
    records_path.write_text("", encoding="utf-8")
    for record in records:
        append_jsonl(records_path, record)
    (run_dir / "report.md").write_text(report, encoding="utf-8")


def ensure_run_artifacts(run_dir: Path, run_id: str, experiment: str, mode: str, snapshot: dict[str, Any], inputs: dict[str, Any], subject: str = "candidate-search") -> None:
    assert_run_writable(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "manifest.json", {"runId": run_id, "experiment": experiment, "mode": mode, "subject": subject, "status": "running", "createdAt": utc_now()})
    write_yaml(run_dir / "config-snapshot.yml", snapshot)
    write_json(run_dir / "inputs.json", {"runId": run_id, "subject": subject, **inputs})
    write_json(run_dir / "scoreboard.json", {"runId": run_id, "rankings": {"candidates": []}, "components": []})
    for filename in RUN_JSONL_FILES:
        (run_dir / filename).touch()


def validate_promoted_robot_dir(path: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    robot_path = path / "robot.yml"
    if not robot_path.exists():
        issues.append(ValidationIssue("missing-artifact", str(robot_path), "missing live-loadable promoted robot contract"))
        return issues
    try:
        robot = load_yaml(robot_path)
    except Exception as exc:
        return [ValidationIssue("invalid-yaml", str(robot_path), str(exc))]
    if robot.get("schema-version") != 1:
        issues.append(_issue(robot_path, "schema-version", "must equal 1"))
    for key_path in find_non_kebab_keys(robot):
        issues.append(ValidationIssue("invalid-name", f"{robot_path}:{key_path}", "promoted robot YAML keys must use kebab-case"))
    for section in PROMOTED_ROBOT_REQUIRED_SECTIONS:
        if not isinstance(robot.get(section), dict):
            issues.append(_issue(robot_path, section, "missing promoted robot section"))

    robot_section = robot.get("robot", {}) if isinstance(robot.get("robot"), dict) else {}
    if not isinstance(robot_section.get("id"), str) or not robot_section.get("id"):
        issues.append(_issue(robot_path, "robot.id", "must be a non-empty string"))
    if not _is_number(robot_section.get("score")):
        issues.append(_issue(robot_path, "robot.score", "must be a number"))
    if not isinstance(robot_section.get("score-version"), str) or not robot_section.get("score-version"):
        issues.append(_issue(robot_path, "robot.score-version", "must be a non-empty string"))

    source = robot.get("source", {}) if isinstance(robot.get("source"), dict) else {}
    for key in ("experiment", "run-id", "candidate-id"):
        if not isinstance(source.get(key), str) or not source.get(key):
            issues.append(_issue(robot_path, f"source.{key}", "must be a non-empty string"))

    strategy = robot.get("strategy", {}) if isinstance(robot.get("strategy"), dict) else {}
    if not isinstance(strategy.get("components"), list):
        issues.append(_issue(robot_path, "strategy.components", "must be a list"))
    if not isinstance(strategy.get("parameters"), dict):
        issues.append(_issue(robot_path, "strategy.parameters", "must be an object"))

    risk = robot.get("risk", {}) if isinstance(robot.get("risk"), dict) else {}
    if not isinstance(risk.get("effective"), dict):
        issues.append(_issue(robot_path, "risk.effective", "must be an object"))

    execution = robot.get("execution", {}) if isinstance(robot.get("execution"), dict) else {}
    if not _is_number(execution.get("payout")):
        issues.append(_issue(robot_path, "execution.payout", "must be a number"))
    if not isinstance(execution.get("payout-source"), str) or not execution.get("payout-source"):
        issues.append(_issue(robot_path, "execution.payout-source", "must be a non-empty string"))

    promotion = robot.get("promotion", {}) if isinstance(robot.get("promotion"), dict) else {}
    if not isinstance(promotion.get("metrics"), dict):
        issues.append(_issue(robot_path, "promotion.metrics", "must be an object"))
    if not isinstance(promotion.get("timestamp"), str) or not promotion.get("timestamp"):
        issues.append(_issue(robot_path, "promotion.timestamp", "must be a non-empty string"))
    return issues


def validate_promoted_catalog(root: Path) -> list[ValidationIssue]:
    promoted = root / "promoted"
    if not promoted.exists():
        return []
    issues: list[ValidationIssue] = []
    for path in sorted(child for child in promoted.iterdir() if child.is_dir()):
        issues.extend(validate_promoted_robot_dir(path))
    return issues


def complete_run(run_dir: Path, metrics: dict[str, Any], report: str) -> None:
    manifest = load_json(run_dir / "manifest.json")
    run_id = manifest["runId"]
    write_json(run_dir / "metrics.json", {"runId": run_id, "status": "completed", "metrics": metrics})
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    manifest["status"] = "completed"
    manifest["completedAt"] = utc_now()
    write_json(run_dir / "manifest.json", manifest)
