from __future__ import annotations

from typing import Any

METRIC_TOTAL_TRADES = "total-trades"
METRIC_WINS = "wins"
METRIC_LOSSES = "losses"
METRIC_REFUNDS = "refunds"
METRIC_WIN_RATE = "win-rate"
METRIC_NET_PROFIT = "net-profit"
METRIC_MAX_DRAWDOWN = "max-drawdown"
METRIC_PROFIT_FACTOR = "profit-factor"
METRIC_EXPECTANCY = "expectancy"
METRIC_MAX_WIN_STREAK = "max-win-streak"
METRIC_MAX_LOSS_STREAK = "max-loss-streak"
METRIC_AVERAGE_TRADE_RETURN = "average-trade-return"
METRIC_AVERAGE_PAYOFF = "average-payoff"

PUBLIC_METRIC_NAMES = {
    METRIC_TOTAL_TRADES: "totalTrades",
    METRIC_WINS: "wins",
    METRIC_LOSSES: "losses",
    METRIC_REFUNDS: "refunds",
    METRIC_WIN_RATE: "winRate",
    METRIC_NET_PROFIT: "netProfit",
    METRIC_MAX_DRAWDOWN: "maxDrawdown",
    METRIC_PROFIT_FACTOR: "profitFactor",
    METRIC_EXPECTANCY: "expectancy",
    METRIC_MAX_WIN_STREAK: "maxWinStreak",
    METRIC_MAX_LOSS_STREAK: "maxLossStreak",
    METRIC_AVERAGE_TRADE_RETURN: "averageTradeReturn",
    METRIC_AVERAGE_PAYOFF: "averagePayoff",
}


def metrics_to_public(metrics: dict[str, Any], keys: tuple[str, ...] | None = None) -> dict[str, Any]:
    selected = keys or tuple(PUBLIC_METRIC_NAMES)
    return {PUBLIC_METRIC_NAMES[key]: metrics.get(key) for key in selected if key in PUBLIC_METRIC_NAMES}


def calculate_trade_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(trades)
    wins = sum(1 for trade in trades if trade.get("result") == "WIN")
    losses = sum(1 for trade in trades if trade.get("result") == "LOSS")
    refunds = sum(1 for trade in trades if trade.get("result") == "REFUND")
    profits = [float(trade.get("profit", 0.0)) for trade in trades]
    gross_profit = sum(profit for profit in profits if profit > 0)
    gross_loss = abs(sum(profit for profit in profits if profit < 0))
    net_profit = sum(profits)
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    current_win_streak = 0
    current_loss_streak = 0
    max_win_streak = 0
    max_loss_streak = 0
    for trade, profit in zip(trades, profits, strict=True):
        equity += profit
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
        result = trade.get("result")
        if result == "WIN":
            current_win_streak += 1
            current_loss_streak = 0
        elif result == "LOSS":
            current_loss_streak += 1
            current_win_streak = 0
        else:
            current_win_streak = 0
            current_loss_streak = 0
        max_win_streak = max(max_win_streak, current_win_streak)
        max_loss_streak = max(max_loss_streak, current_loss_streak)
    average_win = gross_profit / wins if wins else 0.0
    average_loss = gross_loss / losses if losses else 0.0
    return {
        METRIC_TOTAL_TRADES: total,
        METRIC_WINS: wins,
        METRIC_LOSSES: losses,
        METRIC_REFUNDS: refunds,
        METRIC_WIN_RATE: wins / total if total else 0.0,
        METRIC_NET_PROFIT: net_profit,
        METRIC_MAX_DRAWDOWN: max_drawdown,
        METRIC_PROFIT_FACTOR: gross_profit / gross_loss if gross_loss else (gross_profit if gross_profit else 0.0),
        METRIC_EXPECTANCY: net_profit / total if total else 0.0,
        METRIC_MAX_WIN_STREAK: max_win_streak,
        METRIC_MAX_LOSS_STREAK: max_loss_streak,
        METRIC_AVERAGE_TRADE_RETURN: net_profit / total if total else 0.0,
        METRIC_AVERAGE_PAYOFF: average_win / average_loss if average_loss else (average_win if average_win else 0.0),
    }


def summarize_trades(trades: list[dict[str, Any]]) -> dict[str, Any]:
    return metrics_to_public(calculate_trade_metrics(trades))
