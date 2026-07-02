from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from forge.catalog import COMMANDS, SUBCOMMANDS
from forge.cli import main
from forge.responses import SUBCOMMANDS as RESPONSE_SUBCOMMANDS
from forge.workflow import WORKFLOW_HANDLERS
from xenibe.artifacts.store import load_json, load_yaml, write_json, write_yaml


WORKFLOW_COMMANDS = ["new", "status", "show", "check", "data", "backtest", "compare", "promote", "archive", "export"]
REMOVED_COMMAND_SNIPPETS = (
    "forge init",
    "forge experiment",
    "forge run",
    "forge report",
    "forge assets",
    "forge payout",
    "forge history",
    "forge instructions",
    "forge validate",
)


def run_cli(args: list[str], provider_factory=None) -> tuple[int, dict[str, Any]]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main([*args, "--json"], provider_factory=provider_factory)
    return code, json.loads(buffer.getvalue())


def copy_fixture(name: str, destination: Path) -> None:
    shutil.copytree(Path(__file__).parent / "fixtures" / name, destination)


def assert_workflow_actions(testcase: unittest.TestCase, response: dict[str, Any]) -> None:
    for action in response.get("nextActions", []):
        for removed in REMOVED_COMMAND_SNIPPETS:
            testcase.assertNotIn(removed, action)


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


class EmptyProvider(MockProvider):
    def historical_candles(self, asset: str, timeframe: str, start: str, end: str) -> list[dict[str, Any]]:
        return []


class ForgeFeatureTests(unittest.TestCase):
    def test_command_catalog_drives_help_features_and_metadata(self) -> None:
        code, response = run_cli(["--help"])

        self.assertEqual(code, 0)
        self.assertEqual([command.name for command in COMMANDS], WORKFLOW_COMMANDS)
        self.assertEqual(response["data"]["commands"], WORKFLOW_COMMANDS)
        self.assertEqual(RESPONSE_SUBCOMMANDS, SUBCOMMANDS)
        self.assertEqual(set(WORKFLOW_HANDLERS), set(WORKFLOW_COMMANDS))
        for command in COMMANDS:
            self.assertIn(command.usage, response["data"]["help"])
        for removed in REMOVED_COMMAND_SNIPPETS:
            self.assertNotIn(removed, response["data"]["help"])

    def test_removed_namespaces_are_rejected(self) -> None:
        cases = [
            ["init"],
            ["experiment", "list"],
            ["run", "show", "demo", "bt-20260101-000000"],
            ["report", "show", "demo", "bt-20260101-000000"],
            ["assets", "list"],
            ["payout", "get", "EURUSD"],
            ["history", "download", "EURUSD"],
            ["instructions", "orchestrate", "demo"],
            ["validate"],
        ]

        for args in cases:
            with self.subTest(args=args):
                code, response = run_cli(args)
                self.assertNotEqual(code, 0)
                self.assertEqual(response["status"][0]["code"], "unknown-command")
                assert_workflow_actions(self, response)

    def test_legacy_positional_shapes_are_rejected(self) -> None:
        cases = [
            ["compare", "runs", "demo", "bt-20260101-000000", "bt-20260101-000001"],
            ["export", "run", "demo", "bt-20260101-000000"],
            ["promote", "run", "demo", "bt-20260101-000000"],
        ]

        for args in cases:
            with self.subTest(args=args):
                code, response = run_cli(args)
                self.assertNotEqual(code, 0)
                self.assertEqual(response["status"][0]["code"], "unknown-command")
                self.assertIn("legacy command shape removed", response["status"][0]["message"])
                assert_workflow_actions(self, response)

    def test_command_metadata_for_workflow_commands(self) -> None:
        cases = [
            (["new", "demo", "--dry-run"], "forge new"),
            (["backtest", "demo", "--mode", "simulate", "--run-id", "sim-20260101-000000"], "forge backtest"),
            (["check"], "forge check"),
            (["show"], "forge show"),
            (["data", "list"], "forge data list"),
            (["data", "download", "EURUSD", "--experiment", "demo", "--timeframe", "M1", "--from", "2026-01-01", "--to", "2026-01-02"], "forge data download"),
            (["compare", "demo", "bt-20260101-000000", "bt-20260101-000001"], "forge compare"),
            (["promote", "demo", "bt-20260101-000000"], "forge promote"),
            (["archive", "demo"], "forge archive"),
            (["export", "demo"], "forge export"),
            (["export", "demo", "bt-20260101-000000"], "forge export"),
        ]

        for args, expected in cases:
            with self.subTest(args=args):
                _, response = run_cli(args)
                self.assertEqual(response["command"]["name"], expected)

    def test_next_actions_use_only_workflow_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                run_cli(["new", "idx-m1-soros-reversal", "--root", str(root)])[1],
                run_cli(["status", "--root", str(root)])[1],
                run_cli(["data", "list", "--root", str(root)], provider_factory=MockProvider)[1],
                run_cli(["backtest", "idx-m1-soros-reversal", "--root", str(root), "--run-id", "bt-20260101-000000"])[1],
            ]

        for response in responses:
            assert_workflow_actions(self, response)

    def test_global_options_help_and_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_cli(["--root", tmp, "new", "idx-m1-soros-reversal"])[0], 0)
            code, response = run_cli(["show", "--root", tmp, "--dry-run", "--yes", "--no-color"])
        self.assertEqual(code, 0)
        self.assertIn("experiments", response["data"])

        code, response = run_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("forge data list", response["data"]["help"])
        self.assertIn("forge status", response["data"]["help"])
        self.assertIn("forge show [experiment] [run-id]", response["data"]["help"])

        code, response = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("version", response["data"])

    def test_artifact_workflows_use_workflow_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["new", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            experiment_yml = root / "experiment" / "idx-m1-soros-reversal" / "experiment.yml"
            experiment_config = load_yaml(experiment_yml)
            experiment_config["target"] = {"metric": "win-rate", "operator": ">=", "value": 0.0}
            write_yaml(experiment_yml, experiment_config)
            download_code, download_response = run_cli(
                ["data", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-01", "--to", "2026-01-02", "--root", str(root)],
                provider_factory=MockProvider,
            )
            self.assertEqual(download_code, 0, download_response)
            self.assertEqual(run_cli(["backtest", "idx-m1-soros-reversal", "--run-id", "bt-20260101-000000", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["backtest", "idx-m1-soros-reversal", "--run-id", "bt-20260101-000001", "--root", str(root)])[0], 0)

            run_json_path = root / "experiment" / "idx-m1-soros-reversal" / "runs" / "bt-20260101-000000" / "run.json"
            before = run_json_path.read_text(encoding="utf-8")
            code, response = run_cli(["backtest", "idx-m1-soros-reversal", "--run-id", "bt-20260101-000000", "--root", str(root)])
            self.assertNotEqual(code, 0)
            self.assertEqual(response["status"][0]["code"], "immutable-run")
            self.assertEqual(run_json_path.read_text(encoding="utf-8"), before)

            self.assertEqual(run_cli(["check", "idx-m1-soros-reversal", "bt-20260101-000000", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["show", "idx-m1-soros-reversal", "bt-20260101-000000", "--root", str(root)])[0], 0)
            compare_code, compare_response = run_cli(["compare", "idx-m1-soros-reversal", "bt-20260101-000000", "bt-20260101-000001", "--root", str(root)])
            self.assertEqual(compare_code, 0, compare_response)
            self.assertIn("net-profit", compare_response["data"]["runs"][0])
            self.assertNotIn("netProfit", compare_response["data"]["runs"][0])
            self.assertEqual(compare_response["data"]["bestRunId"], "bt-20260101-000000")
            duplicate_row = next(row for row in compare_response["data"]["runs"] if row["runId"] == "bt-20260101-000001")
            self.assertTrue(duplicate_row["duplicateOnly"])
            self.assertFalse(duplicate_row["bestEligible"])
            duplicate_promote_code, duplicate_promote_response = run_cli(["promote", "idx-m1-soros-reversal", "bt-20260101-000001", "--root", str(root)])
            self.assertNotEqual(duplicate_promote_code, 0)
            self.assertEqual(duplicate_promote_response["status"][0]["code"], "invalid-artifact")
            self.assertEqual(run_cli(["promote", "idx-m1-soros-reversal", "bt-20260101-000000", "--reason", "test", "--root", str(root)])[0], 0)
            robot_path = root / "promoted" / "idx-m1-soros-reversal--bt-20260101-000000" / "robot.yml"
            self.assertTrue(robot_path.exists())
            self.assertEqual({path.name for path in robot_path.parent.iterdir()}, {"robot.yml"})
            robot = load_yaml(robot_path)
            self.assertEqual(robot["source"]["experiment"], "idx-m1-soros-reversal")
            self.assertEqual(robot["source"]["run-id"], "bt-20260101-000000")
            self.assertIsInstance(robot["robot"]["score"], float)
            show_code, show_response = run_cli(["show", "idx-m1-soros-reversal", "bt-20260101-000000", "--root", str(root)])
            self.assertEqual(show_code, 0, show_response)
            self.assertTrue(show_response["data"]["promotionStatus"]["promoted"])
            self.assertEqual(show_response["data"]["promotionStatus"]["robotId"], "idx-m1-soros-reversal--bt-20260101-000000")

            before_archives = sorted(path.name for path in (root / "archived").iterdir())
            code, response = run_cli(["archive", "idx-m1-soros-reversal", "--dry-run", "--root", str(root)])
            self.assertEqual(code, 0)
            self.assertTrue(response["data"]["plannedActions"])
            self.assertEqual(sorted(path.name for path in (root / "archived").iterdir()), before_archives)

            run_export_code, run_export_response = run_cli(["export", "idx-m1-soros-reversal", "bt-20260101-000000", "--root", str(root)])
            experiment_export_code, _ = run_cli(["export", "idx-m1-soros-reversal", "--root", str(root)])
            self.assertEqual(run_export_code, 0, run_export_response)
            self.assertEqual(experiment_export_code, 0)
            run_export = load_json(Path(run_export_response["data"]["export"]))
            self.assertIn("bundle", run_export)
            self.assertTrue(run_export["bundle"]["files"])
            self.assertEqual({item["path"] for item in run_export["bundle"]["files"]}, {"run.json", "records.jsonl", "report.md"})
            archive_code, archive_response = run_cli(["archive", "idx-m1-soros-reversal", "--root", str(root)])
            self.assertEqual(archive_code, 0, archive_response)
            self.assertFalse((root / "experiment" / "idx-m1-soros-reversal").exists())
            self.assertTrue(Path(archive_response["data"]["archive"]).exists())
            status_code, status_response = run_cli(["status", "--root", str(root)])
            self.assertEqual(status_code, 0)
            self.assertEqual(status_response["data"]["experiments"], [])
            self.assertEqual(run_cli(["check", "--root", str(root)])[0], 0)

    def test_legacy_run_fixture_still_supports_workflow_consumers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["new", "valid-experiment", "--root", str(root)])[0], 0)
            runs = root / "experiment" / "valid-experiment" / "runs"
            runs.mkdir()
            copy_fixture("valid-run/bt-20260101-000000", runs / "bt-20260101-000000")
            copy_fixture("valid-run/bt-20260101-000000", runs / "bt-20260101-000001")
            for filename in ("manifest.json", "inputs.json", "scoreboard.json", "metrics.json"):
                data = load_json(runs / "bt-20260101-000001" / filename)
                data["runId"] = "bt-20260101-000001"
                write_json(runs / "bt-20260101-000001" / filename, data)

            self.assertEqual(run_cli(["check", "valid-experiment", "bt-20260101-000000", "--root", str(root)])[0], 0)
            show_code, show_response = run_cli(["show", "valid-experiment", "bt-20260101-000000", "--root", str(root)])
            compare_code, compare_response = run_cli(["compare", "valid-experiment", "bt-20260101-000000", "bt-20260101-000001", "--root", str(root)])
            promote_code, promote_response = run_cli(["promote", "valid-experiment", "bt-20260101-000000", "--root", str(root)])
            export_code, export_response = run_cli(["export", "valid-experiment", "bt-20260101-000000", "--root", str(root)])
            exported = load_json(Path(export_response["data"]["export"])) if export_code == 0 else {}

        self.assertEqual(show_code, 0, show_response)
        self.assertEqual(show_response["data"]["layout"], "legacy")
        self.assertIn("manifest", show_response["data"]["artifactPaths"])
        self.assertEqual(compare_code, 0, compare_response)
        self.assertIn(compare_response["data"]["bestRunId"], {"bt-20260101-000000", "bt-20260101-000001"})
        self.assertEqual(promote_code, 0, promote_response)
        self.assertEqual(export_code, 0, export_response)
        self.assertTrue(any(item["path"] == "manifest.json" for item in exported["bundle"]["files"]))

    def test_archive_and_export_reject_path_traversal_experiment_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["new", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)

            archive_code, archive_response = run_cli(["archive", "../idx-m1-soros-reversal", "--root", str(root)])
            export_code, export_response = run_cli(["export", "../idx-m1-soros-reversal", "--root", str(root)])

        self.assertNotEqual(archive_code, 0)
        self.assertEqual(archive_response["status"][0]["code"], "invalid-name")
        self.assertNotEqual(export_code, 0)
        self.assertEqual(export_response["status"][0]["code"], "invalid-name")

    def test_provider_commands_use_injected_provider(self) -> None:
        provider_factory = MockProvider
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["new", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            assets_code, assets_response = run_cli(["data", "list", "--root", str(root)], provider_factory=provider_factory)
            history_code, history_response = run_cli(
                ["data", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-01", "--to", "2026-01-02", "--root", str(root)],
                provider_factory=provider_factory,
            )
            history_path_exists = Path(history_response["data"]["path"]).exists()
            manifest_path_exists = Path(history_response["data"]["manifestPath"]).exists()
            ingest = load_yaml(root / "experiment" / "idx-m1-soros-reversal" / "ingest.yml")
            manifest = load_json(Path(history_response["data"]["manifestPath"]))

        self.assertEqual(assets_code, 0)
        self.assertEqual(assets_response["data"]["assets"][0]["id"], "EURUSD")
        self.assertEqual(assets_response["data"]["assets"][0]["payout"], 0.82)
        self.assertEqual(history_code, 0)
        self.assertEqual(history_response["data"]["candleCount"], 1)
        self.assertTrue(history_path_exists)
        self.assertTrue(manifest_path_exists)
        self.assertTrue(history_response["data"]["path"].endswith("data/EURUSD_M1.csv"))
        self.assertEqual(ingest["data"]["path"], "data/EURUSD_M1.csv")
        self.assertEqual(manifest["path"], "data/EURUSD_M1.csv")
        self.assertEqual(manifest["requestedRange"], {"from": "2026-01-01", "to": "2026-01-02"})

    def test_provider_commands_fail_without_ebinex_credentials_instead_of_offline_fallback(self) -> None:
        with patch.dict("os.environ", {"EBINEX_EMAIL": "", "EBINEX_PASSWORD": "", "EBINEX_PASS": ""}):
            code, response = run_cli(["data", "list"])

        self.assertNotEqual(code, 0)
        self.assertEqual(response["status"][0]["code"], "provider-credentials-missing")
        self.assertNotIn("offline", " ".join(response.get("nextActions", [])).lower())

    def test_data_download_rejects_empty_provider_history_without_writing_canonical_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["new", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            code, response = run_cli(
                ["data", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-01", "--to", "2026-01-02", "--root", str(root)],
                provider_factory=EmptyProvider,
            )
            history_path = Path(response["data"]["path"])
            manifest_path = Path(response["data"]["manifestPath"])

        self.assertNotEqual(code, 0)
        self.assertEqual(response["status"][0]["code"], "provider-unavailable")
        self.assertFalse(history_path.exists())
        self.assertFalse(manifest_path.exists())

    def test_data_download_reuses_covered_canonical_without_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["new", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            first_code, _ = run_cli(
                ["data", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-01", "--to", "2026-01-10", "--root", str(root)],
                provider_factory=MockProvider,
            )
            second_code, second_response = run_cli(
                ["data", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-02", "--to", "2026-01-03", "--root", str(root)],
                provider_factory=ExplodingProvider,
            )
            ingest = load_yaml(root / "experiment" / "idx-m1-soros-reversal" / "ingest.yml")

        self.assertEqual(first_code, 0)
        self.assertEqual(second_code, 0, second_response)
        self.assertEqual(second_response["data"]["action"], "reuse")
        self.assertEqual(ingest["data"]["from"], "2026-01-02")
        self.assertEqual(ingest["data"]["to"], "2026-01-03")

    def test_data_download_expands_conflicts_and_replaces_canonical_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            CountingProvider.calls = []
            self.assertEqual(run_cli(["new", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            self.assertEqual(
                run_cli(
                    ["data", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-02", "--to", "2026-01-03", "--root", str(root)],
                    provider_factory=CountingProvider,
                )[0],
                0,
            )
            expand_code, expand_response = run_cli(
                ["data", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-01", "--to", "2026-01-04", "--root", str(root)],
                provider_factory=CountingProvider,
            )
            conflict_code, conflict_response = run_cli(
                ["data", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-02-01", "--to", "2026-02-02", "--root", str(root)],
                provider_factory=CountingProvider,
            )
            replace_code, replace_response = run_cli(
                ["data", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-02-01", "--to", "2026-02-02", "--replace", "--root", str(root)],
                provider_factory=CountingProvider,
            )

        self.assertEqual(expand_code, 0, expand_response)
        self.assertEqual(expand_response["data"]["action"], "expand")
        self.assertTrue(CountingProvider.calls[1][2].startswith("2026-01-01"))
        self.assertTrue(CountingProvider.calls[1][3].startswith("2026-01-04"))
        self.assertNotEqual(conflict_code, 0)
        self.assertEqual(conflict_response["status"][0]["code"], "replace-required")
        self.assertEqual(conflict_response["data"]["requestedRange"], {"from": "2026-02-01", "to": "2026-02-02"})
        self.assertTrue(any("--replace" in action for action in conflict_response["nextActions"]))
        assert_workflow_actions(self, conflict_response)
        self.assertEqual(replace_code, 0, replace_response)
        self.assertEqual(replace_response["data"]["action"], "replace")

    def test_data_download_reports_manifest_conflict_and_dry_run_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["new", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            self.assertEqual(
                run_cli(
                    ["data", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-01", "--to", "2026-01-02", "--root", str(root)],
                    provider_factory=MockProvider,
                )[0],
                0,
            )
            manifest_path = root / "experiment" / "idx-m1-soros-reversal" / "data" / "EURUSD_M1.manifest.json"
            manifest_path.unlink()
            conflict_code, conflict_response = run_cli(
                ["data", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-01", "--to", "2026-01-02", "--root", str(root)],
                provider_factory=MockProvider,
            )
            (root / "experiment" / "idx-m1-soros-reversal" / "data" / "EURUSD_M1.csv").unlink()
            dry_code, dry_response = run_cli(
                ["data", "download", "EURUSD", "--experiment", "idx-m1-soros-reversal", "--timeframe", "M1", "--from", "2026-01-01", "--to", "2026-01-02", "--root", str(root), "--dry-run"],
                provider_factory=MockProvider,
            )

        self.assertNotEqual(conflict_code, 0)
        self.assertEqual(conflict_response["status"][0]["code"], "canonical-history-conflict")
        assert_workflow_actions(self, conflict_response)
        self.assertEqual(dry_code, 0, dry_response)
        self.assertIn("write canonical CSV", dry_response["data"]["plannedActions"])


if __name__ == "__main__":
    unittest.main()
