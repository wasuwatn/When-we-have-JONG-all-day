"""High-volume extraction via the Gemini Batch API.

Same extraction contract as extract.py (PDF + forced structured output
against the ComponentSpec schema), just submitted as one batch of
requests instead of one call per PDF. When no per-request `key` is
supplied, Gemini's inline batch responses preserve request order, so
results are zipped back to `pdf_paths` positionally.
"""

from __future__ import annotations

import time
from pathlib import Path

from google import genai
from google.genai import types

from smd_nxt_agent.extract import (
    DEFAULT_MODEL,
    ExtractError,
    _build_content,
    _response_config,
)
from smd_nxt_agent.ingest import list_pdfs
from smd_nxt_agent.mapping import load_rules, map_spec
from smd_nxt_agent.schema import ComponentSpec, PartRecord
from smd_nxt_agent.validate import validate

POLL_INTERVAL_S = 10.0

_TERMINAL_STATES = frozenset(
    {
        types.JobState.JOB_STATE_SUCCEEDED,
        types.JobState.JOB_STATE_FAILED,
        types.JobState.JOB_STATE_CANCELLED,
        types.JobState.JOB_STATE_EXPIRED,
    }
)


def _build_request(pdf_path: Path) -> types.InlinedRequest:
    return types.InlinedRequest(contents=_build_content(pdf_path), config=_response_config())


def submit_batch(
    pdf_paths: list[Path],
    *,
    model: str = DEFAULT_MODEL,
    use_cache: bool = False,
    client: genai.Client | None = None,
) -> str:
    """Creates a batch job and returns its job name."""
    if use_cache:
        raise NotImplementedError(
            "use_cache is not supported for batch extraction: each PDF would need "
            "its own cache object since batch entries don't share a prefix, and "
            "this combination is unverified against the Gemini Batch API."
        )
    if client is None:
        client = genai.Client()
    requests = [_build_request(p) for p in pdf_paths]
    batch_job = client.batches.create(model=model, src=requests)
    if not batch_job.name:
        raise RuntimeError(f"Gemini batch creation did not return a job name (model={model!r}).")
    return batch_job.name


def wait_for_batch(
    job_name: str,
    *,
    client: genai.Client,
    poll_interval_s: float = POLL_INTERVAL_S,
) -> None:
    while True:
        job = client.batches.get(name=job_name)
        if job.state in _TERMINAL_STATES:
            return
        time.sleep(poll_interval_s)


def collect_results(
    job_name: str,
    *,
    client: genai.Client,
    model: str,
    pdf_paths: list[Path],
) -> dict[str, ComponentSpec]:
    """Returns pdf stem -> ComponentSpec. Relies on request/response order matching."""
    job = client.batches.get(name=job_name)
    if job.state != types.JobState.JOB_STATE_SUCCEEDED:
        raise ExtractError(
            f"Batch job {job_name!r} did not succeed: {job.state}",
            pdf_path=Path(job_name),
            model=model,
        )

    responses = (job.dest.inlined_responses if job.dest else None) or []
    if len(responses) != len(pdf_paths):
        raise ExtractError(
            f"Batch job {job_name!r} returned {len(responses)} responses for "
            f"{len(pdf_paths)} requests.",
            pdf_path=Path(job_name),
            model=model,
        )

    specs: dict[str, ComponentSpec] = {}
    for pdf_path, item in zip(pdf_paths, responses, strict=True):
        if item.error is not None:
            raise ExtractError(
                f"Batch entry for {pdf_path.name} failed: {item.error}",
                pdf_path=pdf_path,
                model=model,
            )
        response = item.response
        parsed = response.parsed if response else None
        if isinstance(parsed, ComponentSpec):
            specs[pdf_path.stem] = parsed
        elif parsed is not None:
            specs[pdf_path.stem] = ComponentSpec.model_validate(parsed)
        elif response and response.text:
            specs[pdf_path.stem] = ComponentSpec.model_validate_json(response.text)
        else:
            raise ExtractError(
                f"No parseable ComponentSpec in batch entry for {pdf_path.name}.",
                pdf_path=pdf_path,
                model=model,
            )
    return specs


def run_batch(
    input_dir: Path,
    out_dir: Path,
    *,
    model: str = DEFAULT_MODEL,
    use_cache: bool = False,
    config_dir: Path = Path("config"),
    client: genai.Client | None = None,
) -> list[PartRecord]:
    """Same outputs as pipeline.run(), driven by the Batch API for high volume."""
    import csv
    import json

    from smd_nxt_agent.pipeline import CSV_FIELDS, _record_to_csv_row

    out_dir.mkdir(parents=True, exist_ok=True)
    rules = load_rules(config_dir)

    pdf_paths = list_pdfs(input_dir)

    if client is None:
        client = genai.Client()

    job_name = submit_batch(pdf_paths, model=model, use_cache=use_cache, client=client)
    wait_for_batch(job_name, client=client)
    specs_by_stem = collect_results(job_name, client=client, model=model, pdf_paths=pdf_paths)

    records = []
    for pdf_path in pdf_paths:
        spec = specs_by_stem[pdf_path.stem]
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
