from __future__ import annotations

import hashlib
import json
from itertools import product
from typing import Any

from xenibe.metrics.summary import METRIC_NET_PROFIT
from xenibe.strategy.components import CANONICAL_SEARCH_FLOW, LOOP_LIMIT_DEFAULTS, canonical_role


def resolve_limits(searchscope: dict[str, Any], default_max_candidates: int = 25) -> dict[str, Any]:
    limits = {**LOOP_LIMIT_DEFAULTS, **dict(searchscope.get("limits", {}))}
    dynamic_defaults = {**LOOP_LIMIT_DEFAULTS, "max-candidates": default_max_candidates}
    for key, value in list(limits.items()):
        if value == "dynamic":
            limits[key] = dynamic_defaults[key]
    return limits


def _fingerprint_payload(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint_value(value: Any) -> str:
    return hashlib.sha256(_fingerprint_payload(value).encode("utf-8")).hexdigest()


def normalized_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    stage_order = {stage: index for index, stage in enumerate(CANONICAL_SEARCH_FLOW)}
    components = sorted(
        candidate.get("components", []),
        key=lambda component: (
            stage_order.get(canonical_role(component.get("role")), len(stage_order)),
            str(component.get("type", "")),
            _fingerprint_payload(component.get("parameters", {})),
        ),
    )
    return {
        "flow": list(CANONICAL_SEARCH_FLOW),
        "components": [
            {
                "stage": canonical_role(component.get("role", "")),
                "type": str(component.get("type", "")),
                "parameters": component.get("parameters", {}),
            }
            for component in components
        ],
    }


def candidate_fingerprint(candidate: dict[str, Any]) -> str:
    return fingerprint_value(normalized_candidate(candidate))


def evaluation_fingerprint(candidate: dict[str, Any], context: dict[str, Any]) -> str:
    return fingerprint_value(
        {
            "candidateFingerprint": candidate.get("candidateFingerprint") or candidate_fingerprint(candidate),
            "context": context,
        }
    )


def generate_candidates(searchscope: dict[str, Any], limits: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    resolved = limits or resolve_limits(searchscope)
    max_candidates = int(resolved.get("max-candidates", 25))
    components = searchscope.get("components", {})
    groups: list[list[dict[str, Any]]] = []
    flow = searchscope.get("flow")
    stages = flow if isinstance(flow, list) else list(components)
    for role in stages:
        items = components.get(role, [])
        role_items = []
        for item in items:
            parameters = item.get("parameters", {})
            keys = list(parameters)
            values = [value if isinstance(value, list) else [value] for value in parameters.values()]
            combinations = [dict(zip(keys, values_item, strict=False)) for values_item in product(*values)] or [{}]
            for params in combinations:
                role_items.append({"role": role, "type": item.get("type", item.get("role", role)), "parameters": params})
        if role_items:
            groups.append(role_items)
    if not groups:
        return []
    candidates: list[dict[str, Any]] = []
    for index, combination in enumerate(product(*groups), start=1):
        candidate = {
            "candidateId": f"candidate-{index:06d}",
            "components": list(combination),
            "parameters": {item["role"]: item["parameters"] for item in combination},
            "status": "pending",
            "metrics": {},
        }
        candidate["candidateFingerprint"] = candidate_fingerprint(candidate)
        candidates.append(candidate)
        if len(candidates) >= max_candidates:
            break
    return candidates


def classify_candidate(metrics: dict[str, float], target: dict[str, Any]) -> tuple[str, str]:
    if target_satisfied(metrics, target):
        return "winner", "target-hit"
    if float(metrics.get(METRIC_NET_PROFIT, 0.0)) > 0:
        return "approved", "positive-net-profit"
    return "rejected", "target-not-hit"


def build_scoreboard(run_id: str, candidates: list[dict[str, Any]], target_metric: str) -> dict[str, Any]:
    candidates = [candidate for candidate in candidates if candidate.get("classification") != "skipped" and candidate.get("status") != "skipped-duplicate"]
    def ranking_key(candidate: dict[str, Any]) -> tuple[float, float, float, float]:
        horizon = candidate.get("horizonValidation")
        gate_rank = 0.0
        worst_horizon = float("-inf")
        if isinstance(horizon, dict):
            gate_rank = 1.0 if horizon.get("status") == "passed" else 0.0
            if horizon.get("worstHorizonTargetMetric") is not None:
                worst_horizon = float(horizon.get("worstHorizonTargetMetric", 0.0))
        return (
            gate_rank,
            float(candidate.get("metrics", {}).get(target_metric, 0.0)),
            float(candidate.get("metrics", {}).get(METRIC_NET_PROFIT, 0.0)),
            worst_horizon,
        )

    ranked = sorted(
        candidates,
        key=ranking_key,
        reverse=True,
    )
    candidate_rows = [
        {
            "rank": index,
            "candidateId": candidate["candidateId"],
            "classification": candidate.get("classification", "rejected"),
            "status": candidate.get("status", "tested"),
            "candidateFingerprint": candidate.get("candidateFingerprint"),
            "evaluationFingerprint": candidate.get("evaluationFingerprint"),
            "metrics": candidate.get("metrics", {}),
            "horizonValidation": candidate.get("horizonValidation"),
        }
        for index, candidate in enumerate(ranked, start=1)
    ]
    components: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in candidates:
        metrics = candidate.get("metrics", {})
        for component in candidate.get("components", []):
            key = (canonical_role(component.get("role", "unknown")), str(component.get("type", "unknown")))
            row = components.setdefault(
                key,
                {
                    "componentId": f"{key[0]}:{key[1]}",
                    "role": key[0],
                    "type": key[1],
                    "tested": 0,
                    "winners": 0,
                    "targetMetricTotal": 0.0,
                    "netProfitTotal": 0.0,
                },
            )
            row["tested"] += 1
            row["winners"] += 1 if candidate.get("classification") == "winner" else 0
            row["targetMetricTotal"] += float(metrics.get(target_metric, 0.0))
            row["netProfitTotal"] += float(metrics.get(METRIC_NET_PROFIT, 0.0))
    component_rows = []
    for row in components.values():
        tested = int(row["tested"])
        component_rows.append(
            {
                "componentId": row["componentId"],
                "role": row["role"],
                "type": row["type"],
                "tested": tested,
                "winners": row["winners"],
                "avgTargetMetric": row["targetMetricTotal"] / tested if tested else 0.0,
                "avgNetProfit": row["netProfitTotal"] / tested if tested else 0.0,
            }
        )
    component_rows.sort(key=lambda row: (float(row["avgTargetMetric"]), float(row["avgNetProfit"])), reverse=True)
    for rank, row in enumerate(component_rows, start=1):
        row["rank"] = rank
    return {
        "runId": run_id,
        "targetMetric": target_metric,
        "rankings": {"candidates": candidate_rows},
        "components": component_rows,
    }


def target_satisfied(metrics: dict[str, float], target: dict[str, Any]) -> bool:
    metric = str(target["metric"])
    if metric not in metrics:
        return False
    actual = float(metrics[metric])
    expected = float(target["value"])
    operator = target["operator"]
    if operator == ">=":
        return actual >= expected
    if operator == ">":
        return actual > expected
    if operator == "<=":
        return actual <= expected
    if operator == "<":
        return actual < expected
    if operator in {"=", "=="}:
        return actual == expected
    raise ValueError(f"unsupported target operator: {operator}")
