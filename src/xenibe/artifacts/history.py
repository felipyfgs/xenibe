from __future__ import annotations

import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def safe_history_label(value: str) -> str:
    return value.replace("/", "-").replace(" ", "-").upper()


def canonical_history_relative_path(asset: str, timeframe: str) -> Path:
    return Path("data") / f"{safe_history_label(asset)}_{safe_history_label(timeframe)}.csv"


def canonical_manifest_relative_path(asset: str, timeframe: str) -> Path:
    stem = canonical_history_relative_path(asset, timeframe).stem
    return Path("data") / f"{stem}.manifest.json"


def canonical_history_path(experiment_path: Path, asset: str, timeframe: str) -> Path:
    return experiment_path / canonical_history_relative_path(asset, timeframe)


def canonical_manifest_path(experiment_path: Path, asset: str, timeframe: str) -> Path:
    return experiment_path / canonical_manifest_relative_path(asset, timeframe)


def relative_posix(path: Path) -> str:
    return path.as_posix()


def parse_datetime(value: Any) -> datetime | None:
    if hasattr(value, "isoformat") and not isinstance(value, str):
        value = value.isoformat()
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    candidates = [text.replace("Z", "+00:00")]
    if "T" not in text and " " not in text:
        candidates.append(f"{text}T00:00:00+00:00")
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def iso_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_history_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = ["time", "asset", "timeframe", "open", "high", "low", "close"]
    extras = sorted({key for record in records for key in record} - set(ordered))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*ordered, *extras])
        writer.writeheader()
        for record in records:
            writer.writerow(record)


def csv_candle_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return sum(1 for _ in reader)


def validate_canonical_manifest(manifest: dict[str, Any], csv_path: Path, asset: str, timeframe: str) -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []
    expected_path = relative_posix(canonical_history_relative_path(asset, timeframe))
    if str(manifest.get("asset", "")).upper() != safe_history_label(asset):
        errors.append(("asset", "must match ingest.yml:data.asset"))
    if str(manifest.get("timeframe", "")).upper() != safe_history_label(timeframe):
        errors.append(("timeframe", "must match ingest.yml:data.timeframe"))
    if manifest.get("path") != expected_path:
        errors.append(("path", f"must equal {expected_path}"))
    if manifest_range(manifest) is None:
        errors.append(("coverageRange", "must contain valid from/to coverage dates"))
    if not isinstance(manifest.get("candleCount"), int) or int(manifest.get("candleCount", 0)) <= 0:
        errors.append(("candleCount", "must be a positive integer"))
    else:
        try:
            actual_count = csv_candle_count(csv_path)
        except OSError as exc:
            errors.append(("csv", str(exc)))
        else:
            if int(manifest["candleCount"]) != actual_count:
                errors.append(("candleCount", "must match the canonical CSV row count"))
    if str(manifest.get("providerMode", "")).lower() in {"offline", "offline-contract"}:
        errors.append(("providerMode", "offline provider mode is not supported for canonical history"))
    if not isinstance(manifest.get("sha256"), str) or not manifest.get("sha256"):
        errors.append(("sha256", "must be a non-empty checksum"))
    else:
        try:
            actual_hash = file_sha256(csv_path)
        except OSError as exc:
            errors.append(("csv", str(exc)))
        else:
            if manifest["sha256"] != actual_hash:
                errors.append(("sha256", "must match the canonical CSV checksum"))
    return errors


def manifest_range(manifest: dict[str, Any], key: str = "coverageRange") -> tuple[datetime, datetime] | None:
    value = manifest.get(key)
    if not isinstance(value, dict):
        return None
    start = parse_datetime(value.get("from"))
    end = parse_datetime(value.get("to"))
    if start is None or end is None or start >= end:
        return None
    return start, end


def request_range(start: Any, end: Any) -> tuple[datetime, datetime] | None:
    parsed_start = parse_datetime(start)
    parsed_end = parse_datetime(end)
    if parsed_start is None or parsed_end is None or parsed_start >= parsed_end:
        return None
    return parsed_start, parsed_end


def range_contains(outer: tuple[datetime, datetime], inner: tuple[datetime, datetime]) -> bool:
    return outer[0] <= inner[0] and inner[1] <= outer[1]


def ranges_touch_or_overlap(left: tuple[datetime, datetime], right: tuple[datetime, datetime]) -> bool:
    return left[0] <= right[1] and right[0] <= left[1]


def expanded_range(left: tuple[datetime, datetime], right: tuple[datetime, datetime]) -> tuple[datetime, datetime]:
    return min(left[0], right[0]), max(left[1], right[1])
