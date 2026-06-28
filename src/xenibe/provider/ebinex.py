from __future__ import annotations

import importlib
from dataclasses import dataclass
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
    def __init__(self, client: Any | None = None) -> None:
        self.client = client or self._load_client()

    def _load_client(self) -> Any:
        try:
            module = importlib.import_module("pyebinex")
        except Exception as exc:
            raise ProviderError("provider-connection-failed", "pyebinex is not available") from exc
        if hasattr(module, "Ebinex"):
            return module.Ebinex()
        if hasattr(module, "Client"):
            return module.Client()
        raise ProviderError("provider-connection-failed", "pyebinex client class not found")

    def connection_status(self) -> dict[str, Any]:
        return self._call_first(("connection_status", "status", "is_connected"))

    def assets(self) -> Any:
        return self._call_first(("assets", "get_assets", "list_assets"))

    def payout(self, asset: str) -> Any:
        return self._call_first(("payout", "get_payout"), asset)

    def historical_candles(self, asset: str, timeframe: str, start: str, end: str) -> Any:
        return self._call_first(("historical_candles", "get_candles", "candles"), asset, timeframe, start, end)

    def place_order(self, asset: str, side: str, stake: float, duration: int = 60) -> Any:
        return self._call_first(("place_order", "buy", "order"), asset, side, stake, duration)

    def poll_result(self, order_id: str) -> Any:
        return self._call_first(("poll_result", "result", "check_result"), order_id)

    def order_history(self, **filters: Any) -> Any:
        return self._call_first(("order_history", "history", "orders"), **filters)

    def _call_first(self, names: tuple[str, ...], *args: Any, **kwargs: Any) -> Any:
        for name in names:
            method = getattr(self.client, name, None)
            if callable(method):
                try:
                    return method(*args, **kwargs)
                except Exception as exc:
                    raise normalize_provider_error(exc) from exc
        raise ProviderError("provider-connection-failed", f"client does not expose any of: {', '.join(names)}")
