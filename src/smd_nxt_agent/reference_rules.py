"""Lookup helpers over the transcribed Fuji reference tables.

`config/reference/nozzle_compatibility.yaml` and
`config/reference/vision_type_table.yaml` are *unverified* transcriptions
(see their header comments). This module only reads them and returns
candidate matches — it never decides whether a match is trustworthy.
That call belongs to `validate.py`, which forces `needs_review=True`
whenever `MachineMapping.reference_unverified` is set, until a human
flips `verified: true` in the source YAML.

Matching is deliberately conservative: a part's `package_name` must
case-insensitively equal one of a category's/entry's `aliases` (or its
id). No fuzzy/substring matching, to avoid silently picking the wrong
row in a safety-critical lookup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from smd_nxt_agent.schema import ComponentSpec

NOZZLE_COMPAT_FILENAME = "nozzle_compatibility.yaml"
VISION_TABLE_FILENAME = "vision_type_table.yaml"

# Symbols from nozzle_compatibility.yaml that mean "a nozzle can be used".
_SUPPORTED_SYMBOL_PREFIXES = ("supported", "multi:", "image_individual")


class ReferenceData:
    def __init__(
        self,
        nozzle_compat: dict[str, Any] | None,
        vision_table: dict[str, Any] | None,
    ) -> None:
        self.nozzle_compat = nozzle_compat
        self.vision_table = vision_table

    @property
    def nozzle_compat_verified(self) -> bool:
        return bool(self.nozzle_compat and self.nozzle_compat.get("verified"))

    @property
    def vision_table_verified(self) -> bool:
        return bool(self.vision_table and self.vision_table.get("verified"))

    def available_heads(self) -> list[str]:
        if not self.nozzle_compat:
            return []
        return sorted(self.nozzle_compat.get("heads", {}).keys())


def load_reference(config_dir: Path) -> ReferenceData:
    ref_dir = config_dir / "reference"
    nozzle_compat = None
    vision_table = None

    nozzle_path = ref_dir / NOZZLE_COMPAT_FILENAME
    if nozzle_path.exists():
        nozzle_compat = yaml.safe_load(nozzle_path.read_text())

    vision_path = ref_dir / VISION_TABLE_FILENAME
    if vision_path.exists():
        vision_table = yaml.safe_load(vision_path.read_text())

    return ReferenceData(nozzle_compat=nozzle_compat, vision_table=vision_table)


def _matches_aliases(package_name: str, aliases: list[str], category_id: str) -> bool:
    needle = package_name.strip().lower()
    if needle == category_id.strip().lower():
        return True
    return any(needle == alias.strip().lower() for alias in aliases)


def lookup_nozzle(
    spec: ComponentSpec, head_id: str | None, ref: ReferenceData
) -> tuple[str, str, str] | None:
    """Returns (nozzle_id, rule_id, rationale) or None if no confident match."""
    if not head_id or not ref.nozzle_compat:
        return None

    heads = ref.nozzle_compat.get("heads", {})
    head_table = heads.get(head_id)
    if not head_table:
        return None

    for category in ref.nozzle_compat.get("package_categories", []):
        category_id = category["id"]
        if not _matches_aliases(spec.package_name, category.get("aliases", []), category_id):
            continue

        symbol = head_table.get(category_id)
        if not symbol or not symbol.startswith(_SUPPORTED_SYMBOL_PREFIXES):
            return None  # matched category, but this head can't take it — no nozzle guess

        diameter_mm = category.get("diameter_mm")
        if diameter_mm is None:
            return None  # supported per the table, but no diameter recorded to act on

        nozzle_id = f"{diameter_mm}mm"
        rationale = (
            f"Reference table (unverified): head={head_id}, package={category_id}, "
            f"symbol={symbol} -> nozzle diameter {diameter_mm}mm"
        )
        return nozzle_id, f"reference_nozzle_{category_id}", rationale

    return None


def lookup_vision(spec: ComponentSpec, ref: ReferenceData) -> tuple[str, str, str] | None:
    """Returns (vision_type, rule_id, rationale) or None if no confident match."""
    if not ref.vision_table:
        return None

    for entry in ref.vision_table.get("entries", []):
        part_type_id = entry["part_type_id"]
        if not _matches_aliases(spec.package_name, entry.get("aliases", []), part_type_id):
            continue

        rationale = (
            f"Reference table (unverified): package matched {part_type_id} "
            f"-> vision_type {entry['vision_type']}"
            + (f" ({entry['remarks']})" if entry.get("remarks") else "")
        )
        return entry["vision_type"], f"reference_vision_{part_type_id}", rationale

    return None
