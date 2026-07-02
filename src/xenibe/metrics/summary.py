from __future__ import annotations

from collections import Counter
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
METRIC_TOTAL_SESSIONS = "total-sessions"
METRIC_CLOSED_SESSIONS = "closed-sessions"
METRIC_WON_SESSIONS = "won-sessions"
METRIC_LOST_SESSIONS = "lost-sessions"
METRIC_OPEN_SESSIONS = "open-sessions"
METRIC_SESSION_WIN_RATE = "session-win-rate"
METRIC_AVERAGE_TRADES_PER_CLOSED_SESSION = "average-trades-per-closed-session"
METRIC_AVERAGE_NET_PROFIT_PER_CLOSED_SESSION = "average-net-profit-per-closed-session"
METRIC_BLOCKED_SIGNALS = "blocked-signals"
METRIC_BLOCK_REASON_COUNTS = "block-reason-counts"
METRIC_SOROS_TRADES = "soros-trades"
METRIC_SOROS_WINS = "soros-wins"
METRIC_SOROS_LOSSES = "soros-losses"
METRIC_SOROS_NET_PROFIT = "soros-net-profit"

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
    METRIC_TOTAL_SESSIONS: "totalSessions",
    METRIC_CLOSED_SESSIONS: "closedSessions",
    METRIC_WON_SESSIONS: "wonSessions",
    METRIC_LOST_SESSIONS: "lostSessions",
    METRIC_OPEN_SESSIONS: "openSessions",
    METRIC_SESSION_WIN_RATE: "sessionWinRate",
    METRIC_AVERAGE_TRADES_PER_CLOSED_SESSION: "averageTradesPerClosedSession",
    METRIC_AVERAGE_NET_PROFIT_PER_CLOSED_SESSION: "averageNetProfitPerClosedSession",
    METRIC_BLOCKED_SIGNALS: "blockedSignals",
    METRIC_BLOCK_REASON_COUNTS: "blockReasonCounts",
    METRIC_SOROS_TRADES: "sorosTrades",
    METRIC_SOROS_WINS: "sorosWins",
    METRIC_SOROS_LOSSES: "sorosLosses",
    METRIC_SOROS_NET_PROFIT: "sorosNetProfit",
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


def _session_id(record: dict[str, Any]) -> int | None:
    raw_value = record.get("sessionId")
    if raw_value in (None, "", 0, "0"):
        return None
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _session_outcome(record: dict[str, Any]) -> str | None:
    outcome = record.get("sessionOutcome")
    if outcome in {"won", "lost"}:
        return str(outcome)
    reason = str(record.get("sessionCloseReason") or "")
    if reason.startswith("stop-win"):
        return "won"
    if reason == "stop-loss-reached":
        return "lost"
    return None


def calculate_session_metrics(trades: list[dict[str, Any]], blocks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    blocks = blocks or []
    session_ids = {session_id for record in (*trades, *blocks) if (session_id := _session_id(record)) is not None}
    trade_counts = Counter(session_id for trade in trades if (session_id := _session_id(trade)) is not None)
    closed: dict[int, dict[str, Any]] = {}
    for trade in trades:
        session_id = _session_id(trade)
        if session_id is None or session_id in closed or not trade.get("sessionClosed"):
            continue
        outcome = _session_outcome(trade)
        if outcome is None:
            continue
        closed[session_id] = {"outcome": outcome, "netProfit": float(trade.get("sessionNetProfit", 0.0))}
    closed_sessions = len(closed)
    won_sessions = sum(1 for session in closed.values() if session["outcome"] == "won")
    lost_sessions = sum(1 for session in closed.values() if session["outcome"] == "lost")
    open_sessions = len(session_ids - set(closed))
    return {
        METRIC_TOTAL_SESSIONS: len(session_ids),
        METRIC_CLOSED_SESSIONS: closed_sessions,
        METRIC_WON_SESSIONS: won_sessions,
        METRIC_LOST_SESSIONS: lost_sessions,
        METRIC_OPEN_SESSIONS: open_sessions,
        METRIC_SESSION_WIN_RATE: won_sessions / closed_sessions if closed_sessions else 0.0,
        METRIC_AVERAGE_TRADES_PER_CLOSED_SESSION: sum(trade_counts[session_id] for session_id in closed) / closed_sessions if closed_sessions else 0.0,
        METRIC_AVERAGE_NET_PROFIT_PER_CLOSED_SESSION: sum(float(session["netProfit"]) for session in closed.values()) / closed_sessions if closed_sessions else 0.0,
    }


def calculate_block_metrics(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    reason_counts = Counter(str(block.get("code") or "unknown") for block in blocks)
    return {
        METRIC_BLOCKED_SIGNALS: len(blocks),
        METRIC_BLOCK_REASON_COUNTS: dict(sorted(reason_counts.items())),
    }


def calculate_soros_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    soros_trades = [trade for trade in trades if bool(trade.get("sorosActive"))]
    return {
        METRIC_SOROS_TRADES: len(soros_trades),
        METRIC_SOROS_WINS: sum(1 for trade in soros_trades if trade.get("result") == "WIN"),
        METRIC_SOROS_LOSSES: sum(1 for trade in soros_trades if trade.get("result") == "LOSS"),
        METRIC_SOROS_NET_PROFIT: sum(float(trade.get("profit", 0.0)) for trade in soros_trades),
    }


def calculate_backtest_metrics(trades: list[dict[str, Any]], blocks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    blocks = blocks or []
    return {
        **calculate_trade_metrics(trades),
        **calculate_session_metrics(trades, blocks),
        **calculate_block_metrics(blocks),
        **calculate_soros_metrics(trades),
    }


def summarize_trades(trades: list[dict[str, Any]]) -> dict[str, Any]:
    return metrics_to_public(calculate_trade_metrics(trades))
