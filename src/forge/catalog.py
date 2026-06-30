from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ForgeCommand:
    name: str
    usage: str
    subcommands: tuple[str, ...] = ()
    legacy_aliases: tuple[str, ...] = ()


COMMANDS: tuple[ForgeCommand, ...] = (
    ForgeCommand("init", "forge init"),
    ForgeCommand("validate", "forge validate"),
    ForgeCommand("status", "forge status"),
    ForgeCommand("instructions", "forge instructions orchestrate", ("orchestrate",)),
    ForgeCommand("experiment", "forge experiment new|list|show|validate", ("new", "list", "show", "validate")),
    ForgeCommand("run", "forge run backtest|simulate|list|show|validate", ("backtest", "simulate", "list", "show", "validate")),
    ForgeCommand("report", "forge report generate|show", ("generate", "show"), ("forge report <experiment> <run-id>",)),
    ForgeCommand("compare", "forge compare runs", ("runs",), ("forge compare <experiment> <run-id-a> <run-id-b>",)),
    ForgeCommand("promote", "forge promote run", ("run",), ("forge promote <experiment> <run-id>",)),
    ForgeCommand("archive", "forge archive experiment", ("experiment",), ("forge archive <experiment>",)),
    ForgeCommand("export", "forge export run|experiment", ("run", "experiment"), ("forge export <experiment>",)),
    ForgeCommand("assets", "forge assets list", ("list",), ("forge assets",)),
    ForgeCommand("payout", "forge payout get", ("get",), ("forge payout <asset>",)),
    ForgeCommand("history", "forge history download", ("download",)),
)

COMMANDS_BY_NAME = {command.name: command for command in COMMANDS}
COMMAND_NAMES = tuple(command.name for command in COMMANDS)
DISPATCH_COMMAND_NAMES = tuple(name for name in COMMAND_NAMES if name != "init")
SUBCOMMANDS = {
    command.name: set(command.subcommands)
    for command in COMMANDS
    if command.subcommands
}


def render_help() -> str:
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
