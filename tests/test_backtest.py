from __future__ import annotations

import unittest

from xenibe.backtest import run_m1_backtest
from xenibe.candles import Candle
from xenibe.execution import Signal
from xenibe.risk import RiskManager


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

        self.assertEqual(result["orders"][0]["decisionIndex"], 1)
        self.assertEqual(result["orders"][0]["entryIndex"], 2)
        self.assertEqual(result["trades"][0]["settleIndex"], 2)
        self.assertEqual(result["trades"][0]["result"], "WIN")

    def test_cutoff_rejects_entry(self) -> None:
        result = run_m1_backtest(candles_for_tests(), strategy=lambda _closed, _index: Signal("call"), decision_second=55)

        self.assertEqual(result["orders"], [])
        self.assertEqual(result["blocks"][0]["code"], "cutoff-closed")

    def test_tie_defaults_to_refund(self) -> None:
        candles = [
            Candle("2026-01-01T00:00:00Z", 1.0, 1.1, 0.9, 1.05),
            Candle("2026-01-01T00:01:00Z", 1.05, 1.1, 1.0, 1.08),
            Candle("2026-01-01T00:02:00Z", 1.08, 1.2, 1.0, 1.08),
        ]

        result = run_m1_backtest(candles, strategy=lambda _closed, _index: Signal("call"))

        self.assertEqual(result["trades"][0]["result"], "REFUND")
        self.assertEqual(result["trades"][0]["profit"], 0.0)

    def test_soros_resets_after_loss_and_martingale_disabled_by_default(self) -> None:
        manager = RiskManager(
            {
                "stop-loss": 100,
                "stop-win": 150,
                "min-payout": 0.75,
                "balance": 1000,
                "stake": {"stop-loss-divisor": 10, "min": 1, "max": 25},
                "max-open-risk": 25,
                "soros": {"enabled": True, "levels": 2},
                "martingale": {"enabled": False, "max-steps": 0, "multiplier": 2},
            }
        )

        manager.settle("WIN", 10, 8)
        self.assertEqual(manager.state.soros_level, 1)
        manager.settle("LOSS", 10, -10)
        self.assertEqual(manager.state.soros_level, 0)
        self.assertEqual(manager.state.martingale_step, 0)


if __name__ == "__main__":
    unittest.main()
