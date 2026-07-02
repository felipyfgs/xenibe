from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from xenibe.artifacts.naming import is_experiment_name
from xenibe.artifacts.store import experiment_dir, experiments_root, utc_now, write_yaml

from forge.common import relative_files


def archive_experiment(root: Path, experiment: str, dry_run: bool = False) -> dict[str, Any]:
    if not is_experiment_name(experiment):
        return {"error": "invalid-name", "message": "experiment name must be kebab-case", "target": "experiment", "fix": "use a canonical experiment name"}
    source = experiment_dir(root, experiment)
    try:
        source.resolve().relative_to(experiments_root(root).resolve())
    except ValueError:
        return {"error": "invalid-name", "message": "experiment path must stay inside the artifact experiment root", "target": "experiment"}
    if not source.exists():
        return {"error": "missing-artifact", "message": "experiment not found"}
    timestamp = utc_now().replace(":", "").replace("+", "z")
    target = root / "archived" / f"{experiment}-{timestamp}"
    payload: dict[str, Any] = {
        "experiment": experiment,
        "archive": str(target),
        "source": str(source),
        "fileInventory": relative_files(source),
        "metadata": {"source-experiment": experiment, "timestamp": utc_now(), "operation": "move"},
    }
    if dry_run:
        payload["plannedActions"] = ["move experiment artifacts out of the active catalog", "write archive.yml"]
        return payload
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    write_yaml(target / "archive.yml", payload["metadata"])
    return payload
