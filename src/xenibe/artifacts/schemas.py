from __future__ import annotations

from typing import Any

from xenibe.risk.defaults import DEFAULT_RISK
from xenibe.strategy.components import (
    CANONICAL_SEARCH_FLOW,
    COMPONENT_PARAMETER_RULES,
    COMPONENT_TYPE_REGISTRY,
    LOOP_LIMIT_DEFAULTS,
    LOOP_LIMIT_KEYS,
    REQUIRED_SEARCH_STAGES,
    ROLE_ALIASES,
    VALID_TIMEFRAMES,
    canonical_role,
)

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
    "horizons.jsonl",
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
    "stop-loss-risk-exceeded",
    "stop-win-reached",
    "invalid-risk-config",
    "canonical-history-conflict",
    "replace-required",
    "insufficient-primary-sample",
    "horizon-validation-failed",
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

DEFAULT_PROVIDER = {"name": "ebinex", "account": "demo"}

DEFAULT_REPORT = {"format": "markdown", "include": ["summary", "metrics", "winning-candidate"]}
