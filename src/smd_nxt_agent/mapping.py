"""Pure, rule-based nozzle + vision selection.

No AI runs here. Every threshold, nozzle id, and vision id comes from
`config/`; this module contains zero machine constants. Rule conditions
are evaluated by a small safe interpreter (see `_condition_matches`) —
never `eval()`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from smd_nxt_agent import reference_rules
from smd_nxt_agent.schema import ComponentSpec, MachineMapping

FALLBACK_NOZZLE_RULE_ID = "fallback"
FALLBACK_VISION_RULE_ID = "fallback"


class Rules:
    def __init__(
        self,
        nozzle_rules: list[dict[str, Any]],
        vision_rules: list[dict[str, Any]],
        machine: dict[str, Any],
        reference: reference_rules.ReferenceData | None = None,
    ) -> None:
        self.nozzle_rules = nozzle_rules
        self.vision_rules = vision_rules
        self.machine = machine
        self.reference = reference or reference_rules.ReferenceData(None, None)


def load_rules(config_dir: Path) -> Rules:
    nozzle_doc = yaml.safe_load((config_dir / "nozzle_rules.yaml").read_text())
    vision_doc = yaml.safe_load((config_dir / "vision_rules.yaml").read_text())
    machine = yaml.safe_load((config_dir / "machine.yaml").read_text())
    reference = reference_rules.load_reference(config_dir)
    return Rules(
        nozzle_rules=nozzle_doc.get("rules", []),
        vision_rules=vision_doc.get("rules", []),
        machine=machine,
        reference=reference,
    )


def _condition_matches(spec: ComponentSpec, field: str, condition: Any) -> bool:
    value = getattr(spec, field, None)
    field_value = getattr(value, "value", value)

    if isinstance(condition, list):
        return bool(field_value in condition)
    if isinstance(condition, dict):
        if field_value is None:
            return False
        if "max" in condition and field_value > condition["max"]:
            return False
        if "min" in condition and field_value < condition["min"]:
            return False
        return True
    return bool(field_value == condition)


def _rule_matches(spec: ComponentSpec, when: dict[str, Any]) -> bool:
    return all(_condition_matches(spec, field, condition) for field, condition in when.items())


def select_nozzle(spec: ComponentSpec, rules: Rules) -> tuple[str, str, str, bool, bool]:
    """Returns (nozzle, rule_id, rationale, fallback_used, reference_unverified)."""
    head_id = rules.machine.get("head")
    ref_match = reference_rules.lookup_nozzle(spec, head_id, rules.reference)
    if ref_match is not None:
        nozzle, rule_id, rationale = ref_match
        return nozzle, rule_id, rationale, False, not rules.reference.nozzle_compat_verified

    for rule in rules.nozzle_rules:
        if _rule_matches(spec, rule.get("when", {})):
            return rule["nozzle"], rule["id"], rule.get("rationale", ""), False, False

    nozzles = rules.machine["nozzles"]
    fallback_nozzle = (
        "NOZZLE_PLACEHOLDER_FALLBACK"
        if "NOZZLE_PLACEHOLDER_FALLBACK" in nozzles
        else next(iter(nozzles))
    )
    return (
        fallback_nozzle,
        FALLBACK_NOZZLE_RULE_ID,
        "No nozzle rule matched; fell back to default nozzle.",
        True,
        False,
    )


def select_vision(spec: ComponentSpec, rules: Rules) -> tuple[str, str, str, bool, bool]:
    """Returns (vision_type, rule_id, rationale, fallback_used, reference_unverified)."""
    ref_match = reference_rules.lookup_vision(spec, rules.reference)
    if ref_match is not None:
        vision_type, rule_id, rationale = ref_match
        return vision_type, rule_id, rationale, False, not rules.reference.vision_table_verified

    lead_type_value = spec.lead_type.value
    for rule in rules.vision_rules:
        if rule.get("lead_type") == lead_type_value:
            return rule["vision_type"], rule["id"], rule.get("rationale", ""), False, False

    vision_types = rules.machine["vision_types"]
    fallback_vision = (
        "VISION_PLACEHOLDER_FALLBACK"
        if "VISION_PLACEHOLDER_FALLBACK" in vision_types
        else next(iter(vision_types))
    )
    return (
        fallback_vision,
        FALLBACK_VISION_RULE_ID,
        "No vision rule matched; fell back to default vision type.",
        True,
        False,
    )


def map_spec(spec: ComponentSpec, rules: Rules) -> MachineMapping:
    nozzle, nozzle_rule_id, nozzle_rationale, nozzle_fallback, nozzle_unverified = select_nozzle(
        spec, rules
    )
    vision_type, vision_rule_id, vision_rationale, vision_fallback, vision_unverified = (
        select_vision(spec, rules)
    )
    rationale = f"nozzle: {nozzle_rationale} | vision: {vision_rationale}"
    return MachineMapping(
        nozzle=nozzle,
        vision_type=vision_type,
        nozzle_rule_id=nozzle_rule_id,
        vision_rule_id=vision_rule_id,
        rationale=rationale,
        fallback_used=nozzle_fallback or vision_fallback,
        reference_unverified=nozzle_unverified or vision_unverified,
    )
