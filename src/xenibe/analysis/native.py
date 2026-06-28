from __future__ import annotations

from collections.abc import Sequence

from xenibe.analysis.result import IndicatorValue
from xenibe.candles import Candle


def _not_enough(required: int, actual: int) -> IndicatorValue:
    return IndicatorValue.unavailable(f"requires-{required}-values-have-{actual}")


def sma(values: Sequence[float], period: int) -> IndicatorValue:
    if period <= 0:
        return IndicatorValue.unavailable("period-must-be-positive")
    if len(values) < period:
        return _not_enough(period, len(values))
    return IndicatorValue.ok(sum(float(value) for value in values[-period:]) / period)


def ema(values: Sequence[float], period: int) -> IndicatorValue:
    if period <= 0:
        return IndicatorValue.unavailable("period-must-be-positive")
    if len(values) < period:
        return _not_enough(period, len(values))
    seed = sum(float(value) for value in values[:period]) / period
    multiplier = 2.0 / (period + 1.0)
    current = seed
    for value in values[period:]:
        current = (float(value) - current) * multiplier + current
    return IndicatorValue.ok(current)


def rsi(closes: Sequence[float], period: int) -> IndicatorValue:
    if period <= 0:
        return IndicatorValue.unavailable("period-must-be-positive")
    if len(closes) < period + 1:
        return _not_enough(period + 1, len(closes))
    gains = 0.0
    losses = 0.0
    window = [float(value) for value in closes[-(period + 1) :]]
    for previous, current in zip(window, window[1:]):
        change = current - previous
        if change >= 0:
            gains += change
        else:
            losses += abs(change)
    average_gain = gains / period
    average_loss = losses / period
    if average_loss == 0:
        return IndicatorValue.ok(100.0)
    relative_strength = average_gain / average_loss
    return IndicatorValue.ok(100.0 - (100.0 / (1.0 + relative_strength)))


def true_ranges(candles: Sequence[Candle]) -> list[float]:
    ranges: list[float] = []
    for index, candle in enumerate(candles):
        if index == 0:
            ranges.append(float(candle.high) - float(candle.low))
            continue
        previous_close = float(candles[index - 1].close)
        ranges.append(max(float(candle.high) - float(candle.low), abs(float(candle.high) - previous_close), abs(float(candle.low) - previous_close)))
    return ranges


def atr(candles: Sequence[Candle], period: int) -> IndicatorValue:
    if period <= 0:
        return IndicatorValue.unavailable("period-must-be-positive")
    if len(candles) < period + 1:
        return _not_enough(period + 1, len(candles))
    ranges = true_ranges(candles)
    return IndicatorValue.ok(sum(ranges[-period:]) / period)


def adx(candles: Sequence[Candle], period: int) -> IndicatorValue:
    if period <= 0:
        return IndicatorValue.unavailable("period-must-be-positive")
    if len(candles) < period + 1:
        return _not_enough(period + 1, len(candles))
    plus_dm = 0.0
    minus_dm = 0.0
    total_tr = 0.0
    window = candles[-(period + 1) :]
    ranges = true_ranges(window)
    for index in range(1, len(window)):
        current = window[index]
        previous = window[index - 1]
        up_move = float(current.high) - float(previous.high)
        down_move = float(previous.low) - float(current.low)
        plus_dm += up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm += down_move if down_move > up_move and down_move > 0 else 0.0
        total_tr += ranges[index]
    if total_tr == 0:
        return IndicatorValue.ok(0.0)
    plus_di = 100.0 * plus_dm / total_tr
    minus_di = 100.0 * minus_dm / total_tr
    denominator = plus_di + minus_di
    if denominator == 0:
        return IndicatorValue.ok(0.0)
    return IndicatorValue.ok(100.0 * abs(plus_di - minus_di) / denominator)
