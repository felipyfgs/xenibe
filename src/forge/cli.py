from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

from forge.responses import emit, fail, ok
from xenibe.artifacts.naming import is_kebab, is_run_id
from xenibe.artifacts.store import (
    ImmutableRunError,
    append_jsonl,
    complete_run,
    create_experiment,
    ensure_run_artifacts,
    init_artifact_root,
    list_experiments,
    load_experiment,
    make_run_id,
    utc_now,
    validate_experiment_dir,
    validate_run_dir,
    write_json,
    write_yaml,
)
from xenibe.backtest import run_m1_backtest
from xenibe.candles import Candle
from xenibe.strategy import generate_candidates, resolve_limits, target_satisfied


def default_root() -> Path:
    return Path(os.environ.get("FORGE_ROOT", Path.cwd() / "forge")).resolve()


def parse_global(argv: list[str]) -> tuple[list[str], Path, bool]:
    args: list[str] = []
    root = default_root()
    as_json = False
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == "--json":
            as_json = True
            index += 1
        elif item == "--root":
            root = Path(argv[index + 1]).resolve()
            index += 2
        else:
            args.append(item)
            index += 1
    return args, root, as_json


def default_candles() -> list[Candle]:
    return [
        Candle("2026-01-01T00:00:00Z", 1.0, 1.2, 0.9, 1.1),
        Candle("2026-01-01T00:01:00Z", 1.1, 1.2, 1.0, 1.0),
        Candle("2026-01-01T00:02:00Z", 1.0, 1.2, 0.9, 1.15),
        Candle("2026-01-01T00:03:00Z", 1.15, 1.16, 0.95, 1.0),
    ]


def issues_payload(issues: list[Any]) -> list[dict[str, str]]:
    return [{"code": issue.code, "path": issue.path, "message": issue.message} for issue in issues]


def handle_init(root: Path) -> dict[str, Any]:
    created = init_artifact_root(root)
    return ok(
        {"artifactRoot": str(root), "created": [str(path) for path in created]},
        [f"forge experiment new idx-m1-soros-reversal --root {root} --json"],
        "created",
    )


def handle_experiment(args: list[str], root: Path) -> dict[str, Any]:
    if not args:
        return fail("missing-command", "experiment command required", ["forge experiment list --json"])
    command = args[0]
    if command == "new":
        if len(args) < 2:
            return fail("missing-name", "experiment name required", ["forge experiment new idx-m1-soros-reversal --json"])
        name = args[1]
        if not is_kebab(name):
            return fail("invalid-name", "experiment name must use kebab-case", ["choose a kebab-case experiment name"])
        path = create_experiment(root, name)
        return ok(
            {"experiment": name, "path": str(path)},
            [f"forge experiment validate {name} --root {root} --json", f"forge run backtest {name} --root {root} --json"],
            "created",
        )
    if command == "list":
        return ok({"experiments": list_experiments(root)}, ["forge experiment show <name> --json"])
    if command == "show":
        if len(args) < 2:
            return fail("missing-name", "experiment name required", ["forge experiment list --json"])
        name = args[1]
        try:
            data = load_experiment(root, name)
        except Exception as exc:
            return fail("missing-artifact", str(exc), [f"forge experiment validate {name} --root {root} --json"])
        return ok({"experiment": name, "files": data}, [f"forge run backtest {name} --root {root} --json"])
    if command == "validate":
        if len(args) < 2:
            return fail("missing-name", "experiment name required", ["forge experiment list --json"])
        name = args[1]
        issues = validate_experiment_dir(root / name)
        if issues:
            return fail("invalid-artifact", "experiment validation failed", [f"fix artifacts under {root / name}"], {"issues": issues_payload(issues)})
        return ok({"experiment": name, "valid": True}, [f"forge run backtest {name} --root {root} --json"], "validated")
    return fail("unknown-command", f"unknown experiment command: {command}", ["forge experiment list --json"])


def handle_run(args: list[str], root: Path) -> dict[str, Any]:
    if not args:
        return fail("missing-command", "run command required", ["forge run list <experiment> --json"])
    command = args[0]
    if command in {"backtest", "simulate"}:
        if len(args) < 2:
            return fail("missing-name", "experiment name required", ["forge experiment list --json"])
        experiment = args[1]
        mode = "simulate" if command == "simulate" else "backtest"
        prefix = "sim" if mode == "simulate" else "bt"
        run_id = args[args.index("--run-id") + 1] if "--run-id" in args else make_run_id(prefix)
        if not is_run_id(run_id):
            return fail("invalid-name", "run id must use bt-YYYYMMDD-HHMMSS or sim-YYYYMMDD-HHMMSS", ["omit --run-id to generate one"])
        issues = validate_experiment_dir(root / experiment)
        if issues:
            return fail("invalid-artifact", "experiment validation failed", [f"forge experiment validate {experiment} --root {root} --json"], {"issues": issues_payload(issues)})
        configs = load_experiment(root, experiment)
        resolved_limits = resolve_limits(configs["searchscope.yml"])
        candidates = generate_candidates(configs["searchscope.yml"], resolved_limits)
        result = run_m1_backtest(default_candles(), risk_config=configs["risk.yml"])
        tested = []
        winning_candidate = None
        target = configs["experiment.yml"]["target"]
        for candidate in candidates:
            record = {**candidate, "status": "tested", "metrics": result["metrics"]}
            if target_satisfied(result["metrics"], target):
                record["status"] = "target-hit"
                winning_candidate = record["candidateId"]
                tested.append(record)
                if configs["experiment.yml"].get("stop-on-target", True):
                    break
            tested.append(record)
        result["metrics"]["winning-candidate"] = winning_candidate
        run_dir = root / experiment / "runs" / run_id
        ensure_run_artifacts(
            run_dir,
            run_id,
            experiment,
            mode,
            {"experiment": configs["experiment.yml"], "ingest": configs["ingest.yml"], "searchscope": configs["searchscope.yml"], "risk": configs["risk.yml"], "provider": configs["provider.yml"], "report": configs["report.yml"]},
            {"resolvedLimits": resolved_limits},
        )
        for candidate in tested:
            append_jsonl(run_dir / "candidates.jsonl", candidate)
        for name in ("signals", "orders", "trades", "blocks", "equity"):
            for record in result[name]:
                append_jsonl(run_dir / f"{name}.jsonl", record)
        report = f"# Run {run_id}\n\n- Experiment: `{experiment}`\n- Winning candidate: `{winning_candidate}`\n- Win rate: {result['metrics']['win-rate']:.4f}\n"
        complete_run(run_dir, result["metrics"], report)
        return ok(
            {"experiment": experiment, "runId": run_id, "path": str(run_dir), "metrics": result["metrics"]},
            [f"forge run show {experiment} {run_id} --root {root} --json", f"forge promote {experiment} {run_id} --root {root} --json"],
            "created",
        )
    if command == "list":
        if len(args) < 2:
            return fail("missing-name", "experiment name required", ["forge experiment list --json"])
        runs = root / args[1] / "runs"
        return ok({"experiment": args[1], "runs": sorted(path.name for path in runs.iterdir() if path.is_dir()) if runs.exists() else []}, ["forge run show <experiment> <run-id> --json"])
    if command == "show":
        if len(args) < 3:
            return fail("missing-name", "experiment and run id required", ["forge run list <experiment> --json"])
        run_dir = root / args[1] / "runs" / args[2]
        if not run_dir.exists():
            return fail("missing-artifact", "run not found", [f"forge run list {args[1]} --root {root} --json"])
        metrics = {}
        metrics_path = run_dir / "metrics.json"
        if metrics_path.exists():
            import json

            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        return ok({"experiment": args[1], "runId": args[2], "path": str(run_dir), "metrics": metrics}, [f"forge report {args[1]} {args[2]} --root {root} --json"])
    if command == "validate":
        if len(args) < 3:
            return fail("missing-name", "experiment and run id required", ["forge run list <experiment> --json"])
        issues = validate_run_dir(root / args[1] / "runs" / args[2])
        if issues:
            return fail("invalid-artifact", "run validation failed", [f"inspect {root / args[1] / 'runs' / args[2]}"], {"issues": issues_payload(issues)})
        return ok({"experiment": args[1], "runId": args[2], "valid": True}, [f"forge report {args[1]} {args[2]} --root {root} --json"], "validated")
    return fail("unknown-command", f"unknown run command: {command}", ["forge run list <experiment> --json"])


def handle_report(args: list[str], root: Path) -> dict[str, Any]:
    if len(args) < 2:
        return fail("missing-name", "report requires experiment and run id", ["forge run list <experiment> --json"])
    report_path = root / args[0] / "runs" / args[1] / "report.md"
    if not report_path.exists():
        return fail("missing-artifact", "report not found", [f"forge run validate {args[0]} {args[1]} --root {root} --json"])
    return ok({"experiment": args[0], "runId": args[1], "report": report_path.read_text(encoding="utf-8")}, [f"forge promote {args[0]} {args[1]} --root {root} --json"])


def handle_promote(args: list[str], root: Path) -> dict[str, Any]:
    if len(args) < 2:
        return fail("missing-name", "promote requires experiment and run id", ["forge run list <experiment> --json"])
    experiment, run_id = args[0], args[1]
    run_dir = root / experiment / "runs" / run_id
    issues = validate_run_dir(run_dir)
    if issues:
        return fail("invalid-artifact", "run must be valid before promotion", [f"forge run validate {experiment} {run_id} --root {root} --json"], {"issues": issues_payload(issues)})
    target = root / "promoted" / experiment
    target.mkdir(parents=True, exist_ok=True)
    promotion = {"source-experiment": experiment, "source-run-id": run_id, "reason": "target metric satisfied", "timestamp": utc_now()}
    write_yaml(target / "promotion.yml", promotion)
    return ok({"experiment": experiment, "runId": run_id, "promotion": str(target / "promotion.yml")}, [f"forge archive {experiment} --root {root} --json"], "created")


def handle_archive(args: list[str], root: Path) -> dict[str, Any]:
    if not args:
        return fail("missing-name", "archive requires experiment name", ["forge experiment list --json"])
    experiment = args[0]
    source = root / experiment
    if not source.exists():
        return fail("missing-artifact", "experiment not found", [f"forge experiment list --root {root} --json"])
    target = root / "archived" / f"{experiment}-{utc_now().replace(':', '').replace('+', 'z')}"
    shutil.copytree(source, target)
    write_yaml(target / "archive.yml", {"source-experiment": experiment, "timestamp": utc_now()})
    return ok({"experiment": experiment, "archive": str(target)}, ["forge experiment list --json"], "created")


def handle_compare(args: list[str], root: Path) -> dict[str, Any]:
    if len(args) < 3:
        return fail("missing-name", "compare requires experiment and at least two run ids", ["forge run list <experiment> --json"])
    experiment = args[0]
    rows = []
    for run_id in args[1:]:
        metrics_path = root / experiment / "runs" / run_id / "metrics.json"
        if metrics_path.exists():
            import json

            metrics = json.loads(metrics_path.read_text(encoding="utf-8")).get("metrics", {})
            rows.append({"runId": run_id, "winRate": metrics.get("win-rate"), "netProfit": metrics.get("net-profit")})
    return ok({"experiment": experiment, "runs": rows}, ["forge promote <experiment> <run-id> --json"])


def handle_export(args: list[str], root: Path) -> dict[str, Any]:
    if not args:
        return fail("missing-name", "export requires experiment name", ["forge experiment list --json"])
    experiment = args[0]
    target = root / "exports" / f"{experiment}-{make_run_id('sim')}.json"
    write_json(target, {"experiment": experiment, "exportedAt": utc_now(), "source": str(root / experiment)})
    return ok({"experiment": experiment, "export": str(target)}, ["share or inspect the export artifact"], "created")


def handle_provider_view(command: str, args: list[str]) -> dict[str, Any]:
    if command == "assets":
        return ok({"assets": [], "provider": "ebinex", "mode": "offline-contract"}, ["configure provider.yml before live provider calls"])
    if command == "payout":
        asset = args[0] if args else "EURUSD"
        return ok({"asset": asset, "payout": None, "provider": "ebinex", "mode": "offline-contract"}, ["connect Ebinex provider to fetch live payout"])
    if command == "history":
        return ok({"orders": [], "provider": "ebinex", "mode": "offline-contract"}, ["connect Ebinex provider to fetch order history"])
    return fail("unknown-command", f"unknown provider command: {command}", ["forge assets --json"])


def handle_validate(root: Path) -> dict[str, Any]:
    issues = []
    for experiment in list_experiments(root):
        issues.extend(validate_experiment_dir(root / experiment))
        runs = root / experiment / "runs"
        if runs.exists():
            for run_dir in runs.iterdir():
                if run_dir.is_dir():
                    issues.extend(validate_run_dir(run_dir))
    if issues:
        return fail("invalid-artifact", "artifact root validation failed", ["fix reported artifact issues"], {"issues": issues_payload(issues)})
    return ok({"artifactRoot": str(root), "valid": True}, ["forge experiment list --json"], "validated")


def dispatch(args: list[str], root: Path) -> dict[str, Any]:
    if not args:
        return fail("missing-command", "command required", ["forge init --json", "forge experiment list --json"])
    command = args[0]
    try:
        if command == "init":
            return handle_init(root)
        if command == "experiment":
            return handle_experiment(args[1:], root)
        if command == "run":
            return handle_run(args[1:], root)
        if command == "report":
            return handle_report(args[1:], root)
        if command == "promote":
            return handle_promote(args[1:], root)
        if command == "archive":
            return handle_archive(args[1:], root)
        if command == "compare":
            return handle_compare(args[1:], root)
        if command == "export":
            return handle_export(args[1:], root)
        if command in {"assets", "payout", "history"}:
            return handle_provider_view(command, args[1:])
        if command == "validate":
            return handle_validate(root)
    except ImmutableRunError as exc:
        return fail("immutable-run", str(exc), ["create a new run-id or write an audit artifact"])
    except FileExistsError as exc:
        return fail("invalid-artifact", f"artifact already exists: {exc}", ["choose a different name or inspect the existing artifact"])
    except Exception as exc:
        return fail("unexpected-error", str(exc), ["run the command again with --json and inspect status"])
    return fail("unknown-command", f"unknown command: {command}", ["forge init --json", "forge experiment list --json"])


def main(argv: list[str] | None = None) -> int:
    args, root, as_json = parse_global(list(sys.argv[1:] if argv is None else argv))
    response = dispatch(args, root)
    emit(response, as_json)
    return 1 if any(item["level"] == "error" for item in response["status"]) else 0
