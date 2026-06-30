from __future__ import annotations

from typing import Any

from forge.common import dry_status, parse_options, result_error
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
    replace = "--replace" in args[1:]
    download_args = [arg for arg in args[1:] if arg != "--replace"]
    parsed = parse_options(download_args, {"--experiment", "--timeframe", "--from", "--to"})
    if parsed.missing_value is not None:
        return fail("missing-name", f"{parsed.missing_value} requires a value", ["forge history download EURUSD --experiment <experiment> --timeframe M1 --from 2026-01-01 --to 2026-01-02 --json"])
    if not parsed.positionals:
        return fail("missing-name", "history download requires asset", ["forge assets list --json"])
    asset = parsed.positionals[0]
    experiment = parsed.options.get("--experiment")
    timeframe = parsed.options.get("--timeframe")
    start = parsed.options.get("--from")
    end = parsed.options.get("--to")
    if not experiment:
        return fail("missing-name", "history download requires --experiment", ["forge history download EURUSD --experiment <experiment> --timeframe M1 --from 2026-01-01 --to 2026-01-02 --json"])
    if not timeframe or not start or not end:
        return fail("missing-name", "history download requires --timeframe, --from, and --to", ["forge history download EURUSD --experiment <experiment> --timeframe M1 --from 2026-01-01 --to 2026-01-02 --json"])
    result = service.download(context, experiment, asset, timeframe, start, end, replace=replace)
    error = result_error(result)
    if error is not None:
        next_actions = result.get("next") if isinstance(result.get("next"), list) else ["configure provider credentials or inspect provider.yml"]
        return fail(error[0], error[1], next_actions, {"asset": asset, "path": result.get("path"), "manifestPath": result.get("manifestPath")})
    return ok(result, ["forge run backtest <experiment> --json"], dry_status(context.dry_run))
