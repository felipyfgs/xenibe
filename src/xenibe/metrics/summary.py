from __future__ import annotations

from typing import Any


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
        "total-trades": total,
        "wins": wins,
        "losses": losses,
        "refunds": refunds,
        "win-rate": wins / total if total else 0.0,
        "net-profit": net_profit,
        "max-drawdown": max_drawdown,
        "profit-factor": gross_profit / gross_loss if gross_loss else (gross_profit if gross_profit else 0.0),
        "expectancy": net_profit / total if total else 0.0,
        "max-win-streak": max_win_streak,
        "max-loss-streak": max_loss_streak,
        "average-trade-return": net_profit / total if total else 0.0,
        "average-payoff": average_win / average_loss if average_loss else (average_win if average_win else 0.0),
    }


def summarize_trades(trades: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = calculate_trade_metrics(trades)
    return {
        "totalTrades": metrics["total-trades"],
        "wins": metrics["wins"],
        "losses": metrics["losses"],
        "refunds": metrics["refunds"],
        "winRate": metrics["win-rate"],
        "netProfit": metrics["net-profit"],
        "maxDrawdown": metrics["max-drawdown"],
        "profitFactor": metrics["profit-factor"],
        "expectancy": metrics["expectancy"],
        "maxWinStreak": metrics["max-win-streak"],
        "maxLossStreak": metrics["max-loss-streak"],
        "averageTradeReturn": metrics["average-trade-return"],
        "averagePayoff": metrics["average-payoff"],
    }
