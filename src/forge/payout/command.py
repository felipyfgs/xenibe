from __future__ import annotations

from typing import Any

from forge.context import CommandContext
from forge.responses import fail, ok

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if args and args[0] == "get":
        if len(args) < 2:
            return fail("missing-name", "payout get requires asset", ["forge assets list --json"])
        asset = args[1]
    elif args:
        asset = args[0]
    else:
        return fail("missing-name", "payout requires asset", ["forge payout get EURUSD --json"])
    result = service.get_payout(context, asset)
    if "error" in result:
        return fail(str(result["error"]), str(result["message"]), ["configure provider credentials or inspect provider.yml"], {"asset": asset})
    return ok(result, [f"forge history download {asset} --timeframe M1 --from <start> --to <end> --json"], "dry-run" if context.dry_run else "ok")
