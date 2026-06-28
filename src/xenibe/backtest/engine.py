from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from xenibe.artifacts.store import append_jsonl, complete_run, ensure_run_artifacts
from xenibe.candles import Candle
from xenibe.execution import Order, Signal, Trade
from xenibe.metrics.summary import calculate_trade_metrics
from xenibe.risk import RiskManager

Strategy = Callable[[Sequence[Candle], int], Signal | dict[str, Any] | None]


def default_strategy(closed_candles: Sequence[Candle], decision_index: int) -> Signal | None:
    if not closed_candles:
        return None
    last = closed_candles[-1]
    if last.close > last.open:
        return Signal(side="call", reason="previous-candle-bullish")
    if last.close < last.open:
        return Signal(side="put", reason="previous-candle-bearish")
    return None


def normalize_signal(signal: Signal | dict[str, Any] | None) -> Signal | None:
    if signal is None:
        return None
    if isinstance(signal, Signal):
        return signal
    return Signal(side=str(signal["side"]).lower(), confidence=float(signal.get("confidence", 1.0)), reason=str(signal.get("reason", "strategy-signal")))


def settle_binary(side: str, candle: Candle, payout: float, stake: float, tie_policy: str = "refund") -> tuple[str, float]:
    direction = candle.direction()
    if direction == "tie":
        if tie_policy == "refund":
            return "REFUND", 0.0
        if tie_policy == "loss":
            return "LOSS", -stake
        if tie_policy == "win":
            return "WIN", stake * payout
        raise ValueError(f"unsupported tie policy: {tie_policy}")
    if side == direction:
        return "WIN", stake * payout
    return "LOSS", -stake


def run_m1_backtest(
    candles: Sequence[Candle],
    strategy: Strategy | None = None,
    risk_config: dict[str, Any] | None = None,
    payout: float = 0.8,
    decision_second: int = 0,
    tie_policy: str = "refund",
) -> dict[str, Any]:
    strategy = strategy or default_strategy
    risk = RiskManager(
        risk_config
        or {
            "stop-loss": 100.0,
            "stop-win": 150.0,
            "min-payout": 0.75,
            "balance": 1000.0,
            "stake": {"stop-loss-divisor": 10, "min": 1.0, "max": 25.0},
            "max-open-risk": 25.0,
            "soros": {"enabled": True, "levels": 2},
            "martingale": {"enabled": False, "max-steps": 0, "multiplier": 2.0},
        }
    )
    signals: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    equity: list[dict[str, Any]] = []

    for decision_index in range(1, max(len(candles) - 1, 1)):
        closed = tuple(candles[:decision_index])
        signal = normalize_signal(strategy(closed, decision_index))
        if signal is None:
            continue
        signals.append({"decisionIndex": decision_index, "visibleThroughIndex": decision_index - 1, **asdict(signal)})
        decision = risk.preflight(payout=payout, available_seconds=60 - decision_second)
        if not decision.approved:
            blocks.append({"decisionIndex": decision_index, "code": decision.code, "reason": decision.reason})
            continue
        order = Order(
            order_id=f"order-{len(orders) + 1:06d}",
            side=signal.side,
            stake=decision.stake,
            decision_index=decision_index,
            entry_index=decision_index + 1,
        )
        orders.append(
            {
                "orderId": order.order_id,
                "side": order.side,
                "stake": order.stake,
                "decisionIndex": order.decision_index,
                "entryIndex": order.entry_index,
            }
        )
        result, profit = settle_binary(signal.side, candles[order.entry_index], payout, order.stake, tie_policy)
        risk_state = risk.settle(result, order.stake, profit)
        trade = Trade(
            order_id=order.order_id,
            side=order.side,
            stake=order.stake,
            payout=payout,
            result=result,
            profit=profit,
            entry_index=order.entry_index,
            settle_index=order.entry_index,
        )
        trades.append(
            {
                "orderId": trade.order_id,
                "side": trade.side,
                "stake": trade.stake,
                "payout": trade.payout,
                "result": trade.result,
                "profit": trade.profit,
                "entryIndex": trade.entry_index,
                "settleIndex": trade.settle_index,
            }
        )
        equity.append({"settleIndex": trade.settle_index, **risk_state})

    metrics = calculate_trade_metrics(trades)
    return {"signals": signals, "orders": orders, "trades": trades, "blocks": blocks, "equity": equity, "metrics": metrics}


def persist_backtest_run(
    run_dir: Path,
    run_id: str,
    experiment: str,
    snapshot: dict[str, Any],
    inputs: dict[str, Any],
    result: dict[str, Any],
) -> None:
    ensure_run_artifacts(run_dir, run_id, experiment, "backtest", snapshot, inputs)
    for name in ("signals", "orders", "trades", "blocks", "equity"):
        path = run_dir / f"{name}.jsonl"
        for record in result[name]:
            append_jsonl(path, record)
    report = "\n".join(
        [
            f"# Run {run_id}",
            "",
            f"- Experiment: `{experiment}`",
            f"- Total trades: {result['metrics']['total-trades']}",
            f"- Win rate: {result['metrics']['win-rate']:.4f}",
            f"- Net profit: {result['metrics']['net-profit']:.2f}",
            "",
        ]
    )
    complete_run(run_dir, result["metrics"], report)
