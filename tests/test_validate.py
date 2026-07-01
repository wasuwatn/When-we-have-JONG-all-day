from smd_nxt_agent.schema import ComponentSpec, LeadType, MachineMapping, TopSurface
from smd_nxt_agent.validate import validate

MACHINE = {
    "max_nozzle_clearance_mm": 5.0,
    "max_component_weight_g": 10.0,
    "thresholds": {
        "min_confidence": 0.75,
        "min_height_confidence": 0.85,
        "min_polarity_confidence": 0.85,
    },
}


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


def _mapping(fallback_used: bool = False) -> MachineMapping:
    return MachineMapping(
        nozzle="NOZZLE_X",
        vision_type="VISION_X",
        nozzle_rule_id="r1",
        vision_rule_id="r2",
        rationale="test",
        fallback_used=fallback_used,
    )


def test_clean_part_passes() -> None:
    result = validate(_spec(), _mapping(), MACHINE)
    assert result.ok is True
    assert result.needs_review is False
    assert result.height_ok is True
    assert result.polarity_ok is True


def test_height_over_clearance_fails() -> None:
    result = validate(_spec(body_height_mm=6.0), _mapping(), MACHINE)
    assert result.height_ok is False
    assert result.needs_review is True
    assert result.ok is False


def test_low_height_confidence_flags_review() -> None:
    result = validate(_spec(height_confidence=0.5), _mapping(), MACHINE)
    assert result.height_ok is False
    assert result.needs_review is True


def test_polarized_without_feature_fails_polarity() -> None:
    result = validate(_spec(is_polarized=True, polarity_feature=None), _mapping(), MACHINE)
    assert result.polarity_ok is False
    assert result.needs_review is True


def test_low_polarity_confidence_flags_review() -> None:
    result = validate(
        _spec(is_polarized=True, polarity_feature="cathode band", polarity_confidence=0.4),
        _mapping(),
        MACHINE,
    )
    assert result.polarity_ok is False
    assert result.needs_review is True


def test_fallback_mapping_forces_review() -> None:
    result = validate(_spec(), _mapping(fallback_used=True), MACHINE)
    assert result.needs_review is True
    assert "fallback" in " ".join(result.warnings).lower()


def test_low_overall_confidence_forces_review() -> None:
    result = validate(_spec(confidence=0.5), _mapping(), MACHINE)
    assert result.needs_review is True


def test_explicit_needs_review_propagates() -> None:
    result = validate(_spec(needs_review=True), _mapping(), MACHINE)
    assert result.needs_review is True
