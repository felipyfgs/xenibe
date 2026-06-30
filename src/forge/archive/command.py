from __future__ import annotations

from typing import Any

from forge.common import dry_status, result_error
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
    error = result_error(result)
    if error is not None:
        return fail(error[0], error[1], [f"forge experiment list --root {context.root} --json"])
    return ok(result, ["forge experiment list --json"], dry_status(context.dry_run))
