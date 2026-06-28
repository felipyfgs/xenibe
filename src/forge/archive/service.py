from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from xenibe.artifacts.store import utc_now, write_yaml

from forge.common import relative_files


def archive_experiment(root: Path, experiment: str, dry_run: bool = False) -> dict[str, Any]:
    source = root / experiment
    if not source.exists():
        return {"error": "missing-artifact", "message": "experiment not found"}
    timestamp = utc_now().replace(":", "").replace("+", "z")
    target = root / "archived" / f"{experiment}-{timestamp}"
    payload: dict[str, Any] = {
        "experiment": experiment,
        "archive": str(target),
        "source": str(source),
        "includedFiles": relative_files(source),
        "metadata": {"source-experiment": experiment, "timestamp": utc_now()},
    }
    if dry_run:
        payload["plannedActions"] = ["copy experiment artifacts", "write archive.yml"]
        return payload
    shutil.copytree(source, target)
    write_yaml(target / "archive.yml", payload["metadata"])
    return payload
