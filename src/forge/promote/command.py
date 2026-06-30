from __future__ import annotations

from typing import Any

from forge.common import dry_status, parse_options, result_error
from forge.context import CommandContext
from forge.responses import fail, ok

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if not args:
        return fail("missing-command", "promote command required", ["forge promote run <experiment> <run-id> --json"])
    command_args = args[1:] if args[0] == "run" else args
    parsed = parse_options(command_args, {"--reason"})
    if parsed.missing_value is not None:
        return fail("missing-name", f"{parsed.missing_value} requires a value", ["forge promote run <experiment> <run-id> --reason <reason> --json"])
    if args[0] == "run":
        if len(parsed.positionals) < 2:
            return fail("missing-name", "promote run requires experiment and run id", ["forge run list <experiment> --json"])
        experiment, run_id = parsed.positionals[0], parsed.positionals[1]
    else:
        if len(parsed.positionals) < 2:
            return fail("missing-name", "promote requires experiment and run id", ["forge promote run <experiment> <run-id> --json"])
        experiment, run_id = parsed.positionals[0], parsed.positionals[1]
    result = service.promote_run(context.root, experiment, run_id, parsed.options.get("--reason"), context.dry_run)
    error = result_error(result)
    if error is not None:
        return fail(error[0], error[1], [f"forge run validate {experiment} {run_id} --root {context.root} --json"], {"issues": result.get("issues", [])})
    return ok(result, [f"forge archive experiment {experiment} --root {context.root} --json"], dry_status(context.dry_run))
