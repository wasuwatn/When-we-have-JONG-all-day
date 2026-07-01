from pathlib import Path

from smd_nxt_agent.mapping import load_rules, map_spec
from smd_nxt_agent.reference_rules import load_reference, lookup_nozzle, lookup_vision
from smd_nxt_agent.schema import ComponentSpec, LeadType, TopSurface
from smd_nxt_agent.validate import validate

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _spec(**overrides: object) -> ComponentSpec:
    defaults: dict[str, object] = dict(
        package_name="0402",
        body_length_mm=0.4,
        body_width_mm=0.2,
        body_height_mm=0.2,
        lead_type=LeadType.NONE_CHIP_ELECTRODE,
        top_surface=TopSurface.FLAT,
        is_polarized=False,
        confidence=0.95,
        needs_review=False,
        source_notes="ok",
    )
    defaults.update(overrides)
    return ComponentSpec(**defaults)  # type: ignore[arg-type]


def test_reference_data_marked_unverified() -> None:
    ref = load_reference(CONFIG_DIR)
    assert ref.nozzle_compat_verified is False
    assert ref.vision_table_verified is False


def test_lookup_nozzle_matches_known_package_for_head() -> None:
    ref = load_reference(CONFIG_DIR)
    spec = _spec(package_name="0402")
    match = lookup_nozzle(spec, ["H24_H24G_H24S"], ref)
    assert match is not None
    nozzle_id, rule_id, rationale = match
    assert nozzle_id == "0.3mm"
    assert "unverified" in rationale


def test_lookup_nozzle_checks_heads_in_order_and_skips_unsupported() -> None:
    ref = load_reference(CONFIG_DIR)
    # H08M doesn't list "0201" at all (treated as unsupported) but H24_H24G_H24S does;
    # since H08M is checked first here, the lookup should fall through to H24_H24G_H24S.
    spec = _spec(package_name="0201")
    match = lookup_nozzle(spec, ["H08M", "H24_H24G_H24S"], ref)
    assert match is not None
    nozzle_id, rule_id, rationale = match
    assert nozzle_id == "0.2mm"
    assert "head=H24_H24G_H24S" in rationale


def test_lookup_nozzle_returns_none_without_head() -> None:
    ref = load_reference(CONFIG_DIR)
    spec = _spec(package_name="0402")
    assert lookup_nozzle(spec, None, ref) is None
    assert lookup_nozzle(spec, [], ref) is None


def test_lookup_nozzle_returns_none_for_unsupported_symbol() -> None:
    ref = load_reference(CONFIG_DIR)
    # H08M's table doesn't list "0201" at all -> treated as unsupported, and no other
    # head is configured here to fall back to.
    spec = _spec(package_name="0201")
    assert lookup_nozzle(spec, ["H08M"], ref) is None


def test_lookup_vision_matches_alias() -> None:
    ref = load_reference(CONFIG_DIR)
    spec = _spec(package_name="Rectangular parts")
    match = lookup_vision(spec, ref)
    assert match is not None
    vision_type, rule_id, rationale = match
    assert vision_type == "60"


def test_map_spec_uses_reference_table_when_head_configured() -> None:
    rules = load_rules(CONFIG_DIR)
    rules.machine["heads"] = ["H24_H24G_H24S"]
    spec = _spec(package_name="0402")
    mapping = map_spec(spec, rules)
    assert mapping.nozzle == "0.3mm"
    assert mapping.reference_unverified is True
    assert mapping.fallback_used is False


def test_validate_forces_review_when_reference_unverified() -> None:
    rules = load_rules(CONFIG_DIR)
    rules.machine["heads"] = ["H24_H24G_H24S"]
    spec = _spec(package_name="0402")
    mapping = map_spec(spec, rules)
    result = validate(spec, mapping, rules.machine)
    assert result.needs_review is True
    assert any("unverified reference table" in w for w in result.warnings)


def test_shipped_config_checks_all_three_heads_by_default() -> None:
    # config/machine.yaml ships with every known head listed, so any package the
    # reference table recognizes for any head is looked up without extra setup.
    rules = load_rules(CONFIG_DIR)
    assert rules.machine.get("heads") == ["H24_H24G_H24S", "DX_R12", "H08M"]
    spec = _spec(package_name="0402")
    mapping = map_spec(spec, rules)
    assert mapping.reference_unverified is True


def test_no_reference_lookup_when_no_heads_configured() -> None:
    rules = load_rules(CONFIG_DIR)
    rules.machine["heads"] = []
    spec = _spec(package_name="0402")
    mapping = map_spec(spec, rules)
    assert mapping.reference_unverified is False
