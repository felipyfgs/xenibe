from __future__ import annotations

from typing import Any

from forge.context import CommandContext
from forge.responses import fail, ok

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if not args:
        return fail("missing-command", "compare command required", ["forge compare runs <experiment> <run-id-a> <run-id-b> --json"])
    command = args[0]
    if command == "runs":
        if len(args) < 4:
            return fail("missing-name", "compare runs requires experiment and at least two run ids", ["forge run list <experiment> --json"])
        experiment = args[1]
        run_ids = args[2:]
    else:
        if len(args) < 3:
            return fail("missing-name", "compare requires experiment and at least two run ids", ["forge compare runs <experiment> <run-id-a> <run-id-b> --json"])
        experiment = args[0]
        run_ids = args[1:]
    result = service.compare_runs(context.root, experiment, run_ids)
    if "error" in result:
        return fail(str(result["error"]), str(result["message"]), [f"forge run list {experiment} --root {context.root} --json"], {"missingRuns": result.get("missingRuns", [])})
    return ok(result, [f"forge promote run {experiment} {result.get('bestRunId') or '<run-id>'} --root {context.root} --json"])
