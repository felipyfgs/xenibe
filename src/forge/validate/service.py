from __future__ import annotations

from pathlib import Path
from typing import Any

from xenibe.artifacts.store import ValidationIssue, list_experiments, validate_experiment_dir, validate_run_dir

from forge.common import issues_payload


def validate_root(root: Path) -> dict[str, Any]:
    issues: list[ValidationIssue] = []
    if not root.exists():
        issues.append(ValidationIssue("missing-artifact", str(root), "artifact root does not exist"))
        return {"artifactRoot": str(root), "valid": False, "issues": issues_payload(issues)}
    if not (root / "config.yml").exists():
        issues.append(ValidationIssue("missing-artifact", str(root / "config.yml"), "missing config.yml"))
    for experiment in list_experiments(root):
        experiment_dir = root / experiment
        issues.extend(validate_experiment_dir(experiment_dir))
        runs = experiment_dir / "runs"
        if runs.exists():
            for run_dir in runs.iterdir():
                if run_dir.is_dir():
                    issues.extend(validate_run_dir(run_dir))
    if issues:
        return {"artifactRoot": str(root), "valid": False, "issues": issues_payload(issues)}
    return {"artifactRoot": str(root), "valid": True, "issues": []}
