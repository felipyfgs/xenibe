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
    SCENARIO_DERIVED_SIDE_TRIGGERS,
    VALID_TIMEFRAMES,
    canonical_role,
)

EXPERIMENT_FILES = (
    "experiment.yml",
    "ingest.yml",
    "search-scope.yml",
)

CANONICAL_CONTEXT_PATHS = {
    "promoted": "promoted",
    "archived": "archived",
    "experiment": "experiment",
}

COMPACT_RUN_ARTIFACTS = (
    "run.json",
    "records.jsonl",
    "report.md",
)

COMPACT_RECORD_KINDS = (
    "candidate",
    "round",
    "reflection",
    "signal",
    "order",
    "trade",
    "block",
    "equity",
    "horizon",
)

LEGACY_RUN_ARTIFACTS = (
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

RUN_ARTIFACTS = LEGACY_RUN_ARTIFACTS

EXPERIMENT_REQUIRED_KEYS = {
    "experiment.yml": ("name", "hypothesis", "target", "stop-on-target"),
    "ingest.yml": ("data", "validation"),
    "search-scope.yml": ("schema-version", "flow", "components", "limits"),
}

RUN_JSON_REQUIRED_KEYS = {
    "manifest.json": ("runId", "experiment", "mode", "subject", "status", "createdAt"),
    "inputs.json": ("runId", "subject", "resolvedLimits"),
    "scoreboard.json": ("runId", "rankings", "components"),
    "metrics.json": ("runId", "status", "metrics"),
}

COMPACT_RUN_JSON_REQUIRED_KEYS = (
    "runId",
    "experiment",
    "mode",
    "subject",
    "status",
    "createdAt",
    "completedAt",
    "configSnapshot",
    "inputs",
    "metrics",
    "scoreboard",
    "recordCounts",
)

RUN_FORMAT_MARKER_KEYS = (
    "schemaVersion",
    "schema-version",
    "formatVersion",
    "format-version",
)

RUN_JSONL_FILES = (
    "candidates.jsonl",
    "rounds.jsonl",
    "reflections.jsonl",
)

RUN_MODES = ("backtest", "simulate")
RUN_SUBJECT_VALUES = ("candidate-search", "promoted-robot")
RUN_STATUS_VALUES = ("running", "completed", "failed")
RUN_ID_MODE_PREFIXES = {"backtest": "bt", "simulate": "sim"}

PROMOTED_ROBOT_REQUIRED_SECTIONS = ("robot", "source", "strategy", "risk", "execution", "promotion")

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
    "provider-credentials-missing",
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
    "total-sessions",
    "closed-sessions",
    "won-sessions",
    "lost-sessions",
    "open-sessions",
    "session-win-rate",
    "average-trades-per-closed-session",
    "average-net-profit-per-closed-session",
    "blocked-signals",
    "soros-trades",
    "soros-wins",
    "soros-losses",
    "soros-net-profit",
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

DEFAULT_SEARCH_SCOPE = {
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
        "trigger": [{"type": "momentum-close", "parameters": {"body-min-atr": [0.1]}}],
        "confirmation": [],
        "decision": [{"type": "weighted-score", "parameters": {"min-score": [1.0], "entry": ["next-candle-open"]}}],
    },
}

DEFAULT_PROVIDER = {"name": "ebinex", "account": "demo"}

DEFAULT_REPORT = {"format": "markdown", "include": ["summary", "metrics", "winning-candidate"]}
