# HANDOFF — MTG Card Scanner

> If you're a fresh Claude session, **this is everything you need to pick up where the previous session left off.**

---

## TL;DR

- **What:** iPhone app that scans MTG cards using on-device ML, identifies them, builds a personal collection synced via iCloud.
- **Status:** Plan complete (see `PLAN.md`). **No code written yet.** Ready to start Phase 1.
- **User:** strong Python developer, new to iOS/Swift/mobile/ML deployment. Wants **copious teaching** — especially anything transferable to ML engineering job interviews. Email: cgerrity21@gmail.com.
- **Target:** iOS 26.5 on user's iPhone, free Apple ID sideload distribution.
- **Build philosophy:** **Deep on each layer before moving on.** Validated user choice — don't switch without re-asking.

---

## Read in this order

1. `PLAN.md` — full plan with phases, decisions, teaching curriculum
2. `CLAUDE.md` — auto-loaded; same context, terser
3. This file (`HANDOFF.md`) — quickstart pointers

---

## Project state right now

| What | Status |
|---|---|
| `PLAN.md`, `CLAUDE.md`, `HANDOFF.md` | ✅ Created |
| `.claude/` settings | ✅ Exists |
| `ios/` directory | ❌ Empty — Xcode project not yet created |
| `training/` directory | ❌ Empty — Python pipeline not yet created |
| Card DB (`cards.sqlite`) | ❌ Not yet built |
| Any code | ❌ None written |

---

## Next concrete step

**Phase 1 — Foundation + data pipeline (Python).**

Specifically:
1. **Confirm with the user** they want to begin Phase 1 now.
2. Set up `training/` with Python tooling (`pyproject.toml`, virtual env, requirements).
3. Implement `scryfall_download.py` (stream-download Scryfall bulk JSON).
4. Design `schema.sql` and implement `build_db.py` to produce `cards.sqlite`.
5. Tests + size validation (target ≤100 MB).

Full Phase 1 detail in `PLAN.md` § 5.

---

## Communication style for this user

- **Verbose explanations welcome** — user explicitly asked for "copious teaching."
- **Explain why and how**, not just what. "We're using GRDB because it's type-safe over the C SQLite API…" not "Use GRDB."
- **Highlight ML engineering relevance.** User wants to become an ML engineer; flag and explain any transferable skill (reproducible pipelines, quantization, deployment metrics, calibration, etc.).
- **Frame iOS/Swift via Python analogues** when natural. Examples:
  - Swift `protocol` ≈ Python `typing.Protocol` / `abc.ABC`
  - Swift `struct` (value semantics) ≈ Python `dataclass(frozen=True)` semantically
  - SwiftUI `@State` ≈ Python's reactive-state libraries (Solara, Streamlit) but compile-time-checked
- **Be patient with Apple-ecosystem friction**: Xcode quirks, code signing, certificates, provisioning profiles. These trip up everyone the first time.
- **Maintain the learning library.** When you teach a new concept, add a file under `learning/<topic>/<concept>.md` and update `learning/README.md`'s index. The directory is tracked in git (renders well on GitHub). Format documented in `learning/README.md`. Don't defer this to "later" — do it in the same turn the concept is introduced.

---

## Key architectural decisions (locked in — don't relitigate)

- **Identification:** text-OCR pipeline, **not** image hashing or end-to-end CNN classifier
- **Cascading tiers:** collector # → name+set → per-card disambiguator module
- **Multi-frame Bayesian posterior** across video frames
- **Card DB on device:** text-only, ~50–100 MB, downloaded first-launch from Scryfall bulk, weekly refresh
- **Card images:** Scryfall CDN, fetched on demand, locally cached
- **Storage:** SwiftData + CloudKit
- **Card detection:** VisionKit `DataScannerViewController`, fallback to `VNDetectRectanglesRequest`
- **OCR engine:** Apple Vision `VNRecognizeTextRequest`
- **Languages:** English only; non-English visually detected, surfaced as "unidentified"
- **Layouts in scope:** all (standard, DFC, split/fuse/adventure, basic lands, tokens, emblems)

## What we are NOT doing in v1

- Prices (change daily — would need separate refresh)
- Rulings, format legality, related cards
- Multi-card stack scan
- Sharing / social features
- App Store release
- Cloud backend

---

## Open items still to decide

- App display name (tentatively "MTG Scanner")
- Bundle ID confirmation (tentatively `com.cgerrity.MTGScanner`)
- PyTorch vs Create ML for disambiguator models — **defer until Phase 6**
- Set symbol classifier (visual vs OCR set code) — **defer until Phase 4**

---

## Important paths

| Path | What |
|---|---|
| `/Users/cgerrity/Documents/Projects/MTG - Card Scanner/` | Project root |
| `…/PLAN.md` | Full plan |
| `…/CLAUDE.md` | Auto-loaded project context |
| `…/HANDOFF.md` | This file |
| `/Users/cgerrity/.claude/projects/-Users-cgerrity-Documents-Projects-MTG---Card-Scanner/memory/` | Persistent memory across sessions |

---

## Useful prompts to give the assistant when resuming

- "Continue with Phase 1 — set up Python tooling and the Scryfall ingestion pipeline."
- "Start Phase N, sub-task M of the plan."
- "I'm at sub-task M of Phase N and stuck on X."
- "Explain the ML engineering principle behind what we did in Phase N." (For revisiting teaching content.)

---

## Phases at a glance (from `PLAN.md`)

| # | Phase | Stack | Status |
|---|---|---|---|
| 1 | Foundation + data pipeline | Python | ⏳ Next |
| 2 | Card-in-frame detection | Swift / VisionKit | — |
| 3 | Region extraction | Swift | — |
| 4 | OCR | Swift / Vision | — |
| 5 | Matching + multi-frame confidence | Swift | — |
| 6 | Disambiguator framework | PyTorch + Swift / Core ML | — |
| 7 | Inner segmentation model | PyTorch + Swift / Core ML | — |
| 8 | Collection storage + sync | SwiftData + CloudKit | — |
| 9 | Scanning UX | SwiftUI | — |
| 10 | Polish | Swift | — |
