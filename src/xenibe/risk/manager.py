from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


EPSILON = 1e-9
DEFAULT_STAKE_DIVISOR = 3.0


@dataclass
class RiskState:
    balance: float
    net_profit: float = 0.0
    open_risk: float = 0.0
    soros_level: int = 0
    soros_profit: float = 0.0
    martingale_step: int = 0
    session_id: int = 0
    session_active: bool = False
    session_start_balance: float = 0.0
    session_net_profit: float = 0.0
    session_stop_loss: float = 0.0
    session_stop_win: float = 0.0
    session_base_stake: float = 0.0
    session_stake_divisor: float = DEFAULT_STAKE_DIVISOR
    soros_pending: bool = False
    current_order_soros: bool = False
    session_closed: bool = False
    session_close_reason: str | None = None


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    stake: float
    code: str = "ok"
    reason: str = "approved"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskManager:
    config: dict[str, Any]
    state: RiskState = field(init=False)

    def __post_init__(self) -> None:
        self.state = RiskState(balance=float(self.config.get("balance", 0.0)))

    @property
    def base_stake(self) -> float:
        if self.state.session_active:
            return self.state.session_base_stake
        return self._calculate_session_base_stake(self.state.balance)

    def snapshot(
        self,
        *,
        session_active: bool | None = None,
        session_closed: bool | None = None,
        session_close_reason: str | None = None,
        soros_active: bool | None = None,
    ) -> dict[str, Any]:
        return {
            "balance": self.state.balance,
            "netProfit": self.state.net_profit,
            "openRisk": self.state.open_risk,
            "sessionId": self.state.session_id,
            "sessionActive": self.state.session_active if session_active is None else session_active,
            "sessionStartBalance": self.state.session_start_balance,
            "sessionNetProfit": self.state.session_net_profit,
            "sessionStopLoss": self.state.session_stop_loss,
            "sessionStopWin": self.state.session_stop_win,
            "sessionBaseStake": self.state.session_base_stake,
            "sessionStakeDivisor": self.state.session_stake_divisor,
            "sorosLevel": self.state.soros_level,
            "sorosPending": self.state.soros_pending,
            "sorosProfit": self.state.soros_profit,
            "sorosActive": self.state.current_order_soros if soros_active is None else soros_active,
            "martingaleStep": self.state.martingale_step,
            "sessionClosed": self.state.session_closed if session_closed is None else session_closed,
            "sessionCloseReason": self.state.session_close_reason if session_close_reason is None else session_close_reason,
        }

    def _positive_number(self, key: str, default: float | None = None) -> float:
        raw_value = self.config.get(key, default)
        value = float(raw_value)
        if value <= 0.0:
            raise ValueError(f"{key} must be greater than zero")
        return value

    def _stake_config(self) -> dict[str, Any]:
        stake_config = self.config.get("stake", {})
        return stake_config if isinstance(stake_config, dict) else {}

    def _stake_divisor(self) -> float:
        divisor = float(self._stake_config().get("stop-loss-divisor", DEFAULT_STAKE_DIVISOR))
        if divisor <= 0.0:
            raise ValueError("stake.stop-loss-divisor must be greater than zero")
        return divisor

    def _calculate_session_base_stake(self, balance: float) -> float:
        return (balance * self._positive_number("stop-loss") / 100.0) / self._stake_divisor()

    def _start_session(self) -> None:
        start_balance = self.state.balance
        stop_loss = start_balance * self._positive_number("stop-loss") / 100.0
        stop_win = start_balance * self._positive_number("stop-win") / 100.0
        divisor = self._stake_divisor()
        self.state.session_id += 1
        self.state.session_active = True
        self.state.session_start_balance = start_balance
        self.state.session_net_profit = 0.0
        self.state.session_stop_loss = stop_loss
        self.state.session_stop_win = stop_win
        self.state.session_base_stake = stop_loss / divisor
        self.state.session_stake_divisor = divisor
        self.state.soros_level = 0
        self.state.soros_profit = 0.0
        self.state.soros_pending = False
        self.state.current_order_soros = False
        self.state.martingale_step = 0
        self.state.session_closed = False
        self.state.session_close_reason = None

    def _reset_session(self, reason: str) -> None:
        self.state.session_active = False
        self.state.session_start_balance = 0.0
        self.state.session_net_profit = 0.0
        self.state.session_stop_loss = 0.0
        self.state.session_stop_win = 0.0
        self.state.session_base_stake = 0.0
        self.state.session_stake_divisor = DEFAULT_STAKE_DIVISOR
        self.state.soros_level = 0
        self.state.soros_profit = 0.0
        self.state.soros_pending = False
        self.state.current_order_soros = False
        self.state.martingale_step = 0
        self.state.session_closed = True
        self.state.session_close_reason = reason

    def _close_session_decision(self, code: str, reason: str) -> RiskDecision:
        details = self.snapshot(session_active=False, session_closed=True, session_close_reason=code)
        self._reset_session(code)
        return RiskDecision(False, 0.0, code, reason, details)

    def _ensure_session(self) -> RiskDecision | None:
        if self.state.session_active:
            return None
        try:
            self._start_session()
        except (TypeError, ValueError) as exc:
            return RiskDecision(False, 0.0, "invalid-risk-config", str(exc))
        return None

    def preflight(
        self,
        payout: float,
        market_open: bool = True,
        available_seconds: float = 60.0,
        requested_stake: float | None = None,
    ) -> RiskDecision:
        if payout < float(self.config.get("min-payout", 0.0)):
            return RiskDecision(False, 0.0, "payout-below-minimum", "payout below configured minimum")
        if not market_open:
            return RiskDecision(False, 0.0, "market-closed", "market is closed")
        if available_seconds <= 5:
            return RiskDecision(False, 0.0, "cutoff-closed", "entry cutoff closed")

        session_error = self._ensure_session()
        if session_error is not None:
            return session_error
        if self.state.session_net_profit <= -self.state.session_stop_loss + EPSILON:
            return self._close_session_decision("stop-loss-reached", "stop loss reached")
        if self.state.session_net_profit >= self.state.session_stop_win - EPSILON:
            return self._close_session_decision("stop-win-reached", "stop win reached")

        stake = self.next_stake()
        if requested_stake is not None and abs(requested_stake - stake) > EPSILON:
            return RiskDecision(False, 0.0, "stake-out-of-bounds", "requested stake does not match session stake")
        stake_config = self._stake_config()
        if stake < float(stake_config.get("min", 0.0)) or stake > float(stake_config.get("max", stake)):
            return RiskDecision(False, 0.0, "stake-out-of-bounds", "stake outside configured bounds")
        if self.state.balance < stake:
            return RiskDecision(False, 0.0, "insufficient-balance", "insufficient balance")
        max_open_risk = float(self.config.get("max-open-risk", stake))
        if self.state.open_risk + stake > max_open_risk:
            return RiskDecision(False, 0.0, "open-risk-exceeded", "open risk exceeded")
        if self.state.session_net_profit - stake < -self.state.session_stop_loss - EPSILON:
            return self._close_session_decision("stop-loss-risk-exceeded", "next stake could exceed session stop loss")

        expected_soros_stake = self.state.session_base_stake + self.state.soros_profit
        self.state.current_order_soros = (
            self.config.get("soros", {}).get("enabled", True)
            and self.state.soros_pending
            and abs(stake - expected_soros_stake) <= EPSILON
        )
        self.state.open_risk += stake
        return RiskDecision(True, stake, details=self.snapshot())

    def next_stake(self) -> float:
        base = self.base_stake
        soros = self.config.get("soros", {})
        if soros.get("enabled", True) and self.state.soros_pending:
            return base + self.state.soros_profit
        return base

    def settle(self, result: str, stake: float, profit: float) -> dict[str, Any]:
        self.state.net_profit += profit
        self.state.balance += profit
        self.state.open_risk = max(0.0, self.state.open_risk - stake)
        if not self.state.session_active:
            return self.snapshot()

        was_soros = self.state.current_order_soros or (
            self.state.soros_pending
            and abs(stake - (self.state.session_base_stake + self.state.soros_profit)) <= EPSILON
        )
        self.state.session_net_profit += profit
        soros = self.config.get("soros", {})
        if was_soros:
            self.state.soros_level = 0
            self.state.soros_profit = 0.0
            self.state.soros_pending = False
        elif result == "WIN":
            if soros.get("enabled", True):
                self.state.soros_level = 1
                self.state.soros_profit = max(profit, 0.0)
                self.state.soros_pending = True
            self.state.martingale_step = 0
        elif result == "LOSS":
            self.state.soros_level = 0
            self.state.soros_profit = 0.0
            self.state.soros_pending = False
            self.state.martingale_step = 0
        else:
            self.state.soros_level = 0
            self.state.soros_profit = 0.0
            self.state.soros_pending = False
        self.state.current_order_soros = False

        close_reason: str | None = None
        if self.state.session_net_profit <= -self.state.session_stop_loss + EPSILON:
            close_reason = "stop-loss-reached"
        elif self.state.session_net_profit >= self.state.session_stop_win - EPSILON:
            close_reason = "stop-win-reached"
        if close_reason is None:
            return self.snapshot(soros_active=was_soros)

        snapshot = self.snapshot(session_active=False, session_closed=True, session_close_reason=close_reason, soros_active=was_soros)
        self._reset_session(close_reason)
        return snapshot
