from __future__ import annotations

EXPERIMENT_FILES = (
    "experiment.yml",
    "ingest.yml",
    "searchscope.yml",
    "risk.yml",
    "provider.yml",
    "report.yml",
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
    "ingest.yml": ("provider", "asset", "timeframe", "from", "to"),
    "searchscope.yml": ("components", "limits"),
    "risk.yml": ("stop-loss", "stop-win", "min-payout", "balance", "stake", "soros", "martingale"),
    "provider.yml": ("name", "account"),
    "report.yml": ("format", "include"),
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

DEFAULT_EXPERIMENT = {
    "name": "",
    "hypothesis": "Price action pattern can produce a measurable M1 edge.",
    "target": {"metric": "win-rate", "operator": ">=", "value": 0.6},
    "stop-on-target": True,
}

DEFAULT_INGEST = {
    "provider": "ebinex",
    "asset": "EURUSD",
    "timeframe": "M1",
    "from": "2026-01-01",
    "to": "2026-01-02",
}

DEFAULT_SEARCHSCOPE = {
    "limits": {"max-candidates": "dynamic", "max-seconds": 60},
    "components": {
        "indicators": [{"type": "sma", "parameters": {"period": [3, 5]}}],
        "filters": [{"type": "trend", "parameters": {"direction": ["up", "down"]}}],
        "triggers": [{"type": "engulfing", "parameters": {"side": ["call", "put"]}}],
        "decision-rules": [{"type": "all-match", "parameters": {}}],
        "candle-patterns": [{"type": "pinbar", "parameters": {"body-ratio": [0.3]}}],
        "market-patterns": [{"type": "range-break", "parameters": {}}],
        "market-context": [{"type": "session", "parameters": {"name": ["london"]}}],
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
