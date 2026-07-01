"""Sanity checks and confidence gating.

Decides whether a part is safe to trust automatically or must be routed
to the review queue. All thresholds and limits come from
`config/machine.yaml`; nothing here is hardcoded.
"""

from __future__ import annotations

from typing import Any

from smd_nxt_agent.schema import ComponentSpec, MachineMapping, ValidationResult


def validate(
    spec: ComponentSpec,
    mapping: MachineMapping,
    machine: dict[str, Any],
) -> ValidationResult:
    thresholds = machine["thresholds"]
    warnings: list[str] = []

    # Height: safety-critical, uses the max-of-range value already baked into body_height_mm.
    max_clearance = machine["max_nozzle_clearance_mm"]
    height_ok = spec.body_height_mm <= max_clearance
    if not height_ok:
        warnings.append(
            f"body_height_mm={spec.body_height_mm} exceeds max_nozzle_clearance_mm={max_clearance}"
        )
    min_height_confidence = thresholds["min_height_confidence"]
    if spec.height_confidence is not None and spec.height_confidence < min_height_confidence:
        height_ok = False
        warnings.append(
            f"height_confidence={spec.height_confidence} below threshold "
            f"{thresholds['min_height_confidence']}"
        )

    # Polarity: safety-critical.
    polarity_ok = True
    if spec.is_polarized and not spec.polarity_feature:
        warnings.append("is_polarized=True but no polarity_feature was identified")
        polarity_ok = False
    if (
        spec.polarity_confidence is not None
        and spec.polarity_confidence < thresholds["min_polarity_confidence"]
    ):
        polarity_ok = False
        warnings.append(
            f"polarity_confidence={spec.polarity_confidence} below threshold "
            f"{thresholds['min_polarity_confidence']}"
        )

    # Lead geometry rough sanity: count * pitch should roughly bound the lead span.
    if spec.lead_count and spec.lead_pitch_mm and spec.lead_span_mm:
        expected_min_span = (
            (spec.lead_count / 4 - 1) * spec.lead_pitch_mm if spec.lead_count >= 4 else 0
        )
        if expected_min_span and spec.lead_span_mm < expected_min_span * 0.5:
            warnings.append(
                f"lead_span_mm={spec.lead_span_mm} looks too small for "
                f"lead_count={spec.lead_count} at lead_pitch_mm={spec.lead_pitch_mm}"
            )

    # Weight sanity against machine limit, if known.
    max_weight = machine.get("max_component_weight_g")
    if spec.weight_g is not None and max_weight is not None and spec.weight_g > max_weight:
        warnings.append(f"weight_g={spec.weight_g} exceeds max_component_weight_g={max_weight}")

    min_confidence = thresholds["min_confidence"]
    if spec.confidence < min_confidence:
        warnings.append(f"overall confidence={spec.confidence} below threshold {min_confidence}")

    if mapping.fallback_used:
        warnings.append("nozzle/vision mapping used a fallback rule (no specific rule matched)")

    needs_review = (
        spec.needs_review
        or not height_ok
        or not polarity_ok
        or mapping.fallback_used
        or spec.confidence < thresholds["min_confidence"]
    )

    ok = height_ok and polarity_ok and not needs_review

    return ValidationResult(
        ok=ok,
        needs_review=needs_review,
        warnings=warnings,
        height_ok=height_ok,
        polarity_ok=polarity_ok,
    )
