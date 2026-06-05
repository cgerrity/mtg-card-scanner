# MTG Card Scanner — Training

Offline Python pipeline. Builds the on-device card database the iOS app uses, and (starting Phase 6) trains Core ML models for disambiguation and segmentation.

See [`../PLAN.md`](../PLAN.md) for the full project plan.

## Setup

Requires **Python 3.11+**.

```bash
cd training
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

To re-enter the venv in a new shell:

```bash
cd training && source .venv/bin/activate
```

To leave it: `deactivate`.

## Running Phase 1

```bash
# 1. Download the latest Scryfall bulk card data
python -m data.scryfall_download

# 2. Build cards.sqlite from the downloaded JSON
python -m data.build_db

# 3. Run the test suite
pytest
```

All outputs land in `artifacts/` (which is gitignored).

## Project structure

```
training/
├── data/                 # Phase 1 — Scryfall ingestion + SQLite builder
├── models/               # Phase 6+ — ML training (not yet created)
├── tests/                # pytest suite
└── artifacts/            # gitignored: downloads + built DB
```

## Notes on reproducibility

In ML engineering, **reproducible data pipelines are non-negotiable.** Every artifact we produce should:

1. Record the source data version (Scryfall's `updated_at` timestamp)
2. Be deterministic given the same source data
3. Be cheap to rebuild from scratch

These are the patterns interviewers look for when they ask "how would you ensure your training pipeline is reproducible." We'll bake them in from the start.
