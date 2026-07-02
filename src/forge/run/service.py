from __future__ import annotations

import copy
import csv
from dataclasses import dataclass
from datetime import timedelta
from math import ceil
from pathlib import Path
from time import monotonic
from typing import Any

from xenibe.artifacts.history import file_sha256, parse_datetime
from xenibe.artifacts.naming import is_run_id
from xenibe.artifacts.store import (
    ValidationIssue,
    experiment_dir,
    load_experiment,
    load_json,
    load_run_view,
    load_yaml,
    make_run_id,
    utc_now,
    validate_experiment_dir,
    validate_run_dir,
    write_compact_run_artifacts,
)
from xenibe.artifacts.schemas import DEFAULT_PROVIDER, DEFAULT_REPORT
from xenibe.backtest import DEFAULT_BACKTEST_PAYOUT, run_m1_backtest
from xenibe.candles import Candle
from xenibe.execution import ebinex_candle_expiry_execution
from xenibe.metrics.summary import METRIC_NET_PROFIT, calculate_backtest_metrics
from xenibe.risk import DEFAULT_RISK
from xenibe.strategy import UnsupportedComponentError, build_scoreboard, candidate_rank_key, classify_candidate, compile_candidate_strategy, evaluation_fingerprint, generate_candidates, resolve_limits, target_satisfied

from forge.common import issues_payload, render_run_report, run_dir
from forge.run_consumer import completed_run


@dataclass(frozen=True)
class RunSetup:
    base: Path
    configs: dict[str, dict[str, Any]]
    search_scope: dict[str, Any]
    risk: dict[str, Any]
    provider: dict[str, Any]
    report_config: dict[str, Any]
    resolved_limits: dict[str, Any]
    candidates: list[dict[str, Any]]
    candles: list[Candle]
    history_context: dict[str, Any]


@dataclass(frozen=True)
class CandleLoad:
    candles: list[Candle]
    source_kind: str


@dataclass
class SearchResult:
    tested: list[dict[str, Any]]
    round_records: list[dict[str, Any]]
    reflection_records: list[dict[str, Any]]
    horizon_records: list[dict[str, Any]]
    winning_candidate: str | None
    best_record: dict[str, Any] | None
    detail_result: dict[str, Any] | None
    search_state: str
    elapsed_seconds: float
    evaluated_candidate_count: int
    timed_out: bool


def _read_candle_csv(path: Path) -> list[Candle]:
    candles: list[Candle] = []
    if not path.exists() or path.stat().st_size == 0:
        return candles
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                candles.append(Candle.from_mapping(row))
            except Exception:
                continue
    return candles


def _filter_candles(candles: list[Candle], start: Any, end: Any) -> list[Candle]:
    parsed_start = parse_datetime(start)
    parsed_end = parse_datetime(end)
    if parsed_start is None or parsed_end is None:
        return candles
    filtered = []
    for candle in candles:
        candle_time = parse_datetime(candle.time)
        if candle_time is not None and parsed_start <= candle_time < parsed_end:
            filtered.append(candle)
    return filtered


def load_history_candles(experiment_path: Path, ingest: dict[str, Any]) -> list[Candle]:
    data = ingest.get("data", {})
    configured = Path(str(data.get("path", "data")))
    source = configured if configured.is_absolute() else experiment_path / configured
    if source.is_file():
        return _filter_candles(_read_candle_csv(source), data.get("from"), data.get("to"))
    if not source.exists():
        return []
    candles: list[Candle] = []
    for path in sorted(source.glob("*.csv")):
        candles.extend(_read_candle_csv(path))
    return _filter_candles(candles, data.get("from"), data.get("to"))


def configured_history_source(experiment_path: Path, ingest: dict[str, Any]) -> Path:
    data = ingest.get("data", {})
    configured = Path(str(data.get("path", "data")))
    return configured if configured.is_absolute() else experiment_path / configured


def configured_history_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    if source.exists():
        return sorted(source.glob("*.csv"))
    return []


def _file_sha256(path: Path) -> str:
    return file_sha256(path)


def history_data_context(source: Path, candle_count: int) -> dict[str, Any]:
    files = configured_history_files(source)
    context = {
        "source": str(source),
        "candleCount": candle_count,
        "files": [
            {
                "path": str(path),
                "size": path.stat().st_size,
                "sha256": _file_sha256(path),
            }
            for path in files
            if path.exists()
        ],
    }
    if source.is_file() and source.name.endswith(".csv"):
        manifest_path = source.with_name(f"{source.stem}.manifest.json")
        if manifest_path.exists():
            try:
                manifest = load_json(manifest_path)
            except Exception:
                manifest = {}
            context["manifest"] = {
                "path": str(manifest_path),
                "sha256": manifest.get("sha256"),
                "coverageRange": manifest.get("coverageRange"),
                "provider": manifest.get("provider"),
                "providerMode": manifest.get("providerMode"),
                "downloadedAt": manifest.get("downloadedAt"),
            }
            context["files"].append({"path": str(manifest_path), "size": manifest_path.stat().st_size, "sha256": _file_sha256(manifest_path)})
    return context


def _deep_merge(default: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(default)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def optional_config(experiment_path: Path, filename: str, default: dict[str, Any]) -> dict[str, Any]:
    path = experiment_path / filename
    if path.exists():
        return _deep_merge(default, load_yaml(path))
    return copy.deepcopy(default)


def _prior_evaluation_index(experiment_path: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    runs = experiment_path / "runs"
    if not runs.exists():
        return index
    for run_dir in sorted(path for path in runs.iterdir() if path.is_dir()):
        view = load_run_view(run_dir)
        for record in view.get("recordsByKind", {}).get("candidate", []):
            fingerprint = record.get("evaluationFingerprint")
            if isinstance(fingerprint, str) and fingerprint not in index:
                index[fingerprint] = {
                    "runId": run_dir.name,
                    "candidateId": record.get("candidateId"),
                    "candidateFingerprint": record.get("candidateFingerprint"),
                }
    return index


def _execution_semantics(configs: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    ingest_data = configs["ingest.yml"].get("data", {})
    if not isinstance(ingest_data, dict) or ingest_data.get("provider") != "ebinex":
        return None
    return ebinex_candle_expiry_execution(str(ingest_data.get("timeframe", "")))


def _ignored_candidate_parameters(configs: dict[str, dict[str, Any]]) -> set[str]:
    ingest_data = configs["ingest.yml"].get("data", {})
    if isinstance(ingest_data, dict) and ingest_data.get("provider") == "ebinex":
        return {"expiration-candles"}
    return set()


def _evaluation_context(configs: dict[str, dict[str, Any]], risk: dict[str, Any], mode: str, history: dict[str, Any]) -> dict[str, Any]:
    context = {
        "mode": mode,
        "ingest": configs["ingest.yml"],
        "history": history,
        "horizonValidation": configs["search-scope.yml"].get("horizon-validation"),
        "target": configs["experiment.yml"]["target"],
        "risk": risk,
    }
    semantics = _execution_semantics(configs)
    if semantics is not None:
        context["executionSemantics"] = semantics
    return context


def _candidate_key(record: dict[str, Any] | None, target_metric: str) -> tuple[float, float, float, float]:
    return candidate_rank_key(record, target_metric)


def _resolve_run_id(mode: str, run_id: str | None) -> dict[str, Any] | str:
    prefixes = {"backtest": "bt", "simulate": "sim"}
    if mode not in prefixes:
        return {
            "error": "invalid-artifact",
            "message": "run mode must be backtest or simulate",
            "next": ["forge backtest <experiment> --mode backtest --json"],
        }
    prefix = prefixes[mode]
    resolved_run_id = run_id or make_run_id(prefix)
    if not is_run_id(resolved_run_id):
        return {
            "error": "invalid-name",
            "message": f"run id must use {prefix}-YYYYMMDD-HHMMSS",
            "next": ["omit --run-id to generate one"],
        }
    if not resolved_run_id.startswith(f"{prefix}-"):
        return {
            "error": "invalid-name",
            "message": f"{mode} run IDs must use the {prefix}- prefix",
            "next": ["omit --run-id to generate one"],
        }
    return resolved_run_id


def _load_candles_or_error(root: Path, experiment: str, base: Path, ingest: dict[str, Any]) -> CandleLoad | dict[str, Any]:
    candles = load_history_candles(base, ingest)
    if candles:
        return CandleLoad(candles, "configured-history")
    source = configured_history_source(base, ingest)
    history_files = configured_history_files(source)
    ingest_data = ingest.get("data", {})
    return {
        "error": "missing-artifact",
        "message": f"no parseable candle data found at {source}; download or configure real history before running backtest",
        "next": [
            f"forge data download {ingest_data.get('asset', '<asset>')} --experiment {experiment} --timeframe {ingest_data.get('timeframe', 'M1')} --from {ingest_data.get('from', '<from>')} --to {ingest_data.get('to', '<to>')} --root {root} --json",
        ],
        "issues": [
            {
                "code": "missing-artifact",
                "path": f"{base / 'ingest.yml'}:data.path",
                "message": f"configured history file(s) contain no parseable candles: {', '.join(str(path) for path in history_files) if history_files else source}",
            }
        ],
    }


def _load_run_setup(root: Path, experiment: str) -> RunSetup | dict[str, Any]:
    base = experiment_dir(root, experiment)
    issues = validate_experiment_dir(base)
    if issues:
        error = "invalid-yaml" if any(issue.code == "invalid-yaml" for issue in issues) else "invalid-artifact"
        return {"error": error, "message": "experiment validation failed", "issues": issues_payload(issues)}

    configs = load_experiment(root, experiment)
    search_scope = configs["search-scope.yml"]
    try:
        risk = optional_config(base, "risk.yml", DEFAULT_RISK)
        provider = optional_config(base, "provider.yml", DEFAULT_PROVIDER)
        report_config = optional_config(base, "report.yml", DEFAULT_REPORT)
    except Exception as exc:
        issue = ValidationIssue("invalid-yaml", str(base), str(exc))
        return {"error": "invalid-yaml", "message": "optional config validation failed", "issues": issues_payload([issue])}
    resolved_limits = resolve_limits(search_scope)
    candidates = generate_candidates(search_scope, resolved_limits, ignored_parameters=_ignored_candidate_parameters(configs))
    history_source = configured_history_source(base, configs["ingest.yml"])
    candle_load = _load_candles_or_error(root, experiment, base, configs["ingest.yml"])
    if isinstance(candle_load, dict):
        return candle_load
    history_context = history_data_context(history_source, len(candle_load.candles))
    history_context["dataSource"] = candle_load.source_kind
    return RunSetup(base, configs, search_scope, risk, provider, report_config, resolved_limits, candidates, candle_load.candles, history_context)


def _duplicate_record(candidate: dict[str, Any], prior: dict[str, Any]) -> dict[str, Any]:
    return {
        **candidate,
        "status": "skipped-duplicate",
        "classification": "skipped",
        "reason": "duplicate-evaluation",
        "priorCandidate": prior,
        "metrics": {},
        "riskState": {},
    }


def _empty_backtest_result() -> dict[str, Any]:
    return {"signals": [], "orders": [], "trades": [], "blocks": [], "equity": [], "metrics": calculate_backtest_metrics([], [])}


def _horizon_config(search_scope: dict[str, Any]) -> dict[str, Any] | None:
    value = search_scope.get("horizon-validation")
    if isinstance(value, dict) and value.get("enabled") is True:
        return value
    return None


def _window_bounds(end_value: Any, days: int) -> tuple[str, str] | None:
    end = parse_datetime(end_value)
    if end is None:
        return None
    start = end - timedelta(days=days)
    return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")


def _window_candles(candles: list[Candle], end_value: Any, days: int) -> list[Candle]:
    bounds = _window_bounds(end_value, days)
    if bounds is None:
        return candles
    return _filter_candles(candles, bounds[0], bounds[1])


def _minimum_trades(days: int, min_trades_per_hour: Any) -> int:
    return ceil(days * 24 * float(min_trades_per_hour))


def _horizon_record(
    candidate: dict[str, Any],
    days: int,
    end_value: Any,
    min_trades_per_hour: Any,
    target: dict[str, Any],
    result: dict[str, Any] | None,
    require_positive_net_profit: bool,
    reused_primary: bool = False,
    reason: str | None = None,
) -> dict[str, Any]:
    bounds = _window_bounds(end_value, days)
    metrics = dict(result.get("metrics", {})) if result is not None else {}
    required_trades = _minimum_trades(days, min_trades_per_hour)
    total_trades = int(metrics.get("total-trades", 0))
    status = "insufficient-data"
    if reason is None and total_trades >= required_trades:
        positive_profit = float(metrics.get(METRIC_NET_PROFIT, 0.0)) > 0.0
        status = "passed" if target_satisfied(metrics, target) and (positive_profit or not require_positive_net_profit) else "failed"
    return {
        "candidateId": candidate["candidateId"],
        "horizonDays": days,
        "window": {"from": bounds[0], "to": bounds[1]} if bounds is not None else {},
        "status": status,
        "reason": reason or ("minimum-trades-not-met" if status == "insufficient-data" else None),
        "requiredTrades": required_trades,
        "tradeCount": total_trades,
        "reusedPrimary": reused_primary,
        "metrics": metrics,
    }


def _horizon_summary(records: list[dict[str, Any]], config: dict[str, Any], target_metric: str) -> dict[str, Any]:
    passed = [int(record["horizonDays"]) for record in records if record.get("status") == "passed"]
    failed = [int(record["horizonDays"]) for record in records if record.get("status") == "failed"]
    insufficient = [int(record["horizonDays"]) for record in records if record.get("status") == "insufficient-data"]
    sufficient_records = [record for record in records if record.get("status") in {"passed", "failed"}]
    sufficient_count = len(sufficient_records)
    min_sufficient = int(config.get("min-sufficient-horizons", 1))
    worst_metric = None
    if sufficient_records:
        worst_metric = min(float(record.get("metrics", {}).get(target_metric, 0.0)) for record in sufficient_records)
    status = "passed" if sufficient_count >= min_sufficient and not failed and len(passed) >= min_sufficient else "failed"
    reason = None
    if status == "failed":
        reason = "insufficient-sufficient-horizons" if sufficient_count < min_sufficient else "horizon-validation-failed"
    return {
        "enabled": True,
        "primaryWindowDays": int(config.get("primary-window-days", 7)),
        "minTradesPerHour": float(config.get("min-trades-per-hour", 0.0)),
        "gateMode": str(config.get("gate", {}).get("mode", "min-sufficient")),
        "status": status,
        "reason": reason,
        "passedHorizons": passed,
        "failedHorizons": failed,
        "insufficientDataHorizons": insufficient,
        "sufficientHorizonCount": sufficient_count,
        "failedHorizonCount": len(failed),
        "insufficientHorizonCount": len(insufficient),
        "worstHorizonTargetMetric": worst_metric,
    }


def _skipped_horizon_summary(config: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "enabled": True,
        "primaryWindowDays": int(config.get("primary-window-days", 7)),
        "minTradesPerHour": float(config.get("min-trades-per-hour", 0.0)),
        "gateMode": str(config.get("gate", {}).get("mode", "min-sufficient")),
        "status": "skipped",
        "reason": reason,
        "passedHorizons": [],
        "failedHorizons": [],
        "insufficientDataHorizons": [],
        "sufficientHorizonCount": 0,
        "failedHorizonCount": 0,
        "insufficientHorizonCount": 0,
        "worstHorizonTargetMetric": None,
    }


def _evaluate_horizons(
    candidate: dict[str, Any],
    setup: RunSetup,
    target: dict[str, Any],
    primary_result: dict[str, Any],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    days_values = [int(day) for day in config.get("days", [])]
    primary_days = int(config.get("primary-window-days", 7))
    end_value = setup.configs["ingest.yml"].get("data", {}).get("to")
    min_trades_per_hour = config.get("min-trades-per-hour", 0.0)
    require_positive_net_profit = bool(config.get("gate", {}).get("require-positive-net-profit", True))
    records: list[dict[str, Any]] = []
    strategy = compile_candidate_strategy(candidate)
    for days in days_values:
        if days == primary_days:
            record = _horizon_record(candidate, days, end_value, min_trades_per_hour, target, primary_result, require_positive_net_profit, reused_primary=True)
        else:
            candles = _window_candles(setup.candles, end_value, days)
            if not candles:
                record = _horizon_record(candidate, days, end_value, min_trades_per_hour, target, None, require_positive_net_profit, reason="no-candles-in-window")
            else:
                result = run_m1_backtest(candles, strategy=strategy, risk_config=setup.risk)
                record = _horizon_record(candidate, days, end_value, min_trades_per_hour, target, result, require_positive_net_profit)
        records.append(record)
    return records, _horizon_summary(records, config, str(target["metric"]))


def _test_candidate(candidate: dict[str, Any], candles: list[Candle], risk: dict[str, Any], target: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        strategy = compile_candidate_strategy(candidate)
        result = run_m1_backtest(candles, strategy=strategy, risk_config=risk)
        classification, reason = classify_candidate(result["metrics"], target)
    except UnsupportedComponentError as exc:
        result = _empty_backtest_result()
        classification = "rejected"
        reason = f"unsupported-component:{exc.role}:{exc.component_type}"
    risk_state = result["equity"][-1] if result["equity"] else {}
    return (
        {
            **candidate,
            "status": "tested",
            "classification": classification,
            "reason": reason,
            "metrics": result["metrics"],
            "riskState": risk_state,
        },
        result,
    )


def _test_candidate_with_horizon(candidate: dict[str, Any], setup: RunSetup, target: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    config = _horizon_config(setup.search_scope)
    if config is None:
        record, result = _test_candidate(candidate, setup.candles, setup.risk, target)
        return record, result, []

    primary_days = int(config.get("primary-window-days", 7))
    end_value = setup.configs["ingest.yml"].get("data", {}).get("to")
    primary_candles = _window_candles(setup.candles, end_value, primary_days)
    record, result = _test_candidate(candidate, primary_candles, setup.risk, target)
    if str(record.get("reason", "")).startswith("unsupported-component:"):
        record["horizonValidation"] = _skipped_horizon_summary(config, str(record["reason"]))
        return record, result, []
    min_primary_trades = _minimum_trades(primary_days, config.get("min-trades-per-hour", 0.0))
    primary_trades = int(result.get("metrics", {}).get("total-trades", 0))
    if primary_trades < min_primary_trades:
        record["classification"] = "rejected"
        record["reason"] = "insufficient-primary-sample"
        record["horizonValidation"] = _skipped_horizon_summary(config, "insufficient-primary-sample")
        return record, result, []
    if not target_satisfied(record.get("metrics", {}), target):
        record["horizonValidation"] = _skipped_horizon_summary(config, "primary-target-not-hit")
        return record, result, []

    horizon_records, summary = _evaluate_horizons(candidate, setup, target, result, config)
    record["horizonValidation"] = summary
    if summary["status"] == "passed":
        record["classification"] = "winner"
        record["reason"] = "target-hit"
    else:
        record["classification"] = "rejected"
        record["reason"] = "horizon-validation-failed"
    return record, result, horizon_records


def _update_search_state(stop: bool, stagnant_rounds: int, stagnation_limit: int, round_number: int, max_rounds: int, cursor: int, candidate_count: int) -> tuple[str, bool]:
    if stop:
        return "target-hit", True
    if stagnant_rounds >= stagnation_limit:
        return "stagnation", True
    if round_number >= max_rounds and cursor < candidate_count:
        return "max-rounds", False
    if cursor >= candidate_count:
        return "limits-exhausted", False
    return "limits-exhausted", False


def _run_candidate_search(setup: RunSetup, mode: str, resolved_run_id: str) -> SearchResult:
    started_at = monotonic()
    max_seconds_value = setup.resolved_limits.get("max-seconds")
    max_seconds = float(max_seconds_value) if isinstance(max_seconds_value, (int, float)) and not isinstance(max_seconds_value, bool) else None
    target = setup.configs["experiment.yml"]["target"]
    target_metric = str(target["metric"])
    tested: list[dict[str, Any]] = []
    round_records: list[dict[str, Any]] = []
    reflection_records: list[dict[str, Any]] = []
    horizon_records: list[dict[str, Any]] = []
    winning_candidate: str | None = None
    detail_result: dict[str, Any] | None = None
    best_record: dict[str, Any] | None = None
    evaluation_context = _evaluation_context(setup.configs, setup.risk, mode, setup.history_context)
    prior_index = _prior_evaluation_index(setup.base)
    batch_size = max(1, int(setup.resolved_limits.get("batch-size", len(setup.candidates) or 1)))
    max_rounds = max(1, int(setup.resolved_limits.get("max-rounds", 1)))
    stagnation_limit = max(1, int(setup.resolved_limits.get("stagnation-rounds", 1)))
    stop_on_target = bool(setup.configs["experiment.yml"].get("stop-on-target", True))
    search_state = "limits-exhausted"

    def timed_out() -> bool:
        return max_seconds is not None and monotonic() - started_at >= max_seconds

    cursor = 0
    round_number = 0
    stagnant_rounds = 0
    stop = False
    while cursor < len(setup.candidates) and round_number < max_rounds and not stop:
        if timed_out():
            search_state = "timeout"
            break
        round_number += 1
        batch = setup.candidates[cursor : cursor + batch_size]
        cursor += len(batch)
        round_candidate_ids: list[str] = []
        round_start_key = _candidate_key(best_record, target_metric)
        for candidate in batch:
            if timed_out():
                search_state = "timeout"
                stop = True
                break
            candidate["evaluationFingerprint"] = evaluation_fingerprint(candidate, evaluation_context)
            round_candidate_ids.append(candidate["candidateId"])
            prior = prior_index.get(candidate["evaluationFingerprint"])
            if prior is not None:
                tested.append(_duplicate_record(candidate, prior))
                continue
            record, result, candidate_horizons = _test_candidate_with_horizon(candidate, setup, target)
            horizon_records.extend(candidate_horizons)
            prior_index[candidate["evaluationFingerprint"]] = {
                "runId": resolved_run_id,
                "candidateId": record["candidateId"],
                "candidateFingerprint": record.get("candidateFingerprint"),
            }
            if record["classification"] == "winner":
                if winning_candidate is None:
                    winning_candidate = record["candidateId"]
                detail_result = result
            elif record["classification"] == "approved" and detail_result is None:
                detail_result = result
            tested.append(record)
            if _candidate_key(record, target_metric) > _candidate_key(best_record, target_metric):
                best_record = record
            if record["classification"] == "winner" and stop_on_target:
                stop = True
                break

        round_end_key = _candidate_key(best_record, target_metric)
        stagnant_rounds = 0 if round_end_key > round_start_key else stagnant_rounds + 1
        if search_state != "timeout":
            search_state, stop = _update_search_state(stop, stagnant_rounds, stagnation_limit, round_number, max_rounds, cursor, len(setup.candidates))
        round_records.append(
            {
                "round": round_number,
                "status": "timeout" if search_state == "timeout" else "completed",
                "candidateIds": round_candidate_ids,
                "winnerCandidate": winning_candidate,
                "bestCandidate": best_record.get("candidateId") if best_record else None,
                "stagnantRounds": stagnant_rounds,
            }
        )
        reflection_records.append(
            {
                "round": round_number,
                "decision": search_state if stop or cursor >= len(setup.candidates) or round_number >= max_rounds else "continue",
                "summary": f"batch completed with {len(round_candidate_ids)} candidate(s); best={best_record.get('candidateId') if best_record else None}",
                "scoreboard": "scoreboard.json",
            }
        )
    elapsed_seconds = round(monotonic() - started_at, 6)
    evaluated_candidate_count = sum(1 for candidate in tested if candidate.get("status") == "tested")
    return SearchResult(tested, round_records, reflection_records, horizon_records, winning_candidate, best_record, detail_result, search_state, elapsed_seconds, evaluated_candidate_count, search_state == "timeout")


def _final_metrics(result: SearchResult) -> dict[str, Any]:
    metrics = dict(result.best_record["metrics"]) if result.best_record else calculate_backtest_metrics([], [])
    metrics["winning-candidate"] = result.winning_candidate
    metrics["best-candidate"] = result.best_record.get("candidateId") if result.best_record else None
    metrics["skipped-duplicates"] = sum(1 for candidate in result.tested if candidate.get("status") == "skipped-duplicate")
    if result.best_record and isinstance(result.best_record.get("horizonValidation"), dict):
        metrics["horizonValidation"] = result.best_record["horizonValidation"]
    return metrics


def _execution_context(setup: RunSetup) -> dict[str, Any]:
    max_seconds = setup.resolved_limits.get("max-seconds")
    context = {
        "payout": DEFAULT_BACKTEST_PAYOUT,
        "payoutSource": "fixed-default",
        "maxSeconds": max_seconds,
        "maxSecondsEnforced": isinstance(max_seconds, (int, float)) and not isinstance(max_seconds, bool),
        "dataSource": setup.history_context.get("dataSource"),
    }
    semantics = _execution_semantics(setup.configs)
    if semantics is not None:
        context["semantics"] = semantics
    return context


def _run_limitations(setup: RunSetup) -> list[dict[str, Any]]:
    return [
        {
            "code": "fixed-payout",
            "message": f"Backtests currently use fixed payout {DEFAULT_BACKTEST_PAYOUT}.",
        },
    ]


def _run_payload(experiment: str, resolved_run_id: str, directory: Path, metrics: dict[str, Any], result: SearchResult, setup: RunSetup) -> dict[str, Any]:
    return {
        "experiment": experiment,
        "runId": resolved_run_id,
        "subject": "candidate-search",
        "path": str(directory),
        "metrics": metrics,
        "searchState": result.search_state,
        "search": {
            "timedOut": result.timed_out,
            "elapsedSeconds": result.elapsed_seconds,
            "evaluatedCandidateCount": result.evaluated_candidate_count,
        },
        "bestCandidate": result.best_record.get("candidateId") if result.best_record else None,
        "execution": _execution_context(setup),
        "limitations": _run_limitations(setup),
    }


def _compact_records(result: SearchResult) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def add(kind: str, data: dict[str, Any]) -> None:
        records.append({"seq": len(records) + 1, "kind": kind, "data": data})

    for candidate in result.tested:
        add("candidate", candidate)
    for record in result.horizon_records:
        add("horizon", record)
    for record in result.round_records:
        add("round", record)
    for record in result.reflection_records:
        add("reflection", record)
    if result.detail_result is not None:
        for name, kind in (
            ("signals", "signal"),
            ("orders", "order"),
            ("trades", "trade"),
            ("blocks", "block"),
            ("equity", "equity"),
        ):
            for record in result.detail_result[name]:
                add(kind, record)
    return records


def _persist_run(root: Path, experiment: str, mode: str, resolved_run_id: str, setup: RunSetup, result: SearchResult, final_metrics: dict[str, Any]) -> None:
    directory = run_dir(root, experiment, resolved_run_id)
    target_metric = str(setup.configs["experiment.yml"]["target"]["metric"])
    created_at = utc_now()
    completed_at = utc_now()
    execution = _execution_context(setup)
    limitations = _run_limitations(setup)
    search = {
        "timedOut": result.timed_out,
        "elapsedSeconds": result.elapsed_seconds,
        "evaluatedCandidateCount": result.evaluated_candidate_count,
    }
    snapshot = {
        "experiment": setup.configs["experiment.yml"],
        "ingest": setup.configs["ingest.yml"],
        "search-scope": setup.search_scope,
        "risk": setup.risk,
        "provider": setup.provider,
        "report": setup.report_config,
    }
    inputs = {
        "runId": resolved_run_id,
        "subject": "candidate-search",
        "resolvedLimits": setup.resolved_limits,
        "candidateCount": len(setup.candidates),
        "batchCount": len(result.round_records),
        "history": setup.history_context,
        "execution": execution,
        "limitations": limitations,
        "horizonValidation": setup.search_scope.get("horizon-validation"),
        "searchState": result.search_state,
        "search": search,
    }
    scoreboard = build_scoreboard(resolved_run_id, result.tested, target_metric)
    manifest = {
        "runId": resolved_run_id,
        "experiment": experiment,
        "mode": mode,
        "subject": "candidate-search",
        "status": "completed",
        "createdAt": created_at,
        "completedAt": completed_at,
        "searchState": result.search_state,
        "search": search,
        "execution": execution,
        "winnerCandidate": result.winning_candidate,
        "bestCandidate": result.best_record.get("candidateId") if result.best_record else None,
        "skippedDuplicates": final_metrics["skipped-duplicates"],
    }
    run_doc = {
        **manifest,
        "configSnapshot": snapshot,
        "inputs": inputs,
        "metrics": final_metrics,
        "scoreboard": scoreboard,
        "limitations": limitations,
        "promotion": {
            "eligible": result.winning_candidate is not None,
            "candidate": result.best_record if result.best_record and result.best_record.get("classification") == "winner" else None,
        },
        "recordCounts": {},
    }
    records = _compact_records(result)
    report = render_run_report(experiment, resolved_run_id, final_metrics, manifest)
    write_compact_run_artifacts(directory, run_doc, records, report)


def run_backtest(root: Path, experiment: str, mode: str, run_id: str | None, dry_run: bool = False) -> dict[str, Any]:
    resolved = _resolve_run_id(mode, run_id)
    if isinstance(resolved, dict):
        return resolved
    resolved_run_id = resolved
    setup = _load_run_setup(root, experiment)
    if isinstance(setup, dict):
        return setup
    result = _run_candidate_search(setup, mode, resolved_run_id)
    final_metrics = _final_metrics(result)
    directory = run_dir(root, experiment, resolved_run_id)
    payload = _run_payload(experiment, resolved_run_id, directory, final_metrics, result, setup)
    if dry_run:
        payload["plannedActions"] = ["persist compact run.json", "write typed records.jsonl trail", "write report.md"]
        if _horizon_config(setup.search_scope) is not None:
            payload["plannedActions"].extend(["evaluate primary-window candidates", "evaluate configured horizon windows", "write horizon records"])
        return payload
    _persist_run(root, experiment, mode, resolved_run_id, setup, result, final_metrics)
    return payload


def list_runs(root: Path, experiment: str) -> dict[str, Any]:
    runs = experiment_dir(root, experiment) / "runs"
    return {"experiment": experiment, "runs": sorted(path.name for path in runs.iterdir() if path.is_dir()) if runs.exists() else []}


def show_run(root: Path, experiment: str, run_id: str) -> dict[str, Any]:
    loaded = completed_run(root, experiment, run_id)
    if "error" in loaded:
        return loaded
    return {
        "experiment": experiment,
        "runId": run_id,
        "path": loaded["path"],
        "layout": loaded["layout"],
        "metrics": loaded["metrics"],
        "manifest": loaded["manifest"],
        "scoreboard": loaded["scoreboard"],
        "recordCounts": loaded["recordCounts"],
        "duplicateOnly": loaded["duplicateOnly"],
        "promotionEligible": loaded["promotionEligible"],
    }


def validate_run(root: Path, experiment: str, run_id: str) -> dict[str, Any]:
    issues = validate_run_dir(run_dir(root, experiment, run_id), expected_experiment=experiment)
    if issues:
        return {"valid": False, "issues": issues_payload(issues)}
    return {"experiment": experiment, "runId": run_id, "valid": True}
