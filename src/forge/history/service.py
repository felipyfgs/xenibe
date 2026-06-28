from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from xenibe.artifacts.store import experiment_dir, utc_now
from xenibe.provider import ProviderError

from forge.common import normalize_record, safe_provider_message
from forge.context import CommandContext


def _history_path(root: Path, experiment: str, asset: str, timeframe: str, start: str, end: str) -> Path:
    safe_asset = asset.replace("/", "-")
    safe_start = start.replace(":", "").replace("/", "-")
    safe_end = end.replace(":", "").replace("/", "-")
    return experiment_dir(root, experiment) / "data" / f"{safe_asset}_{timeframe}_{safe_start}_{safe_end}.csv"


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = ["time", "asset", "timeframe", "open", "high", "low", "close"]
    extras = sorted({key for record in records for key in record} - set(ordered))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*ordered, *extras])
        writer.writeheader()
        for record in records:
            writer.writerow(record)


def download(context: CommandContext, experiment: str, asset: str, timeframe: str, start: str, end: str) -> dict[str, Any]:
    base = experiment_dir(context.root, experiment)
    if not base.exists():
        return {"error": "missing-artifact", "message": "experiment not found"}
    path = _history_path(context.root, experiment, asset, timeframe, start, end)
    if context.dry_run:
        return {
            "experiment": experiment,
            "asset": asset,
            "timeframe": timeframe,
            "from": start,
            "to": end,
            "path": str(path),
            "provider": "ebinex",
            "mode": "dry-run",
            "candleCount": 0,
            "plannedActions": ["fetch provider candles", "write normalized history artifact"],
        }
    try:
        provider = context.provider()
        candles = provider.historical_candles(asset, timeframe, start, end)
    except ProviderError as exc:
        return {"error": exc.code if exc.code.startswith("provider-") else "provider-error", "message": safe_provider_message(exc)}
    except Exception as exc:
        return {"error": "provider-error", "message": safe_provider_message(exc)}
    provider_name = str(getattr(provider, "name", "ebinex"))
    mode = str(getattr(provider, "mode", "live"))
    normalized = [normalize_record(candle) for candle in candles or []]
    payload = {
        "experiment": experiment,
        "asset": asset,
        "timeframe": timeframe,
        "from": start,
        "to": end,
        "provider": provider_name,
        "mode": mode,
        "downloadedAt": utc_now(),
        "candleCount": len(normalized),
    }
    _write_csv(path, normalized)
    return payload | {"path": str(path)}
