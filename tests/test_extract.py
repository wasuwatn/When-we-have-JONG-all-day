import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from smd_nxt_agent.extract import TOOL_NAME, ExtractError, extract_spec

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _fake_pdf(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "datasheet.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake content")
    return pdf_path


def _tool_use_block(input_data: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=TOOL_NAME, input=input_data)


def _fake_client(response: SimpleNamespace) -> MagicMock:
    client = MagicMock()
    client.with_options.return_value = client
    client.messages.create.return_value = response
    return client


def test_extract_spec_validates_tool_use_response(tmp_path: Path) -> None:
    spec_json = json.loads((FIXTURES_DIR / "0805_chip_resistor.json").read_text())
    response = SimpleNamespace(stop_reason="tool_use", content=[_tool_use_block(spec_json)])
    client = _fake_client(response)

    spec = extract_spec(_fake_pdf(tmp_path), client=client)

    assert spec.package_name == "0805"
    assert spec.body_height_mm == 0.6
    assert spec.needs_review is False
    client.messages.create.assert_called_once()
    _, kwargs = client.messages.create.call_args
    assert kwargs["tool_choice"] == {"type": "tool", "name": TOOL_NAME}


def test_extract_spec_rejects_unknown_model(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        extract_spec(_fake_pdf(tmp_path), model="not-a-real-model", client=MagicMock())


def test_extract_spec_raises_on_max_tokens(tmp_path: Path) -> None:
    response = SimpleNamespace(stop_reason="max_tokens", content=[])
    client = _fake_client(response)

    with pytest.raises(ExtractError):
        extract_spec(_fake_pdf(tmp_path), client=client)


def test_extract_spec_raises_when_no_tool_use_block(tmp_path: Path) -> None:
    response = SimpleNamespace(stop_reason="end_turn", content=[])
    client = _fake_client(response)

    with pytest.raises(ExtractError):
        extract_spec(_fake_pdf(tmp_path), client=client)


def test_extract_spec_surfaces_low_confidence_fixture(tmp_path: Path) -> None:
    spec_json = json.loads((FIXTURES_DIR / "soic8_polarized_low_confidence.json").read_text())
    response = SimpleNamespace(stop_reason="tool_use", content=[_tool_use_block(spec_json)])
    client = _fake_client(response)

    spec = extract_spec(_fake_pdf(tmp_path), client=client)

    assert spec.needs_review is True
    assert spec.polarity_confidence is not None
    assert spec.polarity_confidence < 0.5
