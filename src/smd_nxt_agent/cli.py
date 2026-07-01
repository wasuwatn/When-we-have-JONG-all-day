"""Typer CLI entrypoint: `smd-nxt`."""

from __future__ import annotations

from pathlib import Path

import typer

from smd_nxt_agent.extract import ALLOWED_MODELS, DEFAULT_MODEL

app = typer.Typer(help="Read SMD datasheets and produce reviewable Fuji NXT part data.")


@app.command()
def extract(
    datasheets_dir: Path = typer.Argument(..., help="Folder of datasheet PDFs."),
    out_dir: Path = typer.Argument(
        ..., help="Folder to write parts.json/parts.csv/review_queue.json."
    ),
    model: str = typer.Option(
        DEFAULT_MODEL, help=f"One of: {', '.join(sorted(ALLOWED_MODELS))}"
    ),
    cache: bool = typer.Option(
        False, "--cache", help="Enable prompt caching on the PDF document block."
    ),
    batch: bool = typer.Option(
        False, "--batch", help="Use the Message Batches API instead of sync calls."
    ),
    config: Path = typer.Option(
        Path("config"), help="Folder containing machine.yaml / *_rules.yaml."
    ),
) -> None:
    """Extract part data from every PDF in DATASHEETS_DIR and write results to OUT_DIR."""
    if model not in ALLOWED_MODELS:
        raise typer.BadParameter(f"model must be one of {sorted(ALLOWED_MODELS)}")

    if batch:
        from smd_nxt_agent.batch import run_batch

        run_batch(datasheets_dir, out_dir, model=model, use_cache=cache, config_dir=config)
        return

    from smd_nxt_agent.pipeline import run

    run(datasheets_dir, out_dir, model=model, use_cache=cache, config_dir=config)


@app.command(name="import-flexa")
def import_flexa_cmd(
    export: Path = typer.Argument(..., help="Path to the Flexa part-library export file."),
    config: Path = typer.Option(
        Path("config"), help="Folder to write nozzle_rules.yaml/vision_rules.yaml into."
    ),
    fixtures: Path = typer.Option(
        Path("tests/fixtures"), help="Folder to write derived test fixtures into."
    ),
) -> None:
    """Derive mapping rules and test fixtures from a Flexa part-library export."""
    from smd_nxt_agent.flexa_import import import_flexa

    import_flexa(export, config, fixtures)


if __name__ == "__main__":
    app()
