from __future__ import annotations

from typing import Any


def summarize_trades(trades: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(trades)
    wins = sum(1 for trade in trades if trade.get("result") == "WIN")
    losses = sum(1 for trade in trades if trade.get("result") == "LOSS")
    refunds = sum(1 for trade in trades if trade.get("result") == "REFUND")
    profit = sum(float(trade.get("profit", 0.0)) for trade in trades)
    return {
        "totalTrades": total,
        "wins": wins,
        "losses": losses,
        "refunds": refunds,
        "winRate": wins / total if total else 0.0,
        "netProfit": profit,
    }
