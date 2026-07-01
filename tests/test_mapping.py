from pathlib import Path

from smd_nxt_agent.mapping import load_rules, map_spec
from smd_nxt_agent.schema import ComponentSpec, LeadType, TopSurface

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _spec(**overrides: object) -> ComponentSpec:
    defaults: dict[str, object] = dict(
        package_name="0805",
        body_length_mm=2.0,
        body_width_mm=1.25,
        body_height_mm=0.6,
        lead_type=LeadType.NONE_CHIP_ELECTRODE,
        top_surface=TopSurface.FLAT,
        is_polarized=False,
        confidence=0.95,
        needs_review=False,
        source_notes="ok",
    )
    defaults.update(overrides)
    return ComponentSpec(**defaults)  # type: ignore[arg-type]


def test_small_chip_matches_first_rule() -> None:
    rules = load_rules(CONFIG_DIR)
    rules.machine["heads"] = []  # isolate from the reference table; test placeholder rules only
    spec = _spec(lead_type=LeadType.NONE_CHIP_ELECTRODE, body_height_mm=0.6)
    mapping = map_spec(spec, rules)
    assert mapping.nozzle_rule_id == "placeholder_small_chip"
    assert mapping.nozzle == "NOZZLE_PLACEHOLDER_SMALL"
    assert mapping.fallback_used is False


def test_leaded_package_matches_medium_rule() -> None:
    rules = load_rules(CONFIG_DIR)
    rules.machine["heads"] = []  # isolate from the reference table; test placeholder rules only
    spec = _spec(lead_type=LeadType.GULL_WING, body_height_mm=1.5)
    mapping = map_spec(spec, rules)
    assert mapping.nozzle_rule_id == "placeholder_leaded_medium"
    assert mapping.nozzle == "NOZZLE_PLACEHOLDER_MEDIUM"
    assert mapping.fallback_used is False


def test_unmatched_lead_type_falls_back() -> None:
    rules = load_rules(CONFIG_DIR)
    rules.machine["heads"] = []  # isolate from the reference table; test placeholder rules only
    spec = _spec(lead_type=LeadType.ODD_FORM)
    mapping = map_spec(spec, rules)
    assert mapping.fallback_used is True
    assert mapping.nozzle == "NOZZLE_PLACEHOLDER_FALLBACK"
    assert mapping.vision_type == "VISION_PLACEHOLDER_FALLBACK"


def test_vision_lookup_by_lead_type() -> None:
    rules = load_rules(CONFIG_DIR)
    spec = _spec(lead_type=LeadType.BGA_BALL)
    mapping = map_spec(spec, rules)
    assert mapping.vision_rule_id == "placeholder_bga_vision"
    assert mapping.vision_type == "VISION_PLACEHOLDER_NOLEAD"


def test_height_threshold_excludes_tall_chip() -> None:
    rules = load_rules(CONFIG_DIR)
    rules.machine["heads"] = []  # isolate from the reference table; test placeholder rules only
    spec = _spec(lead_type=LeadType.NONE_CHIP_ELECTRODE, body_height_mm=5.0)
    mapping = map_spec(spec, rules)
    assert mapping.nozzle_rule_id != "placeholder_small_chip"
    assert mapping.fallback_used is True
