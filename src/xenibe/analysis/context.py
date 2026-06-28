from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from xenibe.analysis.adapter import DEFAULT_ADAPTER, IndicatorAdapter
from xenibe.analysis.result import IndicatorValue
from xenibe.candles import Candle


def timeframe_size(timeframe: str) -> int:
    normalized = timeframe.upper()
    if normalized == "M1":
        return 1
    if normalized.startswith("M") and normalized[1:].isdigit():
        return max(1, int(normalized[1:]))
    if normalized.startswith("H") and normalized[1:].isdigit():
        return max(1, int(normalized[1:]) * 60)
    return 1


@dataclass
class AnalysisContext:
    candles: Sequence[Candle]
    decision_index: int
    adapter: IndicatorAdapter = DEFAULT_ADAPTER
    _cache: dict[tuple[str, tuple[object, ...]], object] = field(default_factory=dict)

    @property
    def last(self) -> Candle | None:
        return self.candles[-1] if self.candles else None

    @property
    def previous(self) -> Candle | None:
        return self.candles[-2] if len(self.candles) >= 2 else None

    @property
    def closes(self) -> list[float]:
        return [float(candle.close) for candle in self.candles]

    @property
    def highs(self) -> list[float]:
        return [float(candle.high) for candle in self.candles]

    @property
    def lows(self) -> list[float]:
        return [float(candle.low) for candle in self.candles]

    def candles_for_timeframe(self, timeframe: str = "M1") -> tuple[Candle, ...]:
        size = timeframe_size(timeframe)
        if size <= 1:
            return tuple(self.candles)
        key = ("resample", (timeframe.upper(), len(self.candles)))
        if key in self._cache:
            return self._cache[key]  # type: ignore[return-value]
        completed = len(self.candles) // size
        resampled: list[Candle] = []
        for chunk_index in range(completed):
            chunk = self.candles[chunk_index * size : (chunk_index + 1) * size]
            resampled.append(
                Candle(
                    time=chunk[0].time,
                    open=chunk[0].open,
                    high=max(candle.high for candle in chunk),
                    low=min(candle.low for candle in chunk),
                    close=chunk[-1].close,
                )
            )
        result = tuple(resampled)
        self._cache[key] = result
        return result

    def sma(self, period: int, timeframe: str = "M1") -> IndicatorValue:
        candles = self.candles_for_timeframe(timeframe)
        return self.adapter.sma([candle.close for candle in candles], period)

    def ema(self, period: int, timeframe: str = "M1") -> IndicatorValue:
        candles = self.candles_for_timeframe(timeframe)
        return self.adapter.ema([candle.close for candle in candles], period)

    def rsi(self, period: int, timeframe: str = "M1") -> IndicatorValue:
        candles = self.candles_for_timeframe(timeframe)
        return self.adapter.rsi([candle.close for candle in candles], period)

    def atr(self, period: int, timeframe: str = "M1") -> IndicatorValue:
        return self.adapter.atr(self.candles_for_timeframe(timeframe), period)

    def adx(self, period: int, timeframe: str = "M1") -> IndicatorValue:
        return self.adapter.adx(self.candles_for_timeframe(timeframe), period)
