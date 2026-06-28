from __future__ import annotations

import importlib.util
from collections.abc import Sequence

from xenibe.analysis import native
from xenibe.analysis.result import IndicatorValue
from xenibe.candles import Candle


SUPPORTED_LIBRARIES = ("talib", "ta", "pandas_ta")


def available_libraries() -> tuple[str, ...]:
    return tuple(name for name in SUPPORTED_LIBRARIES if importlib.util.find_spec(name) is not None)


class IndicatorAdapter:
    def __init__(self) -> None:
        self.libraries = available_libraries()

    def sma(self, values: Sequence[float], period: int) -> IndicatorValue:
        return native.sma(values, period)

    def ema(self, values: Sequence[float], period: int) -> IndicatorValue:
        return native.ema(values, period)

    def rsi(self, closes: Sequence[float], period: int) -> IndicatorValue:
        return native.rsi(closes, period)

    def atr(self, candles: Sequence[Candle], period: int) -> IndicatorValue:
        return native.atr(candles, period)

    def adx(self, candles: Sequence[Candle], period: int) -> IndicatorValue:
        return native.adx(candles, period)


DEFAULT_ADAPTER = IndicatorAdapter()
