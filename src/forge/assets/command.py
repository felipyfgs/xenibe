from __future__ import annotations

from typing import Any

from forge.context import CommandContext
from forge.responses import fail, ok

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if args and args[0] != "list":
        return fail("unknown-command", f"unknown assets command: {args[0]}", ["forge assets list --json"])
    result = service.list_assets(context)
    if "error" in result:
        return fail(str(result["error"]), str(result["message"]), ["configure provider credentials or use offline mode"], {"provider": "ebinex"})
    return ok(result, ["forge payout get <asset> --json"], "dry-run" if context.dry_run else "ok")
