from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from xenibe.artifacts.store import (
    ImmutableRunError,
    assert_run_writable,
    create_experiment,
    validate_experiment_dir,
    validate_run_dir,
)


FIXTURES = Path(__file__).parent / "fixtures"


class ArtifactValidationTests(unittest.TestCase):
    def test_valid_experiment_fixture_passes(self) -> None:
        self.assertEqual(validate_experiment_dir(FIXTURES / "valid-experiment"), [])

    def test_invalid_experiment_fixture_reports_issues(self) -> None:
        issues = validate_experiment_dir(FIXTURES / "invalid-experiment")
        self.assertTrue(any(issue.code == "invalid-name" for issue in issues))
        self.assertTrue(any(issue.code == "missing-artifact" for issue in issues))

    def test_valid_run_fixture_passes(self) -> None:
        self.assertEqual(validate_run_dir(FIXTURES / "valid-run" / "bt-20260101-000000"), [])

    def test_invalid_run_fixture_reports_issues(self) -> None:
        issues = validate_run_dir(FIXTURES / "invalid-run" / "bad_run_id")
        self.assertTrue(any(issue.code == "invalid-name" for issue in issues))
        self.assertTrue(any(issue.code == "missing-artifact" for issue in issues))

    def test_create_experiment_scaffolds_subject_yaml_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_experiment(root, "idx-m1-soros-reversal")
            experiment = root / "idx-m1-soros-reversal"
            for filename in ("experiment.yml", "ingest.yml", "searchscope.yml", "risk.yml", "provider.yml", "report.yml"):
                self.assertTrue((experiment / filename).exists())
            self.assertFalse((experiment / "__init__.py").exists())

    def test_completed_run_is_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "bt-20260101-000000"
            shutil.copytree(FIXTURES / "valid-run" / "bt-20260101-000000", run_dir)
            with self.assertRaises(ImmutableRunError):
                assert_run_writable(run_dir)


if __name__ == "__main__":
    unittest.main()
