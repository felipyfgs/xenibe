from __future__ import annotations

from pathlib import Path
from typing import Any

from xenibe.artifacts.store import experiment_dir, make_run_id, utc_now, write_json

from forge.common import relative_files, run_dir
from forge.run_consumer import completed_run


def _export_payload(kind: str, source: Path, experiment: str, run_id: str | None = None) -> dict[str, Any]:
    return {
        "type": kind,
        "source": str(source),
        "sourceExperiment": experiment,
        "sourceRunId": run_id,
        "exportedAt": utc_now(),
        "includedFiles": relative_files(source),
    }


def export_experiment(root: Path, experiment: str, dry_run: bool = False) -> dict[str, Any]:
    source = experiment_dir(root, experiment)
    if not source.exists():
        return {"error": "missing-artifact", "message": "experiment not found"}
    target = root / "promoted" / experiment / "portable" / f"experiment-{experiment}-{make_run_id('sim')}.json"
    metadata = _export_payload("experiment", source, experiment)
    payload: dict[str, Any] = {"experiment": experiment, "export": str(target), "metadata": metadata}
    if dry_run:
        payload["plannedActions"] = ["write portable experiment export metadata"]
        return payload
    write_json(target, metadata)
    return payload


def export_run(root: Path, experiment: str, run_id: str, dry_run: bool = False) -> dict[str, Any]:
    source = run_dir(root, experiment, run_id)
    loaded = completed_run(root, experiment, run_id)
    if "error" in loaded:
        return loaded
    target = root / "promoted" / experiment / "portable" / f"run-{experiment}-{run_id}-{make_run_id('sim')}.json"
    metadata = _export_payload("run", source, experiment, run_id)
    payload: dict[str, Any] = {"experiment": experiment, "runId": run_id, "export": str(target), "metadata": metadata}
    if dry_run:
        payload["plannedActions"] = ["write portable run export metadata"]
        return payload
    write_json(target, metadata)
    return payload
