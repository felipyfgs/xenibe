from __future__ import annotations

from typing import Any

from forge.common import dry_status, result_error
from forge.context import CommandContext
from forge.responses import fail, ok

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if not args:
        return fail("missing-command", "payout command required", ["forge payout get EURUSD --json"])
    if args[0] != "get":
        return fail("unknown-command", f"unknown payout command: {args[0]}", ["forge payout get EURUSD --json"])
    if len(args) < 2:
        return fail("missing-name", "payout get requires asset", ["forge assets list --json"])
    if len(args) > 2:
        return fail("unknown-command", f"unknown payout argument: {args[2]}", ["forge payout get EURUSD --json"], target="command.args", fix="run forge payout get with a single asset")
    asset = args[1]
    result = service.get_payout(context, asset)
    error = result_error(result)
    if error is not None:
        return fail(error[0], error[1], ["configure provider credentials via environment variables or use offline mode"], {"asset": asset})
    return ok(result, [f"forge history download {asset} --timeframe M1 --from <start> --to <end> --json"], dry_status(context.dry_run, "ok"))
