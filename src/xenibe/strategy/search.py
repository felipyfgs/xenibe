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
