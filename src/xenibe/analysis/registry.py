from __future__ import annotations

from collections.abc import Callable
from typing import Any

from xenibe.analysis.context import AnalysisContext
from xenibe.analysis.result import Evaluation, failed, passed, unavailable
from xenibe.candles import Candle
from xenibe.strategy.components import canonical_role


Evaluator = Callable[[AnalysisContext, dict[str, Any], str, str], Evaluation]


def _float(params: dict[str, Any], key: str, default: float) -> float:
    return float(params.get(key, default))


def _int(params: dict[str, Any], key: str, default: int) -> int:
    return int(params.get(key, default))


def _timeframe(params: dict[str, Any]) -> str:
    return str(params.get("timeframe", "M1"))


def _body(candle: Candle) -> float:
    return abs(float(candle.close) - float(candle.open))


def _total_range(candle: Candle) -> float:
    return max(float(candle.high) - float(candle.low), 0.0)


def _upper_wick(candle: Candle) -> float:
    return max(float(candle.high) - max(float(candle.open), float(candle.close)), 0.0)


def _lower_wick(candle: Candle) -> float:
    return max(min(float(candle.open), float(candle.close)) - float(candle.low), 0.0)


def _direction(candle: Candle) -> str | None:
    direction = candle.direction()
    return None if direction == "tie" else direction


def _require_last(ctx: AnalysisContext, role: str, component_type: str) -> Candle | Evaluation:
    if ctx.last is None:
        return unavailable(role, component_type, "no-closed-candles")
    return ctx.last


def _near(value: float, target: float, tolerance: float) -> bool:
    return abs(value - target) <= tolerance


def _recent(candles: tuple[Candle, ...], lookback: int) -> tuple[Candle, ...]:
    return candles[-lookback:] if len(candles) >= lookback else candles


def evaluate_trend(ctx: AnalysisContext, params: dict[str, Any], role: str, component_type: str) -> Evaluation:
    timeframe = _timeframe(params)
    fast_period = _int(params, "fast-period", 9)
    slow_period = _int(params, "slow-period", 21)
    min_adx = _float(params, "min-adx", 18.0)
    fast = ctx.ema(fast_period, timeframe)
    slow = ctx.ema(slow_period, timeframe)
    trend_adx = ctx.adx(14, timeframe)
    if not fast.available or not slow.available or not trend_adx.available:
        return unavailable(role, component_type, "trend-warmup", fast=fast.reason, slow=slow.reason, adx=trend_adx.reason)
    if float(trend_adx.value or 0.0) < min_adx:
        return failed(role, component_type, "adx-below-minimum", adx=trend_adx.value, minAdx=min_adx)
    if float(fast.value or 0.0) == float(slow.value or 0.0):
        return failed(role, component_type, "ema-flat", fast=fast.value, slow=slow.value)
    side = "call" if float(fast.value or 0.0) > float(slow.value or 0.0) else "put"
    return passed(role, component_type, "trend-confirmed", side=side, fast=fast.value, slow=slow.value, adx=trend_adx.value)


def evaluate_range(ctx: AnalysisContext, params: dict[str, Any], role: str, component_type: str) -> Evaluation:
    timeframe = _timeframe(params)
    max_adx = _float(params, "max-adx", 18.0)
    value = ctx.adx(14, timeframe)
    if not value.available:
        return unavailable(role, component_type, "range-warmup", adx=value.reason)
    if float(value.value or 0.0) <= max_adx:
        return passed(role, component_type, "range-confirmed", adx=value.value, maxAdx=max_adx)
    return failed(role, component_type, "adx-above-range", adx=value.value, maxAdx=max_adx)


def evaluate_atr_normalized(ctx: AnalysisContext, params: dict[str, Any], role: str, component_type: str) -> Evaluation:
    last = _require_last(ctx, role, component_type)
    if isinstance(last, Evaluation):
        return last
    period = _int(params, "period", 14)
    minimum = _float(params, "min-ratio", 0.0)
    maximum = _float(params, "max-ratio", 999.0)
    value = ctx.atr(period)
    if not value.available or not value.value:
        return unavailable(role, component_type, "atr-warmup", atr=value.reason)
    ratio = _total_range(last) / float(value.value)
    if minimum <= ratio <= maximum:
        return passed(role, component_type, "atr-ratio-accepted", ratio=ratio, atr=value.value)
    return failed(role, component_type, "atr-ratio-rejected", ratio=ratio, atr=value.value)


def evaluate_candle_anomaly(ctx: AnalysisContext, params: dict[str, Any], role: str, component_type: str) -> Evaluation:
    last = _require_last(ctx, role, component_type)
    if isinstance(last, Evaluation):
        return last
    lookback = _int(params, "lookback", 20)
    maximum = _float(params, "max-body-ratio", 2.5)
    candles = _recent(tuple(ctx.candles), lookback)
    if len(candles) < 2:
        return unavailable(role, component_type, "anomaly-warmup")
    average_body = sum(_body(candle) for candle in candles[:-1]) / max(len(candles) - 1, 1)
    ratio = _body(last) / average_body if average_body else 0.0
    if ratio <= maximum:
        return passed(role, component_type, "candle-size-accepted", ratio=ratio)
    return failed(role, component_type, "candle-size-anomaly", ratio=ratio)


def evaluate_support_resistance(ctx: AnalysisContext, params: dict[str, Any], role: str, component_type: str) -> Evaluation:
    last = _require_last(ctx, role, component_type)
    if isinstance(last, Evaluation):
        return last
    lookback = _int(params, "lookback", 50)
    tolerance_atr = _float(params, "tolerance-atr", 0.25)
    candles = _recent(tuple(ctx.candles), lookback)
    value = ctx.atr(14)
    if not value.available or not value.value:
        return unavailable(role, component_type, "sr-atr-warmup", atr=value.reason)
    support = min(candle.low for candle in candles)
    resistance = max(candle.high for candle in candles)
    tolerance = float(value.value) * tolerance_atr
    if _near(float(last.close), float(support), tolerance):
        return passed(role, component_type, "near-support", side="call", support=support, tolerance=tolerance)
    if _near(float(last.close), float(resistance), tolerance):
        return passed(role, component_type, "near-resistance", side="put", resistance=resistance, tolerance=tolerance)
    return failed(role, component_type, "away-from-sr", support=support, resistance=resistance, tolerance=tolerance)


def evaluate_pullback_to_ema(ctx: AnalysisContext, params: dict[str, Any], role: str, component_type: str) -> Evaluation:
    last = _require_last(ctx, role, component_type)
    if isinstance(last, Evaluation):
        return last
    period = _int(params, "ema-period", 21)
    tolerance_atr = _float(params, "tolerance-atr", 0.2)
    ema_value = ctx.ema(period)
    atr_value = ctx.atr(14)
    if not ema_value.available or not atr_value.available or not atr_value.value:
        return unavailable(role, component_type, "pullback-warmup", ema=ema_value.reason, atr=atr_value.reason)
    tolerance = float(atr_value.value) * tolerance_atr
    if _near(float(last.close), float(ema_value.value or 0.0), tolerance):
        side = "call" if float(last.close) >= float(ema_value.value or 0.0) else "put"
        return passed(role, component_type, "pullback-to-ema", side=side, ema=ema_value.value, tolerance=tolerance)
    return failed(role, component_type, "not-near-ema", ema=ema_value.value, tolerance=tolerance)


def evaluate_range_break_retest(ctx: AnalysisContext, params: dict[str, Any], role: str, component_type: str) -> Evaluation:
    last = _require_last(ctx, role, component_type)
    if isinstance(last, Evaluation):
        return last
    lookback = _int(params, "lookback", 30)
    tolerance_atr = _float(params, "retest-tolerance-atr", 0.3)
    candles = _recent(tuple(ctx.candles), lookback)
    if len(candles) < 3:
        return unavailable(role, component_type, "break-retest-warmup")
    atr_value = ctx.atr(14)
    if not atr_value.available or not atr_value.value:
        return unavailable(role, component_type, "break-retest-atr-warmup", atr=atr_value.reason)
    previous = candles[:-1]
    high = max(candle.high for candle in previous)
    low = min(candle.low for candle in previous)
    tolerance = float(atr_value.value) * tolerance_atr
    if float(last.close) > high and float(last.low) <= high + tolerance:
        return passed(role, component_type, "breakout-retest-call", side="call", level=high, tolerance=tolerance)
    if float(last.close) < low and float(last.high) >= low - tolerance:
        return passed(role, component_type, "breakout-retest-put", side="put", level=low, tolerance=tolerance)
    return failed(role, component_type, "no-break-retest", high=high, low=low, tolerance=tolerance)


def evaluate_trend_pullback(ctx: AnalysisContext, params: dict[str, Any], role: str, component_type: str) -> Evaluation:
    candles = tuple(ctx.candles)
    count = _int(params, "min-pullback-candles", 2)
    if len(candles) < max(22, count + 1):
        return unavailable(role, component_type, "trend-pullback-warmup")
    fast = ctx.ema(9)
    slow = ctx.ema(21)
    if not fast.available or not slow.available:
        return unavailable(role, component_type, "trend-pullback-ema-warmup")
    trend_side = "call" if float(fast.value or 0.0) > float(slow.value or 0.0) else "put"
    recent = candles[-count:]
    if trend_side == "call" and all(candle.close < candle.open for candle in recent):
        return passed(role, component_type, "uptrend-pullback", side="call")
    if trend_side == "put" and all(candle.close > candle.open for candle in recent):
        return passed(role, component_type, "downtrend-pullback", side="put")
    return failed(role, component_type, "pullback-not-confirmed", trendSide=trend_side)


def evaluate_breakout_retest(ctx: AnalysisContext, params: dict[str, Any], role: str, component_type: str) -> Evaluation:
    return evaluate_range_break_retest(ctx, {"lookback": 20, "retest-tolerance-atr": 0.5, **params}, role, component_type)


def evaluate_sr_reversal(ctx: AnalysisContext, params: dict[str, Any], role: str, component_type: str) -> Evaluation:
    last = _require_last(ctx, role, component_type)
    if isinstance(last, Evaluation):
        return last
    total = _total_range(last)
    if total == 0:
        return failed(role, component_type, "zero-range-candle")
    lower_ratio = _lower_wick(last) / total
    upper_ratio = _upper_wick(last) / total
    if lower_ratio >= 0.45 and last.close >= last.open:
        return passed(role, component_type, "support-rejection", side="call", lowerWickRatio=lower_ratio)
    if upper_ratio >= 0.45 and last.close <= last.open:
        return passed(role, component_type, "resistance-rejection", side="put", upperWickRatio=upper_ratio)
    return failed(role, component_type, "reversal-not-confirmed", lowerWickRatio=lower_ratio, upperWickRatio=upper_ratio)


def evaluate_engulfing(ctx: AnalysisContext, params: dict[str, Any], role: str, component_type: str) -> Evaluation:
    if ctx.previous is None or ctx.last is None:
        return unavailable(role, component_type, "engulfing-warmup")
    previous = ctx.previous
    last = ctx.last
    bullish = previous.close < previous.open and last.close > last.open and last.open <= previous.close and last.close >= previous.open
    bearish = previous.close > previous.open and last.close < last.open and last.open >= previous.close and last.close <= previous.open
    if bullish:
        return passed(role, component_type, "bullish-engulfing", side="call")
    if bearish:
        return passed(role, component_type, "bearish-engulfing", side="put")
    return failed(role, component_type, "engulfing-not-found")


def evaluate_pinbar(ctx: AnalysisContext, params: dict[str, Any], role: str, component_type: str) -> Evaluation:
    last = _require_last(ctx, role, component_type)
    if isinstance(last, Evaluation):
        return last
    minimum = _float(params, "min-wick-ratio", 0.55)
    total = _total_range(last)
    if total == 0:
        return failed(role, component_type, "zero-range-candle")
    lower_ratio = _lower_wick(last) / total
    upper_ratio = _upper_wick(last) / total
    if lower_ratio >= minimum and lower_ratio > upper_ratio:
        return passed(role, component_type, "bullish-pinbar", side="call", wickRatio=lower_ratio)
    if upper_ratio >= minimum and upper_ratio > lower_ratio:
        return passed(role, component_type, "bearish-pinbar", side="put", wickRatio=upper_ratio)
    return failed(role, component_type, "pinbar-not-found", lowerWickRatio=lower_ratio, upperWickRatio=upper_ratio)


def evaluate_momentum_close(ctx: AnalysisContext, params: dict[str, Any], role: str, component_type: str) -> Evaluation:
    last = _require_last(ctx, role, component_type)
    if isinstance(last, Evaluation):
        return last
    minimum = _float(params, "body-min-atr", 0.35)
    atr_value = ctx.atr(14)
    if not atr_value.available or not atr_value.value:
        return unavailable(role, component_type, "momentum-atr-warmup", atr=atr_value.reason)
    body_ratio = _body(last) / float(atr_value.value)
    direction = _direction(last)
    if body_ratio >= minimum and direction in {"call", "put"}:
        return passed(role, component_type, "momentum-close", side=direction, bodyRatio=body_ratio)
    return failed(role, component_type, "momentum-not-confirmed", direction=direction, bodyRatio=body_ratio)


def evaluate_mtf_alignment(ctx: AnalysisContext, params: dict[str, Any], role: str, component_type: str) -> Evaluation:
    entry = ctx.candles_for_timeframe(str(params.get("entry-timeframe", "M1")))
    confirm = ctx.candles_for_timeframe(str(params.get("confirm-timeframe", "M5")))
    if not entry or not confirm:
        return unavailable(role, component_type, "mtf-warmup")
    entry_side = _direction(entry[-1])
    confirm_side = _direction(confirm[-1])
    if entry_side and entry_side == confirm_side:
        return passed(role, component_type, "timeframes-aligned", side=entry_side)
    return failed(role, component_type, "timeframes-not-aligned", entrySide=entry_side, confirmSide=confirm_side)


def evaluate_rsi_zone(ctx: AnalysisContext, params: dict[str, Any], role: str, component_type: str) -> Evaluation:
    period = _int(params, "period", 14)
    call_min = _float(params, "call-min", 45.0)
    put_max = _float(params, "put-max", 55.0)
    value = ctx.rsi(period)
    if not value.available:
        return unavailable(role, component_type, "rsi-warmup", rsi=value.reason)
    rsi_value = float(value.value or 0.0)
    if rsi_value > 50.0 and rsi_value >= call_min:
        return passed(role, component_type, "rsi-call-zone", side="call", rsi=rsi_value)
    if rsi_value < 50.0 and rsi_value <= put_max:
        return passed(role, component_type, "rsi-put-zone", side="put", rsi=rsi_value)
    return failed(role, component_type, "rsi-neutral", rsi=rsi_value)


def evaluate_weighted_score(ctx: AnalysisContext, params: dict[str, Any], role: str, component_type: str) -> Evaluation:
    return passed(role, component_type, "weighted-score-rule", minScore=_float(params, "min-score", 1.0))


EVALUATORS: dict[tuple[str, str], Evaluator] = {
    ("regime", "trend"): evaluate_trend,
    ("regime", "range"): evaluate_range,
    ("volatility", "atr-normalized"): evaluate_atr_normalized,
    ("volatility", "candle-anomaly-filter"): evaluate_candle_anomaly,
    ("structure", "support-resistance-zone"): evaluate_support_resistance,
    ("structure", "pullback-to-ema"): evaluate_pullback_to_ema,
    ("structure", "range-break-retest"): evaluate_range_break_retest,
    ("setup", "trend-pullback"): evaluate_trend_pullback,
    ("setup", "breakout-retest"): evaluate_breakout_retest,
    ("setup", "sr-reversal"): evaluate_sr_reversal,
    ("trigger", "engulfing"): evaluate_engulfing,
    ("trigger", "pinbar-rejection"): evaluate_pinbar,
    ("trigger", "momentum-close"): evaluate_momentum_close,
    ("confirmation", "multi-timeframe-alignment"): evaluate_mtf_alignment,
    ("confirmation", "rsi-zone"): evaluate_rsi_zone,
    ("decision", "weighted-score"): evaluate_weighted_score,
}


def get_evaluator(role: str, component_type: str) -> Evaluator | None:
    return EVALUATORS.get((canonical_role(role), component_type))


def evaluate_component(ctx: AnalysisContext, component: dict[str, Any]) -> Evaluation:
    role = canonical_role(component.get("role", ""))
    component_type = str(component.get("type", ""))
    evaluator = get_evaluator(role, component_type)
    if evaluator is None:
        return unavailable(role, component_type, "unsupported-component")
    return evaluator(ctx, dict(component.get("parameters", {})), role, component_type)


def supported_component(role: str, component_type: str) -> bool:
    return (canonical_role(role), component_type) in EVALUATORS
