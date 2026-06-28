from __future__ import annotations

from typing import Any

from forge.common import option_value
from forge.context import CommandContext
from forge.responses import fail, ok

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if not args:
        return fail("missing-command", "promote command required", ["forge promote run <experiment> <run-id> --json"])
    if args[0] == "run":
        if len(args) < 3:
            return fail("missing-name", "promote run requires experiment and run id", ["forge run list <experiment> --json"])
        experiment, run_id = args[1], args[2]
    else:
        if len(args) < 2:
            return fail("missing-name", "promote requires experiment and run id", ["forge promote run <experiment> <run-id> --json"])
        experiment, run_id = args[0], args[1]
    result = service.promote_run(context.root, experiment, run_id, option_value(args, "--reason"), context.dry_run)
    if "error" in result:
        return fail(str(result["error"]), str(result["message"]), [f"forge run validate {experiment} {run_id} --root {context.root} --json"], {"issues": result.get("issues", [])})
    return ok(result, [f"forge archive experiment {experiment} --root {context.root} --json"], "dry-run" if context.dry_run else "created")
