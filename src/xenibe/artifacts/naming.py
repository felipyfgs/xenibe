from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
EXPERIMENT_RE = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")
RUN_ID_RE = re.compile(r"^(?:bt|sim)-\d{8}-\d{6}(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?$")
CAMEL_RE = re.compile(r"^[a-z][A-Za-z0-9]*$")


def is_kebab(value: str) -> bool:
    return bool(KEBAB_RE.fullmatch(value))


def is_experiment_name(value: str) -> bool:
    return bool(EXPERIMENT_RE.fullmatch(value))


def is_run_id(value: str) -> bool:
    return bool(RUN_ID_RE.fullmatch(value))


def is_camel(value: str) -> bool:
    return bool(CAMEL_RE.fullmatch(value))


def find_non_kebab_keys(value: Any, path: str = "") -> list[str]:
    failures: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if not is_kebab(key_text):
                failures.append(child_path)
            failures.extend(find_non_kebab_keys(child, child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            failures.extend(find_non_kebab_keys(child, child_path))
    return failures


def find_non_camel_keys(value: Any, path: str = "") -> list[str]:
    failures: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if not is_camel(key_text):
                failures.append(child_path)
            failures.extend(find_non_camel_keys(child, child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            failures.extend(find_non_camel_keys(child, f"{path}[{index}]"))
    return failures
