from __future__ import annotations

from typing import Any

from forge.context import CommandContext
from forge.responses import fail, ok

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if args:
        return fail("unknown-command", f"unknown validate command: {args[0]}", ["forge validate --json"])
    result = service.validate_root(context.root)
    if not result["valid"]:
        return fail("invalid-artifact", "artifact root validation failed", ["fix reported artifact issues"], {"issues": result["issues"]})
    return ok(result, ["forge experiment list --json"], "validated")
