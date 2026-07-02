from __future__ import annotations

from pathlib import Path
from typing import Any

from xenibe.artifacts.store import utc_now, write_yaml
from xenibe.metrics.summary import METRIC_NET_PROFIT, METRIC_TOTAL_TRADES, METRIC_WIN_RATE

from forge.common import select_metrics
from forge.run_consumer import completed_run


PROMOTION_METRICS = (METRIC_WIN_RATE, METRIC_NET_PROFIT, METRIC_TOTAL_TRADES, "winning-candidate")
SCORE_VERSION = "composite-v1"


def _as_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _robot_id(experiment: str, run_id: str) -> str:
    return f"{experiment}--{run_id}"


def _score_inputs(candidate: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    metrics = candidate.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    target_metric = str(target.get("metric", ""))
    horizon = candidate.get("horizonValidation")
    horizon_status = horizon.get("status") if isinstance(horizon, dict) else None
    return {
        "target-metric": target_metric,
        "target-metric-value": _as_number(metrics.get(target_metric)),
        "net-profit": _as_number(metrics.get(METRIC_NET_PROFIT)),
        "win-rate": _as_number(metrics.get(METRIC_WIN_RATE)),
        "total-trades": _as_number(metrics.get(METRIC_TOTAL_TRADES)),
        "horizon-status": horizon_status,
        "horizon-passed": horizon_status == "passed",
    }


def _score_from_inputs(inputs: dict[str, Any]) -> float:
    horizon_bonus = 10.0 if inputs.get("horizon-passed") else 0.0
    score = (
        _as_number(inputs.get("target-metric-value")) * 1000.0
        + _as_number(inputs.get("win-rate")) * 100.0
        + _as_number(inputs.get("net-profit"))
        + _as_number(inputs.get("total-trades")) * 0.1
        + horizon_bonus
    )
    return round(score, 6)


def _robot_contract(
    robot_id: str,
    experiment: str,
    run_id: str,
    candidate: dict[str, Any],
    loaded: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    directory = Path(loaded["directory"])
    config = loaded.get("configSnapshot", {})
    inputs = loaded.get("inputs", {})
    experiment_config = config.get("experiment", {}) if isinstance(config.get("experiment"), dict) else {}
    target = experiment_config.get("target", {}) if isinstance(experiment_config.get("target"), dict) else {}
    execution = inputs.get("execution", {}) if isinstance(inputs.get("execution"), dict) else {}
    history = inputs.get("history", {}) if isinstance(inputs.get("history"), dict) else {}
    score_inputs = _score_inputs(candidate, target)
    score = _score_from_inputs(score_inputs)
    selected_metrics = select_metrics(loaded["metrics"], PROMOTION_METRICS)
    candidate_metrics = candidate.get("metrics", {})
    if isinstance(candidate_metrics, dict):
        selected_metrics.update({key: candidate_metrics[key] for key in PROMOTION_METRICS if key in candidate_metrics})
    return {
        "schema-version": 1,
        "robot": {
            "id": robot_id,
            "score": score,
            "score-version": SCORE_VERSION,
            "score-inputs": score_inputs,
        },
        "source": {
            "experiment": experiment,
            "run-id": run_id,
            "candidate-id": candidate.get("candidateId"),
            "candidate-fingerprint": candidate.get("candidateFingerprint"),
            "evaluation-fingerprint": candidate.get("evaluationFingerprint"),
            "run-path": str(directory),
        },
        "strategy": {
            "components": candidate.get("components", []),
            "parameters": candidate.get("parameters", {}),
        },
        "risk": {
            "effective": config.get("risk", {}),
        },
        "execution": {
            "mode": loaded.get("manifest", {}).get("mode"),
            "subject": loaded.get("manifest", {}).get("subject"),
            "ingest": config.get("ingest", {}),
            "payout": execution.get("payout"),
            "payout-source": execution.get("payoutSource"),
            "data-source": history.get("dataSource"),
        },
        "promotion": {
            "timestamp": utc_now(),
            "reason": reason,
            "target": target,
            "metrics": selected_metrics,
            "horizon-validation": candidate.get("horizonValidation") or inputs.get("horizonValidation"),
        },
    }


def promote_run(root: Path, experiment: str, run_id: str, reason: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    loaded = completed_run(root, experiment, run_id)
    if "error" in loaded:
        loaded["message"] = "run must be valid before promotion"
        return loaded
    directory = Path(loaded["directory"])
    if loaded.get("duplicateOnly") or not loaded.get("promotionEligible"):
        artifact = "records.jsonl" if loaded.get("layout") == "compact" else "candidates.jsonl"
        return {
            "error": "invalid-artifact",
            "message": "run is audit-only or has no eligible winner candidate to promote",
            "issues": [
                {
                    "code": "invalid-artifact",
                    "path": str(directory / artifact),
                    "message": "duplicate-only runs and runs without a winner candidate cannot be promoted",
                    "target": str(directory / artifact),
                    "fix": "run a backtest that evaluates at least one non-duplicate winner candidate before promoting",
                }
            ],
        }
    winner = loaded.get("winnerCandidate")
    if winner is None:
        artifact = "records.jsonl" if loaded.get("layout") == "compact" else "candidates.jsonl"
        return {
            "error": "invalid-artifact",
            "message": "run has no valid winner candidate to promote",
            "issues": [
                {
                    "code": "invalid-artifact",
                    "path": str(directory / artifact),
                    "message": "expected one candidate with classification winner",
                    "target": str(directory / artifact),
                    "fix": "run a backtest that produces a winner candidate before promoting",
                }
            ],
        }
    resolved_reason = reason or "target metric satisfied"
    robot_id = _robot_id(experiment, run_id)
    target = root / "promoted" / robot_id
    path = target / "robot.yml"
    contract = _robot_contract(robot_id, experiment, run_id, winner, loaded, resolved_reason)
    payload: dict[str, Any] = {"experiment": experiment, "runId": run_id, "robotId": robot_id, "robot": str(path), "metadata": contract}
    if dry_run:
        payload["plannedActions"] = ["write promoted robot contract"]
        return payload
    if path.exists():
        return {
            "error": "invalid-artifact",
            "message": "promoted robot already exists",
            "issues": [
                {
                    "code": "invalid-artifact",
                    "path": str(path),
                    "message": "promoted robot contracts are immutable; create a new run before promoting again",
                    "target": str(path),
                    "fix": "create a new run-id and promote that run",
                }
            ],
        }
    write_yaml(path, contract)
    return payload
