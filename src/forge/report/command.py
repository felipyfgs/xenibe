from __future__ import annotations

from typing import Any

from forge.context import CommandContext
from forge.responses import fail, ok

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if not args:
        return fail("missing-command", "report command required", ["forge report show <experiment> <run-id> --json"])
    command = args[0]
    if command in {"generate", "show"}:
        if len(args) < 3:
            return fail("missing-name", "report requires experiment and run id", ["forge run list <experiment> --json"])
        result = service.generate(context.root, args[1], args[2], context.dry_run) if command == "generate" else service.show(context.root, args[1], args[2])
        if "error" in result:
            return fail(str(result["error"]), str(result["message"]), [f"forge run validate {args[1]} {args[2]} --root {context.root} --json"])
        return ok(result, [f"forge compare runs {args[1]} {args[2]} <other-run-id> --root {context.root} --json", f"forge promote run {args[1]} {args[2]} --root {context.root} --json"], "dry-run" if context.dry_run and command == "generate" else "ok")

    if len(args) >= 2:
        result = service.show(context.root, args[0], args[1])
        if "error" in result:
            return fail(str(result["error"]), str(result["message"]), [f"forge run validate {args[0]} {args[1]} --root {context.root} --json"])
        return ok(result, [f"forge report show {args[0]} {args[1]} --root {context.root} --json", f"forge promote run {args[0]} {args[1]} --root {context.root} --json"])
    return fail("unknown-command", f"unknown report command: {command}", ["forge report show <experiment> <run-id> --json"])
