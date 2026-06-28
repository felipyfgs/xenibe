from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Status:
    code: str
    level: str
    message: str


def ok(data: dict[str, Any] | None = None, next_actions: list[str] | None = None, code: str = "ok") -> dict[str, Any]:
    return {
        "status": [asdict(Status(code=code, level="info", message="ok"))],
        "data": data or {},
        "nextActions": next_actions or [],
    }


def fail(code: str, message: str, next_actions: list[str] | None = None, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": [asdict(Status(code=code, level="error", message=message))],
        "data": data or {},
        "nextActions": next_actions or ["run forge validate --json"],
    }


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
