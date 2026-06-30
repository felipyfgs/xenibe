from __future__ import annotations

from typing import Any

from forge.context import CommandContext
from forge.responses import fail, ok, read_only_action_context

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    action_context = read_only_action_context(context.root)
    if not args:
        return fail(
            "missing-command",
            "instructions command required",
            ["forge instructions orchestrate <experiment> --json"],
            target="command.name",
            fix="choose the orchestrate instruction command",
            action_context=action_context,
        )
    command = args[0]
    if command != "orchestrate":
        return fail(
            "unknown-command",
            f"unknown instructions command: {command}",
            ["forge instructions orchestrate <experiment> --json"],
            target="command.name",
            fix="run forge instructions orchestrate <experiment>",
            action_context=action_context,
        )
    if len(args) < 2:
        return fail(
            "missing-name",
            "instructions orchestrate requires experiment name",
            ["forge experiment list --json"],
            target="command.args[0]",
            fix="pass the experiment name after orchestrate",
            action_context=action_context,
        )
    experiment = args[1]
    data, next_actions, success = service.orchestrate(context.root, experiment)
    if not success:
        return fail(
            str(data.get("error", "invalid-artifact")),
            str(data.get("message", "orchestration instructions blocked")),
            next_actions,
            data,
            action_context=action_context,
        )
    return ok(data, next_actions, action_context=action_context)
