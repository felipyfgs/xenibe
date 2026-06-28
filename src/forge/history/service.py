from __future__ import annotations

from pathlib import Path
from typing import Any

from xenibe.artifacts.store import utc_now, write_json
from xenibe.provider import ProviderError

from forge.common import normalize_record, safe_provider_message
from forge.context import CommandContext


def _history_path(root: Path, asset: str, timeframe: str, start: str, end: str) -> Path:
    safe_asset = asset.replace("/", "-")
    safe_start = start.replace(":", "").replace("/", "-")
    safe_end = end.replace(":", "").replace("/", "-")
    return root / "assets" / "history" / safe_asset / timeframe / f"{safe_start}_{safe_end}.json"


def download(context: CommandContext, asset: str, timeframe: str, start: str, end: str) -> dict[str, Any]:
    path = _history_path(context.root, asset, timeframe, start, end)
    if context.dry_run:
        return {
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
        "asset": asset,
        "timeframe": timeframe,
        "from": start,
        "to": end,
        "provider": provider_name,
        "mode": mode,
        "downloadedAt": utc_now(),
        "candleCount": len(normalized),
        "candles": normalized,
    }
    write_json(path, payload)
    return {key: value for key, value in payload.items() if key != "candles"} | {"path": str(path)}
