from __future__ import annotations

from typing import Any

from xenibe.artifacts.store import utc_now
from xenibe.provider import ProviderError

from forge.common import normalize_record, safe_provider_message
from forge.context import CommandContext


def list_assets(context: CommandContext) -> dict[str, Any]:
    if context.dry_run:
        return {"assets": [], "provider": "ebinex", "mode": "dry-run", "timestamp": utc_now(), "plannedActions": ["fetch provider assets"]}
    try:
        provider = context.provider()
        raw_assets = provider.assets()
    except ProviderError as exc:
        return {"error": exc.code if exc.code.startswith("provider-") else "provider-error", "message": safe_provider_message(exc)}
    except Exception as exc:
        return {"error": "provider-error", "message": safe_provider_message(exc)}
    provider_name = str(getattr(provider, "name", "ebinex"))
    mode = str(getattr(provider, "mode", "live"))
    assets = [normalize_record(asset) for asset in raw_assets or []]
    return {"assets": assets, "provider": provider_name, "mode": mode, "timestamp": utc_now()}
