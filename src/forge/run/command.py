from __future__ import annotations

from typing import Any

from forge.common import option_value
from forge.context import CommandContext
from forge.responses import fail, ok

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if not args:
        return fail("missing-command", "run command required", ["forge run list <experiment> --json"])
    command = args[0]
    if command in {"backtest", "simulate"}:
        if len(args) < 2:
            return fail("missing-name", "experiment name required", ["forge experiment list --json"])
        result = service.run_backtest(context.root, args[1], "simulate" if command == "simulate" else "backtest", option_value(args, "--run-id"), context.dry_run)
        if "error" in result:
            return fail(str(result["error"]), str(result["message"]), [f"forge experiment validate {args[1]} --root {context.root} --json"], {"issues": result.get("issues", [])})
        return ok(
            result,
            [f"forge run show {args[1]} {result['runId']} --root {context.root} --json", f"forge promote run {args[1]} {result['runId']} --root {context.root} --json"],
            "dry-run" if context.dry_run else "created",
        )
    if command == "list":
        if len(args) < 2:
            return fail("missing-name", "experiment name required", ["forge experiment list --json"])
        return ok(service.list_runs(context.root, args[1]), ["forge run show <experiment> <run-id> --json"])
    if command == "show":
        if len(args) < 3:
            return fail("missing-name", "experiment and run id required", ["forge run list <experiment> --json"])
        result = service.show_run(context.root, args[1], args[2])
        if "error" in result:
            return fail(str(result["error"]), str(result["message"]), [f"forge run list {args[1]} --root {context.root} --json"])
        return ok(result, [f"forge report show {args[1]} {args[2]} --root {context.root} --json"])
    if command == "validate":
        if len(args) < 3:
            return fail("missing-name", "experiment and run id required", ["forge run list <experiment> --json"])
        result = service.validate_run(context.root, args[1], args[2])
        if not result["valid"]:
            return fail("invalid-artifact", "run validation failed", [f"inspect {context.root / args[1] / 'runs' / args[2]}"], {"issues": result["issues"]})
        return ok(result, [f"forge report show {args[1]} {args[2]} --root {context.root} --json"], "validated")
    return fail("unknown-command", f"unknown run command: {command}", ["forge run list <experiment> --json"])
