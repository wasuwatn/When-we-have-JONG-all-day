"""Wires ingest -> extract -> map -> validate and writes the three output files.

`extractor` is injectable so the pipeline can be exercised in tests with
fixture data and no network access.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Callable
from pathlib import Path

from smd_nxt_agent.extract import DEFAULT_MODEL, extract_spec
from smd_nxt_agent.ingest import list_pdfs
from smd_nxt_agent.mapping import Rules, load_rules, map_spec
from smd_nxt_agent.schema import ComponentSpec, PartRecord
from smd_nxt_agent.validate import validate

Extractor = Callable[[Path], ComponentSpec]

CSV_FIELDS = [
    "source_file",
    "model",
    "package_name",
    "body_length_mm",
    "body_width_mm",
    "body_height_mm",
    "lead_type",
    "is_polarized",
    "confidence",
    "height_confidence",
    "polarity_confidence",
    "nozzle",
    "vision_type",
    "fallback_used",
    "ok",
    "needs_review",
]


def _record_to_csv_row(record: PartRecord) -> dict[str, object]:
    return {
        "source_file": record.source_file,
        "model": record.model,
        "package_name": record.spec.package_name,
        "body_length_mm": record.spec.body_length_mm,
        "body_width_mm": record.spec.body_width_mm,
        "body_height_mm": record.spec.body_height_mm,
        "lead_type": record.spec.lead_type.value,
        "is_polarized": record.spec.is_polarized,
        "confidence": record.spec.confidence,
        "height_confidence": record.spec.height_confidence,
        "polarity_confidence": record.spec.polarity_confidence,
        "nozzle": record.mapping.nozzle,
        "vision_type": record.mapping.vision_type,
        "fallback_used": record.mapping.fallback_used,
        "ok": record.validation.ok,
        "needs_review": record.validation.needs_review,
    }


def _process_one(
    pdf_path: Path,
    *,
    model: str,
    rules: Rules,
    extractor: Extractor,
) -> PartRecord:
    spec = extractor(pdf_path)
    mapping = map_spec(spec, rules)
    validation = validate(spec, mapping, rules.machine)
    return PartRecord(
        source_file=pdf_path.name,
        model=model,
        spec=spec,
        mapping=mapping,
        validation=validation,
    )


def run(
    input_dir: Path,
    out_dir: Path,
    *,
    model: str = DEFAULT_MODEL,
    use_cache: bool = False,
    config_dir: Path = Path("config"),
    extractor: Extractor | None = None,
) -> list[PartRecord]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rules = load_rules(config_dir)

    if extractor is None:
        def extractor(pdf_path: Path) -> ComponentSpec:
            return extract_spec(pdf_path, model=model, use_cache=use_cache)

    records = [
        _process_one(pdf_path, model=model, rules=rules, extractor=extractor)
        for pdf_path in list_pdfs(input_dir)
    ]

    (out_dir / "parts.json").write_text(
        json.dumps([r.model_dump(mode="json") for r in records], indent=2)
    )

    with (out_dir / "parts.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(_record_to_csv_row(record))

    review_queue = [r.model_dump(mode="json") for r in records if r.validation.needs_review]
    (out_dir / "review_queue.json").write_text(json.dumps(review_queue, indent=2))

    ok_count = sum(1 for r in records if r.validation.ok)
    review_count = len(review_queue)
    print(f"OK: {ok_count}  REVIEW: {review_count}  TOTAL: {len(records)}")

    return records
