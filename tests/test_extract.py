import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from smd_nxt_agent.extract import DEFAULT_MODEL, ExtractError, extract_spec
from smd_nxt_agent.schema import ComponentSpec

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _fake_pdf(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "datasheet.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake content")
    return pdf_path


def _fake_response(
    parsed: ComponentSpec | None, *, finish_reason: str = "STOP", text: str = ""
) -> SimpleNamespace:
    return SimpleNamespace(
        parsed=parsed,
        text=text,
        candidates=[SimpleNamespace(finish_reason=finish_reason)],
    )


def _fake_client(response: SimpleNamespace) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = response
    return client


def test_extract_spec_validates_parsed_response(tmp_path: Path) -> None:
    spec_json = json.loads((FIXTURES_DIR / "0805_chip_resistor.json").read_text())
    parsed = ComponentSpec.model_validate(spec_json)
    client = _fake_client(_fake_response(parsed))

    spec = extract_spec(_fake_pdf(tmp_path), client=client)

    assert spec.package_name == "0805"
    assert spec.body_height_mm == 0.6
    assert spec.needs_review is False
    client.models.generate_content.assert_called_once()
    _, kwargs = client.models.generate_content.call_args
    assert kwargs["model"] == DEFAULT_MODEL
    assert kwargs["config"].response_mime_type == "application/json"


def test_extract_spec_rejects_unknown_model(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        extract_spec(_fake_pdf(tmp_path), model="not-a-real-model", client=MagicMock())


def test_extract_spec_raises_on_abnormal_finish_reason(tmp_path: Path) -> None:
    client = _fake_client(_fake_response(None, finish_reason="MAX_TOKENS"))

    with pytest.raises(ExtractError):
        extract_spec(_fake_pdf(tmp_path), client=client)


def test_extract_spec_raises_when_no_parsed_content(tmp_path: Path) -> None:
    client = _fake_client(_fake_response(None, finish_reason="STOP", text=""))

    with pytest.raises(ExtractError):
        extract_spec(_fake_pdf(tmp_path), client=client)


def test_extract_spec_surfaces_low_confidence_fixture(tmp_path: Path) -> None:
    spec_json = json.loads((FIXTURES_DIR / "soic8_polarized_low_confidence.json").read_text())
    parsed = ComponentSpec.model_validate(spec_json)
    client = _fake_client(_fake_response(parsed))

    spec = extract_spec(_fake_pdf(tmp_path), client=client)

    assert spec.needs_review is True
    assert spec.polarity_confidence is not None
    assert spec.polarity_confidence < 0.5
