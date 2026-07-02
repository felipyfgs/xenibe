from __future__ import annotations

import unittest

from xenibe.backtest import run_m1_backtest
from xenibe.candles import Candle
from xenibe.execution import Signal
from xenibe.risk import RiskManager


def session_risk_config(**overrides):
    config = {
        "stop-loss": 15,
        "stop-win": 20,
        "min-payout": 0.75,
        "balance": 100,
        "stake": {"stop-loss-divisor": 3, "min": 1, "max": 100},
        "max-open-risk": 100,
        "soros": {"enabled": True, "levels": 1},
        "martingale": {"enabled": False, "max-steps": 0, "multiplier": 2},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key] = {**config[key], **value}
        else:
            config[key] = value
    return config


def candles_for_tests() -> list[Candle]:
    return [
        Candle("2026-01-01T00:00:00Z", 1.0, 1.2, 0.9, 1.1),
        Candle("2026-01-01T00:01:00Z", 1.1, 1.2, 1.0, 1.05),
        Candle("2026-01-01T00:02:00Z", 1.05, 1.3, 1.0, 1.2),
        Candle("2026-01-01T00:03:00Z", 1.2, 1.25, 1.0, 1.1),
    ]


class BacktestTests(unittest.TestCase):
    def test_strategy_receives_only_closed_candles(self) -> None:
        seen: list[tuple[int, int, str]] = []

        def strategy(closed, decision_index):
            seen.append((decision_index, len(closed), closed[-1].time))
            return Signal("call")

        run_m1_backtest(candles_for_tests(), strategy=strategy)

        self.assertEqual(seen[0], (1, 1, "2026-01-01T00:00:00Z"))
        self.assertEqual(seen[1], (2, 2, "2026-01-01T00:01:00Z"))

    def test_order_enters_and_settles_on_next_candle(self) -> None:
        result = run_m1_backtest(candles_for_tests(), strategy=lambda _closed, _index: Signal("call"))

        self.assertEqual(result["signals"][0]["visibleThroughIndex"], 0)
        self.assertEqual(result["orders"][0]["submissionIndex"], 1)
        self.assertEqual(result["orders"][0]["decisionIndex"], 1)
        self.assertEqual(result["orders"][0]["contractIndex"], 2)
        self.assertEqual(result["orders"][0]["entryIndex"], 2)
        self.assertEqual(result["orders"][0]["entryPolicy"], "next-candle-open")
        self.assertEqual(result["orders"][0]["settlementPolicy"], "contract-candle-close")
        self.assertEqual(result["trades"][0]["contractIndex"], 2)
        self.assertEqual(result["trades"][0]["settleIndex"], 2)
        self.assertEqual(result["trades"][0]["settlementPolicy"], "contract-candle-close")
        self.assertEqual(result["trades"][0]["result"], "WIN")

    def test_cutoff_rejects_entry(self) -> None:
        result = run_m1_backtest(candles_for_tests(), strategy=lambda _closed, _index: Signal("call"), decision_second=55)

        self.assertEqual(result["orders"], [])
        self.assertEqual(result["blocks"][0]["code"], "cutoff-closed")
        self.assertEqual(result["metrics"]["blocked-signals"], 2)
        self.assertEqual(result["metrics"]["block-reason-counts"], {"cutoff-closed": 2})
        self.assertEqual(result["metrics"]["total-trades"], 0)
        self.assertEqual(result["metrics"]["total-sessions"], 0)

    def test_tie_defaults_to_refund(self) -> None:
        candles = [
            Candle("2026-01-01T00:00:00Z", 1.0, 1.1, 0.9, 1.05),
            Candle("2026-01-01T00:01:00Z", 1.05, 1.1, 1.0, 1.08),
            Candle("2026-01-01T00:02:00Z", 1.08, 1.2, 1.0, 1.08),
        ]

        result = run_m1_backtest(candles, strategy=lambda _closed, _index: Signal("call"))

        self.assertEqual(result["trades"][0]["result"], "REFUND")
        self.assertEqual(result["trades"][0]["profit"], 0.0)

    def test_session_starts_from_signal_and_calculates_percentage_stops_and_stake(self) -> None:
        manager = RiskManager(session_risk_config())

        decision = manager.preflight(payout=0.8)

        self.assertTrue(decision.approved)
        self.assertEqual(manager.state.session_id, 1)
        self.assertTrue(manager.state.session_active)
        self.assertEqual(manager.state.session_start_balance, 100)
        self.assertEqual(manager.state.session_stop_loss, 15)
        self.assertEqual(manager.state.session_stop_win, 20)
        self.assertEqual(manager.state.session_stake_divisor, 3)
        self.assertEqual(decision.stake, 5)

    def test_stake_divisor_defaults_to_three_when_missing(self) -> None:
        config = session_risk_config(stake={"min": 1, "max": 100})
        del config["stake"]["stop-loss-divisor"]
        manager = RiskManager(config)

        decision = manager.preflight(payout=0.8)

        self.assertTrue(decision.approved)
        self.assertEqual(decision.stake, 5)
        self.assertEqual(manager.state.session_stake_divisor, 3)

    def test_invalid_stake_divisor_is_rejected(self) -> None:
        manager = RiskManager(session_risk_config(stake={"stop-loss-divisor": 0}))

        decision = manager.preflight(payout=0.8)

        self.assertFalse(decision.approved)
        self.assertEqual(decision.code, "invalid-risk-config")

    def test_soros_n1_uses_base_plus_previous_profit_and_then_resets_after_win(self) -> None:
        manager = RiskManager(session_risk_config())
        base_decision = manager.preflight(payout=0.8)
        manager.settle("WIN", base_decision.stake, 4)

        self.assertTrue(manager.state.soros_pending)
        self.assertEqual(manager.next_stake(), 9)

        soros_decision = manager.preflight(payout=0.8)
        self.assertTrue(soros_decision.details["sorosActive"])
        manager.settle("WIN", soros_decision.stake, 7.2)

        self.assertFalse(manager.state.soros_pending)
        self.assertEqual(manager.next_stake(), 5)
        self.assertEqual(manager.state.soros_level, 0)

    def test_soros_n1_resets_after_loss_and_base_loss_returns_to_base_stake(self) -> None:
        manager = RiskManager(session_risk_config(martingale={"enabled": True, "max-steps": 3, "multiplier": 2}))
        first = manager.preflight(payout=0.8)
        manager.settle("LOSS", first.stake, -first.stake)

        self.assertFalse(manager.state.soros_pending)
        self.assertEqual(manager.next_stake(), 5)

        second = manager.preflight(payout=0.8)
        manager.settle("WIN", second.stake, 4)
        soros = manager.preflight(payout=0.8)
        manager.settle("LOSS", soros.stake, -soros.stake)

        self.assertFalse(manager.state.soros_pending)
        self.assertEqual(manager.next_stake(), 5)
        self.assertEqual(manager.state.martingale_step, 0)

    def test_session_resets_after_stop_loss_and_next_signal_starts_independent_session(self) -> None:
        manager = RiskManager(session_risk_config(soros={"enabled": False}))
        for _ in range(3):
            decision = manager.preflight(payout=0.8)
            state = manager.settle("LOSS", decision.stake, -decision.stake)

        self.assertTrue(state["sessionClosed"])
        self.assertEqual(state["sessionCloseReason"], "stop-loss-reached")
        self.assertEqual(state["sessionOutcome"], "lost")
        self.assertFalse(manager.state.session_active)
        self.assertEqual(manager.state.session_net_profit, 0)
        self.assertFalse(manager.state.soros_pending)

        next_decision = manager.preflight(payout=0.8)

        self.assertTrue(next_decision.approved)
        self.assertEqual(manager.state.session_id, 2)
        self.assertEqual(manager.state.session_start_balance, 85)
        self.assertAlmostEqual(next_decision.stake, 4.25)

    def test_session_resets_after_stop_win(self) -> None:
        manager = RiskManager(session_risk_config(**{"stop-win": 10}))
        base = manager.preflight(payout=0.8)
        manager.settle("WIN", base.stake, 4)
        soros = manager.preflight(payout=0.8)
        state = manager.settle("WIN", soros.stake, 7.2)

        self.assertTrue(state["sessionClosed"])
        self.assertEqual(state["sessionCloseReason"], "stop-win-reached")
        self.assertEqual(state["sessionOutcome"], "won")
        self.assertFalse(state["sorosPending"])
        self.assertFalse(manager.state.session_active)
        self.assertEqual(manager.state.session_net_profit, 0)
        self.assertAlmostEqual(manager.next_stake(), 5.56)

    def test_preflight_blocks_trade_that_could_exceed_session_stop_loss(self) -> None:
        manager = RiskManager(session_risk_config(soros={"enabled": False}))
        for profit in (-5, 4, -5, -5):
            decision = manager.preflight(payout=0.8)
            result = "WIN" if profit > 0 else "LOSS"
            manager.settle(result, decision.stake, profit)

        decision = manager.preflight(payout=0.8)

        self.assertFalse(decision.approved)
        self.assertEqual(decision.code, "stop-loss-risk-exceeded")
        self.assertTrue(manager.state.session_active)
        self.assertFalse(decision.details["sessionClosed"])
        self.assertIsNone(decision.details["sessionOutcome"])

    def test_blocked_first_signal_does_not_start_session(self) -> None:
        manager = RiskManager(session_risk_config(stake={"max": 1}))

        decision = manager.preflight(payout=0.8)

        self.assertFalse(decision.approved)
        self.assertEqual(decision.code, "stake-out-of-bounds")
        self.assertEqual(manager.state.session_id, 0)
        self.assertFalse(manager.state.session_active)

    def test_soros_and_martingale_state_clear_when_stop_boundaries_close_session(self) -> None:
        stop_win_manager = RiskManager(session_risk_config(**{"stop-win": 4}))
        win = stop_win_manager.preflight(payout=0.8)
        win_state = stop_win_manager.settle("WIN", win.stake, 4)

        self.assertTrue(win_state["sessionClosed"])
        self.assertEqual(win_state["sessionOutcome"], "won")
        self.assertFalse(win_state["sorosPending"])
        self.assertEqual(win_state["sorosLevel"], 0)
        self.assertEqual(win_state["sorosProfit"], 0.0)
        self.assertEqual(win_state["martingaleStep"], 0)
        self.assertFalse(stop_win_manager.state.soros_pending)

        stop_loss_manager = RiskManager(session_risk_config(soros={"enabled": False}, martingale={"enabled": True, "max-steps": 3}))
        for _ in range(3):
            loss = stop_loss_manager.preflight(payout=0.8)
            loss_state = stop_loss_manager.settle("LOSS", loss.stake, -loss.stake)

        self.assertTrue(loss_state["sessionClosed"])
        self.assertEqual(loss_state["sessionOutcome"], "lost")
        self.assertEqual(loss_state["martingaleStep"], 0)

        soros_loss_manager = RiskManager(session_risk_config())
        base_win = soros_loss_manager.preflight(payout=0.8)
        soros_loss_manager.settle("WIN", base_win.stake, 4)
        soros_loss = soros_loss_manager.preflight(payout=0.8)
        self.assertTrue(soros_loss.details["sorosActive"])
        soros_loss_manager.settle("LOSS", soros_loss.stake, -soros_loss.stake)
        for _ in range(2):
            loss = soros_loss_manager.preflight(payout=0.8)
            final_loss_state = soros_loss_manager.settle("LOSS", loss.stake, -loss.stake)

        self.assertTrue(final_loss_state["sessionClosed"])
        self.assertEqual(final_loss_state["sessionOutcome"], "lost")
        next_session = soros_loss_manager.preflight(payout=0.8)
        self.assertTrue(next_session.approved)
        self.assertEqual(soros_loss_manager.state.session_id, 2)
        self.assertFalse(next_session.details["sorosActive"])

    def test_backtest_session_soros_and_block_metrics_are_reported_separately(self) -> None:
        candles = [
            Candle("2026-01-01T00:00:00Z", 1.0, 1.1, 0.9, 1.0),
            Candle("2026-01-01T00:01:00Z", 1.0, 1.1, 0.9, 1.0),
            Candle("2026-01-01T00:02:00Z", 1.0, 1.2, 0.9, 1.1),
            Candle("2026-01-01T00:03:00Z", 1.0, 1.2, 0.9, 1.1),
            Candle("2026-01-01T00:04:00Z", 1.1, 1.2, 0.9, 1.0),
            Candle("2026-01-01T00:05:00Z", 1.1, 1.2, 0.9, 1.0),
            Candle("2026-01-01T00:06:00Z", 1.1, 1.2, 0.9, 1.0),
        ]

        result = run_m1_backtest(candles, strategy=lambda _closed, _index: Signal("call"), risk_config=session_risk_config(**{"stop-win": 10}))
        metrics = result["metrics"]

        self.assertEqual(metrics["total-trades"], 5)
        self.assertEqual(metrics["wins"], 2)
        self.assertEqual(metrics["losses"], 3)
        self.assertAlmostEqual(metrics["win-rate"], 0.4)
        self.assertEqual(metrics["total-sessions"], 2)
        self.assertEqual(metrics["closed-sessions"], 2)
        self.assertEqual(metrics["won-sessions"], 1)
        self.assertEqual(metrics["lost-sessions"], 1)
        self.assertEqual(metrics["open-sessions"], 0)
        self.assertAlmostEqual(metrics["session-win-rate"], 0.5)
        self.assertAlmostEqual(metrics["average-trades-per-closed-session"], 2.5)
        self.assertEqual(metrics["blocked-signals"], 0)
        self.assertEqual(metrics["block-reason-counts"], {})
        self.assertEqual(metrics["soros-trades"], 1)
        self.assertEqual(metrics["soros-wins"], 1)
        self.assertEqual(metrics["soros-losses"], 0)
        self.assertAlmostEqual(metrics["soros-net-profit"], 7.2)
        self.assertTrue(result["orders"][1]["sorosActive"])
        self.assertTrue(result["trades"][1]["sorosActive"])

    def test_open_session_is_reported_without_outcome(self) -> None:
        result = run_m1_backtest(candles_for_tests()[:3], strategy=lambda _closed, _index: Signal("call"), risk_config=session_risk_config())

        self.assertEqual(result["metrics"]["total-sessions"], 1)
        self.assertEqual(result["metrics"]["closed-sessions"], 0)
        self.assertEqual(result["metrics"]["won-sessions"], 0)
        self.assertEqual(result["metrics"]["lost-sessions"], 0)
        self.assertEqual(result["metrics"]["open-sessions"], 1)
        self.assertEqual(result["metrics"]["session-win-rate"], 0.0)

    def test_backtest_continues_after_session_close_and_waits_for_next_signal(self) -> None:
        candles = [
            Candle("2026-01-01T00:00:00Z", 1.0, 1.1, 0.9, 1.05),
            Candle("2026-01-01T00:01:00Z", 1.0, 1.1, 0.9, 1.05),
            Candle("2026-01-01T00:02:00Z", 1.0, 1.0, 0.8, 0.9),
            Candle("2026-01-01T00:03:00Z", 1.0, 1.0, 0.8, 0.9),
            Candle("2026-01-01T00:04:00Z", 1.0, 1.0, 0.8, 0.9),
            Candle("2026-01-01T00:05:00Z", 1.0, 1.1, 0.9, 1.05),
            Candle("2026-01-01T00:06:00Z", 1.0, 1.2, 0.9, 1.1),
        ]

        def strategy(_closed, decision_index):
            return Signal("call") if decision_index in {1, 2, 3, 5} else None

        result = run_m1_backtest(candles, strategy=strategy, risk_config=session_risk_config(soros={"enabled": False}))

        self.assertEqual([order["decisionIndex"] for order in result["orders"]], [1, 2, 3, 5])
        self.assertEqual([order["sessionId"] for order in result["orders"]], [1, 1, 1, 2])
        self.assertEqual(result["orders"][3]["stake"], 4.25)
        self.assertEqual(result["trades"][2]["sessionCloseReason"], "stop-loss-reached")


if __name__ == "__main__":
    unittest.main()
