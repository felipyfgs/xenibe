from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from forge.run.service import run_backtest
from xenibe.analysis import AnalysisContext, evaluate_component
from xenibe.analysis import native
from xenibe.artifacts.store import write_yaml
from xenibe.candles import Candle
from xenibe.strategy import UnsupportedComponentError, compile_candidate_strategy, evaluate_candidate_decision


def candle(index: int, open_price: float, close_price: float, low: float | None = None, high: float | None = None) -> Candle:
    low_price = min(open_price, close_price) - 0.05 if low is None else low
    high_price = max(open_price, close_price) + 0.05 if high is None else high
    return Candle(f"2026-01-01T00:{index:02d}:00Z", open_price, high_price, low_price, close_price)


def bullish_candles(count: int) -> list[Candle]:
    return [candle(index, 1.0 + index * 0.01, 1.08 + index * 0.01) for index in range(count)]


class NativeIndicatorTests(unittest.TestCase):
    def test_native_indicators_return_expected_values_and_warmup(self) -> None:
        self.assertEqual(native.sma([1.0, 2.0, 3.0], 3).value, 2.0)
        self.assertAlmostEqual(native.ema([1.0, 2.0, 3.0], 2).value or 0.0, 2.5)
        self.assertFalse(native.sma([1.0], 3).available)
        self.assertEqual(native.rsi([1.0, 2.0, 3.0, 4.0], 3).value, 100.0)
        candles = bullish_candles(6)
        self.assertTrue(native.atr(candles, 3).available)
        self.assertTrue(native.adx(candles, 3).available)

    def test_context_resamples_only_complete_higher_timeframe_candles(self) -> None:
        candles = bullish_candles(7)
        resampled = AnalysisContext(candles, len(candles)).candles_for_timeframe("M5")

        self.assertEqual(len(resampled), 1)
        self.assertEqual(resampled[0].open, candles[0].open)
        self.assertEqual(resampled[0].close, candles[4].close)


class EvaluatorAndCompilerTests(unittest.TestCase):
    def test_evaluator_uses_only_closed_context_candles(self) -> None:
        closed = bullish_candles(15)
        future_pinbar = candle(16, 1.0, 1.02, low=0.1, high=1.04)
        component = {"role": "trigger", "type": "pinbar-rejection", "parameters": {"side": "call", "min-wick-ratio": 0.8}}

        closed_result = evaluate_component(AnalysisContext(closed, len(closed)), component)
        future_result = evaluate_component(AnalysisContext([*closed, future_pinbar], len(closed) + 1), component)

        self.assertFalse(closed_result.passed)
        self.assertTrue(future_result.passed)

    def test_compiler_emits_signal_for_supported_candidate(self) -> None:
        candidate = {
            "components": [
                {"role": "triggers", "type": "momentum-close", "parameters": {"side": "call", "body-min-atr": 0.1}},
                {"role": "decision", "type": "weighted-score", "parameters": {"min-score": 1.0}},
            ]
        }
        signal = compile_candidate_strategy(candidate)(bullish_candles(20), 20)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.side, "call")

    def test_compiler_rejects_unsupported_component(self) -> None:
        candidate = {"components": [{"role": "indicators", "type": "unknown", "parameters": {}}]}

        with self.assertRaises(UnsupportedComponentError):
            compile_candidate_strategy(candidate)

    def test_weighted_score_threshold_and_side_conflict(self) -> None:
        threshold_candidate = {
            "components": [
                {"role": "trigger", "type": "momentum-close", "parameters": {"side": "call", "body-min-atr": 0.1}},
                {"role": "volatility", "type": "atr-normalized", "parameters": {"period": 14, "min-ratio": 99.0, "max-ratio": 100.0}},
                {"role": "decision", "type": "weighted-score", "parameters": {"min-score": 1.0}},
            ]
        }
        conflict_candidate = {
            "components": [
                {"role": "trigger", "type": "momentum-close", "parameters": {"side": "call", "body-min-atr": 0.1}},
                {"role": "structure", "type": "support-resistance-zone", "parameters": {"lookback": 20, "tolerance-atr": 0.6}},
                {"role": "decision", "type": "weighted-score", "parameters": {"min-score": 0.1}},
            ]
        }

        threshold = evaluate_candidate_decision(threshold_candidate, bullish_candles(20), 20)
        conflict = evaluate_candidate_decision(conflict_candidate, bullish_candles(20), 20)

        self.assertEqual(threshold["reason"], "score-below-threshold")
        self.assertEqual(conflict["reason"], "side-conflict")


class SearchScopeRunIntegrationTests(unittest.TestCase):
    def test_search_scope_candidates_produce_distinct_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            experiment = root / "experiment" / "robo-LKSJDLKKL"
            data = experiment / "data"
            data.mkdir(parents=True)
            write_yaml(
                experiment / "experiment.yml",
                {
                    "name": "robo-LKSJDLKKL",
                    "hypothesis": "Search-scope candidates compile to executable strategies.",
                    "target": {"metric": "win-rate", "operator": ">=", "value": 2.0},
                    "stop-on-target": True,
                },
            )
            write_yaml(
                experiment / "ingest.yml",
                {
                    "data": {
                        "provider": "fixture",
                        "asset": "IDXUSD",
                        "timeframe": "M1",
                        "from": "2026-01-01",
                        "to": "2026-01-02",
                        "source": "local",
                        "format": "csv",
                        "path": "data",
                    },
                    "validation": {"require-complete-candles": True, "reject-gaps": True, "timezone": "UTC"},
                },
            )
            write_yaml(
                experiment / "search-scope.yml",
                {
                    "schema-version": 1,
                    "flow": ["context", "regime", "volatility", "structure", "setup", "trigger", "confirmation", "decision"],
                    "limits": {"max-candidates": 2, "max-seconds": 60, "batch-size": 2, "max-rounds": 1, "stagnation-rounds": 1},
                    "components": {
                        "context": [],
                        "regime": [],
                        "volatility": [{"type": "candle-anomaly-filter", "parameters": {"lookback": [3], "max-body-ratio": [10.0]}}],
                        "structure": [],
                        "setup": [],
                        "trigger": [
                            {"type": "momentum-close", "parameters": {"body-min-atr": [0.1], "side": ["call", "put"]}},
                        ],
                        "confirmation": [],
                        "decision": [{"type": "weighted-score", "parameters": {"min-score": [1.0], "entry": ["next-candle-open"], "expiration-candles": [1]}}],
                    },
                },
            )
            with (data / "IDXUSD_M1.csv").open("w", encoding="utf-8") as handle:
                handle.write("time,open,high,low,close\n")
                for item in bullish_candles(30):
                    handle.write(f"{item.time},{item.open},{item.high},{item.low},{item.close}\n")

            response = run_backtest(root, "robo-LKSJDLKKL", "backtest", "bt-20260101-000000")
            candidates_path = experiment / "runs" / "bt-20260101-000000" / "candidates.jsonl"
            candidates = [json.loads(line) for line in candidates_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            second_response = run_backtest(root, "robo-LKSJDLKKL", "backtest", "bt-20260101-000001")
            second_run = experiment / "runs" / "bt-20260101-000001"
            second_candidates = [json.loads(line) for line in (second_run / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            second_scoreboard = json.loads((second_run / "scoreboard.json").read_text(encoding="utf-8"))

        self.assertEqual(response["runId"], "bt-20260101-000000")
        self.assertIn("max-drawdown", response["metrics"])
        self.assertIn("profit-factor", response["metrics"])
        self.assertEqual(len(candidates), 2)
        self.assertTrue(all(candidate.get("candidateFingerprint") for candidate in candidates))
        self.assertTrue(all(candidate.get("evaluationFingerprint") for candidate in candidates))
        self.assertNotEqual(candidates[0]["metrics"], candidates[1]["metrics"])
        self.assertGreater(candidates[0]["metrics"]["total-trades"], candidates[1]["metrics"]["total-trades"])
        self.assertEqual(second_response["metrics"]["skipped-duplicates"], 2)
        self.assertTrue(all(candidate["status"] == "skipped-duplicate" and candidate["classification"] == "skipped" for candidate in second_candidates))
        self.assertEqual(second_scoreboard["rankings"]["candidates"], [])


if __name__ == "__main__":
    unittest.main()
