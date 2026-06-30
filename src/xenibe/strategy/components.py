from __future__ import annotations

from typing import Any


VALID_TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1")

CANONICAL_SEARCH_FLOW = (
    "context",
    "regime",
    "volatility",
    "structure",
    "setup",
    "trigger",
    "confirmation",
    "decision",
)

ROLE_ALIASES = {
    "regimes": "regime",
    "setups": "setup",
    "triggers": "trigger",
    "confirmations": "confirmation",
    "decision-rules": "decision",
}

REQUIRED_SEARCH_STAGES = ("trigger", "decision")
LOOP_LIMIT_DEFAULTS = {
    "max-candidates": 25,
    "max-seconds": 60,
    "batch-size": 5,
    "max-rounds": 5,
    "stagnation-rounds": 3,
}
LOOP_LIMIT_KEYS = tuple(LOOP_LIMIT_DEFAULTS)

COMPONENT_PARAMETER_RULES = {
    "context": {},
    "regime": {
        "trend": {
            "timeframe": {"allowed": VALID_TIMEFRAMES},
            "method": {"allowed": ("ema-slope",)},
            "fast-period": {"type": "positive-int"},
            "slow-period": {"type": "positive-int"},
            "min-adx": {"type": "nonnegative-number"},
        },
        "range": {
            "timeframe": {"allowed": VALID_TIMEFRAMES},
            "method": {"allowed": ("adx-compression",)},
            "max-adx": {"type": "nonnegative-number"},
        },
    },
    "volatility": {
        "atr-normalized": {
            "period": {"type": "positive-int"},
            "min-ratio": {"type": "nonnegative-number"},
            "max-ratio": {"type": "positive-number"},
        },
        "candle-anomaly-filter": {
            "lookback": {"type": "positive-int"},
            "max-body-ratio": {"type": "positive-number"},
        },
    },
    "structure": {
        "support-resistance-zone": {
            "lookback": {"type": "positive-int"},
            "tolerance-atr": {"type": "nonnegative-number"},
        },
        "pullback-to-ema": {
            "ema-period": {"type": "positive-int"},
            "tolerance-atr": {"type": "nonnegative-number"},
        },
        "range-break-retest": {
            "lookback": {"type": "positive-int"},
            "retest-tolerance-atr": {"type": "nonnegative-number"},
        },
    },
    "setup": {
        "trend-pullback": {
            "direction": {"allowed": ("with-trend",)},
            "min-pullback-candles": {"type": "positive-int"},
        },
        "breakout-retest": {
            "confirmation-close": {"type": "bool"},
        },
        "sr-reversal": {
            "rejection-required": {"type": "bool"},
        },
    },
    "trigger": {
        "engulfing": {
            "close-required": {"type": "bool"},
            "side": {"allowed": ("call", "put")},
        },
        "pinbar-rejection": {
            "min-wick-ratio": {"type": "nonnegative-number"},
            "side": {"allowed": ("call", "put")},
        },
        "momentum-close": {
            "body-min-atr": {"type": "nonnegative-number"},
            "side": {"allowed": ("call", "put")},
        },
    },
    "confirmation": {
        "multi-timeframe-alignment": {
            "entry-timeframe": {"allowed": VALID_TIMEFRAMES},
            "confirm-timeframe": {"allowed": VALID_TIMEFRAMES},
        },
        "rsi-zone": {
            "period": {"type": "positive-int"},
            "call-min": {"type": "number"},
            "put-max": {"type": "number"},
        },
    },
    "decision": {
        "weighted-score": {
            "min-score": {"type": "nonnegative-number"},
            "entry": {"allowed": ("next-candle-open",)},
            "expiration-candles": {"type": "positive-int"},
        },
    },
}

COMPONENT_TYPE_REGISTRY = {
    stage: tuple(sorted(component_rules))
    for stage, component_rules in COMPONENT_PARAMETER_RULES.items()
}


def canonical_role(role: Any) -> str:
    value = str(role)
    return ROLE_ALIASES.get(value, value)
