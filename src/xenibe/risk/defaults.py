from __future__ import annotations

DEFAULT_RISK = {
    "stop-loss": 15.0,
    "stop-win": 20.0,
    "min-payout": 0.75,
    "balance": 1000.0,
    "stake": {"stop-loss-divisor": 3, "min": 1.0, "max": 100.0},
    "max-open-risk": 100.0,
    "soros": {"enabled": True, "levels": 1},
    "martingale": {"enabled": False, "max-steps": 0, "multiplier": 2.0},
}
