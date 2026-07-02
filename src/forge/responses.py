from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from forge.catalog import SUBCOMMANDS


@dataclass(frozen=True)
class Status:
    code: str
    level: str
    message: str
    target: str | None = None
    fix: str | None = None


def _status(status: Status) -> dict[str, str]:
    data = {"code": status.code, "level": status.level, "message": status.message}
    if status.target is not None:
        data["target"] = status.target
    if status.fix is not None:
        data["fix"] = status.fix
    return data


def _default_repair_context(
    code: str,
    message: str,
    next_actions: list[str],
    data: dict[str, Any] | None,
) -> tuple[str | None, str | None]:
    if code == "unexpected-error":
        return None, None
    target: str | None = None
    if code in {"missing-command", "unknown-command"}:
        target = "command.name"
    elif code == "missing-name":
        target = "command.args"
    elif code in {"missing-artifact", "invalid-artifact", "invalid-name", "invalid-json", "invalid-jsonl", "invalid-yaml"}:
        issues = (data or {}).get("issues")
        if isinstance(issues, list) and issues:
            first = issues[0]
            if isinstance(first, dict):
                target = str(first.get("target") or first.get("path") or "artifact")
        target = target or "artifact"
    fix = next_actions[0] if next_actions else message
    return target, fix


def ok(
    data: dict[str, Any] | None = None,
    next_actions: list[str] | None = None,
    code: str = "ok",
    action_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = {
        "status": [_status(Status(code=code, level="info", message="ok"))],
        "data": data or {},
        "nextActions": next_actions or [],
    }
    if action_context is not None:
        response["actionContext"] = action_context
    return response


def fail(
    code: str,
    message: str,
    next_actions: list[str] | None = None,
    data: dict[str, Any] | None = None,
    target: str | None = None,
    fix: str | None = None,
    action_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    actions = next_actions or ["forge check --json"]
    if target is None or fix is None:
        default_target, default_fix = _default_repair_context(code, message, actions, data)
        target = target or default_target
        fix = fix or default_fix
    response = {
        "status": [_status(Status(code=code, level="error", message=message, target=target, fix=fix))],
        "data": data or {},
        "nextActions": actions,
    }
    if action_context is not None:
        response["actionContext"] = action_context
    return response


def read_only_action_context(root: Path, constraints: list[str] | None = None) -> dict[str, Any]:
    return {
        "mode": "repo-local",
        "sourceOfTruth": "artifact-root",
        "allowedEditRoots": [str(root)],
        "mutatesArtifacts": False,
        "constraints": constraints or ["Read-only orchestration inspection."],
    }


def _command_metadata(args: list[str], dry_run: bool) -> dict[str, Any]:
    if not args:
        return {"name": "forge", "args": [], "dryRun": dry_run}
    if args[0].startswith("--"):
        return {"name": f"forge {args[0]}", "args": args[1:], "dryRun": dry_run}
    command_parts = [args[0]]
    rest = args[1:]
    if rest and args[0] in SUBCOMMANDS and rest[0] in SUBCOMMANDS[args[0]]:
        command_parts.append(rest[0])
        rest = rest[1:]
    return {"name": "forge " + " ".join(command_parts), "args": rest, "dryRun": dry_run}


def attach_metadata(response: dict[str, Any], root: Path, args: list[str], dry_run: bool) -> dict[str, Any]:
    response.setdefault("root", {"path": str(root), "exists": root.exists()})
    response.setdefault("command", _command_metadata(args, dry_run))
    return response


def emit(response: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True))
        return
    for item in response["status"]:
        print(f"{item['level']}: {item['message']}")
    if response["nextActions"]:
        print("next:")
        for action in response["nextActions"]:
            print(f"- {action}")
