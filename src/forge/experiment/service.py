from __future__ import annotations

from pathlib import Path
from typing import Any

from xenibe.artifacts.naming import is_kebab
from xenibe.artifacts.store import create_experiment, list_experiments, load_experiment, validate_experiment_dir

from forge.common import issues_payload


def create(root: Path, name: str, dry_run: bool = False) -> dict[str, Any]:
    if not is_kebab(name):
        return {
            "error": "invalid-name",
            "message": "experiment name must use kebab-case",
            "next": ["choose a kebab-case experiment name"],
        }
    path = root / name
    if dry_run:
        return {"experiment": name, "path": str(path), "plannedActions": ["create experiment directory", "write default YAML files", "create runs directory"]}
    return {"experiment": name, "path": str(create_experiment(root, name))}


def list_all(root: Path) -> dict[str, list[str]]:
    return {"experiments": list_experiments(root)}


def show(root: Path, name: str) -> dict[str, Any]:
    return {"experiment": name, "files": load_experiment(root, name)}


def validate(root: Path, name: str) -> dict[str, Any]:
    issues = validate_experiment_dir(root / name)
    if issues:
        return {"valid": False, "issues": issues_payload(issues)}
    return {"experiment": name, "valid": True}
