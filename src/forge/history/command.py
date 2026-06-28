from __future__ import annotations

from typing import Any

from forge.common import option_value
from forge.context import CommandContext
from forge.responses import fail, ok

from . import service


def dispatch(args: list[str], context: CommandContext) -> dict[str, Any]:
    if not args:
        return ok(
            {"orders": [], "provider": "ebinex", "mode": "offline-contract"},
            ["forge history download <asset> --timeframe M1 --from <start> --to <end> --json"],
        )
    if args[0] != "download":
        return fail("unknown-command", f"unknown history command: {args[0]}", ["forge history download <asset> --timeframe M1 --from <start> --to <end> --json"])
    if len(args) < 2:
        return fail("missing-name", "history download requires asset", ["forge assets list --json"])
    experiment = option_value(args, "--experiment")
    timeframe = option_value(args, "--timeframe")
    start = option_value(args, "--from")
    end = option_value(args, "--to")
    if not experiment:
        return fail("missing-name", "history download requires --experiment", ["forge history download EURUSD --experiment <experiment> --timeframe M1 --from 2026-01-01 --to 2026-01-02 --json"])
    if not timeframe or not start or not end:
        return fail("missing-name", "history download requires --timeframe, --from, and --to", ["forge history download EURUSD --experiment <experiment> --timeframe M1 --from 2026-01-01 --to 2026-01-02 --json"])
    result = service.download(context, experiment, args[1], timeframe, start, end)
    if "error" in result:
        return fail(str(result["error"]), str(result["message"]), ["configure provider credentials or inspect provider.yml"], {"asset": args[1]})
    return ok(result, ["forge run backtest <experiment> --json"], "dry-run" if context.dry_run else "created")
