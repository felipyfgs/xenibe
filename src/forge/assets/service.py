from __future__ import annotations

from typing import Any

from xenibe.artifacts.store import utc_now

from forge.common import normalize_record, provider_error_payload, provider_metadata
from forge.context import CommandContext


def list_assets(context: CommandContext) -> dict[str, Any]:
    if context.dry_run:
        return {"assets": [], "provider": "ebinex", "mode": "dry-run", "timestamp": utc_now(), "plannedActions": ["fetch provider assets"]}
    try:
        provider = context.provider()
        raw_assets = provider.assets()
    except Exception as exc:
        return provider_error_payload(exc)
    assets = [normalize_record(asset) for asset in raw_assets or []]
    return {"assets": assets, **provider_metadata(provider), "timestamp": utc_now()}
