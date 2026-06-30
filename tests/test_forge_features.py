from __future__ import annotations

import contextlib
import importlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from forge.catalog import COMMANDS, DISPATCH_COMMAND_NAMES, SUBCOMMANDS
from forge.cli import main
from forge.context import CommandContext
from forge.responses import SUBCOMMANDS as RESPONSE_SUBCOMMANDS
from xenibe.artifacts.store import load_json, load_yaml


FEATURES = DISPATCH_COMMAND_NAMES


def run_cli(args: list[str], provider_factory=None) -> tuple[int, dict[str, Any]]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main([*args, "--json"], provider_factory=provider_factory)
    return code, json.loads(buffer.getvalue())


class MockProvider:
    name = "mock"
    mode = "live"

    def assets(self) -> list[dict[str, Any]]:
        return [{"id": "EURUSD", "displayName": "Euro Dollar", "marketStatus": "open"}]

    def payout(self, asset: str) -> float:
        return 0.82 if asset == "EURUSD" else 0.0

    def historical_candles(self, asset: str, timeframe: str, start: str, end: str) -> list[dict[str, Any]]:
        return [{"time": start, "asset": asset, "timeframe": timeframe, "open": 1.0, "high": 1.2, "low": 0.9, "close": 1.1}]


class CountingProvider(MockProvider):
    calls: list[tuple[str, str, str, str]] = []

    def historical_candles(self, asset: str, timeframe: str, start: str, end: str) -> list[dict[str, Any]]:
        self.calls.append((asset, timeframe, start, end))
        return [
            {"time": start, "asset": asset, "timeframe": timeframe, "open": 1.0, "high": 1.2, "low": 0.9, "close": 1.1},
            {"time": end, "asset": asset, "timeframe": timeframe, "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.1},
        ]


class ExplodingProvider(MockProvider):
    def historical_candles(self, asset: str, timeframe: str, start: str, end: str) -> list[dict[str, Any]]:
        raise AssertionError("provider should not be called")


class ForgeFeatureTests(unittest.TestCase):
    def test_command_catalog_drives_help_features_and_metadata(self) -> None:
        code, response = run_cli(["--help"])

        self.assertEqual(code, 0)
        self.assertEqual(response["data"]["commands"], [command.name for command in COMMANDS])
        self.assertEqual(RESPONSE_SUBCOMMANDS, SUBCOMMANDS)
        for command in COMMANDS:
            self.assertIn(command.usage, response["data"]["help"])

    def test_feature_packages_import_and_dispatch_missing_command(self) -> None:
        context = CommandContext(root=Path("/tmp/forge-test"))
        for feature in FEATURES:
            package = importlib.import_module(f"forge.{feature}")
            command = importlib.import_module(f"forge.{feature}.command")
            self.assertTrue(hasattr(package, "dispatch"))
            response = command.dispatch([], context)
            self.assertIn("status", response)
            self.assertIn(response["status"][0]["code"], {"missing-command", "missing-name", "ok", "validated", "invalid-artifact"})

    def test_global_options_help_and_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_cli(["--root", tmp, "init"])[0], 0)
            code, response = run_cli(["experiment", "list", "--root", tmp, "--dry-run", "--yes", "--no-color"])
        self.assertEqual(code, 0)
        self.assertIn("experiments", response["data"])

        code, response = run_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("forge assets list", response["data"]["help"])
        self.assertIn("forge status", response["data"]["help"])
        self.assertIn("forge instructions orchestrate", response["data"]["help"])

        code, response = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("version", response["data"])

    def test_artifact_workflows_and_legacy_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["init", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["experiment", "new", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["run", "backtest", "idx-m1-soros-reversal", "--run-id", "bt-20260101-000000", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["run", "backtest", "idx-m1-soros-reversal", "--run-id", "bt-20260101-000001", "--root", str(root)])[0], 0)

            metrics_path = root / "experiment" / "idx-m1-soros-reversal" / "runs" / "bt-20260101-000000" / "metrics.json"
            before = metrics_path.read_text(encoding="utf-8")
            code, response = run_cli(["run", "backtest", "idx-m1-soros-reversal", "--run-id", "bt-20260101-000000", "--root", str(root)])
            self.assertNotEqual(code, 0)
            self.assertEqual(response["status"][0]["code"], "immutable-run")
            self.assertEqual(metrics_path.read_text(encoding="utf-8"), before)

            self.assertEqual(run_cli(["run", "validate", "idx-m1-soros-reversal", "bt-20260101-000000", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["report", "show", "idx-m1-soros-reversal", "bt-20260101-000000", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["report", "idx-m1-soros-reversal", "bt-20260101-000000", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["compare", "runs", "idx-m1-soros-reversal", "bt-20260101-000000", "bt-20260101-000001", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["compare", "idx-m1-soros-reversal", "bt-20260101-000000", "bt-20260101-000001", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["promote", "run", "idx-m1-soros-reversal", "bt-20260101-000000", "--reason", "test", "--root", str(root)])[0], 0)
            self.assertTrue((root / "promoted" / "idx-m1-soros-reversal" / "bt-20260101-000000" / "promotion.yml").exists())

            before_archives = sorted(path.name for path in (root / "archived").iterdir())
            code, response = run_cli(["archive", "experiment", "idx-m1-soros-reversal", "--dry-run", "--root", str(root)])
            self.assertEqual(code, 0)
            self.assertTrue(response["data"]["plannedActions"])
            self.assertEqual(sorted(path.name for path in (root / "archived").iterdir()), before_archives)

            self.assertEqual(run_cli(["export", "run", "idx-m1-soros-reversal", "bt-20260101-000000", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["export", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["validate", "--root", str(root)])[0], 0)

    def test_provider_commands_use_injected_provider(self) -> None:
        provider_factory = MockProvider
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["init", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["experiment", "new", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            assets_code, assets_response = run_cli(["assets", "list", "--root", str(root)], provider_factory=provider_factory)
            payout_code, payout_response = run_cli(["payout", "get", "EURUSD", "--root", str(root)], provider_factory=provider_factory)
            history_code, history_response = run_cli(
                ["history", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-01", "--to", "2026-01-02", "--root", str(root)],
                provider_factory=provider_factory,
            )
            history_path_exists = Path(history_response["data"]["path"]).exists()
            manifest_path_exists = Path(history_response["data"]["manifestPath"]).exists()
            ingest = load_yaml(root / "experiment" / "idx-m1-soros-reversal" / "ingest.yml")
            manifest = load_json(Path(history_response["data"]["manifestPath"]))

        self.assertEqual(assets_code, 0)
        self.assertEqual(assets_response["data"]["assets"][0]["id"], "EURUSD")
        self.assertEqual(payout_code, 0)
        self.assertEqual(payout_response["data"]["payout"], 0.82)
        self.assertEqual(history_code, 0)
        self.assertEqual(history_response["data"]["candleCount"], 1)
        self.assertTrue(history_path_exists)
        self.assertTrue(manifest_path_exists)
        self.assertTrue(history_response["data"]["path"].endswith("data/EURUSD_M1.csv"))
        self.assertEqual(ingest["data"]["path"], "data/EURUSD_M1.csv")
        self.assertEqual(manifest["path"], "data/EURUSD_M1.csv")
        self.assertEqual(manifest["requestedRange"], {"from": "2026-01-01", "to": "2026-01-02"})

    def test_history_download_reuses_covered_canonical_without_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["init", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["experiment", "new", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            first_code, _ = run_cli(
                ["history", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-01", "--to", "2026-01-10", "--root", str(root)],
                provider_factory=MockProvider,
            )
            second_code, second_response = run_cli(
                ["history", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-02", "--to", "2026-01-03", "--root", str(root)],
                provider_factory=ExplodingProvider,
            )
            ingest = load_yaml(root / "experiment" / "idx-m1-soros-reversal" / "ingest.yml")

        self.assertEqual(first_code, 0)
        self.assertEqual(second_code, 0, second_response)
        self.assertEqual(second_response["data"]["action"], "reuse")
        self.assertEqual(ingest["data"]["from"], "2026-01-02")
        self.assertEqual(ingest["data"]["to"], "2026-01-03")

    def test_history_download_expands_conflicts_and_replaces_canonical_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            CountingProvider.calls = []
            self.assertEqual(run_cli(["init", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["experiment", "new", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            self.assertEqual(
                run_cli(
                    ["history", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-02", "--to", "2026-01-03", "--root", str(root)],
                    provider_factory=CountingProvider,
                )[0],
                0,
            )
            expand_code, expand_response = run_cli(
                ["history", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-01", "--to", "2026-01-04", "--root", str(root)],
                provider_factory=CountingProvider,
            )
            conflict_code, conflict_response = run_cli(
                ["history", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-02-01", "--to", "2026-02-02", "--root", str(root)],
                provider_factory=CountingProvider,
            )
            replace_code, replace_response = run_cli(
                ["history", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-02-01", "--to", "2026-02-02", "--replace", "--root", str(root)],
                provider_factory=CountingProvider,
            )

        self.assertEqual(expand_code, 0, expand_response)
        self.assertEqual(expand_response["data"]["action"], "expand")
        self.assertTrue(CountingProvider.calls[1][2].startswith("2026-01-01"))
        self.assertTrue(CountingProvider.calls[1][3].startswith("2026-01-04"))
        self.assertNotEqual(conflict_code, 0)
        self.assertEqual(conflict_response["status"][0]["code"], "replace-required")
        self.assertEqual(replace_code, 0, replace_response)
        self.assertEqual(replace_response["data"]["action"], "replace")

    def test_history_download_reports_manifest_conflict_and_dry_run_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["init", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["experiment", "new", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            self.assertEqual(
                run_cli(
                    ["history", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-01", "--to", "2026-01-02", "--root", str(root)],
                    provider_factory=MockProvider,
                )[0],
                0,
            )
            manifest_path = root / "experiment" / "idx-m1-soros-reversal" / "data" / "EURUSD_M1.manifest.json"
            manifest_path.unlink()
            conflict_code, conflict_response = run_cli(
                ["history", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-01", "--to", "2026-01-02", "--root", str(root)],
                provider_factory=MockProvider,
            )
            (root / "experiment" / "idx-m1-soros-reversal" / "data" / "EURUSD_M1.csv").unlink()
            dry_code, dry_response = run_cli(
                ["history", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-01", "--to", "2026-01-02", "--root", str(root), "--dry-run"],
                provider_factory=MockProvider,
            )

        self.assertNotEqual(conflict_code, 0)
        self.assertEqual(conflict_response["status"][0]["code"], "canonical-history-conflict")
        self.assertEqual(dry_code, 0, dry_response)
        self.assertIn("write canonical CSV", dry_response["data"]["plannedActions"])


if __name__ == "__main__":
    unittest.main()
