from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RiskState:
    balance: float
    net_profit: float = 0.0
    open_risk: float = 0.0
    soros_level: int = 0
    soros_profit: float = 0.0
    martingale_step: int = 0


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    stake: float
    code: str = "ok"
    reason: str = "approved"


@dataclass
class RiskManager:
    config: dict[str, Any]
    state: RiskState = field(init=False)

    def __post_init__(self) -> None:
        self.state = RiskState(balance=float(self.config.get("balance", 0.0)))

    @property
    def base_stake(self) -> float:
        stake_config = self.config.get("stake", {})
        divisor = float(stake_config.get("stop-loss-divisor", 1) or 1)
        stake = float(self.config.get("stop-loss", 0.0)) / divisor
        minimum = float(stake_config.get("min", 0.0))
        maximum = float(stake_config.get("max", stake))
        return min(max(stake, minimum), maximum)

    def preflight(
        self,
        payout: float,
        market_open: bool = True,
        available_seconds: float = 60.0,
        requested_stake: float | None = None,
    ) -> RiskDecision:
        if self.state.net_profit <= -abs(float(self.config.get("stop-loss", 0.0))):
            return RiskDecision(False, 0.0, "stop-loss-reached", "stop loss reached")
        if self.state.net_profit >= abs(float(self.config.get("stop-win", 0.0))):
            return RiskDecision(False, 0.0, "stop-win-reached", "stop win reached")
        if payout < float(self.config.get("min-payout", 0.0)):
            return RiskDecision(False, 0.0, "payout-below-minimum", "payout below configured minimum")
        if not market_open:
            return RiskDecision(False, 0.0, "market-closed", "market is closed")
        if available_seconds <= 5:
            return RiskDecision(False, 0.0, "cutoff-closed", "entry cutoff closed")

        stake = requested_stake if requested_stake is not None else self.next_stake()
        stake_config = self.config.get("stake", {})
        if stake < float(stake_config.get("min", 0.0)) or stake > float(stake_config.get("max", stake)):
            return RiskDecision(False, 0.0, "stake-out-of-bounds", "stake outside configured bounds")
        if self.state.balance < stake:
            return RiskDecision(False, 0.0, "insufficient-balance", "insufficient balance")
        max_open_risk = float(self.config.get("max-open-risk", stake))
        if self.state.open_risk + stake > max_open_risk:
            return RiskDecision(False, 0.0, "open-risk-exceeded", "open risk exceeded")
        return RiskDecision(True, stake)

    def next_stake(self) -> float:
        base = self.base_stake
        soros = self.config.get("soros", {})
        if soros.get("enabled", True) and self.state.soros_level > 0:
            return min(base + self.state.soros_profit, float(self.config.get("stake", {}).get("max", base)))
        martingale = self.config.get("martingale", {})
        if martingale.get("enabled", False) and self.state.martingale_step > 0:
            return min(base * (float(martingale.get("multiplier", 2.0)) ** self.state.martingale_step), float(self.config.get("stake", {}).get("max", base)))
        return base

    def settle(self, result: str, stake: float, profit: float) -> dict[str, Any]:
        self.state.net_profit += profit
        self.state.balance += profit
        self.state.open_risk = max(0.0, self.state.open_risk - stake)
        soros = self.config.get("soros", {})
        martingale = self.config.get("martingale", {})
        if result == "WIN":
            if soros.get("enabled", True):
                self.state.soros_level = min(self.state.soros_level + 1, int(soros.get("levels", 1)))
                self.state.soros_profit += max(profit, 0.0)
            self.state.martingale_step = 0
        elif result == "LOSS":
            self.state.soros_level = 0
            self.state.soros_profit = 0.0
            if martingale.get("enabled", False):
                self.state.martingale_step = min(self.state.martingale_step + 1, int(martingale.get("max-steps", 0)))
            else:
                self.state.martingale_step = 0
        return {
            "balance": self.state.balance,
            "netProfit": self.state.net_profit,
            "sorosLevel": self.state.soros_level,
            "martingaleStep": self.state.martingale_step,
        }
