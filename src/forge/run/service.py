from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from xenibe.artifacts.naming import is_run_id
from xenibe.artifacts.store import (
    append_jsonl,
    complete_run,
    ensure_run_artifacts,
    experiment_dir,
    load_experiment,
    load_json,
    load_yaml,
    make_run_id,
    validate_experiment_dir,
    validate_run_dir,
    write_json,
)
from xenibe.artifacts.schemas import DEFAULT_PROVIDER, DEFAULT_REPORT, DEFAULT_RISK
from xenibe.backtest import run_m1_backtest
from xenibe.candles import Candle
from xenibe.metrics.summary import calculate_trade_metrics
from xenibe.strategy import UnsupportedComponentError, build_scoreboard, classify_candidate, compile_candidate_strategy, evaluation_fingerprint, generate_candidates, resolve_limits

from forge.common import issues_payload, load_metrics


def default_candles() -> list[Candle]:
    return [
        Candle("2026-01-01T00:00:00Z", 1.0, 1.2, 0.9, 1.1),
        Candle("2026-01-01T00:01:00Z", 1.1, 1.2, 1.0, 1.0),
        Candle("2026-01-01T00:02:00Z", 1.0, 1.2, 0.9, 1.15),
        Candle("2026-01-01T00:03:00Z", 1.15, 1.16, 0.95, 1.0),
    ]


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


def load_history_candles(experiment_path: Path, ingest: dict[str, Any]) -> list[Candle]:
    data = ingest.get("data", {})
    configured = Path(str(data.get("path", "data")))
    source = configured if configured.is_absolute() else experiment_path / configured
    if source.is_file():
        return _read_candle_csv(source)
    if not source.exists():
        return []
    candles: list[Candle] = []
    for path in sorted(source.glob("*.csv")):
        candles.extend(_read_candle_csv(path))
    return candles


def optional_config(experiment_path: Path, filename: str, default: dict[str, Any]) -> dict[str, Any]:
    path = experiment_path / filename
    if path.exists():
        return load_yaml(path)
    return default


def _prior_evaluation_index(experiment_path: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    runs = experiment_path / "runs"
    if not runs.exists():
        return index
    for run_dir in sorted(path for path in runs.iterdir() if path.is_dir()):
        candidates = run_dir / "candidates.jsonl"
        if not candidates.exists():
            continue
        with candidates.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                fingerprint = record.get("evaluationFingerprint")
                if isinstance(fingerprint, str) and fingerprint not in index:
                    index[fingerprint] = {
                        "runId": run_dir.name,
                        "candidateId": record.get("candidateId"),
                        "candidateFingerprint": record.get("candidateFingerprint"),
                    }
    return index


def _evaluation_context(configs: dict[str, dict[str, Any]], risk: dict[str, Any], mode: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "ingest": configs["ingest.yml"],
        "target": configs["experiment.yml"]["target"],
        "risk": risk,
    }


def _candidate_key(record: dict[str, Any] | None, target_metric: str) -> tuple[float, float]:
    if record is None:
        return (float("-inf"), float("-inf"))
    metrics = record.get("metrics", {})
    return (float(metrics.get(target_metric, 0.0)), float(metrics.get("net-profit", 0.0)))


def run_backtest(root: Path, experiment: str, mode: str, run_id: str | None, dry_run: bool = False) -> dict[str, Any]:
    prefix = "sim" if mode == "simulate" else "bt"
    resolved_run_id = run_id or make_run_id(prefix)
    if not is_run_id(resolved_run_id):
        return {
            "error": "invalid-name",
            "message": "run id must use bt-YYYYMMDD-HHMMSS or sim-YYYYMMDD-HHMMSS",
            "next": ["omit --run-id to generate one"],
        }
    base = experiment_dir(root, experiment)
    issues = validate_experiment_dir(base)
    if issues:
        return {"error": "invalid-artifact", "message": "experiment validation failed", "issues": issues_payload(issues)}

    configs = load_experiment(root, experiment)
    search_scope = configs["search-scope.yml"]
    risk = optional_config(base, "risk.yml", DEFAULT_RISK)
    provider = optional_config(base, "provider.yml", DEFAULT_PROVIDER)
    report_config = optional_config(base, "report.yml", DEFAULT_REPORT)
    resolved_limits = resolve_limits(search_scope)
    candidates = generate_candidates(search_scope, resolved_limits)
    candles = load_history_candles(base, configs["ingest.yml"]) or default_candles()
    tested: list[dict[str, Any]] = []
    round_records: list[dict[str, Any]] = []
    reflection_records: list[dict[str, Any]] = []
    winning_candidate = None
    target = configs["experiment.yml"]["target"]
    target_metric = str(target["metric"])
    detail_result: dict[str, Any] | None = None
    best_record: dict[str, Any] | None = None
    evaluation_context = _evaluation_context(configs, risk, mode)
    prior_index = _prior_evaluation_index(base)
    batch_size = max(1, int(resolved_limits.get("batch-size", len(candidates) or 1)))
    max_rounds = max(1, int(resolved_limits.get("max-rounds", 1)))
    stagnation_limit = max(1, int(resolved_limits.get("stagnation-rounds", 1)))
    stop_on_target = bool(configs["experiment.yml"].get("stop-on-target", True))
    search_state = "limits-exhausted"
    cursor = 0
    round_number = 0
    stagnant_rounds = 0
    stop = False
    while cursor < len(candidates) and round_number < max_rounds and not stop:
        round_number += 1
        batch = candidates[cursor : cursor + batch_size]
        cursor += len(batch)
        round_candidate_ids: list[str] = []
        round_start_key = _candidate_key(best_record, target_metric)
        for candidate in batch:
            candidate["evaluationFingerprint"] = evaluation_fingerprint(candidate, evaluation_context)
            round_candidate_ids.append(candidate["candidateId"])
            prior = prior_index.get(candidate["evaluationFingerprint"])
            if prior is not None:
                tested.append(
                    {
                        **candidate,
                        "status": "skipped-duplicate",
                        "classification": "skipped",
                        "reason": "duplicate-evaluation",
                        "priorCandidate": prior,
                        "metrics": {},
                        "riskState": {},
                    }
                )
                continue
            try:
                strategy = compile_candidate_strategy(candidate)
                result = run_m1_backtest(candles, strategy=strategy, risk_config=risk)
                classification, reason = classify_candidate(result["metrics"], target)
            except UnsupportedComponentError as exc:
                result = {"signals": [], "orders": [], "trades": [], "blocks": [], "equity": [], "metrics": calculate_trade_metrics([])}
                classification = "rejected"
                reason = f"unsupported-component:{exc.role}:{exc.component_type}"
            risk_state = result["equity"][-1] if result["equity"] else {}
            record = {
                **candidate,
                "status": "tested",
                "classification": classification,
                "reason": reason,
                "metrics": result["metrics"],
                "riskState": risk_state,
            }
            prior_index[candidate["evaluationFingerprint"]] = {
                "runId": resolved_run_id,
                "candidateId": record["candidateId"],
                "candidateFingerprint": record.get("candidateFingerprint"),
            }
            if classification == "winner":
                record["status"] = "target-hit"
                if winning_candidate is None:
                    winning_candidate = record["candidateId"]
                detail_result = result
            elif classification == "approved" and detail_result is None:
                detail_result = result
            tested.append(record)
            if _candidate_key(record, target_metric) > _candidate_key(best_record, target_metric):
                best_record = record
            if classification == "winner" and stop_on_target:
                search_state = "target-hit"
                stop = True
                break

        round_end_key = _candidate_key(best_record, target_metric)
        if round_end_key > round_start_key:
            stagnant_rounds = 0
        else:
            stagnant_rounds += 1
        round_records.append(
            {
                "round": round_number,
                "status": "completed",
                "candidateIds": round_candidate_ids,
                "winnerCandidate": winning_candidate,
                "bestCandidate": best_record.get("candidateId") if best_record else None,
                "stagnantRounds": stagnant_rounds,
            }
        )
        if not stop and stagnant_rounds >= stagnation_limit:
            search_state = "stagnation"
            stop = True
        elif not stop and round_number >= max_rounds and cursor < len(candidates):
            search_state = "max-rounds"
        elif not stop and cursor >= len(candidates):
            search_state = "limits-exhausted"
        reflection_records.append(
            {
                "round": round_number,
                "decision": search_state if stop or cursor >= len(candidates) or round_number >= max_rounds else "continue",
                "summary": f"batch completed with {len(round_candidate_ids)} candidate(s); best={best_record.get('candidateId') if best_record else None}",
                "scoreboard": "scoreboard.json",
            }
        )
    final_metrics = dict(best_record["metrics"]) if best_record else calculate_trade_metrics([])
    final_metrics["winning-candidate"] = winning_candidate
    final_metrics["best-candidate"] = best_record.get("candidateId") if best_record else None
    final_metrics["skipped-duplicates"] = sum(1 for candidate in tested if candidate.get("status") == "skipped-duplicate")
    run_dir = base / "runs" / resolved_run_id
    payload = {
        "experiment": experiment,
        "runId": resolved_run_id,
        "path": str(run_dir),
        "metrics": final_metrics,
        "searchState": search_state,
        "bestCandidate": best_record.get("candidateId") if best_record else None,
    }
    if dry_run:
        payload["plannedActions"] = ["persist resolved limits", "create run artifacts", "append candidate batches, round, and reflection records", "write scoreboard, metrics, and report"]
        return payload

    ensure_run_artifacts(
        run_dir,
        resolved_run_id,
        experiment,
        mode,
        {
            "experiment": configs["experiment.yml"],
            "ingest": configs["ingest.yml"],
            "search-scope": search_scope,
            "risk": risk,
            "provider": provider,
            "report": report_config,
        },
        {
            "resolvedLimits": resolved_limits,
            "candidateCount": len(candidates),
            "batchCount": len(round_records),
            "searchState": search_state,
        },
    )
    for candidate in tested:
        append_jsonl(run_dir / "candidates.jsonl", candidate)
    scoreboard = build_scoreboard(resolved_run_id, tested, target_metric)
    write_json(run_dir / "scoreboard.json", scoreboard)
    for record in round_records:
        append_jsonl(run_dir / "rounds.jsonl", record)
    for record in reflection_records:
        append_jsonl(run_dir / "reflections.jsonl", record)
    if detail_result is not None:
        for name in ("signals", "orders", "trades", "blocks", "equity"):
            for record in detail_result[name]:
                append_jsonl(run_dir / f"{name}.jsonl", record)
    manifest = load_json(run_dir / "manifest.json")
    manifest["searchState"] = search_state
    manifest["winnerCandidate"] = winning_candidate
    manifest["bestCandidate"] = best_record.get("candidateId") if best_record else None
    manifest["skippedDuplicates"] = final_metrics["skipped-duplicates"]
    write_json(run_dir / "manifest.json", manifest)
    report = (
        f"# Run {resolved_run_id}\n\n"
        f"- Experiment: `{experiment}`\n"
        f"- Winning candidate: `{winning_candidate}`\n"
        f"- Best candidate: `{final_metrics['best-candidate']}`\n"
        f"- Search state: `{search_state}`\n"
        f"- Win rate: {final_metrics['win-rate']:.4f}\n"
    )
    complete_run(run_dir, final_metrics, report)
    return payload


def list_runs(root: Path, experiment: str) -> dict[str, Any]:
    runs = experiment_dir(root, experiment) / "runs"
    return {"experiment": experiment, "runs": sorted(path.name for path in runs.iterdir() if path.is_dir()) if runs.exists() else []}


def show_run(root: Path, experiment: str, run_id: str) -> dict[str, Any]:
    run_dir = experiment_dir(root, experiment) / "runs" / run_id
    if not run_dir.exists():
        return {"error": "missing-artifact", "message": "run not found"}
    return {"experiment": experiment, "runId": run_id, "path": str(run_dir), "metrics": load_metrics(run_dir)}


def validate_run(root: Path, experiment: str, run_id: str) -> dict[str, Any]:
    issues = validate_run_dir(experiment_dir(root, experiment) / "runs" / run_id)
    if issues:
        return {"valid": False, "issues": issues_payload(issues)}
    return {"experiment": experiment, "runId": run_id, "valid": True}
