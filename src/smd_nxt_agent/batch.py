"""High-volume extraction via the Anthropic Message Batches API.

Same extraction contract as extract.py (base64 document + forced
tool_use against the ComponentSpec schema), just submitted as one batch
of requests instead of one call per PDF. Batch results return unordered,
so everything downstream is keyed by `custom_id` (the PDF stem).
"""

from __future__ import annotations

import time
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from smd_nxt_agent.extract import (
    DEFAULT_MODEL,
    TOOL_NAME,
    ExtractError,
    _build_content,
    _component_spec_tool,
)
from smd_nxt_agent.ingest import list_pdfs
from smd_nxt_agent.mapping import load_rules, map_spec
from smd_nxt_agent.schema import ComponentSpec, PartRecord
from smd_nxt_agent.validate import validate

POLL_INTERVAL_S = 10.0


def _build_request(pdf_path: Path, *, model: str, use_cache: bool) -> Request:
    content = _build_content(pdf_path, use_cache=use_cache)
    return Request(
        custom_id=pdf_path.stem,
        params=MessageCreateParamsNonStreaming(
            model=model,
            max_tokens=4096,
            tools=[_component_spec_tool()],  # type: ignore[list-item]
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": content}],  # type: ignore[typeddict-item]
        ),
    )


def submit_batch(
    pdf_paths: list[Path],
    *,
    model: str = DEFAULT_MODEL,
    use_cache: bool = False,
    client: anthropic.Anthropic | None = None,
) -> str:
    """Creates a batch job and returns its batch id."""
    if client is None:
        client = anthropic.Anthropic()
    requests = [_build_request(p, model=model, use_cache=use_cache) for p in pdf_paths]
    batch = client.messages.batches.create(requests=requests)
    return batch.id


def wait_for_batch(
    batch_id: str,
    *,
    client: anthropic.Anthropic,
    poll_interval_s: float = POLL_INTERVAL_S,
) -> None:
    while True:
        status = client.messages.batches.retrieve(batch_id)
        if status.processing_status == "ended":
            return
        time.sleep(poll_interval_s)


def collect_results(
    batch_id: str,
    *,
    client: anthropic.Anthropic,
    model: str,
) -> dict[str, ComponentSpec]:
    """Returns custom_id -> ComponentSpec. Batch results are unordered."""
    specs: dict[str, ComponentSpec] = {}
    for entry in client.messages.batches.results(batch_id):
        custom_id = entry.custom_id
        result = entry.result
        if result.type != "succeeded":
            raise ExtractError(
                f"Batch entry {custom_id!r} did not succeed: {result.type}",
                pdf_path=Path(custom_id),
                model=model,
            )
        message = result.message
        tool_block = next(
            (
                block
                for block in message.content
                if block.type == "tool_use" and block.name == TOOL_NAME
            ),
            None,
        )
        if tool_block is None:
            raise ExtractError(
                f"No {TOOL_NAME} tool_use block for {custom_id!r}",
                pdf_path=Path(custom_id),
                model=model,
            )
        specs[custom_id] = ComponentSpec.model_validate(tool_block.input)
    return specs


def run_batch(
    input_dir: Path,
    out_dir: Path,
    *,
    model: str = DEFAULT_MODEL,
    use_cache: bool = False,
    config_dir: Path = Path("config"),
    client: anthropic.Anthropic | None = None,
) -> list[PartRecord]:
    """Same outputs as pipeline.run(), driven by the Batches API for high volume."""
    import csv
    import json

    from smd_nxt_agent.pipeline import CSV_FIELDS, _record_to_csv_row

    out_dir.mkdir(parents=True, exist_ok=True)
    rules = load_rules(config_dir)

    pdf_paths = list_pdfs(input_dir)
    by_stem = {p.stem: p for p in pdf_paths}

    if client is None:
        client = anthropic.Anthropic()

    batch_id = submit_batch(pdf_paths, model=model, use_cache=use_cache, client=client)
    wait_for_batch(batch_id, client=client)
    specs_by_id = collect_results(batch_id, client=client, model=model)

    records = []
    for custom_id, spec in specs_by_id.items():
        pdf_path = by_stem[custom_id]
        mapping = map_spec(spec, rules)
        validation = validate(spec, mapping, rules.machine)
        records.append(
            PartRecord(
                source_file=pdf_path.name,
                model=model,
                spec=spec,
                mapping=mapping,
                validation=validation,
            )
        )

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
    print(f"OK: {ok_count}  REVIEW: {len(review_queue)}  TOTAL: {len(records)}")

    return records
