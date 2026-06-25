"""Generate a synthetic SMD datasheet PDF for trying out `smd-nxt extract`.

This is a FICTIONAL component (no real manufacturer, part number, or
specs) so it can be committed without any IP concern. It exists only to
give you a one-page datasheet — with a dimensions table and a simple
mechanical drawing — to run the pipeline against.

Standalone helper, NOT part of the smd_nxt_agent package. To regenerate:

    pip install reportlab
    python examples/make_sample_datasheet.py

The committed PDF (examples/sample_0805_chip_resistor.pdf) is produced by
this script; you don't need reportlab just to run `smd-nxt extract`.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter as LETTER  # type: ignore[import-untyped]
from reportlab.lib.units import mm  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

OUT_PATH = Path(__file__).resolve().parent / "sample_0805_chip_resistor.pdf"


def build(path: Path) -> None:
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


if __name__ == "__main__":
    build(OUT_PATH)
    print(f"Wrote {OUT_PATH}")
