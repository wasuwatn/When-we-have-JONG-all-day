"""AI extraction step: datasheet PDF -> ComponentSpec.

This module is the ONLY place the AI runs. It extracts physical facts and
nothing else — it never selects a nozzle or vision type. That decision
belongs to `mapping.py`, which is pure rule-based code driven by
`config/`.

The Gemini call is isolated behind `_extract_with_gemini` so a different
provider could be swapped in later without touching `extract_spec`'s
public contract.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import APIError

from smd_nxt_agent.schema import ComponentSpec

DEFAULT_MODEL = "gemini-2.5-flash"

ALLOWED_MODELS = frozenset(
    {
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    }
)

_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

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

Record your findings as a single JSON object matching the provided schema.
"""


class ExtractError(Exception):
    """Raised when extraction from a PDF fails."""

    def __init__(self, message: str, *, pdf_path: Path, model: str, request_id: str | None = None):
        super().__init__(message)
        self.pdf_path = pdf_path
        self.model = model
        self.request_id = request_id


def _response_config(*, cached_content: str | None = None) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        max_output_tokens=4096,
        response_mime_type="application/json",
        response_schema=ComponentSpec,
        cached_content=cached_content,
    )


def _build_content(pdf_path: Path) -> list[Any]:
    return [
        types.Part.from_bytes(data=pdf_path.read_bytes(), mime_type="application/pdf"),
        EXTRACTION_INSTRUCTIONS,
    ]


def _generate_with_retry(
    client: genai.Client,
    *,
    model: str,
    contents: list[Any],
    config: types.GenerateContentConfig,
    max_retries: int,
) -> types.GenerateContentResponse:
    delay = 1.0
    for attempt in range(max_retries + 1):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except APIError as exc:
            code = getattr(exc, "code", None)
            if code not in _RETRYABLE_STATUS_CODES or attempt == max_retries:
                raise
            time.sleep(delay)
            delay *= 2
    raise AssertionError("unreachable")  # loop above always returns or raises


def _extract_with_gemini(
    pdf_path: Path,
    *,
    model: str,
    use_cache: bool,
    client: genai.Client,
    max_retries: int,
) -> ComponentSpec:
    contents = _build_content(pdf_path)
    cached_content: str | None = None

    try:
        if use_cache:
            # Explicit caching has a minimum content size (commonly cited around
            # 2048 input tokens), so a small single-page datasheet may not
            # actually be eligible — caches.create can fail for tiny PDFs.
            cache = client.caches.create(
                model=model,
                config=types.CreateCachedContentConfig(contents=[contents[0]]),
            )
            if not cache.name:
                raise ExtractError(
                    f"Cache creation for {pdf_path.name} did not return a cache name.",
                    pdf_path=pdf_path,
                    model=model,
                )
            cached_content = cache.name
            contents = [EXTRACTION_INSTRUCTIONS]

        resp = _generate_with_retry(
            client,
            model=model,
            contents=contents,
            config=_response_config(cached_content=cached_content),
            max_retries=max_retries,
        )
    except APIError as exc:
        raise ExtractError(
            f"Gemini API call failed for {pdf_path.name}: {exc}",
            pdf_path=pdf_path,
            model=model,
            request_id=str(getattr(exc, "code", None)),
        ) from exc

    candidates = resp.candidates or []
    if not candidates:
        raise ExtractError(
            f"No candidates in response for {pdf_path.name}.",
            pdf_path=pdf_path,
            model=model,
        )
    finish_reason = candidates[0].finish_reason
    if finish_reason is not None and "STOP" not in str(finish_reason):
        raise ExtractError(
            f"Response for {pdf_path.name} finished abnormally: {finish_reason!r}.",
            pdf_path=pdf_path,
            model=model,
        )

    parsed = resp.parsed
    if isinstance(parsed, ComponentSpec):
        return parsed
    if parsed is not None:
        return ComponentSpec.model_validate(parsed)
    if resp.text:
        return ComponentSpec.model_validate_json(resp.text)

    raise ExtractError(
        f"No parseable ComponentSpec in response for {pdf_path.name} "
        f"(finish_reason={finish_reason!r}).",
        pdf_path=pdf_path,
        model=model,
    )


def extract_spec(
    pdf_path: Path,
    *,
    model: str = DEFAULT_MODEL,
    use_cache: bool = False,
    client: genai.Client | None = None,
    timeout: float = 600.0,
    max_retries: int = 4,
) -> ComponentSpec:
    """Extract a ComponentSpec from a single datasheet PDF.

    `client` is injectable for testing; when omitted, a `genai.Client()` is
    constructed from the environment (GEMINI_API_KEY).
    """
    if model not in ALLOWED_MODELS:
        raise ValueError(f"model must be one of {sorted(ALLOWED_MODELS)}, got {model!r}")

    if client is None:
        # HttpOptions.timeout is documented in milliseconds for the SDK's REST
        # transport.
        client = genai.Client(http_options=types.HttpOptions(timeout=int(timeout * 1000)))

    return _extract_with_gemini(
        pdf_path, model=model, use_cache=use_cache, client=client, max_retries=max_retries
    )
