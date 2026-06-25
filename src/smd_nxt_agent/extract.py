"""AI extraction step: datasheet PDF -> ComponentSpec.

This module is the ONLY place the AI runs. It extracts physical facts and
nothing else — it never selects a nozzle or vision type. That decision
belongs to `mapping.py`, which is pure rule-based code driven by
`config/`.

The Claude call is isolated behind `_extract_with_claude` so a different
provider could be swapped in later without touching `extract_spec`'s
public contract.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import anthropic

from smd_nxt_agent.schema import ComponentSpec

DEFAULT_MODEL = "claude-sonnet-4-6"

ALLOWED_MODELS = frozenset(
    {
        "claude-sonnet-4-6",
        "claude-opus-4-8",
        "claude-haiku-4-5",
    }
)

TOOL_NAME = "record_component_spec"

EXTRACTION_INSTRUCTIONS = """\
Extract the physical specification of the SMD component described in this \
datasheet by reading BOTH the dimension table(s) AND the mechanical drawing.

Unit conversion: if any dimension is given in inches or mils, convert it to \
millimeters (1 inch = 25.4 mm) before recording it. All dimensions in your \
output must be in millimeters.

JEDEC mechanical-drawing symbol legend, if the drawing uses it:
  D = body length, E = body width, A (or A2/A_max) = body height (use the \
MAXIMUM value of any height range), e = lead pitch, b = lead width, \
L = foot/lead length.

Height handling: body_height_mm must be the MAXIMUM stated height (seated \
max), never typical or minimum, because it determines nozzle clearance.

Never guess. If a value is not explicitly stated or clearly derivable, \
omit the optional field (or, for required fields, give your best estimate \
but lower the relevant confidence) and explain what's missing in \
source_notes. Set needs_review=true whenever a safety-critical field — \
body_height_mm or is_polarized — was uncertain, ambiguous, or inferred \
rather than directly read from the datasheet. Report height_confidence and \
polarity_confidence separately from the overall confidence for exactly \
this reason.

Record your findings using the record_component_spec tool.
"""


class ExtractError(Exception):
    """Raised when extraction from a PDF fails."""

    def __init__(self, message: str, *, pdf_path: Path, model: str, request_id: str | None = None):
        super().__init__(message)
        self.pdf_path = pdf_path
        self.model = model
        self.request_id = request_id


def _component_spec_tool() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": "Record the extracted SMD component specification.",
        "input_schema": ComponentSpec.model_json_schema(),
    }


def _build_content(pdf_path: Path, *, use_cache: bool) -> list[dict[str, Any]]:
    b64 = base64.standard_b64encode(pdf_path.read_bytes()).decode()
    doc: dict[str, Any] = {
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
    }
    if use_cache:
        doc["cache_control"] = {"type": "ephemeral"}
    return [doc, {"type": "text", "text": EXTRACTION_INSTRUCTIONS}]


def _extract_with_claude(
    pdf_path: Path,
    *,
    model: str,
    use_cache: bool,
    client: anthropic.Anthropic,
) -> ComponentSpec:
    content = _build_content(pdf_path, use_cache=use_cache)
    try:
        resp = client.messages.create(  # type: ignore[call-overload]
            model=model,
            max_tokens=4096,
            tools=[_component_spec_tool()],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": content}],
        )
    except (
        anthropic.APIStatusError,
        anthropic.RateLimitError,
        anthropic.APIConnectionError,
        anthropic.BadRequestError,
    ) as exc:
        request_id = getattr(exc, "request_id", None)
        raise ExtractError(
            f"Anthropic API call failed for {pdf_path.name}: {exc}",
            pdf_path=pdf_path,
            model=model,
            request_id=request_id,
        ) from exc

    if resp.stop_reason == "max_tokens":
        raise ExtractError(
            f"Response for {pdf_path.name} was truncated at max_tokens before "
            "completing the tool call.",
            pdf_path=pdf_path,
            model=model,
        )
    if resp.stop_reason == "refusal":
        raise ExtractError(
            f"Model refused to extract {pdf_path.name}: {resp.stop_reason!r} "
            f"(stop_sequence={getattr(resp, 'stop_sequence', None)!r})",
            pdf_path=pdf_path,
            model=model,
        )

    tool_block = next(
        (block for block in resp.content if block.type == "tool_use" and block.name == TOOL_NAME),
        None,
    )
    if tool_block is None:
        raise ExtractError(
            f"No {TOOL_NAME} tool_use block in response for {pdf_path.name} "
            f"(stop_reason={resp.stop_reason!r}).",
            pdf_path=pdf_path,
            model=model,
        )

    return ComponentSpec.model_validate(tool_block.input)


def extract_spec(
    pdf_path: Path,
    *,
    model: str = DEFAULT_MODEL,
    use_cache: bool = False,
    client: anthropic.Anthropic | None = None,
    timeout: float = 600.0,
    max_retries: int = 4,
) -> ComponentSpec:
    """Extract a ComponentSpec from a single datasheet PDF.

    `client` is injectable for testing; when omitted, an `anthropic.Anthropic()`
    client is constructed from the environment (ANTHROPIC_API_KEY).
    """
    if model not in ALLOWED_MODELS:
        raise ValueError(f"model must be one of {sorted(ALLOWED_MODELS)}, got {model!r}")

    if client is None:
        client = anthropic.Anthropic()
    client = client.with_options(timeout=timeout, max_retries=max_retries)

    return _extract_with_claude(pdf_path, model=model, use_cache=use_cache, client=client)
