# CLAUDE.md — MTG Card Scanner project context

> This file is automatically loaded into Claude Code sessions for this project.
> **Read `PLAN.md` for the full plan and `HANDOFF.md` for the quickstart.**

## What this project is

An iPhone app that uses the camera + on-device machine learning to scan Magic: The Gathering cards, identify them precisely (down to specific printing — set, collector number, foil, language), and maintain a personal collection synced via iCloud. For personal use, sideloaded via free Apple ID to the developer's iPhone.

## Critical user profile

- **Background:** strong Python developer
- **New to:** Swift, iOS, Xcode, mobile development, ML deployment, the Apple ecosystem
- **Career goal:** become a machine learning engineer
- **Wants:** copious teaching woven into the build — explain **why** and **how**, not just **what**
- **IDE:** VS Code primary, Xcode where required

### How to work with this user
- Default to **verbose, teaching-oriented explanations**.
- Frame iOS/Swift concepts via Python analogues when natural (e.g., "Swift protocols are like Python's `Protocol` types").
- **Flag any concept transferable to ML engineering jobs** and explain why it matters in interviews / on the job.
- Don't compress responses just because they're long — depth is what the user wants.
- Be patient with Apple-ecosystem friction (Xcode quirks, signing, certificates, provisioning).

### Learning notes — maintain these as you teach

The `learning/` directory is the user's reference library — per-concept teaching files organized by topic, tracked in git so they sync across machines and render on GitHub. **When you teach a new concept in a session, add or update the corresponding learning file in the same turn.** Don't defer.

- Format and topic layout documented in `learning/README.md`.
- Files use a consistent template: TL;DR → What it is → Why it matters → How it works → Watch out for → See also → Interview angle.
- Use Mermaid / ASCII diagrams where visuals help.
- Cross-link related concepts with relative markdown links.
- Update `learning/README.md`'s index when adding files.
- Existing topic dirs: `ml-engineering/`, `apple-ios/`, `python-tooling/`, `data-engineering/`. Create new ones as needed.

## Build philosophy (validated user choice)

**Deep on each layer before moving to the next.** Complete and validate each phase before starting the next. Do not switch to a vertical-slice approach without re-asking the user.

## Architecture (locked in)

- **Identification pipeline:** OCR-based, not image-hashing
  - Tier 1: collector number + set code → unique lookup
  - Tier 2: name + set → may return multiple candidates
  - Tier 3: per-card disambiguator module (e.g., `IsFoilDetector`)
- **Multi-frame Bayesian posterior** for confidence accumulation across video frames
- **On-device ML** via Core ML; training in Python (PyTorch + coremltools)
- **Card data:** Scryfall bulk JSON, text-only on-device DB (~50–100 MB), downloaded on first launch, refreshed weekly
- **Card images:** Scryfall CDN, fetched on demand, locally cached
- **Storage:** SwiftData + CloudKit sync
- **Card detection:** AVFoundation `AVCaptureSession` + Vision `VNDetectRectanglesRequest` (real-time per-frame rectangle detection). VisionKit `DataScannerViewController` is *not* used for rectangle detection — it handles only text + barcodes; we may use it for OCR in Phase 4.
- **OCR:** Apple Vision `VNRecognizeTextRequest`
- **Languages:** English only; non-English visually detected, surfaced as "unidentified"
- **Card layouts in scope:** all — standard, DFC, split/fuse/adventure, basic lands, tokens, emblems

## Target

- iPhone running **iOS 26.5** (user's device)
- Deployment target: **iOS 26.0** minimum
- Distribution: sideload via **free Apple ID** (re-sign every 7 days)
- Bundle ID (tentative): `com.cgerrity.MTGScanner`

## Status

Plan complete 2026-06-05. **No code written yet.** Next step is Phase 1 (Foundation + data pipeline, Python).

## Repo layout (planned)

```
/MTG - Card Scanner/
├── CLAUDE.md          (this file)
├── PLAN.md            (full plan + teaching curriculum)
├── HANDOFF.md         (fresh-session quickstart)
├── ios/               (Xcode project — to be created in Phase 2)
├── training/          (Python: data + model training — Phase 1)
├── shared/            (test fixtures, schemas)
└── .claude/           (project settings)
```

## What we are NOT doing in v1

Prices, rulings, format legality, multi-card stack scan, sharing/social features, App Store release, cloud backend.

## Useful prompts for continuing work

- "Continue with Phase 1 — set up Python tooling and the Scryfall ingestion pipeline."
- "Start Phase N, sub-task M."
- "I'm at sub-task M of Phase N and stuck on X."
