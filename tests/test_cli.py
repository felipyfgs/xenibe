from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from forge.cli import main
from xenibe.artifacts.store import load_yaml


def run_cli(args: list[str]) -> tuple[int, dict]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main([*args, "--json"])
    return code, json.loads(buffer.getvalue())


class CliTests(unittest.TestCase):
    def test_json_success_contains_contract_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, response = run_cli(["init", "--root", tmp])

        self.assertEqual(code, 0)
        self.assertIn("status", response)
        self.assertIn("data", response)
        self.assertIn("nextActions", response)

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
        self.assertTrue(response["nextActions"])

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
            self.assertEqual(run_cli(["run", "validate", "idx-m1-soros-reversal", "bt-20260101-000000", "--root", str(root)])[0], 0)

        self.assertEqual(code, 0)
        self.assertEqual(response["data"]["runId"], "bt-20260101-000000")
        self.assertIn("win-rate", response["data"]["metrics"])


if __name__ == "__main__":
    unittest.main()
