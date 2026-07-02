from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
            from xenibe.provider import EbinexProvider

            return EbinexProvider()
        return self.provider_factory()
