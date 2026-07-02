from __future__ import annotations

from typing import Any

from xenibe.artifacts.store import utc_now

from forge.common import provider_error_payload, provider_metadata
from forge.context import CommandContext


def get_payout(context: CommandContext, asset: str) -> dict[str, Any]:
    if context.dry_run:
        return {"asset": asset, "payout": None, "provider": "ebinex", "freshness": "dry-run", "timestamp": utc_now(), "plannedActions": ["fetch provider payout"]}
    try:
        provider = context.provider()
        payout = provider.payout(asset)
    except Exception as exc:
        return provider_error_payload(exc)
    metadata = provider_metadata(provider)
    freshness = "unavailable" if payout is None else "live"
    return {"asset": asset, "payout": payout, **metadata, "freshness": freshness, "timestamp": utc_now()}
