from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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


def ebinex_candle_expiry_execution(timeframe: str) -> dict[str, Any]:
    return {
        "executionModel": "ebinex-candle-expiry",
        "provider": "ebinex",
        "timeframe": timeframe,
        "historyPolicy": "closed-candles-before-submission-candle",
        "submission": {
            "candle": "current-timeframe-candle",
            "cutoff": {"policy": "before-candle-boundary", "secondsBeforeClose": 5},
        },
        "contract": {"candle": "next-timeframe-candle", "entry": "open"},
        "settlement": {"policy": "contract-candle-close", "candle": "contract-candle"},
    }
