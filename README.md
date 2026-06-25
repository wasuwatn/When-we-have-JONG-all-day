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

### Try it immediately with the bundled samples

The repo ships two synthetic (fictional, non-IP) datasheets so you can run
the pipeline before sourcing your own PDFs:

```bash
smd-nxt extract ./examples ./out
```

- `sample_0805_chip_resistor.pdf` is a clean, unambiguous datasheet. With
  the placeholder config it maps to `NOZZLE_PLACEHOLDER_SMALL` /
  `VISION_PLACEHOLDER_CHIP` and should land as **OK** — proof the whole
  flow works end to end.
- `sample_tantalum_cap_ambiguous.pdf` is a polarized part whose datasheet
  deliberately omits the polarity marking and gives a contradictory
  height (dimension table vs. mechanical drawing note). It should land in
  **`review_queue.json`** instead of OK, so you can see the review path
  in action. (This depends on the live model's judgment call rather than
  a canned fixture, so it's very likely but not 100% guaranteed to be
  flagged — `validate.py` will always flag the missing polarity feature
  regardless, but `needs_review` from the height contradiction depends on
  the model noticing it.)

Run both together and you should see one OK and one REVIEW result.
(Regenerate the samples with
`pip install reportlab && python examples/make_sample_datasheet.py`.)

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
