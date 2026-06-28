from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Candle:
    time: str
    open: float
    high: float
    low: float
    close: float

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "Candle":
        return cls(
            time=str(data["time"]),
            open=float(data["open"]),
            high=float(data["high"]),
            low=float(data["low"]),
            close=float(data["close"]),
        )

    def direction(self) -> str:
        if self.close > self.open:
            return "call"
        if self.close < self.open:
            return "put"
        return "tie"
