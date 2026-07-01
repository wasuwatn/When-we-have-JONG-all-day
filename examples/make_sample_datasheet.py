"""Generate synthetic SMD datasheet PDFs for trying out `smd-nxt extract`.

Both components are FICTIONAL (no real manufacturer, part number, or
specs) so they can be committed without any IP concern.

- `sample_0805_chip_resistor.pdf` is a clean, unambiguous datasheet.
  Run it through the pipeline and it should land as OK.
- `sample_tantalum_cap_ambiguous.pdf` is a polarized part whose datasheet
  deliberately omits the polarity marking and gives a contradictory
  height (dimension table vs. mechanical drawing note). It exists to
  demonstrate the review queue: `validate.py` flags any polarized part
  with no identified polarity_feature regardless of confidence, and the
  extraction instructions tell the model to lower height_confidence and
  set needs_review when the table and drawing disagree. Since the actual
  outcome depends on the live model's judgment call on a real datasheet
  (not a canned fixture), it should land as REVIEW but isn't 100%
  guaranteed the way the offline test fixtures are.

Standalone helper, NOT part of the smd_nxt_agent package. To regenerate:

    pip install reportlab
    python examples/make_sample_datasheet.py

The committed PDFs are produced by this script; you don't need reportlab
just to run `smd-nxt extract`.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter as LETTER  # type: ignore[import-untyped]
from reportlab.lib.units import mm  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

RESISTOR_OUT_PATH = Path(__file__).resolve().parent / "sample_0805_chip_resistor.pdf"
CAPACITOR_OUT_PATH = Path(__file__).resolve().parent / "sample_tantalum_cap_ambiguous.pdf"


def build_resistor(path: Path) -> None:
    width, height = LETTER
    c = canvas.Canvas(str(path), pagesize=LETTER)
    left = 20 * mm
    y = height - 20 * mm

    c.setFont("Helvetica-Bold", 16)
    c.drawString(left, y, "ACME COMPONENTS (FICTIONAL SAMPLE)")
    y -= 7 * mm
    c.setFont("Helvetica-Bold", 13)
    c.drawString(left, y, "Thick Film Chip Resistor  -  0805 Package")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    c.drawString(left, y, "Part Number: ACM-R0805-103J    Standard: EIA 0805 (2012 metric)")
    y -= 5 * mm
    c.setFillColorRGB(0.6, 0.0, 0.0)
    c.drawString(left, y, "NOTE: Synthetic sample for tool testing only - not a real product.")
    c.setFillColorRGB(0, 0, 0)

    # Dimensions table.
    y -= 12 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Dimensions (millimeters)")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    rows = [
        ("Symbol", "Description", "Min", "Nom", "Max"),
        ("L (D)", "Body length", "1.90", "2.00", "2.10"),
        ("W (E)", "Body width", "1.15", "1.25", "1.35"),
        ("H (A)", "Body height (seated)", "0.45", "0.50", "0.55"),
        ("t", "Terminal (end-cap) width", "0.25", "0.40", "0.55"),
    ]
    col_x = [left, left + 22 * mm, left + 88 * mm, left + 108 * mm, left + 128 * mm]
    for r_i, row in enumerate(rows):
        if r_i == 0:
            c.setFont("Helvetica-Bold", 9)
        else:
            c.setFont("Helvetica", 9)
        for c_i, cell in enumerate(row):
            c.drawString(col_x[c_i], y, cell)
        y -= 5.5 * mm

    # Electrical / handling facts.
    y -= 4 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Construction & Handling")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    for line in [
        "Termination: two metallized end electrodes (chip, no formed leads).",
        "Polarity: non-polarized; may be placed in either orientation.",
        "Top surface: flat (suitable for vacuum nozzle pickup).",
        "Weight: approx. 0.004 g per piece.",
        "Packaging: 8 mm carrier tape, 4 mm pocket pitch, 7-inch reel.",
    ]:
        c.drawString(left, y, "- " + line)
        y -= 5 * mm

    # Simple mechanical drawing (top view rectangle with D/E labels).
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Mechanical Drawing (top view)")
    draw_top = y - 8 * mm
    rect_w = 60 * mm
    rect_h = 32 * mm
    rect_x = left + 10 * mm
    rect_y = draw_top - rect_h
    # End-cap terminals.
    c.setFillColorRGB(0.85, 0.85, 0.85)
    c.rect(rect_x, rect_y, 8 * mm, rect_h, stroke=1, fill=1)
    c.rect(rect_x + rect_w - 8 * mm, rect_y, 8 * mm, rect_h, stroke=1, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.rect(rect_x + 8 * mm, rect_y, rect_w - 16 * mm, rect_h, stroke=1, fill=1)
    c.setFillColorRGB(0, 0, 0)
    # Dimension labels.
    c.setFont("Helvetica-Oblique", 9)
    c.drawCentredString(rect_x + rect_w / 2, rect_y - 6 * mm, "D = 2.00 mm (length)")
    c.saveState()
    c.translate(rect_x - 5 * mm, rect_y + rect_h / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, "E = 1.25 mm (width)")
    c.restoreState()
    c.drawString(rect_x + rect_w + 6 * mm, rect_y + rect_h / 2, "A (height) = 0.55 mm max")

    c.showPage()
    c.save()


def build_capacitor(path: Path) -> None:
    """Polarized part, deliberately ambiguous on the two safety-critical fields."""
    width, height = LETTER
    c = canvas.Canvas(str(path), pagesize=LETTER)
    left = 20 * mm
    y = height - 20 * mm

    c.setFont("Helvetica-Bold", 16)
    c.drawString(left, y, "ACME COMPONENTS (FICTIONAL SAMPLE)")
    y -= 7 * mm
    c.setFont("Helvetica-Bold", 13)
    c.drawString(left, y, "Tantalum Chip Capacitor  -  Case A (EIA 3216)")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    c.drawString(left, y, "Part Number: ACM-T10UF16V-A    10 uF, 16V")
    y -= 5 * mm
    c.setFillColorRGB(0.6, 0.0, 0.0)
    c.drawString(left, y, "NOTE: Synthetic sample for tool testing only - not a real product.")
    c.drawString(left, y - 4.5 * mm, "This datasheet is intentionally ambiguous (see below) to")
    c.drawString(
        left, y - 9 * mm, "demonstrate the review queue - it is not a documentation defect."
    )
    c.setFillColorRGB(0, 0, 0)
    y -= 14 * mm

    # Dimensions table - height here deliberately conflicts with the drawing note below.
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Dimensions (millimeters)")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    rows = [
        ("Symbol", "Description", "Min", "Nom", "Max"),
        ("L (D)", "Body length", "3.05", "3.20", "3.35"),
        ("W (E)", "Body width", "1.45", "1.60", "1.80"),
        ("H (A)", "Body height (seated)", "1.40", "1.50", "1.60"),
    ]
    col_x = [left, left + 22 * mm, left + 88 * mm, left + 108 * mm, left + 128 * mm]
    for r_i, row in enumerate(rows):
        c.setFont("Helvetica-Bold" if r_i == 0 else "Helvetica", 9)
        for c_i, cell in enumerate(row):
            c.drawString(col_x[c_i], y, cell)
        y -= 5.5 * mm

    # Electrical / handling facts - polarity stated as required, marking deliberately
    # not described (so the model has nothing concrete to report as polarity_feature).
    y -= 4 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Construction & Handling")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    for line in [
        "Termination: two metallized end electrodes (chip, no formed leads).",
        "Polarity: YES - this is a polarity-sensitive device. Reverse voltage",
        "  may damage the part. Orientation marking varies by date code; see",
        "  manufacturer date-code orientation guide (not included in this excerpt).",
        "Top surface: flat (suitable for vacuum nozzle pickup).",
        "Weight: approx. 0.09 g per piece.",
        "Packaging: 8 mm carrier tape, 4 mm pocket pitch, 7-inch reel.",
    ]:
        c.drawString(left, y, "- " + line if not line.startswith("  ") else line)
        y -= 5 * mm

    # Mechanical drawing with a height note that contradicts the table above.
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Mechanical Drawing (side view)")
    draw_top = y - 8 * mm
    rect_w = 50 * mm
    rect_h = 22 * mm
    rect_x = left + 10 * mm
    rect_y = draw_top - rect_h
    c.setFillColorRGB(0.85, 0.85, 0.85)
    c.rect(rect_x, rect_y, rect_w, rect_h, stroke=1, fill=1)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Oblique", 9)
    c.drawCentredString(rect_x + rect_w / 2, rect_y - 6 * mm, "D = 3.20 mm (length)")
    c.drawString(
        rect_x + rect_w + 6 * mm, rect_y + rect_h / 2, "A (height) = 1.80 mm max per Rev.A drawing"
    )
    y = rect_y - 12 * mm
    c.setFillColorRGB(0.6, 0.0, 0.0)
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(
        left,
        y,
        "Drawing note: Rev.A mechanical drawing lists H max = 1.80 mm; the Rev.B table above",
    )
    c.drawString(
        left, y - 4 * mm, "lists H max = 1.60 mm. Discrepancy unresolved - confirm before tooling."
    )
    c.setFillColorRGB(0, 0, 0)

    c.showPage()
    c.save()


if __name__ == "__main__":
    build_resistor(RESISTOR_OUT_PATH)
    print(f"Wrote {RESISTOR_OUT_PATH}")
    build_capacitor(CAPACITOR_OUT_PATH)
    print(f"Wrote {CAPACITOR_OUT_PATH}")
