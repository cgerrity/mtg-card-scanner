# MTG Card Scanner

An iPhone app that uses on-device machine learning to identify Magic: The Gathering cards from the camera and maintain a personal collection synced via iCloud.

Built primarily as a personal tool — and as a working playground for learning ML engineering end-to-end: data pipelines, on-device model deployment, Bayesian streaming inference, and the surrounding production-engineering practices.

## Status

Plan complete; Phase 1 (data pipeline) implementation passing tests. See [`PLAN.md`](PLAN.md) for the full roadmap.

```
Phase 1: Foundation + data pipeline (Python)     [IN PROGRESS] — tests passing, end-to-end pending
Phase 2: Card-in-frame detection (Swift / VisionKit)
Phase 3: Region extraction
Phase 4: OCR pipeline
Phase 5: Matching + multi-frame Bayesian confidence
Phase 6: Disambiguator framework + first Core ML model
Phase 7: Inner segmentation model (fallback)
Phase 8: Collection storage + CloudKit sync
Phase 9: Scanning UX
Phase 10: Polish
```

## How it identifies a card

1. **Card detection** — VisionKit finds the card-shaped rectangle in the camera frame.
2. **Deskew** — perspective-transform to canonical 488×680 pixels.
3. **Region extraction** — crop name / collector-info / type-line regions.
4. **OCR** — Apple Vision reads text from each region.
5. **Cascading lookup**
   - Tier 1: `set_code + collector_number + language` → unique printing (works for ~80% of cards)
   - Tier 2: name + set → may return multiple candidates
   - Tier 3: per-card disambiguator module (e.g., `IsFoilDetector`)
6. **Bayesian posterior across video frames** — log-space sequential updates until threshold.
7. **Confirmation UI** — user verifies the identified card.

Full architectural detail in [`PLAN.md`](PLAN.md) and the design notes in [`learning/`](learning/).

## Project layout

```
.
├── PLAN.md             # Full plan + 10-phase roadmap with teaching curriculum
├── HANDOFF.md          # Session-to-session handoff for picking up the project
├── CLAUDE.md           # Auto-loaded context for Claude Code sessions
├── learning/           # Per-concept reference library
│   ├── ml-engineering/
│   ├── apple-ios/
│   ├── python-tooling/
│   └── data-engineering/
├── training/           # Python — data ingestion + ML training pipelines
│   ├── data/           # Scryfall ingestion → SQLite (Phase 1)
│   ├── models/         # ML training (Phase 6+)
│   └── tests/
└── ios/                # Xcode project — created in Phase 2
```

## Quickstart (Python data pipeline)

```bash
cd training
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                                    # run tests (13 should pass)
python -m data.scryfall_download          # download Scryfall bulk (~500 MB)
python -m data.build_db                   # build cards.sqlite
```

See `training/README.md` for details.

## Tech stack

| Layer | Choice |
|---|---|
| App UI | SwiftUI (iOS 26+) |
| Card detection | VisionKit `DataScannerViewController` |
| OCR | Apple Vision `VNRecognizeTextRequest` |
| On-device ML inference | Core ML |
| ML training | PyTorch + coremltools |
| Card data | Scryfall bulk JSON → SQLite (FTS5 trigram) |
| Card images | Scryfall CDN, fetched on demand |
| Persistence | SwiftData + CloudKit |
| Distribution | Sideload via free Apple ID (personal use) |

## License

Personal project — no license declared at this time.
