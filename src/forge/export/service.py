from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from xenibe.artifacts.history import file_sha256
from xenibe.artifacts.naming import is_experiment_name
from xenibe.artifacts.schemas import COMPACT_RUN_ARTIFACTS
from xenibe.artifacts.store import experiment_dir, experiments_root, make_run_id, utc_now, write_json

from forge.common import run_dir
from forge.run_consumer import completed_run


def _bundle_files(source: Path, include: tuple[str, ...] | None = None) -> tuple[list[dict[str, Any]], int]:
    if include is not None:
        paths = [source / name for name in include if (source / name).is_file()]
    else:
        paths = [source] if source.is_file() else sorted(path for path in source.rglob("*") if path.is_file())
    files: list[dict[str, Any]] = []
    byte_size = 0
    for path in paths:
        content = path.read_bytes()
        byte_size += len(content)
        files.append(
            {
                "path": path.name if source.is_file() else str(path.relative_to(source)),
                "size": len(content),
                "sha256": file_sha256(path),
                "encoding": "base64",
                "content": base64.b64encode(content).decode("ascii"),
            }
        )
    return files, byte_size


def _experiment_source(root: Path, experiment: str) -> Path | dict[str, Any]:
    if not is_experiment_name(experiment):
        return {"error": "invalid-name", "message": "experiment name must be kebab-case", "target": "experiment", "fix": "use a canonical experiment name"}
    source = experiment_dir(root, experiment)
    try:
        source.resolve().relative_to(experiments_root(root).resolve())
    except ValueError:
        return {"error": "invalid-name", "message": "experiment path must stay inside the artifact experiment root", "target": "experiment"}
    return source


def _export_payload(kind: str, source: Path, experiment: str, run_id: str | None = None, include: tuple[str, ...] | None = None) -> dict[str, Any]:
    files, byte_size = _bundle_files(source, include)
    created_at = utc_now()
    return {
        "schemaVersion": 1,
        "metadata": {
            "type": kind,
            "source": str(source),
            "sourceExperiment": experiment,
            "sourceRunId": run_id,
            "createdAt": created_at,
            "fileCount": len(files),
            "byteSize": byte_size,
        },
        "bundle": {
            "encoding": "base64",
            "files": files,
        },
    }


def export_experiment(root: Path, experiment: str, dry_run: bool = False) -> dict[str, Any]:
    source = _experiment_source(root, experiment)
    if isinstance(source, dict):
        return source
    if not source.exists():
        return {"error": "missing-artifact", "message": "experiment not found"}
    target = root / "exports" / f"experiment-{experiment}-{make_run_id('sim')}.json"
    package = _export_payload("experiment", source, experiment)
    payload: dict[str, Any] = {"experiment": experiment, "export": str(target), "metadata": package["metadata"]}
    if dry_run:
        payload["plannedActions"] = ["write portable experiment export package"]
        return payload
    write_json(target, package)
    return payload


def export_run(root: Path, experiment: str, run_id: str, dry_run: bool = False) -> dict[str, Any]:
    experiment_source = _experiment_source(root, experiment)
    if isinstance(experiment_source, dict):
        return experiment_source
    source = run_dir(root, experiment, run_id)
    loaded = completed_run(root, experiment, run_id)
    if "error" in loaded:
        return loaded
    target = root / "exports" / f"run-{experiment}-{run_id}-{make_run_id('sim')}.json"
    include = COMPACT_RUN_ARTIFACTS if loaded.get("layout") == "compact" else None
    package = _export_payload("run", source, experiment, run_id, include)
    payload: dict[str, Any] = {"experiment": experiment, "runId": run_id, "export": str(target), "metadata": package["metadata"]}
    if dry_run:
        payload["plannedActions"] = ["write portable run export package"]
        return payload
    write_json(target, package)
    return payload
