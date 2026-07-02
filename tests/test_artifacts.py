from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from xenibe.artifacts.history import file_sha256
from xenibe.artifacts.naming import is_run_id
from xenibe.artifacts.store import (
    ImmutableRunError,
    append_scope_revision,
    assert_run_writable,
    create_experiment,
    init_artifact_root,
    load_json,
    load_run_view,
    load_yaml,
    validate_config,
    validate_experiment_dir,
    validate_promoted_robot_dir,
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

    def test_valid_compact_run_fixture_passes(self) -> None:
        run_dir = FIXTURES / "compact-run" / "bt-20260101-000000"
        view = load_run_view(run_dir, expected_experiment="valid-experiment")

        self.assertEqual(validate_run_dir(run_dir, expected_experiment="valid-experiment"), [])
        self.assertEqual(sorted(path.name for path in run_dir.iterdir()), ["records.jsonl", "report.md", "run.json"])
        self.assertEqual(view["layout"], "compact")
        self.assertTrue(view["promotionEligible"])
        self.assertEqual(view["recordCounts"]["candidate"], 1)
        self.assertEqual(view["scoreboard"]["rankings"]["candidates"][0]["candidateId"], "candidate-000001")

    def test_compact_run_validation_reports_structural_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corrupt = Path(tmp) / "bt-20260101-000000"
            shutil.copytree(FIXTURES / "compact-run" / "bt-20260101-000000", corrupt)
            (corrupt / "run.json").write_text("{bad-json\n", encoding="utf-8")
            corrupt_issues = validate_run_dir(corrupt)

            unsupported = Path(tmp) / "bt-20260101-000001"
            shutil.copytree(FIXTURES / "compact-run" / "bt-20260101-000000", unsupported)
            data = load_json(unsupported / "run.json")
            data["runId"] = "bt-20260101-000001"
            data["inputs"]["runId"] = "bt-20260101-000001"
            data["scoreboard"]["runId"] = "bt-20260101-000001"
            write_json(unsupported / "run.json", data)
            (unsupported / "records.jsonl").write_text('{"seq":1,"kind":"unknown","data":{}}\n', encoding="utf-8")
            unsupported_issues = validate_run_dir(unsupported)

            non_monotonic = Path(tmp) / "bt-20260101-000002"
            shutil.copytree(FIXTURES / "compact-run" / "bt-20260101-000000", non_monotonic)
            data = load_json(non_monotonic / "run.json")
            data["runId"] = "bt-20260101-000002"
            data["inputs"]["runId"] = "bt-20260101-000002"
            data["scoreboard"]["runId"] = "bt-20260101-000002"
            data["recordCounts"] = {key: 0 for key in data["recordCounts"]}
            data["recordCounts"]["round"] = 2
            write_json(non_monotonic / "run.json", data)
            (non_monotonic / "records.jsonl").write_text('{"seq":1,"kind":"round","data":{}}\n{"seq":1,"kind":"round","data":{}}\n', encoding="utf-8")
            non_monotonic_issues = validate_run_dir(non_monotonic)

            mismatch = Path(tmp) / "bt-20260101-000003"
            shutil.copytree(FIXTURES / "compact-run" / "bt-20260101-000000", mismatch)
            data = load_json(mismatch / "run.json")
            data["runId"] = "bt-20260101-000003"
            data["inputs"]["runId"] = "bt-20260101-000003"
            data["scoreboard"]["runId"] = "bt-20260101-000003"
            data["recordCounts"]["candidate"] = 2
            write_json(mismatch / "run.json", data)
            mismatch_issues = validate_run_dir(mismatch)

        self.assertTrue(any(issue.code == "invalid-json" and issue.path.endswith("run.json") for issue in corrupt_issues))
        self.assertTrue(any(issue.code == "invalid-jsonl" and issue.path.endswith("records.jsonl:1:kind") for issue in unsupported_issues))
        self.assertTrue(any(issue.code == "invalid-jsonl" and issue.path.endswith("records.jsonl:2:seq") for issue in non_monotonic_issues))
        self.assertTrue(any(issue.path.endswith("run.json:recordCounts.candidate") for issue in mismatch_issues))

    def test_duplicate_only_compact_run_is_valid_but_not_promotable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "bt-20260101-000000"
            shutil.copytree(FIXTURES / "compact-run" / "bt-20260101-000000", run_dir)
            run_doc = load_json(run_dir / "run.json")
            run_doc["winnerCandidate"] = None
            run_doc["bestCandidate"] = None
            run_doc["skippedDuplicates"] = 1
            run_doc["promotion"] = {"eligible": False, "candidate": None}
            run_doc["metrics"]["winning-candidate"] = None
            run_doc["metrics"]["best-candidate"] = None
            run_doc["metrics"]["skipped-duplicates"] = 1
            run_doc["scoreboard"]["rankings"]["candidates"] = []
            run_doc["recordCounts"]["round"] = 0
            run_doc["recordCounts"]["reflection"] = 0
            write_json(run_dir / "run.json", run_doc)
            candidate = {
                "candidateFingerprint": "fixture-candidate-fingerprint",
                "candidateId": "candidate-000001",
                "classification": "skipped",
                "components": [],
                "evaluationFingerprint": "fixture-evaluation-fingerprint",
                "metrics": {},
                "parameters": {},
                "priorCandidate": {"runId": "bt-20251231-000000"},
                "reason": "duplicate-evaluation",
                "riskState": {},
                "status": "skipped-duplicate",
            }
            (run_dir / "records.jsonl").write_text(json.dumps({"seq": 1, "kind": "candidate", "data": candidate}) + "\n", encoding="utf-8")

            issues = validate_run_dir(run_dir)
            view = load_run_view(run_dir)

        self.assertEqual(issues, [])
        self.assertTrue(view["duplicateOnly"])
        self.assertFalse(view["promotionEligible"])

    def test_synthetic_run_markers_are_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "bt-20260101-000000"
            shutil.copytree(FIXTURES / "valid-run" / "bt-20260101-000000", run_dir)
            manifest = load_json(run_dir / "manifest.json")
            manifest["execution"]["dataSource"] = "synthetic-default"
            write_json(run_dir / "manifest.json", manifest)
            inputs = load_json(run_dir / "inputs.json")
            inputs["execution"]["dataSource"] = "synthetic-default"
            inputs["history"]["dataSource"] = "synthetic-default"
            inputs["history"]["synthetic"] = True
            inputs["limitations"] = [{"code": "synthetic-default-candles", "message": "legacy synthetic fallback"}]
            write_json(run_dir / "inputs.json", inputs)

            issues = validate_run_dir(run_dir)

        paths = {issue.path for issue in issues if issue.code == "invalid-artifact"}
        self.assertIn(str(run_dir / "manifest.json") + ":execution.dataSource", paths)
        self.assertIn(str(run_dir / "inputs.json") + ":execution.dataSource", paths)
        self.assertIn(str(run_dir / "inputs.json") + ":history.dataSource", paths)
        self.assertIn(str(run_dir / "inputs.json") + ":history.synthetic", paths)
        self.assertIn(str(run_dir / "inputs.json") + ":limitations[0].code", paths)
        self.assertTrue(all("configured real history" in issue.message for issue in issues if issue.path in paths))

    def test_candidate_target_hit_status_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "bt-20260101-000000"
            shutil.copytree(FIXTURES / "valid-run" / "bt-20260101-000000", run_dir)
            (run_dir / "candidates.jsonl").write_text(
                '{"candidateId":"candidate-000001","components":[],"parameters":{},"classification":"winner","status":"target-hit","reason":"target-hit","metrics":{},"candidateFingerprint":"c","evaluationFingerprint":"e"}\n',
                encoding="utf-8",
            )

            issues = validate_run_dir(run_dir)

        self.assertTrue(any("status" in issue.message for issue in issues))

    def test_promoted_robot_contract_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            robot_dir = Path(tmp) / "promoted" / "demo--bt-20260101-000000"
            write_yaml(
                robot_dir / "robot.yml",
                {
                    "schema-version": 1,
                    "robot": {"id": "demo--bt-20260101-000000", "score": 108.1, "score-version": "composite-v1"},
                    "source": {"experiment": "demo", "run-id": "bt-20260101-000000", "candidate-id": "candidate-000001"},
                    "strategy": {"components": [], "parameters": {}},
                    "risk": {"effective": {}},
                    "execution": {"payout": 0.8, "payout-source": "fixed-default"},
                    "promotion": {"timestamp": "2026-01-01T00:00:00+00:00", "metrics": {}},
                },
            )

            issues = validate_promoted_robot_dir(robot_dir)

        self.assertEqual(issues, [])

    def test_promoted_catalog_directory_requires_robot_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            robot_dir = Path(tmp) / "promoted" / "demo--bt-20260101-000000"
            robot_dir.mkdir(parents=True)

            issues = validate_promoted_robot_dir(robot_dir)

        self.assertTrue(any(issue.code == "missing-artifact" and issue.path.endswith("robot.yml") for issue in issues))

    def test_run_ids_accept_backtest_and_simulate_prefixes_without_suffixes(self) -> None:
        self.assertTrue(is_run_id("bt-20260101-000000"))
        self.assertTrue(is_run_id("sim-20260101-000000"))
        self.assertFalse(is_run_id("bt-20260101-000000-extra"))

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

    def test_config_context_paths_must_be_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_artifact_root(root)
            self.assertEqual(validate_config(root), [])

            write_yaml(
                root / "config.yml",
                {
                    "schema-version": 1,
                    "artifact": {"root": str(root)},
                    "contexts": {
                        "promoted": {"path": "promoted"},
                        "archived": {"path": "archive"},
                        "experiment": {"path": "experiments"},
                        "scratch": {"path": "scratch"},
                    },
                },
            )

            issues = validate_config(root)

        paths = {issue.path for issue in issues}
        self.assertIn(str(root / "config.yml") + ":contexts.archived.path", paths)
        self.assertIn(str(root / "config.yml") + ":contexts.experiment.path", paths)
        self.assertIn(str(root / "config.yml") + ":contexts.scratch", paths)

    def test_experiment_and_run_identity_contracts_are_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            upper = Path(tmp) / "Robo-Upper"
            upper.mkdir()
            upper_issues = validate_experiment_dir(upper)

            suffix_run = Path(tmp) / "bt-20260101-000000-extra"
            shutil.copytree(FIXTURES / "valid-run" / "bt-20260101-000000", suffix_run)
            suffix_issues = validate_run_dir(suffix_run)

            mismatch_run = Path(tmp) / "bt-20260101-000000"
            shutil.copytree(FIXTURES / "valid-run" / "bt-20260101-000000", mismatch_run)
            for filename in ("manifest.json", "inputs.json", "scoreboard.json", "metrics.json"):
                data = load_json(mismatch_run / filename)
                data["runId"] = "bt-20260101-000001"
                write_json(mismatch_run / filename, data)
            mismatch_issues = validate_run_dir(mismatch_run, expected_experiment="valid-experiment")

            mode_run = Path(tmp) / "bt-20260101-000002"
            shutil.copytree(FIXTURES / "valid-run" / "bt-20260101-000000", mode_run)
            for filename in ("manifest.json", "inputs.json", "scoreboard.json", "metrics.json"):
                data = load_json(mode_run / filename)
                data["runId"] = "bt-20260101-000002"
                if filename == "manifest.json":
                    data["mode"] = "simulate"
                write_json(mode_run / filename, data)
            mode_issues = validate_run_dir(mode_run)

            simulate_run = Path(tmp) / "sim-20260101-000000"
            shutil.copytree(FIXTURES / "valid-run" / "bt-20260101-000000", simulate_run)
            for filename in ("manifest.json", "inputs.json", "scoreboard.json", "metrics.json"):
                data = load_json(simulate_run / filename)
                data["runId"] = "sim-20260101-000000"
                if filename == "manifest.json":
                    data["mode"] = "simulate"
                write_json(simulate_run / filename, data)
            simulate_issues = validate_run_dir(simulate_run)

        self.assertTrue(any(issue.code == "invalid-name" for issue in upper_issues))
        self.assertTrue(any(issue.code == "invalid-name" for issue in suffix_issues))
        self.assertTrue(any(issue.path.endswith(f"{filename}:runId") for filename in ("manifest.json", "inputs.json", "scoreboard.json", "metrics.json") for issue in mismatch_issues))
        self.assertIn(str(mode_run / "manifest.json") + ":mode", {issue.path for issue in mode_issues})
        self.assertEqual(simulate_issues, [])

    def test_disabled_horizon_validation_does_not_require_gate_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_experiment(root, "idx-m1-soros-reversal")
            experiment = root / "experiment" / "idx-m1-soros-reversal"
            scope = load_yaml(experiment / "search-scope.yml")
            scope["horizon-validation"] = {"enabled": False}
            write_yaml(experiment / "search-scope.yml", scope)

            issues = validate_experiment_dir(experiment)

        self.assertFalse(any("horizon-validation.days" in issue.path or "horizon-validation.gate" in issue.path for issue in issues))

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

    def test_canonical_history_manifest_rejects_noncanonical_csv_path(self) -> None:
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

            noncanonical_path = experiment / "data" / "EURUSD_M1_2026-01-01_2026-01-02.csv"
            noncanonical_path.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
            ingest["data"]["path"] = "data/EURUSD_M1_2026-01-01_2026-01-02.csv"
            write_yaml(experiment / "ingest.yml", ingest)
            noncanonical_issues = validate_experiment_dir(experiment)

        self.assertEqual(valid_issues, [])
        self.assertIn(str(experiment / "ingest.yml") + ":data.path", {issue.path for issue in noncanonical_issues})
        self.assertTrue(any("data/EURUSD_M1.csv" in issue.message for issue in noncanonical_issues))

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
        self.assertIn(str(experiment / "search-scope.yml") + ":components.trigger[1].parameters.side", paths)
        self.assertIn(str(experiment / "search-scope.yml") + ":components.trigger[1].parameters.unknown", paths)
        self.assertIn(str(experiment / "search-scope.yml") + ":components.decision", paths)

    def test_search_scope_rejects_fixed_trigger_side(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_experiment(root, "idx-m1-soros-reversal")
            experiment = root / "experiment" / "idx-m1-soros-reversal"
            scope = load_yaml(experiment / "search-scope.yml")
            scope["components"]["trigger"][0]["parameters"]["side"] = ["call"]
            write_yaml(experiment / "search-scope.yml", scope)

            issues = validate_experiment_dir(experiment)

        self.assertIn(str(experiment / "search-scope.yml") + ":components.trigger[0].parameters.side", {issue.path for issue in issues})
        self.assertTrue(any("derive call or put from the scenario" in issue.message for issue in issues))

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

    def test_ebinex_search_scope_rejects_configurable_expiration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_experiment(root, "idx-m1-soros-reversal")
            experiment = root / "experiment" / "idx-m1-soros-reversal"

            valid_issues = validate_experiment_dir(experiment)
            scope = load_yaml(experiment / "search-scope.yml")
            scope["components"]["decision"][0]["parameters"]["expiration-candles"] = [1]
            write_yaml(experiment / "search-scope.yml", scope)
            rejected_issues = validate_experiment_dir(experiment)

            ingest = load_yaml(experiment / "ingest.yml")
            ingest["data"]["provider"] = "fixture"
            write_yaml(experiment / "ingest.yml", ingest)
            fixture_issues = validate_experiment_dir(experiment)

        self.assertEqual(valid_issues, [])
        self.assertIn(str(experiment / "search-scope.yml") + ":components.decision[0].parameters.expiration-candles", {issue.path for issue in rejected_issues})
        self.assertTrue(any("remove expiration-candles" in issue.message for issue in rejected_issues))
        self.assertEqual(fixture_issues, [])

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

    def test_canonical_history_manifest_rejects_empty_or_offline_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_experiment(root, "idx-m1-soros-reversal")
            experiment = root / "experiment" / "idx-m1-soros-reversal"
            csv_path = experiment / "data" / "EURUSD_M1.csv"
            csv_path.write_text("time,asset,timeframe,open,high,low,close\n", encoding="utf-8")
            ingest = load_yaml(experiment / "ingest.yml")
            ingest["data"]["path"] = "data/EURUSD_M1.csv"
            write_yaml(experiment / "ingest.yml", ingest)
            write_json(
                experiment / "data" / "EURUSD_M1.manifest.json",
                {
                    "asset": "EURUSD",
                    "timeframe": "M1",
                    "requestedRange": {"from": "2026-01-01", "to": "2026-01-02"},
                    "coverageRange": {"from": "2026-01-01", "to": "2026-01-02"},
                    "path": "data/EURUSD_M1.csv",
                    "candleCount": 0,
                    "sha256": file_sha256(csv_path),
                    "provider": "ebinex",
                    "providerMode": "offline-contract",
                    "downloadedAt": "2026-01-01T00:00:00Z",
                },
            )

            issues = validate_experiment_dir(experiment)

        paths = {issue.path for issue in issues}
        self.assertIn(str(experiment / "data" / "EURUSD_M1.manifest.json") + ":candleCount", paths)
        self.assertIn(str(experiment / "data" / "EURUSD_M1.manifest.json") + ":providerMode", paths)

    def test_horizons_jsonl_is_validated_as_optional_detail_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "bt-20260101-000000"
            shutil.copytree(FIXTURES / "valid-run" / "bt-20260101-000000", run_dir)
            (run_dir / "horizons.jsonl").write_text("{bad-json\n", encoding="utf-8")

            issues = validate_run_dir(run_dir)

        self.assertTrue(any(issue.code == "invalid-jsonl" and "horizons.jsonl" in issue.path for issue in issues))

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
