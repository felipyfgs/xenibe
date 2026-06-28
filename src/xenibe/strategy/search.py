from __future__ import annotations

from itertools import product
from typing import Any


def resolve_limits(searchscope: dict[str, Any], default_max_candidates: int = 25) -> dict[str, Any]:
    limits = dict(searchscope.get("limits", {}))
    if limits.get("max-candidates") == "dynamic":
        limits["max-candidates"] = default_max_candidates
    if limits.get("max-seconds") == "dynamic":
        limits["max-seconds"] = 60
    return limits


def generate_candidates(searchscope: dict[str, Any], limits: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    resolved = limits or resolve_limits(searchscope)
    max_candidates = int(resolved.get("max-candidates", 25))
    components = searchscope.get("components", {})
    groups: list[list[dict[str, Any]]] = []
    for role, items in components.items():
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
        candidates.append(
            {
                "candidateId": f"candidate-{index:06d}",
                "components": list(combination),
                "parameters": {item["role"]: item["parameters"] for item in combination},
                "status": "pending",
                "metrics": {},
            }
        )
        if len(candidates) >= max_candidates:
            break
    return candidates


def classify_candidate(metrics: dict[str, float], target: dict[str, Any]) -> tuple[str, str]:
    if target_satisfied(metrics, target):
        return "winner", "target-hit"
    if float(metrics.get("net-profit", 0.0)) > 0:
        return "approved", "positive-net-profit"
    return "rejected", "target-not-hit"


def build_scoreboard(run_id: str, candidates: list[dict[str, Any]], target_metric: str) -> dict[str, Any]:
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            float(candidate.get("metrics", {}).get(target_metric, 0.0)),
            float(candidate.get("metrics", {}).get("net-profit", 0.0)),
        ),
        reverse=True,
    )
    candidate_rows = [
        {
            "rank": index,
            "candidateId": candidate["candidateId"],
            "classification": candidate.get("classification", "rejected"),
            "status": candidate.get("status", "tested"),
            "metrics": candidate.get("metrics", {}),
        }
        for index, candidate in enumerate(ranked, start=1)
    ]
    components: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in candidates:
        metrics = candidate.get("metrics", {})
        for component in candidate.get("components", []):
            key = (str(component.get("role", "unknown")), str(component.get("type", "unknown")))
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
            row["netProfitTotal"] += float(metrics.get("net-profit", 0.0))
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
