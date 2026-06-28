from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from xenibe.analysis import AnalysisContext, Evaluation, evaluate_component, supported_component
from xenibe.candles import Candle
from xenibe.execution import Signal


class UnsupportedComponentError(ValueError):
    def __init__(self, role: str, component_type: str) -> None:
        super().__init__(f"unsupported-component:{role}:{component_type}")
        self.role = role
        self.component_type = component_type


def _decision_components(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    return [component for component in candidate.get("components", []) if component.get("role") in {"decision", "decision-rules"}]


def _analysis_components(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    return [component for component in candidate.get("components", []) if component.get("role") not in {"decision", "decision-rules"}]


def validate_supported(candidate: dict[str, Any]) -> None:
    for component in candidate.get("components", []):
        role = str(component.get("role", ""))
        component_type = str(component.get("type", ""))
        if not supported_component(role, component_type):
            raise UnsupportedComponentError(role, component_type)


def decision_parameters(candidate: dict[str, Any]) -> dict[str, Any]:
    for component in _decision_components(candidate):
        if component.get("type") == "weighted-score":
            return dict(component.get("parameters", {}))
    return {"min-score": 1.0}


def evaluate_candidate_decision(candidate: dict[str, Any], closed_candles: Sequence[Candle], decision_index: int) -> dict[str, Any]:
    validate_supported(candidate)
    ctx = AnalysisContext(tuple(closed_candles), decision_index)
    evaluations = [evaluate_component(ctx, component) for component in _analysis_components(candidate)]
    params = decision_parameters(candidate)
    minimum = float(params.get("min-score", 1.0))
    total = len(evaluations)
    passed_count = sum(1 for evaluation in evaluations if evaluation.passed)
    score = passed_count / total if total else 0.0
    side_votes = {evaluation.side for evaluation in evaluations if evaluation.passed and evaluation.side in {"call", "put"}}
    diagnostics = {
        "score": score,
        "minScore": minimum,
        "passed": passed_count,
        "total": total,
        "evaluations": [asdict(evaluation) for evaluation in evaluations],
    }
    if len(side_votes) > 1:
        return {"side": None, "confidence": score, "reason": "side-conflict", "diagnostics": diagnostics}
    if not side_votes:
        return {"side": None, "confidence": score, "reason": "no-side-vote", "diagnostics": diagnostics}
    if score < minimum:
        return {"side": None, "confidence": score, "reason": "score-below-threshold", "diagnostics": diagnostics}
    side = next(iter(side_votes))
    passed_reasons = [f"{evaluation.role}:{evaluation.type}:{evaluation.reason}" for evaluation in evaluations if evaluation.passed]
    reason = f"weighted-score:{score:.4f}:{'|'.join(passed_reasons[:6])}"
    return {"side": side, "confidence": score, "reason": reason, "diagnostics": diagnostics}


def compile_candidate_strategy(candidate: dict[str, Any]):
    validate_supported(candidate)

    def strategy(closed_candles: Sequence[Candle], decision_index: int) -> Signal | None:
        decision = evaluate_candidate_decision(candidate, closed_candles, decision_index)
        side = decision["side"]
        if side not in {"call", "put"}:
            return None
        return Signal(side=side, confidence=float(decision["confidence"]), reason=str(decision["reason"]))

    return strategy
