from __future__ import annotations

from typing import Any

from xenibe.artifacts.store import utc_now
from xenibe.provider import ProviderError

from forge.common import safe_provider_message
from forge.context import CommandContext


def get_payout(context: CommandContext, asset: str) -> dict[str, Any]:
    if context.dry_run:
        return {"asset": asset, "payout": None, "provider": "ebinex", "freshness": "dry-run", "timestamp": utc_now(), "plannedActions": ["fetch provider payout"]}
    try:
        provider = context.provider()
        payout = provider.payout(asset)
    except ProviderError as exc:
        return {"error": exc.code if exc.code.startswith("provider-") else "provider-error", "message": safe_provider_message(exc)}
    except Exception as exc:
        return {"error": "provider-error", "message": safe_provider_message(exc)}
    provider_name = str(getattr(provider, "name", "ebinex"))
    mode = str(getattr(provider, "mode", "live"))
    freshness = "offline" if mode == "offline-contract" else ("unavailable" if payout is None else "live")
    return {"asset": asset, "payout": payout, "provider": provider_name, "freshness": freshness, "mode": mode, "timestamp": utc_now()}
