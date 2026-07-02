from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from forge.cli import main
from xenibe.artifacts.store import init_artifact_root, load_json, load_yaml


def run_cli(args: list[str]) -> tuple[int, dict]:
    code, output = run_cli_raw(args)
    return code, json.loads(output)


def run_cli_raw(args: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main([*args, "--json"])
    return code, buffer.getvalue()


def copy_fixture(name: str, destination: Path) -> None:
    shutil.copytree(Path(__file__).parent / "fixtures" / name, destination)


def write_configured_history(root: Path, experiment: str) -> None:
    data_dir = root / "experiment" / experiment / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "EURUSD_M1.csv").write_text(
        "time,asset,timeframe,open,high,low,close\n"
        "2026-01-01T00:00:00Z,EURUSD,M1,1.00,1.20,0.90,1.10\n"
        "2026-01-01T00:01:00Z,EURUSD,M1,1.10,1.25,1.00,1.05\n"
        "2026-01-01T00:02:00Z,EURUSD,M1,1.05,1.30,1.00,1.20\n"
        "2026-01-01T00:03:00Z,EURUSD,M1,1.20,1.22,1.00,1.05\n",
        encoding="utf-8",
    )


class CliTests(unittest.TestCase):
    def test_json_success_contains_contract_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, response = run_cli(["new", "idx-m1-soros-reversal", "--root", tmp])

        self.assertEqual(code, 0)
        for key in ("status", "data", "nextActions", "root", "command"):
            self.assertIn(key, response)
        self.assertEqual(response["command"]["name"], "forge new")
        self.assertEqual(response["command"]["dryRun"], False)
        self.assertIn("path", response["root"])
        self.assertIn("exists", response["root"])

    def test_new_scaffolds_root_and_experiment_then_check_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "forge" / "robo-lksjdlkkk"
            code, response = run_cli(["new", "idx-m1-soros-reversal", "--root", str(root)])

            self.assertEqual(code, 0, response)
            self.assertEqual(response["status"][0]["code"], "created")
            self.assertEqual(response["data"]["artifactRoot"], str(root))
            self.assertEqual({Path(path).name for path in response["data"]["createdRootArtifacts"]}, {"promoted", "archived", "experiment", "config.yml"})
            self.assertTrue((root / "config.yml").exists())
            self.assertFalse((root / "assets").exists())
            self.assertFalse((root / "exports").exists())
            self.assertEqual(
                load_yaml(root / "config.yml"),
                {
                    "schema-version": 1,
                    "artifact": {"root": str(root)},
                    "contexts": {
                        "promoted": {"path": "promoted"},
                        "archived": {"path": "archived"},
                        "experiment": {"path": "experiment"},
                    },
                },
            )
            experiment = root / "experiment" / "idx-m1-soros-reversal"
            for filename in ("experiment.yml", "ingest.yml", "search-scope.yml"):
                self.assertTrue((experiment / filename).exists())
            self.assertTrue((experiment / "data").is_dir())
            self.assertEqual(list(root.rglob("*.py")), [])

            check_code, check_response = run_cli(["check", "--root", str(root)])
            self.assertEqual(check_code, 0, check_response)
            self.assertTrue(check_response["data"]["valid"])

    def test_new_preserves_existing_root_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "forge" / "robo-lksjdlkkk"
            root.mkdir(parents=True)
            config = root / "config.yml"
            config.write_text("", encoding="utf-8")

            code, response = run_cli(["new", "first-experiment", "--root", str(root)])
            second_code, second_response = run_cli(["new", "second-experiment", "--root", str(root)])

            self.assertEqual(code, 0, response)
            self.assertEqual(second_code, 0, second_response)
            self.assertEqual(config.read_text(encoding="utf-8"), "")
            self.assertNotIn(str(config), response["data"]["createdRootArtifacts"])
            self.assertEqual(second_response["data"]["createdRootArtifacts"], [])

    def test_json_error_contains_next_actions(self) -> None:
        code, response = run_cli(["check", "missing"])

        self.assertNotEqual(code, 0)
        self.assertEqual(response["status"][0]["level"], "error")
        self.assertIn("target", response["status"][0])
        self.assertIn("fix", response["status"][0])
        self.assertTrue(response["nextActions"])

    def test_json_error_stdout_is_single_document(self) -> None:
        code, output = run_cli_raw(["data", "download"])

        self.assertNotEqual(code, 0)
        response = json.loads(output)
        self.assertEqual(output.strip()[0], "{")
        self.assertEqual(output.strip()[-1], "}")
        self.assertEqual(response["status"][0]["code"], "missing-name")
        self.assertEqual(response["command"]["name"], "forge data download")

    def test_status_reports_missing_and_empty_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            missing_code, missing_response = run_cli(["status", "--root", str(missing)])
            self.assertEqual(missing_code, 0, missing_response)
            self.assertEqual(missing_response["data"]["state"], "missing-root")
            self.assertTrue(any("forge new" in action for action in missing_response["nextActions"]))

            root = Path(tmp) / "forge"
            init_artifact_root(root)
            empty_code, empty_response = run_cli(["status", "--root", str(root)])

        self.assertEqual(empty_code, 0, empty_response)
        self.assertEqual(empty_response["data"]["state"], "no-experiments")
        self.assertIn("actionContext", empty_response)
        self.assertFalse(empty_response["actionContext"]["mutatesArtifacts"])

    def test_status_reports_experiments_invalid_issues_and_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_artifact_root(root)
            copy_fixture("valid-experiment", root / "experiment" / "valid-experiment")
            runs = root / "experiment" / "valid-experiment" / "runs"
            runs.mkdir()
            copy_fixture("valid-run/bt-20260101-000000", runs / "bt-20260101-000000")
            copy_fixture("invalid-experiment", root / "experiment" / "invalid-experiment")

            code, response = run_cli(["status", "--root", str(root)])

        self.assertEqual(code, 0, response)
        self.assertEqual(response["data"]["state"], "blocked")
        experiments = {item["name"]: item for item in response["data"]["experiments"]}
        self.assertTrue(experiments["valid-experiment"]["valid"])
        self.assertEqual(experiments["valid-experiment"]["latestRunIds"], ["bt-20260101-000000"])
        self.assertFalse(experiments["invalid-experiment"]["valid"])
        self.assertTrue(experiments["invalid-experiment"]["issues"])

    def test_run_consumers_reject_incomplete_and_status_reports_corrupt_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_artifact_root(root)
            copy_fixture("valid-experiment", root / "experiment" / "valid-experiment")
            runs = root / "experiment" / "valid-experiment" / "runs"
            runs.mkdir()
            incomplete = runs / "bt-20260101-000000"
            incomplete.mkdir()
            (incomplete / "manifest.json").write_text('{"runId":"bt-20260101-000000","experiment":"valid-experiment","mode":"backtest","status":"completed","createdAt":"2026-01-01T00:00:00Z"}\n', encoding="utf-8")

            export_code, export_response = run_cli(["export", "valid-experiment", "bt-20260101-000000", "--root", str(root)])
            check_code, check_response = run_cli(["check", "--root", str(root)])

            shutil.rmtree(incomplete)
            copy_fixture("valid-run/bt-20260101-000000", incomplete)
            (incomplete / "metrics.json").write_text("{bad-json\n", encoding="utf-8")
            status_code, status_response = run_cli(["status", "--root", str(root)])

        self.assertNotEqual(export_code, 0)
        self.assertEqual(export_response["status"][0]["code"], "invalid-artifact")
        self.assertNotEqual(check_code, 0)
        self.assertTrue(check_response["data"]["issues"])
        self.assertEqual(status_code, 0, status_response)
        run_summary = status_response["data"]["experiments"][0]["latestRuns"][0]
        self.assertFalse(run_summary["valid"])
        self.assertTrue(any(issue["code"] == "invalid-json" for issue in run_summary["issues"]))

    def test_show_experiment_and_run_details_are_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_artifact_root(root)
            experiment = root / "experiment" / "valid-experiment"
            copy_fixture("valid-experiment", experiment)
            runs = experiment / "runs"
            runs.mkdir()
            copy_fixture("valid-run/bt-20260101-000000", runs / "bt-20260101-000000")
            before = sorted((str(path.relative_to(root)), path.read_text(encoding="utf-8")) for path in root.rglob("*") if path.is_file())

            experiment_code, experiment_response = run_cli(["show", "valid-experiment", "--root", str(root)])
            run_code, run_response = run_cli(["show", "valid-experiment", "bt-20260101-000000", "--root", str(root)])
            after = sorted((str(path.relative_to(root)), path.read_text(encoding="utf-8")) for path in root.rglob("*") if path.is_file())

        self.assertEqual(experiment_code, 0, experiment_response)
        self.assertIn("configSummary", experiment_response["data"])
        self.assertIn("dataSummary", experiment_response["data"])
        self.assertEqual(experiment_response["data"]["recentRuns"][0]["runId"], "bt-20260101-000000")
        self.assertEqual(experiment_response["data"]["bestKnownCandidate"]["candidateId"], "candidate-000001")
        self.assertEqual(run_code, 0, run_response)
        self.assertIn("report", run_response["data"])
        self.assertIn("artifactPaths", run_response["data"])
        self.assertFalse(run_response["data"]["promotionStatus"]["promoted"])
        self.assertEqual(before, after)

    def test_experiment_and_backtest_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["new", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["check", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            missing_code, missing_response = run_cli(["backtest", "idx-m1-soros-reversal", "--root", str(root), "--run-id", "bt-20260101-000000"])
            removed_code, removed_response = run_cli(["backtest", "idx-m1-soros-reversal", "--allow-synthetic", "--root", str(root), "--run-id", "bt-20260101-000000"])
            write_configured_history(root, "idx-m1-soros-reversal")
            code, response = run_cli(["backtest", "idx-m1-soros-reversal", "--root", str(root), "--run-id", "bt-20260101-000000"])
            run_dir = root / "experiment" / "idx-m1-soros-reversal" / "runs" / "bt-20260101-000000"
            self.assertEqual(sorted(path.name for path in run_dir.iterdir()), ["records.jsonl", "report.md", "run.json"])
            self.assertFalse((run_dir / "scoreboard.json").exists())
            self.assertFalse((run_dir / "rounds.jsonl").exists())
            self.assertFalse((run_dir / "reflections.jsonl").exists())
            run_doc = load_json(run_dir / "run.json")
            records = [json.loads(line) for line in (run_dir / "records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            inputs = run_doc["inputs"]
            self.assertEqual(run_cli(["check", "idx-m1-soros-reversal", "bt-20260101-000000", "--root", str(root)])[0], 0)
            status_code, status_response = run_cli(["status", "--root", str(root)])
            show_code, show_response = run_cli(["show", "idx-m1-soros-reversal", "bt-20260101-000000", "--root", str(root)])
            persisted_metrics = run_doc["metrics"]
            report = (run_dir / "report.md").read_text(encoding="utf-8")

        self.assertNotEqual(missing_code, 0)
        self.assertEqual(missing_response["status"][0]["code"], "missing-artifact")
        self.assertTrue(any("forge data download" in action for action in missing_response["nextActions"]))
        self.assertFalse(any("--allow-synthetic" in action for action in missing_response["nextActions"]))
        self.assertNotEqual(removed_code, 0)
        self.assertEqual(removed_response["status"][0]["code"], "unknown-command")
        self.assertIn("--allow-synthetic has been removed", removed_response["status"][0]["message"])
        self.assertTrue(any("forge data download" in action for action in removed_response["nextActions"]))
        self.assertEqual(code, 0)
        self.assertEqual(response["data"]["runId"], "bt-20260101-000000")
        self.assertEqual(run_doc["runId"], "bt-20260101-000000")
        self.assertEqual(run_doc["status"], "completed")
        self.assertNotIn("schemaVersion", run_doc)
        self.assertEqual(run_doc["recordCounts"]["candidate"], sum(1 for record in records if record["kind"] == "candidate"))
        self.assertTrue(all(set(record) == {"seq", "kind", "data"} for record in records))
        self.assertIn("win-rate", response["data"]["metrics"])
        self.assertIn("session-win-rate", response["data"]["metrics"])
        self.assertIn("blocked-signals", response["data"]["metrics"])
        self.assertIn("soros-trades", response["data"]["metrics"])
        self.assertIn("session-win-rate", persisted_metrics)
        self.assertIn("Trade win rate", report)
        self.assertIn("Session win rate", report)
        self.assertEqual(status_code, 0)
        self.assertIn("session-win-rate", status_response["data"]["experiments"][0]["latestRuns"][0]["metrics"])
        self.assertEqual(show_code, 0)
        self.assertIn("Session win rate", show_response["data"]["report"])
        self.assertEqual(response["data"]["subject"], "candidate-search")
        self.assertEqual(response["data"]["execution"]["payout"], 0.8)
        self.assertEqual(response["data"]["execution"]["dataSource"], "configured-history")
        self.assertEqual(response["data"]["execution"]["payoutSource"], "fixed-default")
        self.assertTrue(response["data"]["execution"]["maxSecondsEnforced"])
        self.assertEqual(response["data"]["execution"]["semantics"]["executionModel"], "ebinex-candle-expiry")
        self.assertEqual(response["data"]["execution"]["semantics"]["historyPolicy"], "closed-candles-before-submission-candle")
        self.assertEqual(response["data"]["execution"]["semantics"]["submission"]["cutoff"]["secondsBeforeClose"], 5)
        self.assertEqual(response["data"]["execution"]["semantics"]["contract"], {"candle": "next-timeframe-candle", "entry": "open"})
        self.assertEqual(response["data"]["execution"]["semantics"]["settlement"]["policy"], "contract-candle-close")
        self.assertNotIn("max-seconds-not-enforced", {item["code"] for item in response["data"]["limitations"]})
        self.assertNotIn("synthetic-default-candles", {item["code"] for item in response["data"]["limitations"]})
        self.assertEqual(inputs["subject"], "candidate-search")
        self.assertEqual(inputs["history"]["dataSource"], "configured-history")
        self.assertEqual(inputs["execution"]["payoutSource"], "fixed-default")
        self.assertTrue(inputs["execution"]["maxSecondsEnforced"])
        self.assertEqual(inputs["execution"]["semantics"]["executionModel"], "ebinex-candle-expiry")
        self.assertIn("Execution model: `ebinex-candle-expiry`", report)
        self.assertIn("Submission: current `M1` candle before provider cutoff", report)
        self.assertIn("Settlement: contract candle close", report)

    def test_simulate_mode_uses_sim_prefix_and_rejects_backtest_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["new", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            write_configured_history(root, "idx-m1-soros-reversal")

            code, response = run_cli(["backtest", "idx-m1-soros-reversal", "--mode", "simulate", "--run-id", "sim-20260101-000000", "--root", str(root)])
            wrong_code, wrong_response = run_cli(["backtest", "idx-m1-soros-reversal", "--mode", "simulate", "--run-id", "bt-20260101-000001", "--root", str(root)])
            run_doc = load_json(root / "experiment" / "idx-m1-soros-reversal" / "runs" / "sim-20260101-000000" / "run.json")

        self.assertEqual(code, 0, response)
        self.assertEqual(response["data"]["runId"], "sim-20260101-000000")
        self.assertEqual(run_doc["mode"], "simulate")
        self.assertNotEqual(wrong_code, 0)
        self.assertEqual(wrong_response["status"][0]["code"], "invalid-name")

    def test_partial_risk_merges_defaults_and_optional_yaml_errors_are_structured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["new", "partial-risk", "--root", str(root)])[0], 0)
            write_configured_history(root, "partial-risk")
            risk_path = root / "experiment" / "partial-risk" / "risk.yml"
            risk_path.write_text("balance: 500\n", encoding="utf-8")
            run_code, run_response = run_cli(["backtest", "partial-risk", "--run-id", "bt-20260101-000000", "--root", str(root)])
            snapshot = load_json(root / "experiment" / "partial-risk" / "runs" / "bt-20260101-000000" / "run.json")["configSnapshot"]

            malformed_results = []
            for filename in ("risk.yml", "provider.yml", "report.yml"):
                name = f"bad-{filename.removesuffix('.yml')}"
                self.assertEqual(run_cli(["new", name, "--root", str(root)])[0], 0)
                write_configured_history(root, name)
                (root / "experiment" / name / filename).write_text("bad: [\n", encoding="utf-8")
                malformed_results.append(run_cli(["backtest", name, "--root", str(root)]))

        self.assertEqual(run_code, 0, run_response)
        self.assertEqual(snapshot["risk"]["balance"], 500)
        self.assertIn("stake", snapshot["risk"])
        for code, response in malformed_results:
            self.assertNotEqual(code, 0)
            self.assertEqual(response["status"][0]["code"], "invalid-yaml")
            self.assertTrue(response["data"]["issues"])


if __name__ == "__main__":
    unittest.main()
