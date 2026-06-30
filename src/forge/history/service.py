from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from xenibe.artifacts.history import (
    canonical_history_path,
    canonical_history_relative_path,
    canonical_manifest_path,
    canonical_manifest_relative_path,
    expanded_range,
    file_sha256,
    iso_datetime,
    manifest_range,
    parse_datetime,
    range_contains,
    ranges_touch_or_overlap,
    relative_posix,
    request_range,
    safe_history_label,
)
from xenibe.artifacts.store import experiment_dir, load_json, load_yaml, utc_now, write_json, write_yaml

from forge.common import normalize_record, provider_error_payload, provider_metadata
from forge.context import CommandContext


def _history_path(root: Path, experiment: str, asset: str, timeframe: str, start: str, end: str) -> Path:
    return canonical_history_path(experiment_dir(root, experiment), asset, timeframe)


def _manifest_path(root: Path, experiment: str, asset: str, timeframe: str) -> Path:
    return canonical_manifest_path(experiment_dir(root, experiment), asset, timeframe)


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = ["time", "asset", "timeframe", "open", "high", "low", "close"]
    extras = sorted({key for record in records for key in record} - set(ordered))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*ordered, *extras])
        writer.writeheader()
        for record in records:
            writer.writerow(record)


def _csv_candle_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return sum(1 for _ in reader)


def _normalize_candle_records(candles: Any, asset: str, timeframe: str, start: str, end: str) -> list[dict[str, Any]]:
    requested = request_range(start, end)
    records: list[dict[str, Any]] = []
    for candle in candles or []:
        record = normalize_record(candle)
        if "time" not in record and "timestamp" in record:
            record["time"] = record["timestamp"]
        record.setdefault("asset", asset)
        record.setdefault("timeframe", timeframe)
        candle_time = parse_datetime(record.get("time"))
        if requested is not None and candle_time is not None and not (requested[0] <= candle_time < requested[1]):
            continue
        records.append(record)
    records.sort(key=lambda item: str(item.get("time", "")))
    return records


def _canonical_payload(
    experiment: str,
    asset: str,
    timeframe: str,
    start: str,
    end: str,
    path: Path,
    manifest_path: Path,
    action: str,
    candle_count: int,
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "experiment": experiment,
        "asset": asset,
        "timeframe": timeframe,
        "from": start,
        "to": end,
        "requestedRange": {"from": start, "to": end},
        "path": str(path),
        "relativePath": relative_posix(canonical_history_relative_path(asset, timeframe)),
        "manifestPath": str(manifest_path),
        "manifestRelativePath": relative_posix(canonical_manifest_relative_path(asset, timeframe)),
        "candleCount": candle_count,
        "action": action,
        **(metadata or {"provider": "ebinex"}),
    }


def _write_manifest(
    manifest_path: Path,
    asset: str,
    timeframe: str,
    requested_start: str,
    requested_end: str,
    coverage_start: str,
    coverage_end: str,
    csv_path: Path,
    candle_count: int,
    metadata: dict[str, str],
) -> dict[str, Any]:
    manifest = {
        "asset": safe_history_label(asset),
        "timeframe": safe_history_label(timeframe),
        "requestedRange": {"from": requested_start, "to": requested_end},
        "coverageRange": {"from": coverage_start, "to": coverage_end},
        "path": relative_posix(canonical_history_relative_path(asset, timeframe)),
        "candleCount": candle_count,
        "sha256": file_sha256(csv_path),
        "provider": metadata.get("provider"),
        "providerMode": metadata.get("mode"),
        "downloadedAt": utc_now(),
    }
    write_json(manifest_path, manifest)
    return manifest


def _manifest_conflict(message: str, path: Path) -> dict[str, Any]:
    return {
        "error": "canonical-history-conflict",
        "message": message,
        "path": str(path),
        "next": ["re-run history download for the desired full range", "pass --replace only for disconnected replacement when the manifest is valid"],
    }


def _load_valid_manifest(path: Path, csv_path: Path, asset: str, timeframe: str) -> dict[str, Any] | dict[str, str]:
    if not csv_path.exists() and not path.exists():
        return {}
    if csv_path.exists() and not path.exists():
        return _manifest_conflict(f"canonical CSV exists without paired manifest: {path}", path)
    if path.exists() and not csv_path.exists():
        return _manifest_conflict(f"canonical manifest exists without paired CSV: {csv_path}", path)
    try:
        manifest = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _manifest_conflict(f"canonical manifest is malformed: {exc}", path)
    expected_path = relative_posix(canonical_history_relative_path(asset, timeframe))
    if str(manifest.get("asset", "")).upper() != safe_history_label(asset):
        return _manifest_conflict("canonical manifest asset does not match requested asset", path)
    if str(manifest.get("timeframe", "")).upper() != safe_history_label(timeframe):
        return _manifest_conflict("canonical manifest timeframe does not match requested timeframe", path)
    if manifest.get("path") != expected_path:
        return _manifest_conflict(f"canonical manifest path must be {expected_path}", path)
    if manifest_range(manifest) is None:
        return _manifest_conflict("canonical manifest coverageRange is missing or invalid", path)
    if not isinstance(manifest.get("candleCount"), int) or int(manifest["candleCount"]) < 0:
        return _manifest_conflict("canonical manifest candleCount must be a non-negative integer", path)
    try:
        if manifest.get("sha256") != file_sha256(csv_path):
            return _manifest_conflict("canonical manifest checksum does not match CSV", path)
        if int(manifest["candleCount"]) != _csv_candle_count(csv_path):
            return _manifest_conflict("canonical manifest candleCount does not match CSV", path)
    except OSError as exc:
        return _manifest_conflict(f"canonical CSV cannot be read: {exc}", csv_path)
    return manifest


def _update_ingest(base: Path, asset: str, timeframe: str, start: str, end: str) -> None:
    path = base / "ingest.yml"
    ingest = load_yaml(path)
    data = ingest.setdefault("data", {})
    data["asset"] = asset
    data["timeframe"] = timeframe
    data["from"] = start
    data["to"] = end
    data["path"] = relative_posix(canonical_history_relative_path(asset, timeframe))
    write_yaml(path, ingest)


def _coverage_decision(
    manifest: dict[str, Any],
    requested: tuple[Any, Any],
    replace: bool,
) -> tuple[str, tuple[Any, Any]]:
    coverage = manifest_range(manifest)
    if coverage is None:
        return "conflict", requested
    if range_contains(coverage, requested):
        return "reuse", coverage
    if ranges_touch_or_overlap(coverage, requested):
        return "expand", expanded_range(coverage, requested)
    if replace:
        return "replace", requested
    return "replace-required", requested


def _planned_actions(action: str) -> list[str]:
    actions = {
        "download": ["fetch provider candles", "write canonical CSV", "write paired manifest", "update ingest.yml"],
        "reuse": ["reuse canonical CSV", "verify paired manifest", "update ingest.yml"],
        "expand": ["fetch provider candles for full expanded range", "overwrite canonical CSV", "write paired manifest", "update ingest.yml"],
        "replace": ["fetch provider candles for replacement range", "overwrite canonical CSV", "write paired manifest", "update ingest.yml"],
    }
    return actions.get(action, ["report canonical history conflict"])


def download(context: CommandContext, experiment: str, asset: str, timeframe: str, start: str, end: str, replace: bool = False) -> dict[str, Any]:
    base = experiment_dir(context.root, experiment)
    if not base.exists():
        return {"error": "missing-artifact", "message": "experiment not found"}
    path = _history_path(context.root, experiment, asset, timeframe, start, end)
    manifest_path = _manifest_path(context.root, experiment, asset, timeframe)
    requested = request_range(start, end)
    if requested is None:
        return {"error": "invalid-artifact", "message": "--from and --to must be valid ISO dates with --to after --from"}
    manifest = _load_valid_manifest(manifest_path, path, asset, timeframe)
    if "error" in manifest:
        return manifest
    action = "download"
    download_range = requested
    if manifest:
        action, download_range = _coverage_decision(manifest, requested, replace)
    if action == "replace-required":
        return {
            "error": "replace-required",
            "message": "requested range is disconnected from canonical coverage; pass --replace to overwrite it",
            "path": str(path),
            "manifestPath": str(manifest_path),
            "requestedRange": {"from": start, "to": end},
            "coverageRange": manifest.get("coverageRange") if manifest else None,
        }
    if action == "conflict":
        return _manifest_conflict("canonical coverage cannot be safely reused or expanded", manifest_path)
    if context.dry_run:
        payload = _canonical_payload(experiment, asset, timeframe, start, end, path, manifest_path, action, int(manifest.get("candleCount", 0)) if manifest else 0, {"provider": "ebinex", "mode": "dry-run"})
        payload["plannedActions"] = _planned_actions(action)
        payload["coverageRange"] = {"from": iso_datetime(download_range[0]), "to": iso_datetime(download_range[1])}
        return payload
    if action == "reuse":
        _update_ingest(base, asset, timeframe, start, end)
        payload = _canonical_payload(experiment, asset, timeframe, start, end, path, manifest_path, action, int(manifest.get("candleCount", 0)), {"provider": str(manifest.get("provider", "ebinex")), "mode": str(manifest.get("providerMode", "live"))})
        payload["coverageRange"] = manifest.get("coverageRange")
        payload["downloadedAt"] = manifest.get("downloadedAt")
        return payload
    download_start = start if download_range == requested else iso_datetime(download_range[0])
    download_end = end if download_range == requested else iso_datetime(download_range[1])
    try:
        provider = context.provider()
        candles = provider.historical_candles(asset, timeframe, download_start, download_end)
    except Exception as exc:
        return provider_error_payload(exc)
    metadata = provider_metadata(provider)
    normalized = _normalize_candle_records(candles, asset, timeframe, download_start, download_end)
    _write_csv(path, normalized)
    manifest_data = _write_manifest(manifest_path, asset, timeframe, start, end, iso_datetime(download_range[0]), iso_datetime(download_range[1]), path, len(normalized), metadata)
    _update_ingest(base, asset, timeframe, start, end)
    payload = {
        **_canonical_payload(experiment, asset, timeframe, start, end, path, manifest_path, action, len(normalized), metadata),
        "coverageRange": manifest_data["coverageRange"],
        "downloadedAt": utc_now(),
    }
    return payload
