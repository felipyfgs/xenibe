from __future__ import annotations

from pathlib import Path
from typing import Any

from forge.common import run_dir
from forge.run_consumer import completed_run


def show(root: Path, experiment: str, run_id: str) -> dict[str, Any]:
    directory = run_dir(root, experiment, run_id)
    loaded = completed_run(root, experiment, run_id)
    if "error" in loaded:
        return loaded
    report_path = directory / "report.md"
    mode = loaded["manifest"].get("mode")
    return {"experiment": experiment, "runId": run_id, "mode": mode, "reportPath": str(report_path), "report": report_path.read_text(encoding="utf-8")}
