from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class OfflineProvider:
    name = "ebinex"
    mode = "offline-contract"

    def assets(self) -> list[dict[str, Any]]:
        return []

    def payout(self, _asset: str) -> None:
        return None

    def historical_candles(self, _asset: str, _timeframe: str, _start: str, _end: str) -> list[dict[str, Any]]:
        return []


ProviderFactory = Callable[[], Any]


@dataclass(frozen=True)
class CommandContext:
    root: Path
    as_json: bool = False
    dry_run: bool = False
    yes: bool = False
    no_color: bool = False
    provider_factory: ProviderFactory | None = None

    def provider(self) -> Any:
        if self.provider_factory is None:
            return OfflineProvider()
        return self.provider_factory()
