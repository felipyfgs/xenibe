from __future__ import annotations

from pathlib import Path
from typing import Any

from xenibe.artifacts.naming import is_run_id
from xenibe.artifacts.store import (
    append_jsonl,
    complete_run,
    ensure_run_artifacts,
    load_experiment,
    load_json,
    make_run_id,
    validate_experiment_dir,
    validate_run_dir,
    write_json,
)
from xenibe.backtest import run_m1_backtest
from xenibe.candles import Candle
from xenibe.strategy import build_scoreboard, classify_candidate, generate_candidates, resolve_limits

from forge.common import issues_payload, load_metrics


def default_candles() -> list[Candle]:
    return [
        Candle("2026-01-01T00:00:00Z", 1.0, 1.2, 0.9, 1.1),
        Candle("2026-01-01T00:01:00Z", 1.1, 1.2, 1.0, 1.0),
        Candle("2026-01-01T00:02:00Z", 1.0, 1.2, 0.9, 1.15),
        Candle("2026-01-01T00:03:00Z", 1.15, 1.16, 0.95, 1.0),
    ]


def run_backtest(root: Path, experiment: str, mode: str, run_id: str | None, dry_run: bool = False) -> dict[str, Any]:
    prefix = "sim" if mode == "simulate" else "bt"
    resolved_run_id = run_id or make_run_id(prefix)
    if not is_run_id(resolved_run_id):
        return {
            "error": "invalid-name",
            "message": "run id must use bt-YYYYMMDD-HHMMSS or sim-YYYYMMDD-HHMMSS",
            "next": ["omit --run-id to generate one"],
        }
    issues = validate_experiment_dir(root / experiment)
    if issues:
        return {"error": "invalid-artifact", "message": "experiment validation failed", "issues": issues_payload(issues)}

    configs = load_experiment(root, experiment)
    resolved_limits = resolve_limits(configs["searchscope.yml"])
    candidates = generate_candidates(configs["searchscope.yml"], resolved_limits)
    result = run_m1_backtest(default_candles(), risk_config=configs["risk.yml"])
    tested = []
    winning_candidate = None
    target = configs["experiment.yml"]["target"]
    risk_state = result["equity"][-1] if result["equity"] else {}
    for candidate in candidates:
        classification, reason = classify_candidate(result["metrics"], target)
        record = {
            **candidate,
            "status": "tested",
            "classification": classification,
            "reason": reason,
            "metrics": result["metrics"],
            "riskState": risk_state,
        }
        if classification == "winner":
            record["status"] = "target-hit"
            if winning_candidate is None:
                winning_candidate = record["candidateId"]
        tested.append(record)
        if classification == "winner":
            break
    result["metrics"]["winning-candidate"] = winning_candidate
    run_dir = root / experiment / "runs" / resolved_run_id
    payload = {"experiment": experiment, "runId": resolved_run_id, "path": str(run_dir), "metrics": result["metrics"]}
    if dry_run:
        payload["plannedActions"] = ["persist resolved limits", "create run artifacts", "append candidate, round, and reflection records", "write scoreboard, metrics, and report"]
        return payload

    ensure_run_artifacts(
        run_dir,
        resolved_run_id,
        experiment,
        mode,
        {
            "experiment": configs["experiment.yml"],
            "ingest": configs["ingest.yml"],
            "searchscope": configs["searchscope.yml"],
            "risk": configs["risk.yml"],
            "provider": configs["provider.yml"],
            "report": configs["report.yml"],
        },
        {"resolvedLimits": resolved_limits},
    )
    for candidate in tested:
        append_jsonl(run_dir / "candidates.jsonl", candidate)
    scoreboard = build_scoreboard(resolved_run_id, tested, str(target["metric"]))
    write_json(run_dir / "scoreboard.json", scoreboard)
    append_jsonl(
        run_dir / "rounds.jsonl",
        {
            "round": 1,
            "status": "completed",
            "candidateIds": [candidate["candidateId"] for candidate in tested],
            "winnerCandidate": winning_candidate,
        },
    )
    append_jsonl(
        run_dir / "reflections.jsonl",
        {
            "round": 1,
            "decision": "stop-target-hit" if winning_candidate else "limits-exhausted",
            "summary": "target metric satisfied" if winning_candidate else "resolved search limits exhausted without target hit",
            "scoreboard": "scoreboard.json",
        },
    )
    if any(candidate["classification"] in {"approved", "winner"} for candidate in tested):
        for name in ("signals", "orders", "trades", "blocks", "equity"):
            for record in result[name]:
                append_jsonl(run_dir / f"{name}.jsonl", record)
    manifest = load_json(run_dir / "manifest.json")
    manifest["searchState"] = "target-hit" if winning_candidate else "limits-exhausted"
    manifest["winnerCandidate"] = winning_candidate
    write_json(run_dir / "manifest.json", manifest)
    report = f"# Run {resolved_run_id}\n\n- Experiment: `{experiment}`\n- Winning candidate: `{winning_candidate}`\n- Win rate: {result['metrics']['win-rate']:.4f}\n"
    complete_run(run_dir, result["metrics"], report)
    return payload


def list_runs(root: Path, experiment: str) -> dict[str, Any]:
    runs = root / experiment / "runs"
    return {"experiment": experiment, "runs": sorted(path.name for path in runs.iterdir() if path.is_dir()) if runs.exists() else []}


def show_run(root: Path, experiment: str, run_id: str) -> dict[str, Any]:
    run_dir = root / experiment / "runs" / run_id
    if not run_dir.exists():
        return {"error": "missing-artifact", "message": "run not found"}
    return {"experiment": experiment, "runId": run_id, "path": str(run_dir), "metrics": load_metrics(run_dir)}


def validate_run(root: Path, experiment: str, run_id: str) -> dict[str, Any]:
    issues = validate_run_dir(root / experiment / "runs" / run_id)
    if issues:
        return {"valid": False, "issues": issues_payload(issues)}
    return {"experiment": experiment, "runId": run_id, "valid": True}
