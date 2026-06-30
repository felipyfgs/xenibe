from __future__ import annotations

from typing import Any

from forge.context import CommandContext
from forge.responses import fail, ok, read_only_action_context

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if args:
        return fail(
            "unknown-command",
            f"unknown status command: {args[0]}",
            ["forge status --json"],
            target="command.name",
            fix="run forge status without subcommands",
            action_context=read_only_action_context(context.root),
        )
    data = service.inspect_root(context.root)
    return ok(data, service.next_actions(context.root, data), action_context=read_only_action_context(context.root))
