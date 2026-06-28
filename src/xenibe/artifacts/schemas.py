from __future__ import annotations

EXPERIMENT_FILES = (
    "experiment.yml",
    "ingest.yml",
    "search-scope.yml",
)

RUN_ARTIFACTS = (
    "manifest.json",
    "config-snapshot.yml",
    "inputs.json",
    "candidates.jsonl",
    "scoreboard.json",
    "rounds.jsonl",
    "reflections.jsonl",
    "metrics.json",
    "report.md",
)

EXPERIMENT_REQUIRED_KEYS = {
    "experiment.yml": ("name", "hypothesis", "target", "stop-on-target"),
    "ingest.yml": ("data", "validation"),
    "search-scope.yml": ("schema-version", "flow", "components", "limits"),
}

RUN_JSON_REQUIRED_KEYS = {
    "manifest.json": ("runId", "experiment", "mode", "status", "createdAt"),
    "inputs.json": ("runId", "resolvedLimits"),
    "scoreboard.json": ("runId", "rankings", "components"),
    "metrics.json": ("runId", "status", "metrics"),
}

RUN_JSONL_FILES = (
    "candidates.jsonl",
    "rounds.jsonl",
    "reflections.jsonl",
)

DETAIL_JSONL_FILES = (
    "signals.jsonl",
    "orders.jsonl",
    "trades.jsonl",
    "blocks.jsonl",
    "equity.jsonl",
)

VALID_STATUS_CODES = {
    "ok",
    "created",
    "dry-run",
    "validated",
    "missing-command",
    "missing-name",
    "unknown-command",
    "missing-artifact",
    "invalid-artifact",
    "invalid-name",
    "invalid-json",
    "invalid-yaml",
    "invalid-jsonl",
    "immutable-run",
    "payout-below-minimum",
    "market-closed",
    "insufficient-balance",
    "stake-out-of-bounds",
    "stop-loss-reached",
    "stop-win-reached",
    "open-risk-exceeded",
    "cutoff-closed",
    "provider-connection-failed",
    "provider-unavailable",
    "provider-error",
    "provider-order-rejected",
    "provider-asset-closed",
    "provider-low-payout",
    "provider-settlement-timeout",
    "unexpected-error",
}

VALID_PROVIDERS = ("ebinex", "fixture", "mock")
VALID_TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1")
VALID_SOURCES = ("remote", "local")
VALID_FORMATS = ("csv",)
VALID_TARGET_METRICS = (
    "total-trades",
    "wins",
    "losses",
    "refunds",
    "win-rate",
    "net-profit",
    "max-drawdown",
    "profit-factor",
    "expectancy",
    "max-win-streak",
    "max-loss-streak",
    "average-trade-return",
    "average-payoff",
)
VALID_TARGET_OPERATORS = (">=", ">", "<=", "<", "=", "==")

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
    "context": {
        "session": {
            "name": {"allowed": ("london", "new-york", "tokyo", "sydney")},
        },
    },
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

DEFAULT_EXPERIMENT = {
    "name": "",
    "hypothesis": "Price action pattern can produce a measurable M1 edge.",
    "target": {"metric": "win-rate", "operator": ">=", "value": 0.6},
    "stop-on-target": True,
}

DEFAULT_INGEST = {
    "data": {
        "provider": "ebinex",
        "asset": "EURUSD",
        "timeframe": "M1",
        "from": "2026-01-01",
        "to": "2026-01-02",
        "source": "remote",
        "format": "csv",
        "path": "data",
    },
    "validation": {
        "require-complete-candles": True,
        "reject-gaps": True,
        "timezone": "UTC",
    },
}

DEFAULT_SEARCHSCOPE = {
    "schema-version": 1,
    "flow": list(CANONICAL_SEARCH_FLOW),
    "limits": {
        "max-candidates": "dynamic",
        "max-seconds": 60,
        "batch-size": 5,
        "max-rounds": "dynamic",
        "stagnation-rounds": "dynamic",
    },
    "components": {
        "context": [],
        "regime": [],
        "volatility": [],
        "structure": [],
        "setup": [],
        "trigger": [{"type": "momentum-close", "parameters": {"body-min-atr": [0.1], "side": ["call", "put"]}}],
        "confirmation": [],
        "decision": [{"type": "weighted-score", "parameters": {"min-score": [1.0], "entry": ["next-candle-open"], "expiration-candles": [1]}}],
    },
}

DEFAULT_RISK = {
    "stop-loss": 100.0,
    "stop-win": 150.0,
    "min-payout": 0.75,
    "balance": 1000.0,
    "stake": {"stop-loss-divisor": 10, "min": 1.0, "max": 25.0},
    "max-open-risk": 25.0,
    "soros": {"enabled": True, "levels": 2},
    "martingale": {"enabled": False, "max-steps": 0, "multiplier": 2.0},
}

DEFAULT_PROVIDER = {"name": "ebinex", "account": "demo"}

DEFAULT_REPORT = {"format": "markdown", "include": ["summary", "metrics", "winning-candidate"]}
