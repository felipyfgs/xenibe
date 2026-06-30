from __future__ import annotations

from typing import Any

from forge.common import result_error
from forge.context import CommandContext
from forge.responses import fail, ok

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if not args:
        return fail("missing-command", "report command required", ["forge report show <experiment> <run-id> --json"])
    command = args[0]
    if command == "show":
        if len(args) < 3:
            return fail("missing-name", "report requires experiment and run id", ["forge run list <experiment> --json"])
        result = service.show(context.root, args[1], args[2])
        error = result_error(result)
        if error is not None:
            return fail(error[0], error[1], [f"forge run validate {args[1]} {args[2]} --root {context.root} --json"])
        return ok(result, [f"forge run compare {args[1]} {args[2]} <other-run-id> --root {context.root} --json", f"forge run promote {args[1]} {args[2]} --root {context.root} --json"])
    return fail("unknown-command", f"unknown report command: {command}", ["forge report show <experiment> <run-id> --json"])
