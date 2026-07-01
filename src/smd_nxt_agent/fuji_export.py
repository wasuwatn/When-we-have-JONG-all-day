"""Adapter: PartRecord list -> Auto-gen-part-Fuji parameter-based batch CSV.

Auto-gen-part-Fuji (https://github.com/wasuwatn/Auto-gen-part-Fuji) reads a
CSV with columns `partno, part_type, body_x, body_y, body_h, tol_x, tol_y,
pin_count, pitch_x, pitch_y, tape_width, feed_pitch, feeder_type, comment,
creator` (its "parameter-based" batch mode; see its README and
`fuji_generator/batch.py`). This module builds that CSV from this
project's `parts.json` output.

Kept separate from mapping.py/validate.py so those stay pure functions of
(ComponentSpec, config) with no knowledge of a downstream tool's file
format. Field mapping constants live in config/fuji_export.yaml, never
here, per CLAUDE.md.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from smd_nxt_agent.schema import ComponentSpec, PartRecord

FUJI_CSV_FIELDS = [
    "partno",
    "part_type",
    "body_x",
    "body_y",
    "body_h",
    "tol_x",
    "tol_y",
    "pin_count",
    "pitch_x",
    "pitch_y",
    "tape_width",
    "feed_pitch",
    "feeder_type",
    "comment",
    "creator",
]


@dataclass
class SkippedRecord:
    source_file: str
    reason: str


@dataclass
class ExportResult:
    rows: list[dict[str, object]]
    skipped: list[SkippedRecord]


def load_export_config(config_dir: Path) -> dict[str, Any]:
    return cast(
        "dict[str, Any]", yaml.safe_load((config_dir / "fuji_export.yaml").read_text())
    )


def load_parts(parts_json: Path) -> list[PartRecord]:
    data = json.loads(parts_json.read_text())
    return [PartRecord.model_validate(item) for item in data]


def load_decisions(decisions_path: Path | None) -> dict[str, str]:
    if decisions_path is None or not decisions_path.exists():
        return {}
    return cast("dict[str, str]", json.loads(decisions_path.read_text()))


def _is_exportable(record: PartRecord, decisions: dict[str, str]) -> bool:
    """Safety gate: only human-reviewable-OK records reach the machine.

    A record is exportable if validation passed outright, or if a human
    explicitly confirmed it in human_review_decisions.json. Anything else
    (needs_review and not confirmed, or explicitly rejected) is skipped,
    never silently exported.
    """
    if record.validation.ok:
        return True
    return decisions.get(record.source_file) == "confirmed"


def _to_ascii(text: str) -> str:
    return text.encode("ascii", "ignore").decode("ascii")


def _sanitize_partno(raw: str) -> str:
    partno = _to_ascii(raw).replace("/", "-").replace("\\", "-").strip()
    return partno[:255]


def _part_type(spec: ComponentSpec, config: dict[str, Any]) -> str:
    return cast(
        str,
        config["part_type_by_lead_type"].get(spec.lead_type.value, config["default_part_type"]),
    )


def _comment(spec: ComponentSpec) -> str:
    parts = [p for p in (spec.package_name, spec.manufacturer, spec.part_number) if p]
    return _to_ascii(" ".join(parts))[:255]


def _record_to_fuji_row(record: PartRecord, config: dict[str, Any]) -> dict[str, object]:
    spec = record.spec
    partno = _sanitize_partno(spec.part_number or Path(record.source_file).stem)

    row: dict[str, object] = {
        "partno": partno,
        "part_type": _part_type(spec, config),
        "body_x": spec.body_width_mm,
        "body_y": spec.body_length_mm,
        "body_h": spec.body_height_mm,
        "tol_x": config["default_tol_x_mm"],
        "tol_y": config["default_tol_y_mm"],
        "tape_width": int(spec.tape_width_mm)
        if spec.tape_width_mm is not None
        else config["default_tape_width_mm"],
        "feed_pitch": int(spec.pocket_pitch_mm)
        if spec.pocket_pitch_mm is not None
        else config["default_feed_pitch_mm"],
        "feeder_type": config["default_feeder_type"],
        "comment": _comment(spec),
        "creator": config["creator"],
    }

    if spec.lead_count and spec.lead_pitch_mm:
        row["pin_count"] = spec.lead_count
        row["pitch_x"] = spec.lead_pitch_mm
        row["pitch_y"] = spec.lead_pitch_mm

    return row


def build_fuji_rows(
    records: list[PartRecord],
    config: dict[str, Any],
    decisions: dict[str, str] | None = None,
) -> ExportResult:
    decisions = decisions or {}
    rows: list[dict[str, object]] = []
    skipped: list[SkippedRecord] = []

    for record in records:
        if not _is_exportable(record, decisions):
            skipped.append(
                SkippedRecord(
                    source_file=record.source_file,
                    reason="validation.ok=False and not confirmed in human_review_decisions.json",
                )
            )
            continue
        rows.append(_record_to_fuji_row(record, config))

    return ExportResult(rows=rows, skipped=skipped)


def write_fuji_csv(result: ExportResult, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "fuji_parts.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FUJI_CSV_FIELDS, restval="")
        writer.writeheader()
        for row in result.rows:
            writer.writerow(row)

    skipped_path = out_dir / "fuji_export_skipped.json"
    skipped_payload = [
        {"source_file": s.source_file, "reason": s.reason} for s in result.skipped
    ]
    skipped_path.write_text(json.dumps(skipped_payload, indent=2))

    return csv_path


def run(
    parts_json: Path,
    out_dir: Path,
    *,
    config_dir: Path = Path("config"),
    decisions_path: Path | None = None,
) -> ExportResult:
    records = load_parts(parts_json)
    config = load_export_config(config_dir)
    decisions = load_decisions(decisions_path)
    result = build_fuji_rows(records, config, decisions)
    write_fuji_csv(result, out_dir)
    print(f"EXPORTED: {len(result.rows)}  SKIPPED: {len(result.skipped)}  TOTAL: {len(records)}")
    return result
