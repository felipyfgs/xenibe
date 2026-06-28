from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


Side = str | None


@dataclass(frozen=True)
class IndicatorValue:
    value: float | None
    available: bool
    reason: str = "ok"

    @classmethod
    def ok(cls, value: float) -> "IndicatorValue":
        return cls(float(value), True)

    @classmethod
    def unavailable(cls, reason: str) -> "IndicatorValue":
        return cls(None, False, reason)


@dataclass(frozen=True)
class Evaluation:
    role: str
    type: str
    passed: bool
    score: float
    reason: str
    side: Side = None
    available: bool = True
    diagnostics: dict[str, Any] = field(default_factory=dict)


def passed(role: str, component_type: str, reason: str, side: Side = None, score: float = 1.0, **diagnostics: Any) -> Evaluation:
    return Evaluation(role, component_type, True, score, reason, side=side, diagnostics=diagnostics)


def failed(role: str, component_type: str, reason: str, side: Side = None, **diagnostics: Any) -> Evaluation:
    return Evaluation(role, component_type, False, 0.0, reason, side=side, diagnostics=diagnostics)


def unavailable(role: str, component_type: str, reason: str, **diagnostics: Any) -> Evaluation:
    return Evaluation(role, component_type, False, 0.0, reason, available=False, diagnostics=diagnostics)
