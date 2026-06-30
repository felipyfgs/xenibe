from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from xenibe.artifacts.history import file_sha256
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
    write_json,
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

    def test_canonical_history_manifest_and_active_legacy_csv_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_experiment(root, "idx-m1-soros-reversal")
            experiment = root / "experiment" / "idx-m1-soros-reversal"
            csv_path = experiment / "data" / "EURUSD_M1.csv"
            csv_path.write_text("time,asset,timeframe,open,high,low,close\n2026-01-01T00:00:00Z,EURUSD,M1,1,2,1,2\n", encoding="utf-8")
            write_json(
                experiment / "data" / "EURUSD_M1.manifest.json",
                {
                    "asset": "EURUSD",
                    "timeframe": "M1",
                    "requestedRange": {"from": "2026-01-01", "to": "2026-01-02"},
                    "coverageRange": {"from": "2026-01-01", "to": "2026-01-02"},
                    "path": "data/EURUSD_M1.csv",
                    "candleCount": 1,
                    "sha256": file_sha256(csv_path),
                    "provider": "fixture",
                    "providerMode": "test",
                    "downloadedAt": "2026-01-01T00:00:00Z",
                },
            )
            ingest = load_yaml(experiment / "ingest.yml")
            ingest["data"]["path"] = "data/EURUSD_M1.csv"
            write_yaml(experiment / "ingest.yml", ingest)

            valid_issues = validate_experiment_dir(experiment)

            legacy_path = experiment / "data" / "EURUSD_M1_2026-01-01_2026-01-02.csv"
            legacy_path.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
            ingest["data"]["path"] = "data/EURUSD_M1_2026-01-01_2026-01-02.csv"
            write_yaml(experiment / "ingest.yml", ingest)
            legacy_issues = validate_experiment_dir(experiment)

        self.assertEqual(valid_issues, [])
        self.assertIn(str(experiment / "ingest.yml") + ":data.path", {issue.path for issue in legacy_issues})
        self.assertTrue(any("data/EURUSD_M1.csv" in issue.message for issue in legacy_issues))

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

    def test_search_scope_rejects_declared_but_unsupported_context_components(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_experiment(root, "idx-m1-soros-reversal")
            experiment = root / "experiment" / "idx-m1-soros-reversal"
            scope = load_yaml(experiment / "search-scope.yml")
            scope["components"]["context"] = [{"type": "session", "parameters": {"name": ["london"]}}]
            write_yaml(experiment / "search-scope.yml", scope)

            issues = validate_experiment_dir(experiment)

        self.assertIn(str(experiment / "search-scope.yml") + ":components.context[0].type", {issue.path for issue in issues})

    def test_risk_validation_rejects_declared_but_unsupported_strategies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_experiment(root, "idx-m1-soros-reversal")
            experiment = root / "experiment" / "idx-m1-soros-reversal"
            write_yaml(
                experiment / "risk.yml",
                {
                    "stop-loss": 15,
                    "stop-win": 20,
                    "soros": {"enabled": True, "levels": 2},
                    "martingale": {"enabled": True, "max-steps": 1, "multiplier": 2},
                },
            )

            issues = validate_experiment_dir(experiment)

        paths = {issue.path for issue in issues}
        self.assertIn(str(experiment / "risk.yml") + ":soros.levels", paths)
        self.assertIn(str(experiment / "risk.yml") + ":martingale.enabled", paths)
        self.assertIn(str(experiment / "risk.yml") + ":martingale.max-steps", paths)

    def test_horizon_validation_config_and_required_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_experiment(root, "idx-m1-soros-reversal")
            experiment = root / "experiment" / "idx-m1-soros-reversal"
            csv_path = experiment / "data" / "EURUSD_M1.csv"
            csv_path.write_text("time,asset,timeframe,open,high,low,close\n2026-01-01T00:00:00Z,EURUSD,M1,1,2,1,2\n", encoding="utf-8")
            write_json(
                experiment / "data" / "EURUSD_M1.manifest.json",
                {
                    "asset": "EURUSD",
                    "timeframe": "M1",
                    "requestedRange": {"from": "2026-01-01", "to": "2026-01-31"},
                    "coverageRange": {"from": "2026-01-01", "to": "2026-01-31"},
                    "path": "data/EURUSD_M1.csv",
                    "candleCount": 1,
                    "sha256": file_sha256(csv_path),
                    "provider": "fixture",
                    "providerMode": "test",
                    "downloadedAt": "2026-01-01T00:00:00Z",
                },
            )
            ingest = load_yaml(experiment / "ingest.yml")
            ingest["data"]["path"] = "data/EURUSD_M1.csv"
            ingest["data"]["from"] = "2026-01-01"
            ingest["data"]["to"] = "2026-01-31"
            write_yaml(experiment / "ingest.yml", ingest)
            scope = load_yaml(experiment / "search-scope.yml")
            scope["horizon-validation"] = {
                "enabled": True,
                "primary-window-days": 7,
                "days": [3, 7, 15],
                "min-trades-per-hour": 0.2,
                "min-sufficient-horizons": 3,
                "gate": {"mode": "min-sufficient", "target-source": "experiment-target", "require-positive-net-profit": True},
            }
            write_yaml(experiment / "search-scope.yml", scope)

            valid_issues = validate_experiment_dir(experiment)

            scope["horizon-validation"]["days"] = [0]
            write_yaml(experiment / "search-scope.yml", scope)
            invalid_config_issues = validate_experiment_dir(experiment)
            scope["horizon-validation"]["days"] = [3, 7, 15]
            write_yaml(experiment / "search-scope.yml", scope)
            manifest = load_yaml(experiment / "ingest.yml")
            self.assertEqual(manifest["data"]["path"], "data/EURUSD_M1.csv")
            write_json(
                experiment / "data" / "EURUSD_M1.manifest.json",
                {
                    "asset": "EURUSD",
                    "timeframe": "M1",
                    "requestedRange": {"from": "2026-01-20", "to": "2026-01-31"},
                    "coverageRange": {"from": "2026-01-20", "to": "2026-01-31"},
                    "path": "data/EURUSD_M1.csv",
                    "candleCount": 1,
                    "sha256": file_sha256(csv_path),
                    "provider": "fixture",
                    "providerMode": "test",
                    "downloadedAt": "2026-01-20T00:00:00Z",
                },
            )
            coverage_issues = validate_experiment_dir(experiment)

        self.assertEqual(valid_issues, [])
        self.assertIn(str(experiment / "search-scope.yml") + ":horizon-validation.days[0]", {issue.path for issue in invalid_config_issues})
        self.assertTrue(any(issue.path.endswith("EURUSD_M1.manifest.json:coverageRange") for issue in coverage_issues))

    def test_horizons_jsonl_is_validated_as_optional_detail_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "bt-20260101-000000"
            shutil.copytree(FIXTURES / "valid-run" / "bt-20260101-000000", run_dir)
            (run_dir / "horizons.jsonl").write_text("{bad-json\n", encoding="utf-8")

            issues = validate_run_dir(run_dir)

        self.assertTrue(any(issue.code == "invalid-jsonl" and "horizons.jsonl" in issue.path for issue in issues))

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
