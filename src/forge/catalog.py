from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ForgeCommand:
    name: str
    usage: str
    subcommands: tuple[str, ...] = ()


COMMANDS: tuple[ForgeCommand, ...] = (
    ForgeCommand("new", "forge new <experiment>"),
    ForgeCommand("status", "forge status"),
    ForgeCommand("show", "forge show [experiment] [run-id]"),
    ForgeCommand("check", "forge check [experiment] [run-id]"),
    ForgeCommand("data", "forge data list|download <asset> --experiment <experiment> --timeframe <timeframe> --from <start> --to <end>", ("list", "download")),
    ForgeCommand("backtest", "forge backtest <experiment> [--mode backtest|simulate]"),
    ForgeCommand("compare", "forge compare <experiment> <run-id-a> <run-id-b> [<run-id>...]"),
    ForgeCommand("promote", "forge promote <experiment> <run-id> [--reason <reason>]"),
    ForgeCommand("archive", "forge archive <experiment>"),
    ForgeCommand("export", "forge export <experiment> [run-id]"),
)

COMMAND_NAMES = tuple(command.name for command in COMMANDS)
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
    "new": """forge new - create an experiment and initialize the root when needed

Usage:
  forge new <experiment>
""",
    "status": """forge status - inspect the artifact root at a glance

Usage:
  forge status
""",
    "show": """forge show - inspect root, experiment, or run details

Usage:
  forge show
  forge show <experiment>
  forge show <experiment> <run-id>
""",
    "check": """forge check - validate root, experiment, or run contracts

Usage:
  forge check
  forge check <experiment>
  forge check <experiment> <run-id>
""",
    "data": """forge data - list provider assets or download canonical history

Usage:
  forge data list
  forge data download <asset> --experiment <experiment> --timeframe <timeframe> --from <start> --to <end> [--replace]
""",
    "backtest": """forge backtest - run a backtest or simulation search

Usage:
  forge backtest <experiment> [--mode backtest|simulate] [--run-id <run-id>]
""",
    "compare": """forge compare - compare completed runs

Usage:
  forge compare <experiment> <run-id-a> <run-id-b> [<run-id>...]
""",
    "promote": """forge promote - promote a completed run

Usage:
  forge promote <experiment> <run-id> [--reason <reason>]
""",
    "archive": """forge archive - archive an experiment

Usage:
  forge archive <experiment>
""",
    "export": """forge export - export an experiment or completed run

Usage:
  forge export <experiment>
  forge export <experiment> <run-id>
""",
}


def render_help(command_name: str | None = None) -> str:
    if command_name is not None and command_name in COMMAND_HELP:
        return COMMAND_HELP[command_name]
    return _global_help()
