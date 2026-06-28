from __future__ import annotations

from typing import Any

from forge.context import CommandContext
from forge.responses import fail, ok

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if not args:
        return fail("missing-command", "archive command required", ["forge archive experiment <experiment> --json"])
    if args[0] == "experiment":
        if len(args) < 2:
            return fail("missing-name", "archive experiment requires experiment name", ["forge experiment list --json"])
        experiment = args[1]
    else:
        experiment = args[0]
    result = service.archive_experiment(context.root, experiment, context.dry_run)
    if "error" in result:
        return fail(str(result["error"]), str(result["message"]), [f"forge experiment list --root {context.root} --json"])
    return ok(result, ["forge experiment list --json"], "dry-run" if context.dry_run else "created")
