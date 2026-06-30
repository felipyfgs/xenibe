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
            root = Path(tmp) / "forge" / "robo-LKSJDLKKL"
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
            root = Path(tmp) / "forge" / "robo-LKSJDLKKL"
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
            code, response = run_cli(["run", "backtest", "idx-m1-soros-reversal", "--root", str(root), "--run-id", "bt-20260101-000000"])
            run_dir = root / "experiment" / "idx-m1-soros-reversal" / "runs" / "bt-20260101-000000"
            self.assertTrue((run_dir / "scoreboard.json").exists())
            self.assertTrue((run_dir / "rounds.jsonl").exists())
            self.assertTrue((run_dir / "reflections.jsonl").exists())
            inputs = json.loads((run_dir / "inputs.json").read_text(encoding="utf-8"))
            self.assertEqual(run_cli(["run", "validate", "idx-m1-soros-reversal", "bt-20260101-000000", "--root", str(root)])[0], 0)

        self.assertEqual(code, 0)
        self.assertEqual(response["data"]["runId"], "bt-20260101-000000")
        self.assertIn("win-rate", response["data"]["metrics"])
        self.assertEqual(response["data"]["execution"]["payout"], 0.8)
        self.assertEqual(response["data"]["execution"]["dataSource"], "synthetic-default")
        self.assertIn("synthetic-default-candles", {item["code"] for item in response["data"]["limitations"]})
        self.assertEqual(inputs["history"]["dataSource"], "synthetic-default")
        self.assertEqual(inputs["execution"]["payoutSource"], "fixed-default")
        self.assertFalse(inputs["execution"]["maxSecondsEnforced"])


if __name__ == "__main__":
    unittest.main()
