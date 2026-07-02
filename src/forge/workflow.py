from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from forge.archive import service as archive_service
from forge.assets import service as assets_service
from forge.common import dry_status, parse_options, result_error
from forge.compare import service as compare_service
from forge.context import CommandContext
from forge.experiment import service as experiment_service
from forge.export import service as export_service
from forge.history import service as history_service
from forge.payout import service as payout_service
from forge.promote import service as promote_service
from forge.report import service as report_service
from forge.responses import fail, ok, read_only_action_context
from forge.run import service as run_service
from forge.status import service as status_service
from forge.validate import service as validate_service
from xenibe.artifacts.store import experiment_dir, init_artifact_root, load_yaml


Handler = Callable[[list[str], CommandContext], dict[str, Any]]


def _workflow_next_for_experiment(root: Path, experiment: str) -> list[str]:
    return [
        f"forge data download EURUSD --experiment {experiment} --timeframe M1 --from 2026-01-01 --to 2026-01-02 --root {root} --json",
        f"forge backtest {experiment} --root {root} --json",
    ]


def _reject_extra(command: str, extra: str, usage: str) -> dict[str, Any]:
    return fail(
        "unknown-command",
        f"unknown {command} argument: {extra}",
        [usage],
        target="command.args",
        fix=f"run {usage}",
    )


def _reject_legacy_shape(command: str, legacy: str, usage: str) -> dict[str, Any]:
    return fail(
        "unknown-command",
        f"legacy command shape removed: forge {command} {legacy}",
        [usage],
        target="command.name",
        fix=f"run {usage}",
    )


def _fail_from_result(result: dict[str, Any], fallback_next: list[str]) -> dict[str, Any]:
    error = result_error(result)
    if error is None:
        raise ValueError("result does not contain an error")
    next_actions = result.get("next") if isinstance(result.get("next"), list) else fallback_next
    return fail(error[0], error[1], next_actions, {"issues": result.get("issues", [])})


def new(args: list[str], context: CommandContext) -> dict[str, Any]:
    if not args:
        return fail("missing-name", "experiment name required", ["forge new idx-m1-soros-reversal --json"])
    if len(args) > 1:
        return _reject_extra("new", args[1], "forge new <experiment> --json")
    experiment = args[0]
    if context.dry_run:
        result = experiment_service.create(context.root, experiment, dry_run=True)
        error = result_error(result)
        if error is not None:
            return fail(error[0], error[1], result.get("next"))
        data = {
            "artifactRoot": str(context.root),
            "experiment": experiment,
            "path": result["path"],
            "plannedActions": [
                "create artifact root if missing",
                "create promoted, archived, and experiment directories if missing",
                "write config.yml if missing",
                *result.get("plannedActions", []),
            ],
        }
        return ok(data, _workflow_next_for_experiment(context.root, experiment), "dry-run")

    created = init_artifact_root(context.root)
    result = experiment_service.create(context.root, experiment, dry_run=False)
    error = result_error(result)
    if error is not None:
        return fail(error[0], error[1], result.get("next"))
    data = {
        **result,
        "artifactRoot": str(context.root),
        "createdRootArtifacts": [str(path) for path in created],
    }
    return ok(data, _workflow_next_for_experiment(context.root, experiment), dry_status(context.dry_run))


def status(args: list[str], context: CommandContext) -> dict[str, Any]:
    if args:
        return _reject_extra("status", args[0], "forge status --json")
    data = status_service.inspect_root(context.root)
    return ok(data, status_service.next_actions(context.root, data), action_context=read_only_action_context(context.root))


def check(args: list[str], context: CommandContext) -> dict[str, Any]:
    if len(args) > 2:
        return _reject_extra("check", args[2], "forge check [experiment] [run-id] --json")
    if not args:
        result = validate_service.validate_root(context.root)
        if not result["valid"]:
            return fail("invalid-artifact", "artifact root validation failed", ["fix reported artifact issues", f"forge check --root {context.root} --json"], {"issues": result["issues"]})
        return ok(result, [f"forge status --root {context.root} --json"], "validated", read_only_action_context(context.root))
    if len(args) == 1:
        experiment = args[0]
        result = experiment_service.validate(context.root, experiment)
        if not result["valid"]:
            return fail("invalid-artifact", "experiment validation failed", [f"fix reported artifacts under {experiment_dir(context.root, experiment)}", f"forge check {experiment} --root {context.root} --json"], {"issues": result["issues"]})
        return ok(result, [f"forge backtest {experiment} --root {context.root} --json"], "validated", read_only_action_context(context.root))
    experiment, run_id = args
    result = run_service.validate_run(context.root, experiment, run_id)
    if not result["valid"]:
        return fail("invalid-artifact", "run validation failed", [f"inspect {experiment_dir(context.root, experiment) / 'runs' / run_id}", f"forge show {experiment} {run_id} --root {context.root} --json"], {"issues": result["issues"]})
    return ok(result, [f"forge show {experiment} {run_id} --root {context.root} --json"], "validated", read_only_action_context(context.root))


def _data_summary(base: Path) -> dict[str, Any]:
    data_dir = base / "data"
    files = sorted(str(path.relative_to(base)) for path in data_dir.rglob("*") if path.is_file()) if data_dir.exists() else []
    manifests = [name for name in files if name.endswith(".manifest.json")]
    csvs = [name for name in files if name.endswith(".csv")]
    return {"path": str(data_dir), "fileCount": len(files), "csvCount": len(csvs), "manifestCount": len(manifests), "files": files[:20]}


def _best_known_run(latest_runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    ranked = [
        run
        for run in latest_runs
        if not run.get("duplicateOnly") and isinstance(run.get("metrics"), dict) and run["metrics"].get("net-profit") is not None
    ]
    if not ranked:
        return next((run for run in latest_runs if not run.get("duplicateOnly")), latest_runs[0] if latest_runs else None)
    return max(ranked, key=lambda run: float(run.get("metrics", {}).get("net-profit") or 0.0))


def _promotion_status(root: Path, experiment: str, run_id: str) -> dict[str, Any]:
    promoted = root / "promoted"
    if promoted.exists():
        for robot_dir in sorted(path for path in promoted.iterdir() if path.is_dir()):
            path = robot_dir / "robot.yml"
            if not path.exists():
                continue
            try:
                robot = load_yaml(path)
            except Exception:
                continue
            source = robot.get("source", {})
            if isinstance(source, dict) and source.get("experiment") == experiment and source.get("run-id") == run_id:
                return {"promoted": True, "robotId": robot_dir.name, "path": str(path)}
    return {"promoted": False}


def show(args: list[str], context: CommandContext) -> dict[str, Any]:
    if len(args) > 2:
        return _reject_extra("show", args[2], "forge show [experiment] [run-id] --json")
    if not args:
        data = status_service.inspect_root(context.root)
        return ok(data, status_service.next_actions(context.root, data), action_context=read_only_action_context(context.root))
    experiment = args[0]
    if len(args) == 1:
        root_data = status_service.inspect_root(context.root)
        summary = next((item for item in root_data.get("experiments", []) if item.get("name") == experiment), None)
        if summary is None:
            return fail("missing-artifact", "experiment not found", [f"forge new {experiment} --root {context.root} --json", f"forge status --root {context.root} --json"])
        try:
            files = experiment_service.show(context.root, experiment)["files"]
        except Exception as exc:
            return fail("missing-artifact", str(exc), [f"forge check {experiment} --root {context.root} --json"])
        best_run = _best_known_run(summary.get("latestRuns", []))
        data = {
            "experiment": experiment,
            "path": summary["path"],
            "valid": summary["valid"],
            "issues": summary["issues"],
            "configSummary": files,
            "dataSummary": _data_summary(Path(summary["path"])),
            "recentRuns": summary.get("latestRuns", []),
            "bestKnownRun": best_run,
            "bestKnownCandidate": (best_run or {}).get("scoreboard", {}).get("topCandidate") if best_run else None,
            "artifactPaths": summary.get("artifactPaths", {}),
        }
        return ok(data, [f"forge backtest {experiment} --root {context.root} --json", f"forge check {experiment} --root {context.root} --json"], action_context=read_only_action_context(context.root))

    run_id = args[1]
    result = run_service.show_run(context.root, experiment, run_id)
    error = result_error(result)
    if error is not None:
        return _fail_from_result(result, [f"forge check {experiment} {run_id} --root {context.root} --json"])
    report = report_service.show(context.root, experiment, run_id)
    error = result_error(report)
    if error is not None:
        return _fail_from_result(report, [f"forge check {experiment} {run_id} --root {context.root} --json"])
    summary = status_service.run_summary(experiment_dir(context.root, experiment) / "runs" / run_id)
    data = {
        **result,
        "report": report.get("report"),
        "reportPath": report.get("reportPath"),
        "artifactPaths": summary.get("artifactPaths", {}),
        "promotionStatus": _promotion_status(context.root, experiment, run_id),
    }
    return ok(data, [f"forge compare {experiment} {run_id} <other-run-id> --root {context.root} --json", f"forge promote {experiment} {run_id} --root {context.root} --json"], action_context=read_only_action_context(context.root))


def data(args: list[str], context: CommandContext) -> dict[str, Any]:
    if not args:
        return fail("missing-command", "data command required", ["forge data list --json", "forge data download <asset> --experiment <experiment> --timeframe M1 --from <start> --to <end> --json"])
    command = args[0]
    if command == "list":
        if len(args) > 1:
            return _reject_extra("data list", args[1], "forge data list --json")
        result = assets_service.list_assets(context)
        error = result_error(result)
        if error is not None:
            return fail(error[0], error[1], ["configure Ebinex credentials and install the Ebinex provider dependency"], {"provider": "ebinex"})
        for asset in result.get("assets", []):
            asset_id = asset.get("id") or asset.get("asset") or asset.get("symbol")
            if "payout" not in asset and asset_id is not None:
                payout = payout_service.get_payout(context, str(asset_id))
                if result_error(payout) is None and payout.get("payout") is not None:
                    asset["payout"] = payout["payout"]
        return ok(result, ["forge data download <asset> --experiment <experiment> --timeframe M1 --from <start> --to <end> --json"], dry_status(context.dry_run, "ok"))
    if command != "download":
        return fail("unknown-command", f"unknown data command: {command}", ["forge data list --json", "forge data download <asset> --experiment <experiment> --timeframe M1 --from <start> --to <end> --json"])

    replace = "--replace" in args[1:]
    download_args = [arg for arg in args[1:] if arg != "--replace"]
    parsed = parse_options(download_args, {"--experiment", "--timeframe", "--from", "--to"})
    if parsed.missing_value is not None:
        return fail("missing-name", f"{parsed.missing_value} requires a value", ["forge data download EURUSD --experiment <experiment> --timeframe M1 --from 2026-01-01 --to 2026-01-02 --json"])
    if not parsed.positionals:
        return fail("missing-name", "data download requires asset", ["forge data list --json"])
    if len(parsed.positionals) > 1:
        return _reject_extra("data download", parsed.positionals[1], "forge data download <asset> --experiment <experiment> --timeframe M1 --from <start> --to <end> --json")
    asset = parsed.positionals[0]
    experiment = parsed.options.get("--experiment")
    timeframe = parsed.options.get("--timeframe")
    start = parsed.options.get("--from")
    end = parsed.options.get("--to")
    if not experiment:
        return fail("missing-name", "data download requires --experiment", ["forge data download EURUSD --experiment <experiment> --timeframe M1 --from 2026-01-01 --to 2026-01-02 --json"])
    if not timeframe or not start or not end:
        return fail("missing-name", "data download requires --timeframe, --from, and --to", ["forge data download EURUSD --experiment <experiment> --timeframe M1 --from 2026-01-01 --to 2026-01-02 --json"])
    result = history_service.download(context, experiment, asset, timeframe, start, end, replace=replace)
    error = result_error(result)
    if error is not None:
        next_actions = result.get("next") if isinstance(result.get("next"), list) else ["configure Ebinex credentials and install the Ebinex provider dependency"]
        payload = {
            "asset": asset,
            "path": result.get("path"),
            "manifestPath": result.get("manifestPath"),
            "requestedRange": result.get("requestedRange"),
            "coverageRange": result.get("coverageRange"),
        }
        return fail(error[0], error[1], next_actions, payload)
    return ok(result, [f"forge backtest {experiment} --root {context.root} --json"], dry_status(context.dry_run))


def backtest(args: list[str], context: CommandContext) -> dict[str, Any]:
    if "--allow-synthetic" in args:
        parsed_without_removed = parse_options([arg for arg in args if arg != "--allow-synthetic"], {"--mode", "--run-id"})
        experiment = parsed_without_removed.positionals[0] if parsed_without_removed.positionals else "<experiment>"
        next_action = f"forge data download <asset> --experiment {experiment} --timeframe M1 --from <from> --to <to> --root {context.root} --json"
        return fail(
            "unknown-command",
            "--allow-synthetic has been removed; configure or download real history before running backtest",
            [next_action],
            {"removedOption": "--allow-synthetic"},
            target="command.args",
            fix=next_action,
        )
    parsed = parse_options(args, {"--mode", "--run-id"})
    if parsed.missing_value is not None:
        return fail("missing-name", f"{parsed.missing_value} requires a value", [f"forge backtest <experiment> {parsed.missing_value} <value> --json"])
    if not parsed.positionals:
        return fail("missing-name", "experiment name required", ["forge show --json"])
    if len(parsed.positionals) > 1:
        return _reject_extra("backtest", parsed.positionals[1], "forge backtest <experiment> [--mode backtest|simulate] --json")
    experiment = parsed.positionals[0]
    mode = parsed.options.get("--mode", "backtest")
    result = run_service.run_backtest(context.root, experiment, mode, parsed.options.get("--run-id"), context.dry_run)
    error = result_error(result)
    if error is not None:
        return _fail_from_result(result, [f"forge check {experiment} --root {context.root} --json"])
    return ok(
        result,
        [f"forge show {experiment} {result['runId']} --root {context.root} --json", f"forge promote {experiment} {result['runId']} --root {context.root} --json"],
        dry_status(context.dry_run),
    )


def compare(args: list[str], context: CommandContext) -> dict[str, Any]:
    if args and args[0] == "runs":
        return _reject_legacy_shape("compare", "runs", "forge compare <experiment> <run-id-a> <run-id-b> --json")
    if len(args) < 3:
        return fail("missing-name", "compare requires experiment and at least two run ids", ["forge show <experiment> --json"])
    experiment = args[0]
    result = compare_service.compare_runs(context.root, experiment, args[1:])
    error = result_error(result)
    if error is not None:
        return _fail_from_result(result, [f"forge check {experiment} {result.get('runId') or '<run-id>'} --root {context.root} --json"])
    return ok(result, [f"forge promote {experiment} {result.get('bestRunId') or '<run-id>'} --root {context.root} --json"])


def promote(args: list[str], context: CommandContext) -> dict[str, Any]:
    parsed = parse_options(args, {"--reason"})
    if parsed.missing_value is not None:
        return fail("missing-name", f"{parsed.missing_value} requires a value", ["forge promote <experiment> <run-id> --reason <reason> --json"])
    if len(parsed.positionals) < 2:
        return fail("missing-name", "promote requires experiment and run id", ["forge show <experiment> --json"])
    if parsed.positionals[0] == "run":
        return _reject_legacy_shape("promote", "run", "forge promote <experiment> <run-id> [--reason <reason>] --json")
    if len(parsed.positionals) > 2:
        return _reject_extra("promote", parsed.positionals[2], "forge promote <experiment> <run-id> [--reason <reason>] --json")
    experiment, run_id = parsed.positionals
    result = promote_service.promote_run(context.root, experiment, run_id, parsed.options.get("--reason"), context.dry_run)
    error = result_error(result)
    if error is not None:
        return _fail_from_result(result, [f"forge check {experiment} {run_id} --root {context.root} --json"])
    return ok(result, [f"forge archive {experiment} --root {context.root} --json"], dry_status(context.dry_run))


def archive(args: list[str], context: CommandContext) -> dict[str, Any]:
    if not args:
        return fail("missing-name", "archive requires experiment", ["forge show --json"])
    if len(args) > 1:
        return _reject_extra("archive", args[1], "forge archive <experiment> --json")
    experiment = args[0]
    result = archive_service.archive_experiment(context.root, experiment, context.dry_run)
    error = result_error(result)
    if error is not None:
        return _fail_from_result(result, [f"forge show --root {context.root} --json"])
    return ok(result, [f"forge show --root {context.root} --json"], dry_status(context.dry_run))


def export(args: list[str], context: CommandContext) -> dict[str, Any]:
    if not args:
        return fail("missing-name", "export requires experiment", ["forge export <experiment> [run-id] --json"])
    if args[0] in {"run", "experiment"}:
        return _reject_legacy_shape("export", args[0], "forge export <experiment> [run-id] --json")
    if len(args) > 2:
        return _reject_extra("export", args[2], "forge export <experiment> [run-id] --json")
    experiment = args[0]
    if len(args) == 1:
        result = export_service.export_experiment(context.root, experiment, context.dry_run)
        fallback = [f"forge show {experiment} --root {context.root} --json"]
    else:
        run_id = args[1]
        result = export_service.export_run(context.root, experiment, run_id, context.dry_run)
        fallback = [f"forge check {experiment} {run_id} --root {context.root} --json"]
    error = result_error(result)
    if error is not None:
        return _fail_from_result(result, fallback)
    return ok(result, ["share or inspect the export artifact"], dry_status(context.dry_run))


WORKFLOW_HANDLERS: dict[str, Handler] = {
    "new": new,
    "status": status,
    "show": show,
    "check": check,
    "data": data,
    "backtest": backtest,
    "compare": compare,
    "promote": promote,
    "archive": archive,
    "export": export,
}
