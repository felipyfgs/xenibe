from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from xenibe.artifacts.store import (
    ImmutableRunError,
    append_scope_revision,
    assert_run_writable,
    create_experiment,
    init_artifact_root,
    load_yaml,
    validate_config,
    validate_experiment_dir,
    validate_run_dir,
    write_yaml,
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
            experiment = root / "experiment" / "idx-m1-soros-reversal"
            for filename in ("experiment.yml", "ingest.yml", "search-scope.yml"):
                self.assertTrue((experiment / filename).exists())
            self.assertTrue((experiment / "data").is_dir())
            self.assertFalse((experiment / "runs").exists())
            self.assertFalse((experiment / "__init__.py").exists())

    def test_invalid_config_reports_semantic_issue_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_artifact_root(root)
            write_yaml(root / "config.yml", {"schema-version": 2, "artifact": {}, "contexts": {"experiment": {"path": "../outside"}}})

            issues = validate_config(root)

        paths = {issue.path for issue in issues}
        self.assertIn(str(root / "config.yml") + ":schema-version", paths)
        self.assertIn(str(root / "config.yml") + ":artifact.root", paths)
        self.assertIn(str(root / "config.yml") + ":contexts.promoted", paths)
        self.assertIn(str(root / "config.yml") + ":contexts.experiment.path", paths)

    def test_ingest_and_target_semantic_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_experiment(root, "idx-m1-soros-reversal")
            experiment = root / "experiment" / "idx-m1-soros-reversal"
            experiment_yml = load_yaml(experiment / "experiment.yml")
            experiment_yml["name"] = "other-name"
            experiment_yml["target"] = {"metric": "unknown", "operator": "contains", "value": "bad"}
            experiment_yml["stop-on-target"] = "yes"
            write_yaml(experiment / "experiment.yml", experiment_yml)
            ingest = load_yaml(experiment / "ingest.yml")
            ingest["data"]["provider"] = "unknown"
            ingest["data"]["timeframe"] = "M2"
            ingest["data"]["from"] = "2026-01-03"
            ingest["data"]["to"] = "2026-01-02"
            ingest["data"]["path"] = "../outside"
            write_yaml(experiment / "ingest.yml", ingest)

            issues = validate_experiment_dir(experiment)

        paths = {issue.path for issue in issues}
        self.assertIn(str(experiment / "experiment.yml") + ":name", paths)
        self.assertIn(str(experiment / "experiment.yml") + ":target.metric", paths)
        self.assertIn(str(experiment / "experiment.yml") + ":target.operator", paths)
        self.assertIn(str(experiment / "experiment.yml") + ":target.value", paths)
        self.assertIn(str(experiment / "experiment.yml") + ":stop-on-target", paths)
        self.assertIn(str(experiment / "ingest.yml") + ":data.provider", paths)
        self.assertIn(str(experiment / "ingest.yml") + ":data.timeframe", paths)
        self.assertIn(str(experiment / "ingest.yml") + ":data.to", paths)
        self.assertIn(str(experiment / "ingest.yml") + ":data.path", paths)

    def test_missing_ingest_directory_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_experiment(root, "idx-m1-soros-reversal")
            experiment = root / "experiment" / "idx-m1-soros-reversal"
            ingest = load_yaml(experiment / "ingest.yml")
            ingest["data"]["path"] = "missing-data"
            write_yaml(experiment / "ingest.yml", ingest)

            issues = validate_experiment_dir(experiment)

        self.assertIn(str(experiment / "ingest.yml") + ":data.path", {issue.path for issue in issues})

    def test_search_scope_semantic_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_experiment(root, "idx-m1-soros-reversal")
            experiment = root / "experiment" / "idx-m1-soros-reversal"
            scope = load_yaml(experiment / "search-scope.yml")
            scope["flow"] = ["trigger", "decision"]
            scope["limits"]["max-candidates"] = 0
            scope["limits"]["unknown-limit"] = 1
            del scope["components"]["context"]
            scope["components"]["trigger"] = [
                {"type": "unknown-trigger", "parameters": {"side": ["call"]}},
                {"type": "momentum-close", "parameters": {"body-min-atr": [], "side": ["maybe"], "unknown": [1]}},
            ]
            scope["components"]["decision"] = []
            write_yaml(experiment / "search-scope.yml", scope)

            issues = validate_experiment_dir(experiment)

        paths = {issue.path for issue in issues}
        self.assertIn(str(experiment / "search-scope.yml") + ":flow", paths)
        self.assertIn(str(experiment / "search-scope.yml") + ":limits.max-candidates", paths)
        self.assertIn(str(experiment / "search-scope.yml") + ":limits.unknown-limit", paths)
        self.assertIn(str(experiment / "search-scope.yml") + ":components.context", paths)
        self.assertIn(str(experiment / "search-scope.yml") + ":components.trigger[0].type", paths)
        self.assertIn(str(experiment / "search-scope.yml") + ":components.trigger[1].parameters.body-min-atr", paths)
        self.assertIn(str(experiment / "search-scope.yml") + ":components.trigger[1].parameters.side[0]", paths)
        self.assertIn(str(experiment / "search-scope.yml") + ":components.trigger[1].parameters.unknown", paths)
        self.assertIn(str(experiment / "search-scope.yml") + ":components.decision", paths)

    def test_legacy_searchscope_without_canonical_file_reports_migration_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_experiment(root, "idx-m1-soros-reversal")
            experiment = root / "experiment" / "idx-m1-soros-reversal"
            (experiment / "search-scope.yml").rename(experiment / "searchscope.yml")

            issues = validate_experiment_dir(experiment)

        self.assertTrue(any(issue.code == "missing-artifact" and "legacy searchscope.yml" in issue.message for issue in issues))

    def test_scope_revision_record_is_appended(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_experiment(root, "idx-m1-soros-reversal")
            experiment = root / "experiment" / "idx-m1-soros-reversal"
            previous_scope = load_yaml(experiment / "search-scope.yml")
            new_scope = {**previous_scope, "limits": {**previous_scope["limits"], "max-candidates": 10}}

            record = append_scope_revision(experiment, "narrow-search", "prefer faster validation", "bt-20260101-000000", previous_scope, new_scope)

            lines = (experiment / "scope-revisions.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(record["decision"], "narrow-search")
        self.assertNotEqual(record["previousScopeHash"], record["newScopeHash"])

    def test_completed_run_is_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "bt-20260101-000000"
            shutil.copytree(FIXTURES / "valid-run" / "bt-20260101-000000", run_dir)
            with self.assertRaises(ImmutableRunError):
                assert_run_writable(run_dir)


if __name__ == "__main__":
    unittest.main()
