from __future__ import annotations

from pathlib import Path
from typing import Any

from xenibe.artifacts.store import ValidationIssue, experiment_dir, list_experiments, validate_config, validate_experiment_dir, validate_run_dir

from forge.common import issues_payload


def validate_root(root: Path) -> dict[str, Any]:
    issues: list[ValidationIssue] = []
    if not root.exists():
        issues.append(ValidationIssue("missing-artifact", str(root), "artifact root does not exist"))
        return {"artifactRoot": str(root), "valid": False, "issues": issues_payload(issues)}
    issues.extend(validate_config(root))
    for experiment in list_experiments(root):
        path = experiment_dir(root, experiment)
        issues.extend(validate_experiment_dir(path))
        runs = path / "runs"
        if runs.exists():
            for run_dir in runs.iterdir():
                if run_dir.is_dir():
                    issues.extend(validate_run_dir(run_dir))
    if issues:
        return {"artifactRoot": str(root), "valid": False, "issues": issues_payload(issues)}
    return {"artifactRoot": str(root), "valid": True, "issues": []}
