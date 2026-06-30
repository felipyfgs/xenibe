from __future__ import annotations

from typing import Any

from forge.common import dry_status, result_error
from forge.context import CommandContext
from forge.responses import fail, ok

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if args and args[0] != "list":
        return fail("unknown-command", f"unknown assets command: {args[0]}", ["forge assets list --json"])
    result = service.list_assets(context)
    error = result_error(result)
    if error is not None:
        return fail(error[0], error[1], ["configure provider credentials or use offline mode"], {"provider": "ebinex"})
    return ok(result, ["forge payout get <asset> --json"], dry_status(context.dry_run, "ok"))
