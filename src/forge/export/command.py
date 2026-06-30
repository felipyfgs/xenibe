from __future__ import annotations

from typing import Any

from forge.common import dry_status, result_error
from forge.context import CommandContext
from forge.responses import fail, ok

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if not args:
        return fail("missing-command", "export command required", ["forge export run <experiment> <run-id> --json", "forge export experiment <experiment> --json"])
    if args[0] == "run":
        if len(args) < 3:
            return fail("missing-name", "export run requires experiment and run id", ["forge run list <experiment> --json"])
        result = service.export_run(context.root, args[1], args[2], context.dry_run)
    elif args[0] == "experiment":
        if len(args) < 2:
            return fail("missing-name", "export experiment requires experiment name", ["forge experiment list --json"])
        result = service.export_experiment(context.root, args[1], context.dry_run)
    else:
        result = service.export_experiment(context.root, args[0], context.dry_run)
    error = result_error(result)
    if error is not None:
        return fail(error[0], error[1], [f"forge experiment list --root {context.root} --json"])
    return ok(result, ["share or inspect the export artifact"], dry_status(context.dry_run))
