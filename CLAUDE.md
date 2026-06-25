# smd-nxt-agent — behavioral contract

This tool reads SMD component datasheets and produces part data for
configuring a Fuji NXT pick-and-place machine. Read this before changing
anything — the constraints below are safety rules, not style preferences.

## Hard safety rules

- **The AI extracts physical facts only.** `extract.py` (and `batch.py`)
  must never decide a nozzle or vision type. That decision belongs
  exclusively to `mapping.py`, driven by `config/`.
- **Machine-specific values live only in `config/`.** No nozzle id,
  vision id, clearance limit, weight limit, or confidence threshold may
  be hardcoded in `src/`. If you catch yourself writing a number that
  describes the machine rather than the algorithm, it belongs in
  `config/machine.yaml`.
- **Always produce `review_queue.json`.** Every pipeline run writes it,
  even if empty. Low-confidence or `needs_review` items must never be
  silently treated as OK.
- **Dimensions are always millimeters.** Convert at extraction time.
  `body_height_mm` is always the MAXIMUM of any stated range — that's
  the value that determines nozzle clearance, not typical or minimum.
- **No fabricated Fuji nozzle part numbers or vision algorithm names.**
  Use the neutral placeholders already in `config/` (e.g.
  `NOZZLE_PLACEHOLDER_*`) until the user supplies real catalog values.
- **`body_height_mm` and `is_polarized` are safety-critical.** A wrong
  height crashes a nozzle; a wrong polarity reverses a part on the
  board. Their confidence (`height_confidence`, `polarity_confidence`)
  is always surfaced separately from the overall `confidence`, and
  `validate.py` reports `height_ok` / `polarity_ok` separately too.
- **Rule predicates are evaluated by a safe interpreter, never `eval()`.**
  See `mapping._condition_matches`. New condition types must extend that
  function, not introduce dynamic code execution.

## Architecture

```
ingest   -> list PDFs in a folder
extract  -> Claude API, forced tool_use, ComponentSpec (facts only)
mapping  -> pure rules from config/, ComponentSpec -> MachineMapping
validate -> sanity + confidence thresholds -> ValidationResult
pipeline -> wires the above, writes parts.json/parts.csv/review_queue.json
batch    -> same contract as extract.py via the Message Batches API
flexa_import -> seeds nozzle_rules.yaml/vision_rules.yaml from a
                historical Flexa export (scaffolded; export format TBD)
```

`mapping.py` and `validate.py` must stay pure functions of
`(ComponentSpec, config)` — no network calls, no AI, no global state.

## Commands

```bash
pip install -e ".[dev]"
pytest                          # offline; no network, no API key needed
ruff check .
mypy src
smd-nxt extract <datasheets_dir> <out_dir> [--model] [--cache] [--batch]
smd-nxt import-flexa <export> [--config config] [--fixtures tests/fixtures]
```

## Layout

- `src/smd_nxt_agent/` — the package; one module per pipeline stage.
- `config/` — `machine.yaml` (catalog + limits + thresholds),
  `nozzle_rules.yaml`, `vision_rules.yaml`. All currently placeholders;
  fill with real values before trusting output against a real machine.
- `tests/fixtures/` — pre-extracted `ComponentSpec` JSON used to test
  `mapping.py`/`validate.py`/`extract.py` without a network call.
- `datasheets/`, `out/`, `*.pdf` are gitignored — never commit real
  datasheets or pipeline output (IP + size).

## Before changing extract.py

Any change to `EXTRACTION_INSTRUCTIONS` or `ComponentSpec` field
descriptions changes what the model is told to extract — re-read both
together; the schema's `Field(description=...)` values ARE the
extraction instructions sent as the tool's input schema.

## Before changing mapping.py or validate.py

These files must remain pure and config-driven. If a new rule type is
needed, extend the declarative `when` condition schema in
`mapping._condition_matches` rather than adding `eval`, regex hacks, or
machine-specific branches in code.

## Open item

`flexa_import._read_export()` assumes a documented CSV layout because
the real Flexa export hasn't been provided yet. When it arrives, adapt
that one function — everything downstream (rule derivation, fixture
generation) is already format-agnostic.
