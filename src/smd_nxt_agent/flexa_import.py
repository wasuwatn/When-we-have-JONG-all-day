"""Seeds nozzle/vision rules and test fixtures from a Flexa part-library export.

SCAFFOLD: the real Flexa export and its column layout have not been
provided yet. `_read_export()` is the one function to adapt once it
arrives — everything downstream (bucketing, rule derivation, fixture
generation) is format-agnostic and works off the intermediate
`FlexaPartRow` records it produces.

Expected export shape (TODO: confirm against the real file): one row per
historical part, as CSV, with at least these columns:
    part_number, package_name, lead_type, body_length_mm, body_width_mm,
    body_height_mm, is_polarized, nozzle, vision_type
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FlexaPartRow:
    part_number: str
    package_name: str
    lead_type: str
    body_length_mm: float
    body_width_mm: float
    body_height_mm: float
    is_polarized: bool
    nozzle: str
    vision_type: str


def _read_export(export_path: Path) -> list[FlexaPartRow]:
    """TODO: adapt to the real Flexa export format once it's provided.

    Currently assumes a CSV with the columns documented in the module
    docstring.
    """
    rows: list[FlexaPartRow] = []
    with export_path.open(newline="") as f:
        for row in csv.DictReader(f):
            rows.append(
                FlexaPartRow(
                    part_number=row["part_number"],
                    package_name=row["package_name"],
                    lead_type=row["lead_type"],
                    body_length_mm=float(row["body_length_mm"]),
                    body_width_mm=float(row["body_width_mm"]),
                    body_height_mm=float(row["body_height_mm"]),
                    is_polarized=row["is_polarized"].strip().lower() in {"1", "true", "yes"},
                    nozzle=row["nozzle"],
                    vision_type=row["vision_type"],
                )
            )
    return rows


def _derive_nozzle_rules(rows: list[FlexaPartRow]) -> list[dict[str, object]]:
    """For each lead_type, pick the historically most common nozzle as a rule."""
    by_lead_type: dict[str, Counter[str]] = {}
    for row in rows:
        by_lead_type.setdefault(row.lead_type, Counter())[row.nozzle] += 1

    rules: list[dict[str, object]] = []
    for lead_type, counts in sorted(by_lead_type.items()):
        nozzle, count = counts.most_common(1)[0]
        rules.append(
            {
                "id": f"flexa_{lead_type}",
                "when": {"lead_type": [lead_type]},
                "nozzle": nozzle,
                "rationale": f"Historically the most common nozzle ({count} parts) for "
                f"lead_type={lead_type} in the Flexa export.",
            }
        )
    return rules


def _derive_vision_rules(rows: list[FlexaPartRow]) -> list[dict[str, object]]:
    by_lead_type: dict[str, Counter[str]] = {}
    for row in rows:
        by_lead_type.setdefault(row.lead_type, Counter())[row.vision_type] += 1

    rules: list[dict[str, object]] = []
    for lead_type, counts in sorted(by_lead_type.items()):
        vision_type, count = counts.most_common(1)[0]
        rules.append(
            {
                "id": f"flexa_{lead_type}_vision",
                "lead_type": lead_type,
                "vision_type": vision_type,
                "rationale": f"Historically the most common vision type ({count} parts) for "
                f"lead_type={lead_type} in the Flexa export.",
            }
        )
    return rules


def _write_fixtures(rows: list[FlexaPartRow], fixtures_dir: Path, *, sample_size: int = 5) -> None:
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    for row in rows[:sample_size]:
        spec = {
            "package_name": row.package_name,
            "body_length_mm": row.body_length_mm,
            "body_width_mm": row.body_width_mm,
            "body_height_mm": row.body_height_mm,
            "lead_type": row.lead_type,
            "is_polarized": row.is_polarized,
            "confidence": 0.95,
            "needs_review": False,
            "source_notes": f"Derived from Flexa export, part_number={row.part_number}.",
        }
        out_path = fixtures_dir / f"flexa_{row.part_number}.json"
        out_path.write_text(json.dumps(spec, indent=2))


def import_flexa(export_path: Path, config_dir: Path, fixtures_dir: Path) -> None:
    """Reads a Flexa export and regenerates nozzle_rules.yaml/vision_rules.yaml + fixtures.

    Does not touch machine.yaml (nozzle/vision catalog + thresholds stay
    user-maintained); only the derived rule lists and sample fixtures are
    written.
    """
    import yaml

    rows = _read_export(export_path)
    if not rows:
        raise ValueError(f"No rows read from Flexa export: {export_path}")

    nozzle_rules = _derive_nozzle_rules(rows)
    vision_rules = _derive_vision_rules(rows)

    (config_dir / "nozzle_rules.yaml").write_text(
        yaml.safe_dump({"rules": nozzle_rules}, sort_keys=False)
    )
    (config_dir / "vision_rules.yaml").write_text(
        yaml.safe_dump({"rules": vision_rules}, sort_keys=False)
    )
    _write_fixtures(rows, fixtures_dir)

    print(
        f"Derived {len(nozzle_rules)} nozzle rules and {len(vision_rules)} vision rules "
        f"from {len(rows)} Flexa parts."
    )
