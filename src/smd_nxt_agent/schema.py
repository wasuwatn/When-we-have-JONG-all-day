"""Data models shared across the pipeline.

`ComponentSpec` is the AI extraction output (facts only, no nozzle/vision
decisions). Its field descriptions double as the per-field extraction
instructions sent to the model, since `ComponentSpec.model_json_schema()`
is used directly as the tool input schema in `extract.py`.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class LeadType(StrEnum):
    NONE_CHIP_ELECTRODE = "none_chip_electrode"
    GULL_WING = "gull_wing"
    J_LEAD = "j_lead"
    QFN_NO_LEAD_PAD = "qfn_no_lead_pad"
    BGA_BALL = "bga_ball"
    THROUGH_HOLE_PIN = "through_hole_pin"
    ODD_FORM = "odd_form"
    OTHER = "other"


class TopSurface(StrEnum):
    FLAT = "flat"
    CURVED = "curved"
    UNEVEN = "uneven"
    UNKNOWN = "unknown"


class TapeCarrierMaterial(StrEnum):
    PAPER = "paper"
    EMBOSSED = "embossed"
    UNKNOWN = "unknown"


class ComponentSpec(BaseModel):
    """Physical facts extracted from a datasheet. No nozzle/vision decisions here."""

    manufacturer: str | None = Field(
        default=None, description="Manufacturer name as printed on the datasheet, if present."
    )
    part_number: str | None = Field(
        default=None, description="Manufacturer part number / ordering code, if present."
    )
    package_name: str = Field(
        description=(
            "Package or case name as printed on the datasheet (e.g. '0805', 'SOIC-8', "
            "'QFN-32', 'SOT-23'). Use the exact designator from the datasheet."
        )
    )
    jedec_or_standard: str | None = Field(
        default=None,
        description="JEDEC or other standard package designator, if explicitly given.",
    )
    body_length_mm: float = Field(
        description=(
            "Component body length in millimeters. Convert from inches/mils if needed "
            "(1 inch = 25.4 mm). Corresponds to JEDEC 'D' dimension where applicable. "
            "If the datasheet gives a tolerance range, use the NOMINAL (typical/center) "
            "value, not the minimum or maximum."
        )
    )
    body_width_mm: float = Field(
        description=(
            "Component body width in millimeters. Convert from inches/mils if needed. "
            "Corresponds to JEDEC 'E' dimension where applicable. If the datasheet gives "
            "a tolerance range, use the NOMINAL (typical/center) value, not the minimum "
            "or maximum."
        )
    )
    body_height_mm: float = Field(
        description=(
            "Component body height (seated max) in millimeters, safety-critical for nozzle "
            "clearance. If the datasheet gives a range, use the MAXIMUM value, never the "
            "typical or minimum. Corresponds to JEDEC 'A' (max) dimension where applicable."
        )
    )
    height_min_mm: float | None = Field(
        default=None, description="Minimum height in mm, if the datasheet states a range."
    )
    height_max_mm: float | None = Field(
        default=None,
        description="Maximum height in mm, if the datasheet states a range (same value used "
        "for body_height_mm).",
    )
    lead_type: LeadType = Field(
        description=(
            "Lead/electrode geometry. Use 'none_chip_electrode' for two-terminal chip parts "
            "(resistors, capacitors) with metallized end electrodes and no formed leads. "
            "Use 'odd_form' for connectors, switches, or anything not covered by other values."
        )
    )
    lead_count: int | None = Field(
        default=None,
        description=(
            "Total number of leads/pins/balls. Required whenever lead_type is not "
            "'none_chip_electrode': read the pin/lead count from the pin table, pinout "
            "diagram, or package outline drawing (e.g. count leads per side x number of "
            "sides for QFP, or rows x columns for BGA) rather than leaving it blank. Omit "
            "only if the datasheet genuinely never states or shows the count."
        ),
    )
    lead_pitch_mm: float | None = Field(
        default=None,
        description="Distance between adjacent lead centers in mm (JEDEC 'e'), if applicable.",
    )
    lead_width_mm: float | None = Field(
        default=None,
        description=(
            "Width of an individual lead in mm (JEDEC 'b'). Required whenever lead_type "
            "is not 'none_chip_electrode': read it from the dimension table or mechanical "
            "drawing (JEDEC 'b' dimension) rather than leaving it blank when the part has "
            "formed leads/pins/balls."
        ),
    )
    lead_span_mm: float | None = Field(
        default=None,
        description="Outer lead-to-lead span (tip to tip) in mm, if given or derivable.",
    )
    is_polarized: bool = Field(
        description=(
            "Whether the component is polarity-sensitive (e.g. tantalum/electrolytic "
            "capacitors, diodes, polarized connectors). Safety-critical: reversing a "
            "polarized part is a defect. If genuinely unknown, set false and explain in "
            "source_notes with low polarity_confidence rather than guessing true."
        )
    )
    polarity_feature: str | None = Field(
        default=None,
        description=(
            "WHAT the polarity marking looks like (e.g. 'cathode band', 'pin 1 dot', "
            "'beveled corner'), if is_polarized is true and the datasheet shows it."
        ),
    )
    polarity_reference_location: str | None = Field(
        default=None,
        description=(
            "WHERE the polarity marking is located on the package footprint, stated "
            "relative to a fixed reference (e.g. 'on the end opposite pin 1', 'top-left "
            "corner when viewed from above with pin 1 at bottom-left', 'cathode band on "
            "the terminal nearest the tape sprocket-hole edge'). Required whenever "
            "is_polarized is true and the datasheet's top/marking view shows the "
            "orientation — a marking type alone (polarity_feature) is not enough to place "
            "the part correctly on the board; the placement machine needs to know which "
            "side/corner it's on. If the datasheet shows the marking but not a clear "
            "reference direction, say so in source_notes and lower polarity_confidence."
        ),
    )
    weight_g: float | None = Field(
        default=None, description="Component weight in grams, if stated."
    )
    tape_width_mm: float | None = Field(
        default=None,
        description=(
            "Carrier tape width in mm, from the datasheet's tape & reel / packaging "
            "section (e.g. 8, 12, 16, 24). Required whenever the datasheet documents a "
            "tape & reel packing option — read it from that section's table or drawing "
            "rather than leaving it blank."
        ),
    )
    pocket_pitch_mm: float | None = Field(
        default=None,
        description=(
            "Component pitch on the carrier tape in mm: the center-to-center distance "
            "between successive component pockets/cavities (e.g. 2, 4, 8, 12), from the "
            "tape & reel section. Required whenever the datasheet documents a tape & reel "
            "packing option — read it from that section's table or drawing rather than "
            "leaving it blank."
        ),
    )
    tape_carrier_material: TapeCarrierMaterial = Field(
        default=TapeCarrierMaterial.UNKNOWN,
        description=(
            "Carrier tape material/construction, from the tape & reel section: "
            "'embossed' (pockets formed into a thicker plastic tape, common for taller "
            "parts) vs 'paper' (punched paper/soft tape, common for very low-profile "
            "chip parts). Use 'unknown' only if the datasheet's tape & reel section does "
            "not state or show it."
        ),
    )
    top_surface: TopSurface = Field(
        default=TopSurface.UNKNOWN,
        description="Shape of the component's top surface, relevant to vacuum-pickup reliability.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Overall confidence (0-1) that all fields above are correct. Lower this whenever "
            "any value was inferred, ambiguous, or not explicitly stated rather than guessing."
        ),
    )
    height_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence specifically in body_height_mm. Safety-critical: report separately "
            "from overall confidence since a wrong height can crash a nozzle."
        ),
    )
    polarity_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence specifically in is_polarized / polarity_feature. Safety-critical: "
            "report separately since a wrong polarity reverses parts on the board."
        ),
    )
    needs_review: bool = Field(
        description=(
            "Set true if any safety-critical field (height, polarity) or required dimension "
            "was uncertain, missing, ambiguous, or had to be inferred from indirect evidence."
        )
    )
    source_notes: str = Field(
        description=(
            "Brief explanation of where each key value came from (table vs. drawing vs. "
            "inferred), unit conversions performed, and the reason for any low confidence or "
            "needs_review=true. Empty string only if extraction was fully unambiguous."
        )
    )


class MachineMapping(BaseModel):
    """Derived nozzle + vision selection. Produced by pure rules, never by the AI."""

    nozzle: str
    vision_type: str
    nozzle_rule_id: str
    vision_rule_id: str
    rationale: str
    fallback_used: bool
    reference_unverified: bool = False


class ValidationResult(BaseModel):
    """Sanity/confidence checks. height_ok and polarity_ok are surfaced separately
    because they are safety-critical."""

    ok: bool
    needs_review: bool
    warnings: list[str]
    height_ok: bool
    polarity_ok: bool


class PartRecord(BaseModel):
    """One datasheet's full result, bundled for output."""

    source_file: str
    model: str
    spec: ComponentSpec
    mapping: MachineMapping
    validation: ValidationResult
