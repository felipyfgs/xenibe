from __future__ import annotations

from typing import Any

from forge.compare import service as compare_service
from forge.common import dry_status, parse_options, result_error
from forge.context import CommandContext
from forge.export import service as export_service
from forge.promote import service as promote_service
from forge.responses import fail, ok

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if not args:
        return fail("missing-command", "run command required", ["forge run list <experiment> --json"])
    command = args[0]
    if command == "backtest":
        allow_synthetic = "--allow-synthetic" in args[1:]
        command_args = [arg for arg in args[1:] if arg != "--allow-synthetic"]
        parsed = parse_options(command_args, {"--run-id"})
        if parsed.missing_value is not None:
            return fail("missing-name", f"{parsed.missing_value} requires a value", [f"forge run {command} <experiment> {parsed.missing_value} <value> --json"])
        if not parsed.positionals:
            return fail("missing-name", "experiment name required", ["forge experiment list --json"])
        experiment = parsed.positionals[0]
        result = service.run_backtest(context.root, experiment, "backtest", parsed.options.get("--run-id"), context.dry_run, allow_synthetic)
        error = result_error(result)
        if error is not None:
            next_actions = result.get("next") if isinstance(result.get("next"), list) else [f"forge experiment validate {experiment} --root {context.root} --json"]
            return fail(error[0], error[1], next_actions, {"issues": result.get("issues", [])})
        return ok(
            result,
            [f"forge run show {experiment} {result['runId']} --root {context.root} --json", f"forge run promote {experiment} {result['runId']} --root {context.root} --json"],
            dry_status(context.dry_run),
        )
    if command == "list":
        if len(args) < 2:
            return fail("missing-name", "experiment name required", ["forge experiment list --json"])
        return ok(service.list_runs(context.root, args[1]), ["forge run show <experiment> <run-id> --json"])
    if command == "show":
        if len(args) < 3:
            return fail("missing-name", "experiment and run id required", ["forge run list <experiment> --json"])
        result = service.show_run(context.root, args[1], args[2])
        error = result_error(result)
        if error is not None:
            return fail(error[0], error[1], [f"forge run list {args[1]} --root {context.root} --json"])
        return ok(result, [f"forge report show {args[1]} {args[2]} --root {context.root} --json"])
    if command == "validate":
        if len(args) < 3:
            return fail("missing-name", "experiment and run id required", ["forge run list <experiment> --json"])
        result = service.validate_run(context.root, args[1], args[2])
        if not result["valid"]:
            return fail("invalid-artifact", "run validation failed", [f"inspect {context.root / 'experiment' / args[1] / 'runs' / args[2]}"], {"issues": result["issues"]})
        return ok(result, [f"forge report show {args[1]} {args[2]} --root {context.root} --json"], "validated")
    if command == "compare":
        if len(args) < 4:
            return fail("missing-name", "run compare requires experiment and at least two run ids", ["forge run list <experiment> --json"])
        experiment = args[1]
        run_ids = args[2:]
        result = compare_service.compare_runs(context.root, experiment, run_ids)
        error = result_error(result)
        if error is not None:
            return fail(error[0], error[1], [f"forge run validate {experiment} {result.get('runId') or '<run-id>'} --root {context.root} --json"], {"issues": result.get("issues", [])})
        return ok(result, [f"forge run promote {experiment} {result.get('bestRunId') or '<run-id>'} --root {context.root} --json"])
    if command == "promote":
        parsed = parse_options(args[1:], {"--reason"})
        if parsed.missing_value is not None:
            return fail("missing-name", f"{parsed.missing_value} requires a value", ["forge run promote <experiment> <run-id> --reason <reason> --json"])
        if len(parsed.positionals) < 2:
            return fail("missing-name", "run promote requires experiment and run id", ["forge run list <experiment> --json"])
        experiment, run_id = parsed.positionals[0], parsed.positionals[1]
        result = promote_service.promote_run(context.root, experiment, run_id, parsed.options.get("--reason"), context.dry_run)
        error = result_error(result)
        if error is not None:
            return fail(error[0], error[1], [f"forge run validate {experiment} {run_id} --root {context.root} --json"], {"issues": result.get("issues", [])})
        return ok(result, [f"forge experiment archive {experiment} --root {context.root} --json"], dry_status(context.dry_run))
    if command == "export":
        if len(args) < 3:
            return fail("missing-name", "run export requires experiment and run id", ["forge run list <experiment> --json"])
        result = export_service.export_run(context.root, args[1], args[2], context.dry_run)
        error = result_error(result)
        if error is not None:
            return fail(error[0], error[1], [f"forge run validate {args[1]} {args[2]} --root {context.root} --json"], {"issues": result.get("issues", [])})
        return ok(result, ["share or inspect the export artifact"], dry_status(context.dry_run))
    return fail("unknown-command", f"unknown run command: {command}", ["forge run list <experiment> --json"])
