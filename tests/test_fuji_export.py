import json
from pathlib import Path

from smd_nxt_agent.fuji_export import build_fuji_rows, load_export_config, write_fuji_csv
from smd_nxt_agent.mapping import load_rules, map_spec
from smd_nxt_agent.schema import ComponentSpec, PartRecord
from smd_nxt_agent.validate import validate

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
FIXTURES_DIR = ROOT / "tests" / "fixtures"


def _record(fixture_name: str, source_file: str) -> PartRecord:
    spec = ComponentSpec.model_validate_json((FIXTURES_DIR / fixture_name).read_text())
    rules = load_rules(CONFIG_DIR)
    mapping = map_spec(spec, rules)
    validation = validate(spec, mapping, rules.machine)
    return PartRecord(
        source_file=source_file, model="test", spec=spec, mapping=mapping, validation=validation
    )


def test_ok_record_is_exported_with_mapped_fields() -> None:
    record = _record("0805_chip_resistor.json", "0805_chip_resistor.pdf")
    assert record.validation.ok is True  # sanity: fixture is a clean pass

    config = load_export_config(CONFIG_DIR)
    result = build_fuji_rows([record], config)

    assert result.skipped == []
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["partno"] == "ERJ-EXAMPLE"
    assert row["part_type"] == "Passive"
    assert row["body_x"] == record.spec.body_width_mm
    assert row["body_y"] == record.spec.body_length_mm
    assert row["body_h"] == record.spec.body_height_mm
    assert row["tape_width"] == 8
    assert row["feed_pitch"] == 4
    assert row["creator"] == config["creator"]
    # No lead pitch on a chip resistor: no pin grid columns.
    assert "pin_count" not in row


def test_needs_review_record_is_skipped_unless_confirmed() -> None:
    record = _record("soic8_polarized_low_confidence.json", "soic8.pdf")
    assert record.validation.ok is False  # sanity: fixture is meant to fail the gate

    config = load_export_config(CONFIG_DIR)

    unconfirmed = build_fuji_rows([record], config)
    assert unconfirmed.rows == []
    assert len(unconfirmed.skipped) == 1
    assert unconfirmed.skipped[0].source_file == "soic8.pdf"

    confirmed = build_fuji_rows([record], config, decisions={"soic8.pdf": "confirmed"})
    assert confirmed.skipped == []
    assert len(confirmed.rows) == 1
    row = confirmed.rows[0]
    assert row["part_type"] == "QFP"
    assert row["pin_count"] == record.spec.lead_count
    assert row["pitch_x"] == record.spec.lead_pitch_mm
    assert row["pitch_y"] == record.spec.lead_pitch_mm


def test_write_fuji_csv_round_trips(tmp_path: Path) -> None:
    record = _record("0805_chip_resistor.json", "0805_chip_resistor.pdf")
    config = load_export_config(CONFIG_DIR)
    result = build_fuji_rows([record], config)

    csv_path = write_fuji_csv(result, tmp_path)
    assert csv_path.exists()
    text = csv_path.read_text()
    assert "partno,part_type,body_x" in text.splitlines()[0]
    assert "ERJ-EXAMPLE" in text

    skipped_path = tmp_path / "fuji_export_skipped.json"
    assert json.loads(skipped_path.read_text()) == []
