from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Signal:
    side: str
    confidence: float = 1.0
    reason: str = "strategy-signal"


@dataclass(frozen=True)
class Order:
    order_id: str
    side: str
    stake: float
    decision_index: int
    entry_index: int


@dataclass(frozen=True)
class Trade:
    order_id: str
    side: str
    stake: float
    payout: float
    result: str
    profit: float
    entry_index: int
    settle_index: int
