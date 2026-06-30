from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ForgeCommand:
    name: str
    usage: str
    subcommands: tuple[str, ...] = ()


COMMANDS: tuple[ForgeCommand, ...] = (
    ForgeCommand("init", "forge init"),
    ForgeCommand("validate", "forge validate"),
    ForgeCommand("status", "forge status"),
    ForgeCommand("instructions", "forge instructions orchestrate <experiment>", ("orchestrate",)),
    ForgeCommand("experiment", "forge experiment new|list|show|validate|archive|export", ("new", "list", "show", "validate", "archive", "export")),
    ForgeCommand("run", "forge run backtest|list|show|validate|compare|promote|export", ("backtest", "list", "show", "validate", "compare", "promote", "export")),
    ForgeCommand("report", "forge report show <experiment> <run-id>", ("show",)),
    ForgeCommand("assets", "forge assets list", ("list",)),
    ForgeCommand("payout", "forge payout get <asset>", ("get",)),
    ForgeCommand("history", "forge history download <asset> --experiment <experiment> --timeframe <timeframe> --from <start> --to <end>", ("download",)),
)

COMMANDS_BY_NAME = {command.name: command for command in COMMANDS}
COMMAND_NAMES = tuple(command.name for command in COMMANDS)
DISPATCH_COMMAND_NAMES = tuple(name for name in COMMAND_NAMES if name != "init")
SUBCOMMANDS = {
    command.name: set(command.subcommands)
    for command in COMMANDS
    if command.subcommands
}


def _global_help() -> str:
    command_lines = "\n".join(f"  {command.usage}" for command in COMMANDS)
    return f"""forge - Xenibe experiment lab

Usage:
  forge [global options] <command> [args]

Global options:
  --root <path>   Artifact root
  --json          Emit JSON response envelope
  --dry-run       Plan without filesystem mutation
  --yes           Assume yes for confirmations
  --no-color      Disable colored text
  --version       Show version
  --help          Show this help

Commands:
{command_lines}
"""


COMMAND_HELP: dict[str, str] = {
    "experiment": """forge experiment - manage experiment artifacts

Usage:
  forge experiment new <name>
  forge experiment list
  forge experiment show <name>
  forge experiment validate <name>
  forge experiment archive <name>
  forge experiment export <name>
""",
    "run": """forge run - execute and manage run artifacts

Usage:
  forge run backtest <experiment> [--run-id <run-id>] [--allow-synthetic]
  forge run list <experiment>
  forge run show <experiment> <run-id>
  forge run validate <experiment> <run-id>
  forge run compare <experiment> <run-id-a> <run-id-b> [<run-id>...]
  forge run promote <experiment> <run-id> [--reason <reason>]
  forge run export <experiment> <run-id>
""",
    "report": """forge report - read run reports

Usage:
  forge report show <experiment> <run-id>
""",
    "assets": """forge assets - inspect provider assets

Usage:
  forge assets list
""",
    "payout": """forge payout - inspect provider payout

Usage:
  forge payout get <asset>
""",
    "history": """forge history - manage candle history

Usage:
  forge history download <asset> --experiment <experiment> --timeframe <timeframe> --from <start> --to <end> [--replace]
""",
    "instructions": """forge instructions - inspect orchestration guidance

Usage:
  forge instructions orchestrate <experiment>
""",
}


def render_help(command_name: str | None = None) -> str:
    if command_name is not None and command_name in COMMAND_HELP:
        return COMMAND_HELP[command_name]
    return _global_help()
