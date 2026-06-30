from __future__ import annotations

import asyncio
import importlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ProviderError(Exception):
    code: str
    message: str


def normalize_provider_error(exc: Exception) -> ProviderError:
    message = str(exc).lower()
    if "payout" in message:
        return ProviderError("provider-low-payout", str(exc))
    if "closed" in message or "asset" in message:
        return ProviderError("provider-asset-closed", str(exc))
    if "timeout" in message or "settlement" in message:
        return ProviderError("provider-settlement-timeout", str(exc))
    if "reject" in message or "order" in message:
        return ProviderError("provider-order-rejected", str(exc))
    return ProviderError("provider-connection-failed", str(exc))


class EbinexProvider:
    name = "ebinex"
    mode = "live"

    def __init__(self, client: Any | None = None, email: str | None = None, password: str | None = None, demo: bool = True) -> None:
        self.email = email or os.environ.get("EBINEX_EMAIL", "")
        self.password = password or os.environ.get("EBINEX_PASSWORD", "") or os.environ.get("EBINEX_PASS", "")
        self.demo = demo
        self.client = client

    def _load_client(self) -> Any:
        if self.client is not None:
            return self.client
        if not self.email or not self.password:
            raise ProviderError("provider-connection-failed", "Ebinex credentials are not configured")
        try:
            module = importlib.import_module("ebinex")
        except Exception as exc:
            raise ProviderError("provider-connection-failed", "ebinex dependency is not available") from exc
        client_class = getattr(module, "EbinexClient", None)
        if client_class is None:
            raise ProviderError("provider-connection-failed", "ebinex client class not found")
        return client_class(self.email, self.password, demo=self.demo)

    def _run(self, awaitable: Any) -> Any:
        try:
            return asyncio.run(awaitable)
        except ProviderError:
            raise
        except Exception as exc:
            raise normalize_provider_error(exc) from exc

    def _parse_timestamp(self, value: str) -> float:
        text = str(value)
        if "T" in text:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
        return datetime.fromisoformat(f"{text}T00:00:00+00:00").timestamp()

    async def _connected_call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        client = self._load_client()
        await client.connect()
        try:
            method = getattr(client, method_name)
            return await method(*args, **kwargs)
        finally:
            await client.disconnect()

    def connection_status(self) -> dict[str, Any]:
        client = self._load_client()
        return {"connected": bool(getattr(client, "is_connected", False)), "status": str(getattr(client, "connection_status", "unknown"))}

    def assets(self) -> Any:
        assets = self._run(self._connected_call("get_assets"))
        if isinstance(assets, dict):
            return [self._asset_payload(symbol, info) for symbol, info in assets.items()]
        return assets

    def payout(self, asset: str) -> Any:
        return self._run(self._connected_call("get_payout", asset))

    def historical_candles(self, asset: str, timeframe: str, start: str, end: str) -> Any:
        candles = self._run(
            self._connected_call(
                "get_candles_history",
                asset,
                timeframe=timeframe,
                start=self._parse_timestamp(start),
                end=self._parse_timestamp(end),
            )
        )
        return [self._candle_payload(asset, timeframe, candle) for candle in candles]

    def place_order(self, asset: str, side: str, stake: float, duration: int = 60) -> Any:
        return self._run(self._connected_call("buy", asset, side, stake, duration=duration))

    def poll_result(self, order_id: str) -> Any:
        return self._run(self._connected_call("check_win", order_id))

    def order_history(self, **filters: Any) -> Any:
        return self._run(self._connected_call("get_history", **filters))

    def _asset_payload(self, symbol: str, info: Any) -> dict[str, Any]:
        return {
            "id": symbol,
            "displayName": getattr(info, "display_name", symbol),
            "marketStatus": getattr(info, "market_status", None),
            "payout": getattr(info, "payout", None),
            "active": getattr(info, "is_active", None),
        }

    def _candle_payload(self, asset: str, timeframe: str, candle: Any) -> dict[str, Any]:
        open_time = getattr(candle, "open_time", None) or getattr(candle, "time", None)
        if hasattr(open_time, "astimezone"):
            time_value = open_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        else:
            time_value = str(open_time)
        return {
            "time": time_value,
            "asset": asset,
            "timeframe": timeframe,
            "open": getattr(candle, "open"),
            "high": getattr(candle, "high"),
            "low": getattr(candle, "low"),
            "close": getattr(candle, "close"),
            "volume": getattr(candle, "volume", ""),
        }
