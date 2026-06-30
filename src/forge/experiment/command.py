from __future__ import annotations

from typing import Any

from forge.common import dry_status, result_error
from forge.context import CommandContext
from forge.responses import fail, ok

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if not args:
        return fail("missing-command", "experiment command required", ["forge experiment list --json"])
    command = args[0]
    if command == "new":
        if len(args) < 2:
            return fail("missing-name", "experiment name required", ["forge experiment new idx-m1-soros-reversal --json"])
        result = service.create(context.root, args[1], context.dry_run)
        error = result_error(result)
        if error is not None:
            return fail(error[0], error[1], result.get("next"))
        return ok(
            result,
            [f"forge experiment validate {args[1]} --root {context.root} --json", f"forge run backtest {args[1]} --root {context.root} --json"],
            dry_status(context.dry_run),
        )
    if command == "list":
        return ok(service.list_all(context.root), ["forge experiment show <name> --json"])
    if command == "show":
        if len(args) < 2:
            return fail("missing-name", "experiment name required", ["forge experiment list --json"])
        try:
            return ok(service.show(context.root, args[1]), [f"forge run backtest {args[1]} --root {context.root} --json"])
        except Exception as exc:
            return fail("missing-artifact", str(exc), [f"forge experiment validate {args[1]} --root {context.root} --json"])
    if command == "validate":
        if len(args) < 2:
            return fail("missing-name", "experiment name required", ["forge experiment list --json"])
        result = service.validate(context.root, args[1])
        if not result["valid"]:
            return fail("invalid-artifact", "experiment validation failed", [f"fix reported artifacts under {context.root / 'experiment' / args[1]}", f"forge experiment validate {args[1]} --root {context.root} --json"], {"issues": result["issues"]})
        return ok(result, [f"forge run backtest {args[1]} --root {context.root} --json"], "validated")
    return fail("unknown-command", f"unknown experiment command: {command}", ["forge experiment list --json"])
