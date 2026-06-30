from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from forge.cli import main
from xenibe.artifacts.store import load_yaml


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


class CliTests(unittest.TestCase):
    def test_json_success_contains_contract_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, response = run_cli(["init", "--root", tmp])

        self.assertEqual(code, 0)
        for key in ("status", "data", "nextActions", "root", "command"):
            self.assertIn(key, response)
        self.assertEqual(response["command"]["name"], "forge init")
        self.assertEqual(response["command"]["dryRun"], False)
        self.assertIn("path", response["root"])
        self.assertIn("exists", response["root"])

    def test_init_scaffolds_minimal_root_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "forge" / "robo-lksjdlkkk"
            code, response = run_cli(["init", "--root", str(root)])

            self.assertEqual(code, 0, response)
            self.assertEqual(response["status"][0]["code"], "created")
            self.assertEqual(response["data"]["artifactRoot"], str(root))
            self.assertEqual({Path(path).name for path in response["data"]["created"]}, {"promoted", "archived", "experiment", "config.yml"})
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
            for filename in ("experiment.yml", "ingest.yml", "search-scope.yml", "risk.yml", "provider.yml", "report.yml"):
                self.assertFalse((root / filename).exists())
            self.assertEqual(list(root.rglob("*.py")), [])

            validate_code, validate_response = run_cli(["validate", "--root", str(root)])
            self.assertEqual(validate_code, 0, validate_response)
            self.assertTrue(validate_response["data"]["valid"])

    def test_init_is_idempotent_and_preserves_existing_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "forge" / "robo-lksjdlkkk"
            root.mkdir(parents=True)
            config = root / "config.yml"
            config.write_text("", encoding="utf-8")

            code, response = run_cli(["init", "--root", str(root)])
            self.assertEqual(code, 0, response)
            self.assertEqual(config.read_text(encoding="utf-8"), "")
            self.assertNotIn(str(config), response["data"]["created"])

            second_code, second_response = run_cli(["init", "--root", str(root)])
            self.assertEqual(second_code, 0, second_response)
            self.assertEqual(second_response["data"]["created"], [])
            self.assertEqual(config.read_text(encoding="utf-8"), "")

    def test_json_error_contains_next_actions(self) -> None:
        code, response = run_cli(["experiment", "validate", "missing"])

        self.assertNotEqual(code, 0)
        self.assertEqual(response["status"][0]["level"], "error")
        self.assertIn("target", response["status"][0])
        self.assertIn("fix", response["status"][0])
        self.assertTrue(response["nextActions"])

    def test_json_error_stdout_is_single_document(self) -> None:
        code, output = run_cli_raw(["instructions", "orchestrate"])

        self.assertNotEqual(code, 0)
        response = json.loads(output)
        self.assertEqual(output.strip()[0], "{")
        self.assertEqual(output.strip()[-1], "}")
        self.assertEqual(response["status"][0]["code"], "missing-name")
        self.assertEqual(response["command"]["name"], "forge instructions orchestrate")

    def test_status_reports_missing_and_empty_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            missing_code, missing_response = run_cli(["status", "--root", str(missing)])
            self.assertEqual(missing_code, 0, missing_response)
            self.assertEqual(missing_response["data"]["state"], "missing-root")
            self.assertTrue(any("forge init" in action for action in missing_response["nextActions"]))

            root = Path(tmp) / "forge"
            self.assertEqual(run_cli(["init", "--root", str(root)])[0], 0)
            empty_code, empty_response = run_cli(["status", "--root", str(root)])

        self.assertEqual(empty_code, 0, empty_response)
        self.assertEqual(empty_response["data"]["state"], "no-experiments")
        self.assertIn("actionContext", empty_response)
        self.assertFalse(empty_response["actionContext"]["mutatesArtifacts"])

    def test_status_reports_experiments_invalid_issues_and_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["init", "--root", str(root)])[0], 0)
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
            self.assertEqual(run_cli(["init", "--root", str(root)])[0], 0)
            copy_fixture("valid-experiment", root / "experiment" / "valid-experiment")
            runs = root / "experiment" / "valid-experiment" / "runs"
            runs.mkdir()
            incomplete = runs / "bt-20260101-000000"
            incomplete.mkdir()
            (incomplete / "manifest.json").write_text('{"runId":"bt-20260101-000000","experiment":"valid-experiment","mode":"backtest","status":"completed","createdAt":"2026-01-01T00:00:00Z"}\n', encoding="utf-8")

            export_code, export_response = run_cli(["run", "export", "valid-experiment", "bt-20260101-000000", "--root", str(root)])
            validate_code, validate_response = run_cli(["validate", "--root", str(root)])

            shutil.rmtree(incomplete)
            copy_fixture("valid-run/bt-20260101-000000", incomplete)
            (incomplete / "metrics.json").write_text("{bad-json\n", encoding="utf-8")
            status_code, status_response = run_cli(["status", "--root", str(root)])

        self.assertNotEqual(export_code, 0)
        self.assertEqual(export_response["status"][0]["code"], "invalid-artifact")
        self.assertNotEqual(validate_code, 0)
        self.assertTrue(validate_response["data"]["issues"])
        self.assertEqual(status_code, 0, status_response)
        run_summary = status_response["data"]["experiments"][0]["latestRuns"][0]
        self.assertFalse(run_summary["valid"])
        self.assertTrue(any(issue["code"] == "invalid-json" for issue in run_summary["issues"]))

    def test_instructions_report_target_hit_and_best_candidate_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["init", "--root", str(root)])[0], 0)
            experiment = root / "experiment" / "valid-experiment"
            copy_fixture("valid-experiment", experiment)
            runs = experiment / "runs"
            runs.mkdir()
            copy_fixture("valid-run/bt-20260101-000000", runs / "bt-20260101-000000")
            before = sorted((str(path.relative_to(root)), path.read_text(encoding="utf-8")) for path in root.rglob("*") if path.is_file())

            code, response = run_cli(["instructions", "orchestrate", "valid-experiment", "--root", str(root)])
            after = sorted((str(path.relative_to(root)), path.read_text(encoding="utf-8")) for path in root.rglob("*") if path.is_file())

        self.assertEqual(code, 0, response)
        self.assertEqual(response["data"]["state"], "target-hit")
        self.assertEqual(response["data"]["bestCandidate"]["candidateId"], "candidate-000001")
        self.assertIn("latestRun", response["data"]["contextFiles"])
        self.assertIn("scoreboard", response["data"]["artifactPaths"])
        self.assertEqual(before, after)

    def test_instructions_prefers_scoreboard_and_ignores_horizon_failed_target_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["init", "--root", str(root)])[0], 0)
            experiment = root / "experiment" / "valid-experiment"
            copy_fixture("valid-experiment", experiment)
            runs = experiment / "runs"
            runs.mkdir()
            run_dir = runs / "bt-20260101-000000"
            copy_fixture("valid-run/bt-20260101-000000", run_dir)
            scoreboard = json.loads((run_dir / "scoreboard.json").read_text(encoding="utf-8"))
            scoreboard["rankings"]["candidates"] = [
                {
                    "rank": 1,
                    "candidateId": "candidate-000002",
                    "classification": "winner",
                    "status": "target-hit",
                    "metrics": {"win-rate": 1.0, "net-profit": 8.0},
                    "horizonValidation": {"status": "failed"},
                },
                scoreboard["rankings"]["candidates"][0],
            ]
            (run_dir / "scoreboard.json").write_text(json.dumps(scoreboard), encoding="utf-8")

            code, response = run_cli(["instructions", "orchestrate", "valid-experiment", "--root", str(root)])

        self.assertEqual(code, 0, response)
        self.assertEqual(response["data"]["bestCandidate"]["candidateId"], "candidate-000002")
        self.assertNotEqual(response["data"]["state"], "target-hit")

    def test_instructions_missing_root_and_invalid_experiment_fail_structured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            missing_code, missing_response = run_cli(["instructions", "orchestrate", "valid-experiment", "--root", str(missing)])
            self.assertNotEqual(missing_code, 0)
            self.assertEqual(missing_response["data"]["state"], "missing-root")

            root = Path(tmp) / "forge"
            self.assertEqual(run_cli(["init", "--root", str(root)])[0], 0)
            copy_fixture("invalid-experiment", root / "experiment" / "invalid-experiment")
            invalid_code, invalid_response = run_cli(["instructions", "orchestrate", "invalid-experiment", "--root", str(root)])

        self.assertNotEqual(invalid_code, 0)
        self.assertEqual(invalid_response["data"]["state"], "blocked")
        self.assertTrue(invalid_response["data"]["blockedReasons"])
        self.assertIn("target", invalid_response["data"]["blockedReasons"][0])

    def test_experiment_and_backtest_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["init", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["experiment", "new", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["experiment", "validate", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)
            missing_code, missing_response = run_cli(["run", "backtest", "idx-m1-soros-reversal", "--root", str(root), "--run-id", "bt-20260101-000000"])
            code, response = run_cli(["run", "backtest", "idx-m1-soros-reversal", "--allow-synthetic", "--root", str(root), "--run-id", "bt-20260101-000000"])
            run_dir = root / "experiment" / "idx-m1-soros-reversal" / "runs" / "bt-20260101-000000"
            self.assertTrue((run_dir / "scoreboard.json").exists())
            self.assertTrue((run_dir / "rounds.jsonl").exists())
            self.assertTrue((run_dir / "reflections.jsonl").exists())
            inputs = json.loads((run_dir / "inputs.json").read_text(encoding="utf-8"))
            self.assertEqual(run_cli(["run", "validate", "idx-m1-soros-reversal", "bt-20260101-000000", "--root", str(root)])[0], 0)

        self.assertNotEqual(missing_code, 0)
        self.assertEqual(missing_response["status"][0]["code"], "missing-artifact")
        self.assertTrue(any("--allow-synthetic" in action for action in missing_response["nextActions"]))
        self.assertEqual(code, 0)
        self.assertEqual(response["data"]["runId"], "bt-20260101-000000")
        self.assertIn("win-rate", response["data"]["metrics"])
        self.assertEqual(response["data"]["execution"]["payout"], 0.8)
        self.assertEqual(response["data"]["execution"]["dataSource"], "synthetic-default")
        self.assertIn("synthetic-default-candles", {item["code"] for item in response["data"]["limitations"]})
        self.assertEqual(inputs["history"]["dataSource"], "synthetic-default")
        self.assertEqual(inputs["execution"]["payoutSource"], "fixed-default")
        self.assertFalse(inputs["execution"]["maxSecondsEnforced"])

    def test_simulate_command_is_not_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["init", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["experiment", "new", "idx-m1-soros-reversal", "--root", str(root)])[0], 0)

            code, response = run_cli(["run", "simulate", "idx-m1-soros-reversal", "--allow-synthetic", "--run-id", "sim-20260101-000000", "--root", str(root)])

        self.assertNotEqual(code, 0)
        self.assertEqual(response["status"][0]["code"], "unknown-command")

    def test_partial_risk_merges_defaults_and_optional_yaml_errors_are_structured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_cli(["init", "--root", str(root)])[0], 0)
            self.assertEqual(run_cli(["experiment", "new", "partial-risk", "--root", str(root)])[0], 0)
            risk_path = root / "experiment" / "partial-risk" / "risk.yml"
            risk_path.write_text("balance: 500\n", encoding="utf-8")
            run_code, run_response = run_cli(["run", "backtest", "partial-risk", "--allow-synthetic", "--run-id", "bt-20260101-000000", "--root", str(root)])
            snapshot = load_yaml(root / "experiment" / "partial-risk" / "runs" / "bt-20260101-000000" / "config-snapshot.yml")

            malformed_results = []
            for filename in ("risk.yml", "provider.yml", "report.yml"):
                name = f"bad-{filename.removesuffix('.yml')}"
                self.assertEqual(run_cli(["experiment", "new", name, "--root", str(root)])[0], 0)
                (root / "experiment" / name / filename).write_text("bad: [\n", encoding="utf-8")
                malformed_results.append(run_cli(["run", "backtest", name, "--allow-synthetic", "--root", str(root)]))

        self.assertEqual(run_code, 0, run_response)
        self.assertEqual(snapshot["risk"]["balance"], 500)
        self.assertIn("stake", snapshot["risk"])
        for code, response in malformed_results:
            self.assertNotEqual(code, 0)
            self.assertEqual(response["status"][0]["code"], "invalid-yaml")
            self.assertTrue(response["data"]["issues"])


if __name__ == "__main__":
    unittest.main()
