# smd-nxt-agent

Reads SMD component datasheets (PDF) and produces reviewable part data for
configuring a Fuji NXT pick-and-place machine: body size, lead/electrode
info, polarity, and a derived nozzle + vision/recognition type.

**Design principle:** the AI (Claude) extracts physical facts from the
datasheet; pure rule-based code decides the nozzle and vision type from
those facts plus your machine's configuration. The AI never picks
hardware settings. See [`CLAUDE.md`](CLAUDE.md) for the full set of
safety rules this tool enforces.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in ANTHROPIC_API_KEY
```

## Fill in your machine config before trusting output

`config/machine.yaml`, `config/nozzle_rules.yaml`, and
`config/vision_rules.yaml` ship with neutral **placeholder** values
(`NOZZLE_PLACEHOLDER_*`, `VISION_PLACEHOLDER_*`, a 999mm clearance
limit). Replace them with your real nozzle catalog, vision option names,
machine limits, and confidence thresholds before any output is used to
configure a real machine.

If you have a Flexa part-library export, seed the rule files from your
own placement history instead of writing them by hand:

```bash
smd-nxt import-flexa /path/to/export.csv
```

## Usage

```bash
smd-nxt extract ./datasheets ./out
```

Writes three files to `./out`:

- `parts.json` — full extracted spec, mapping, and validation per part.
- `parts.csv` — flattened key fields (dimensions, nozzle, vision,
  confidences, OK/REVIEW flags) for spreadsheet review.
- `review_queue.json` — only the parts that need a human to check them
  before they're used (low confidence, fallback mapping, height/polarity
  concerns, or anything the model itself flagged).

Options:

- `--model` — `claude-sonnet-4-6` (default), `claude-opus-4-8` (hard
  drawings), or `claude-haiku-4-5` (cheap/easy parts).
- `--cache` — enable prompt caching on the PDF document block, useful if
  you re-run extraction on the same datasheet.
- `--batch` — use the Anthropic Message Batches API for high-volume runs
  instead of one call per PDF.

## Safety note

**Always review `review_queue.json` before loading any part data into the
machine.** A wrong height can crash a nozzle; a wrong polarity reverses a
part on the board. Nothing in this tool auto-commits a part to the
machine — it only produces reviewable data.

## Development

```bash
pytest          # offline; no network or API key required
ruff check .
mypy src
```

`tests/fixtures/` contains pre-extracted `ComponentSpec` JSON so the
mapping/validation/extraction logic can be tested without a real PDF or
API call. Real datasheets and pipeline output are gitignored — don't
commit them.
