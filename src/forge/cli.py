from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from forge import __version__
from forge.catalog import COMMAND_NAMES, render_help
from forge.context import CommandContext, ProviderFactory
from forge.responses import attach_metadata, emit, fail, ok
from forge.workflow import WORKFLOW_HANDLERS
from xenibe.artifacts.store import ImmutableRunError


@dataclass(frozen=True)
class ParsedGlobal:
    args: list[str]
    context: CommandContext
    show_help: bool = False
    show_version: bool = False
    error: dict[str, Any] | None = None


def default_root() -> Path:
    return Path(os.environ.get("FORGE_ROOT", Path.cwd() / "forge")).resolve()


def parse_global(argv: list[str], provider_factory: ProviderFactory | None = None) -> ParsedGlobal:
    args: list[str] = []
    root = default_root()
    as_json = False
    dry_run = False
    yes = False
    no_color = False
    show_help = False
    show_version = False
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == "--json":
            as_json = True
            index += 1
        elif item == "--dry-run":
            dry_run = True
            index += 1
        elif item == "--yes":
            yes = True
            index += 1
        elif item == "--no-color":
            no_color = True
            index += 1
        elif item == "--version":
            show_version = True
            index += 1
        elif item in {"--help", "-h"}:
            show_help = True
            index += 1
        elif item == "--root":
            if index + 1 >= len(argv):
                context = CommandContext(root=root, as_json=as_json, dry_run=dry_run, yes=yes, no_color=no_color, provider_factory=provider_factory)
                return ParsedGlobal(args, context, error=fail("missing-name", "--root requires a path", ["forge --root <path> new <experiment> --json"]))
            root = Path(argv[index + 1]).resolve()
            index += 2
        else:
            args.append(item)
            index += 1
    context = CommandContext(root=root, as_json=as_json, dry_run=dry_run, yes=yes, no_color=no_color, provider_factory=provider_factory)
    return ParsedGlobal(args=args, context=context, show_help=show_help, show_version=show_version)


def dispatch(args: list[str], context_or_root: CommandContext | Path | None = None) -> dict[str, Any]:
    context = context_or_root if isinstance(context_or_root, CommandContext) else CommandContext(root=(context_or_root or default_root()))
    if not args:
        return fail("missing-command", "command required", ["forge new <experiment> --json", "forge status --json"])
    command = args[0]
    try:
        if command in WORKFLOW_HANDLERS:
            return WORKFLOW_HANDLERS[command](args[1:], context)
    except ImmutableRunError as exc:
        return fail("immutable-run", str(exc), ["create a new run-id or write an audit artifact"])
    except FileExistsError as exc:
        return fail("invalid-artifact", f"artifact already exists: {exc}", ["choose a different name or inspect the existing artifact"])
    except Exception as exc:
        return fail("unexpected-error", str(exc), ["run the command again with --json and inspect status"])
    return fail("unknown-command", f"unknown command: {command}", ["forge --help", "forge status --json"], target="command.name", fix="run forge --help to choose a supported command")


def _special_response(parsed: ParsedGlobal) -> dict[str, Any] | None:
    if parsed.error is not None:
        return parsed.error
    if parsed.show_version:
        return ok({"version": __version__}, [], "ok")
    if parsed.show_help:
        command_name = parsed.args[0] if parsed.args and parsed.args[0] in COMMAND_NAMES else None
        return ok({"help": render_help(command_name), "commands": list(COMMAND_NAMES)}, [], "ok")
    return None


def _metadata_args(parsed: ParsedGlobal) -> list[str]:
    if parsed.show_version:
        return ["--version"]
    if parsed.show_help:
        return [*parsed.args, "--help"] if parsed.args else ["--help"]
    return parsed.args


def main(argv: list[str] | None = None, provider_factory: ProviderFactory | None = None) -> int:
    parsed = parse_global(list(sys.argv[1:] if argv is None else argv), provider_factory)
    response = _special_response(parsed) or dispatch(parsed.args, parsed.context)
    response = attach_metadata(response, parsed.context.root, _metadata_args(parsed), parsed.context.dry_run)
    if not parsed.context.as_json and "help" in response.get("data", {}):
        print(response["data"]["help"])
    elif not parsed.context.as_json and "version" in response.get("data", {}):
        print(f"forge {response['data']['version']}")
    else:
        emit(response, parsed.context.as_json)
    return 1 if any(item["level"] == "error" for item in response["status"]) else 0
