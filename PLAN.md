# MTG Card Scanner — Project Plan

> **Status:** Plan complete 2026-06-05. No code written yet. Next step: Phase 1.

---

## 1. Project goal

Build an iPhone app that uses the camera and on-device machine learning to identify Magic: The Gathering cards precisely — down to the specific printing (set, collector number, foil, language) — and maintain a personal collection synced to iCloud.

| Dimension | Decision |
|---|---|
| Primary use case | Personal collection tracking |
| Target device | iPhone running **iOS 26.5** |
| Deployment target | iOS 26.0 minimum |
| Distribution | Sideload via free Apple ID (no $99/yr Apple Developer Program) |
| ML inference | **On-device** via Core ML |
| ML training | Offline on dev Mac with PyTorch + coremltools |
| Card data | Scryfall bulk JSON, text-only on-device DB (~50–100 MB) |
| Card images | Scryfall CDN, fetched on demand, locally cached |
| Persistence | SwiftData + CloudKit sync |
| Languages | English only; non-English visually detected, surfaced as "unidentified" |
| Card layouts in scope | All — standard, double-faced (DFC/MDFC), split/fuse/aftermath/adventure, basic lands, tokens, emblems |

### Out of scope for v1
- Card prices (change daily — would need separate refresh job)
- Rulings, format legality, related cards
- Multi-card stack scanning
- Sharing / social features
- App Store release
- Cloud backend

---

## 2. About the developer

> **Important context for any Claude session reading this file.**

- **Background:** strong Python developer
- **New to:** Swift, iOS, Xcode, mobile development, ML deployment, the Apple ecosystem in general
- **Career goal:** machine learning engineer — wants extensive teaching woven into the build
- **IDE preference:** VS Code primary, Xcode where required (build, debug, simulator, device deployment)
- **Build philosophy (validated user choice):** *deep on each layer before moving to the next.* Do not switch to vertical-slice without re-asking the user.

### How to assist this user
- Default to **verbose, teaching-oriented explanations**.
- Explain **why** and **how**, not just **what**.
- Frame iOS/Swift concepts via Python analogues where they help (e.g., "Swift protocols are like Python `Protocol` types / abstract base classes").
- **Highlight transferable ML engineering skills** — quantization, deployment metrics, reproducible training, etc. — and explain why each matters in a job context.
- Be patient with Apple-ecosystem friction (Xcode quirks, certificates, provisioning, signing).

---

## 3. The identification pipeline (locked-in design)

```
        ┌──────────────────────┐
        │   Camera frame       │  (live video, ~30 fps)
        └─────────┬────────────┘
                  │
                  ▼
        ┌──────────────────────┐
        │ Card detection       │  AVFoundation AVCaptureSession +
        │  → 4 corner points   │  Vision VNDetectRectanglesRequest
        └─────────┬────────────┘
                  │
                  ▼
        ┌──────────────────────┐
        │  Perspective deskew  │  CGAffineTransform → canonical 488×680
        └─────────┬────────────┘
                  │
                  ▼
        ┌──────────────────────┐
        │  Frame style classify│  modern / old / special  (rule-based v1)
        └─────────┬────────────┘
                  │
                  ▼
        ┌──────────────────────┐
        │  Region extraction   │  template-based crops:
        │                      │   name / type-line / collector-info / art
        └─────────┬────────────┘
                  │
                  ▼
        ┌──────────────────────┐
        │  OCR per region      │  Apple Vision VNRecognizeTextRequest
        └─────────┬────────────┘
                  │
                  ▼
        ┌──────────────────────┐
        │  Cascading lookup    │  Tier 1: collector # + set code → unique
        │                      │  Tier 2: name + set → maybe multiple
        │                      │  Tier 3: per-card disambiguator module
        └─────────┬────────────┘
                  │
                  ▼
        ┌──────────────────────┐
        │  Bayesian posterior  │  accumulate across video frames
        │  P(card | frames)    │  until max posterior > threshold
        └─────────┬────────────┘
                  │
                  ▼
        ┌──────────────────────┐
        │  Confirmation UI     │  show card image from Scryfall CDN
        │                      │  user confirms / corrects / adds to collection
        └──────────────────────┘
```

### Cascading identification, in detail

The key insight that drives this design: **on MTG cards from M10 (2008) onward, the bottom-left corner contains `set_code` + `collector_number`. This combination is globally unique across all printings.** So if we OCR that text correctly, we have a perfect identification — including alt arts and foils.

**Tier 1 — Collector number lookup** (~80% of cards we'll scan)
- OCR the bottom-left region
- Validate format (e.g., `0123/271 · MOM · en`)
- DB query: `SELECT * FROM cards WHERE set_code=? AND collector_number=? AND language=?`
- If exactly one match → identified

**Tier 2 — Name + set fallback** (old frames, no collector number)
- OCR the card name (Beleren font on modern cards, various on old)
- OCR or classify the set symbol
- DB query: `SELECT * FROM cards WHERE name LIKE ? AND set_code=?`
- If exactly one match → identified
- If multiple matches → Tier 3

**Tier 3 — Disambiguator modules** (extensible plug-in framework)
- Each card row in the DB carries a JSON list of disambiguator flags:
  `[{"name": "isFoilDetector", "args": {...}}]`
- The flag tells us which specialized Core ML module to invoke
- Each disambiguator takes the image + candidate list and returns a likelihood per candidate
- Plugs directly into the Bayesian posterior

### Multi-frame Bayesian posterior

For each candidate card `c` returned by Tier 1/2/3, maintain `P(c | frames_so_far)`:

```
Initial:  P(c | ∅) = uniform over candidate set
Each frame t:
   likelihood(c, frame_t) = product of per-region OCR/match likelihoods
   P(c | frames_1..t) ∝ P(c | frames_1..t-1) × likelihood(c, frame_t)
   normalize so Σ P(·) = 1

Identified when:  max_c P(c | frames) > τ   (e.g., τ = 0.99)
Reset when:       card-change detector fires (corners moved a lot, or no card detected for N frames)
```

> 📚 **ML eng teaching note** — This is *exactly* the kind of streaming-Bayesian-inference work that shows up in production ML systems (e.g., online ranking with per-impression updates, sensor fusion, A/B test posteriors). We'll implement this in log-space for numerical stability and unit-test it carefully. Talking about this kind of thing is gold in ML engineering interviews.

---

## 4. Repo structure (planned)

```
/MTG - Card Scanner/
├── CLAUDE.md                # Auto-loaded project context for Claude sessions
├── PLAN.md                  # This file
├── HANDOFF.md               # Quickstart for fresh sessions
├── ios/                     # Xcode project (SwiftUI app)
│   ├── MTGScanner.xcodeproj
│   ├── MTGScanner/
│   │   ├── App.swift        # @main entry point
│   │   ├── Views/           # SwiftUI views
│   │   ├── Models/          # SwiftData models (CollectionEntry, Deck, etc.)
│   │   ├── Services/        # CardDetector, RegionExtractor, OCR, Matcher
│   │   ├── ML/              # Core ML model wrappers + disambiguators
│   │   ├── Data/            # SQLite access (GRDB or raw)
│   │   └── Resources/       # Compiled .mlmodelc, assets, fixtures
│   └── MTGScannerTests/
├── training/                # Python: data + model training
│   ├── pyproject.toml
│   ├── data/                # Scryfall ingestion → SQLite builder
│   │   ├── scryfall_download.py
│   │   ├── build_db.py
│   │   └── schema.sql
│   ├── models/              # Inner segmenter, disambiguators
│   │   ├── is_foil/
│   │   ├── inner_segmenter/
│   │   └── shared/          # Augmentation, training loop utilities
│   ├── notebooks/           # Exploration
│   └── README.md
├── shared/                  # Test fixtures, sample card photos, schemas
└── .claude/                 # Project settings (already exists)
```

---

## 5. Phased build plan

User chose **deep on each layer before next**. We complete and validate each phase before starting the next.

> Each phase carries an **Educational thread** — the ML-engineering concepts we'll teach as we encounter them.

---

### Phase 1 — Foundation + data pipeline (Python)

**Goal:** A queryable SQLite database of all MTG cards on disk, generated reproducibly from Scryfall bulk data.

**Sub-tasks**
1. `training/` directory bootstrap: `pyproject.toml`, virtual env, dependencies (requests, sqlite3, pandas, pydantic, pytest, coremltools — coremltools comes later but we install upfront).
2. `scryfall_download.py`:
   - Hit `https://api.scryfall.com/bulk-data` to discover the latest bulk URL.
   - Stream-download `all_cards` JSON (~1.5 GB uncompressed).
   - Verify the `updated_at` timestamp and store metadata.
3. `schema.sql`:
   - `cards` (id PK, name, set_code, collector_number, language, type_line, mana_cost, oracle_text, power, toughness, rarity, frame, layout, image_uri)
   - `sets` (code PK, name, release_date, symbol_uri, parent_set)
   - `disambiguator_flags` (card_id FK, flag_name, args_json)
   - `meta` (key PK, value) — stores `db_version`, `scryfall_updated_at`
   - FTS5 virtual table on `cards.name` for fuzzy name search
4. `build_db.py`:
   - Parse Scryfall JSON in streaming fashion (don't load 1.5 GB into RAM).
   - Filter to scope (keep all languages in column but flag English).
   - Normalize fields, infer `frame` style.
   - Detect name+set collisions and emit disambiguator flag rows.
   - Emit `cards.sqlite`.
5. Tests with pytest: row counts, distinct sets, sample lookups, FTS sanity.
6. Validate DB size <100 MB.

**Educational thread**
- SQL schema design for an on-device read-mostly workload
- FTS5 for fuzzy name search
- Streaming JSON parsing (`ijson`) vs naive `json.load` — memory matters when artifacts are >1 GB
- Reproducible data pipelines: versioning the artifact, snapshotting source metadata
- pytest fixtures and parametrized tests

**Deliverable:** `cards.sqlite` artifact ~50–100 MB, plus tests proving correctness

---

### Phase 2 — Card-in-frame detection (Swift — first iOS work)

**Goal:** A standalone scanner playground that points the camera at a card, draws a box around it, deskews it to canonical 488×680 dimensions, and saves the cropped image.

**Sub-tasks**
1. Create Xcode project (`ios/MTGScanner.xcodeproj`):
   - SwiftUI App template
   - Deployment target: iOS 26.0
   - Bundle ID: `com.cgerrity.MTGScanner`
   - Add `NSCameraUsageDescription` to Info.plist
2. Camera setup with `AVFoundation` + `AVCaptureSession` for raw frame access; wrap as a SwiftUI view via `UIViewControllerRepresentable`.
3. Per-frame: `VNDetectRectanglesRequest` configured with aspect ratio ~0.716 (63/88).
4. Implement `CGAffineTransform` (or `CIPerspectiveTransform`) to unwarp to canonical pixel size.
5. Quality scoring:
   - In-focus check (Laplacian variance)
   - Glare detection (highlight saturation)
   - Occlusion check (rectangle confidence)
7. Debug overlay: corners drawn on live preview.
8. Save deskewed frames to `Documents/` for inspection.

**Educational thread**
- **What is `AVFoundation`?** Apple's media capture framework — sits between hardware and your code.
- **Why YUV?** iPhone cameras deliver YUV (luminance + chrominance) frame buffers; converting to RGB costs CPU. We'll measure the cost.
- **What is `CVPixelBuffer`?** Apple's zero-copy image container — passed around without re-allocation. Important for real-time pipelines.
- **Perspective transform math:** the 4-corner unwarp is a homography. We'll derive it briefly.
- **iOS app lifecycle:** what happens when the user backgrounds the app mid-scan? We'll plan for it.
- **SwiftUI + UIKit bridging:** `UIViewControllerRepresentable` — the mechanism for using older UIKit-only components in SwiftUI.

**Deliverable:** Scanner playground producing real-time deskewed card crops on-device

---

### Phase 3 — Region extraction

**Goal:** Given a canonical card image, return `{nameImage, typeLineImage, collectorInfoImage, artImage, rulesTextImage}`.

**Sub-tasks**
1. Identify and document canonical pixel coordinates per region per frame style:
   - Modern post-M15 (2014–present)
   - Modern M15+ (subtle changes — 2015+ holofoil layout shift)
   - Old pre-2008
   - Future special cases (DFC back, split, etc.)
2. Rule-based `FrameStyleClassifier`:
   - Check frame border color (silver/black/gold/etc.)
   - Check frame thickness
   - Check presence of holofoil stamp position
3. `RegionExtractor.swift` with template-based cropping.
4. Test harness with sample card photos in `shared/fixtures/`.
5. Snapshot tests: cropped regions vs. expected images (pixel-diff with tolerance).

**Educational thread**
- "Rule-based first, learned model later" — a critical instinct in production ML. Most systems should *try* rules before learning; rules are debuggable and free at runtime.
- Snapshot testing — what it is, when it pays for itself
- Swift Package Manager fixtures
- The discipline of **defining the interface before the model exists**

**Deliverable:** `RegionExtractor.swift` with passing snapshot tests for ≥10 sample cards across 3 frame styles

---

### Phase 4 — OCR

**Goal:** Reliable structured OCR output for each region.

**Sub-tasks**
1. Vision framework `VNRecognizeTextRequest` integration with `.accurate` mode + region-specific configs.
2. Per-region recognizers:
   - **Collector info:** custom character set `[A-Z0-9·/ ]`, expected-format regex
   - **Name:** standard English, vocabulary biased toward MTG-known words via `customWords`
   - **Type line:** standard English
3. **Pre-upscale tiny regions** (collector info text is small — Vision struggles below a threshold)
4. Confidence parsing: Vision returns per-token confidence; surface it in `OCRResult`
5. Tests on real card photos: target ≥95% pass rate on collector info text

**Educational thread**
- **What is OCR doing under the hood?** Conceptual: detection (where is text?) + recognition (what does it say?). Vision's accurate mode uses a CNN+CTC architecture.
- **Pre-processing pays.** Upscaling small text 2–4× often dramatically improves recognition. Worth measuring.
- **Confidence calibration** — confidence values from off-the-shelf models are *not* calibrated probabilities. You usually need to calibrate them with isotonic regression or temperature scaling for downstream use.
- **Custom vocabulary biasing** — when the domain vocabulary is constrained, telling the recognizer about it helps a lot.

**Deliverable:** `CardOCR.swift` returning structured `OCRResult` per frame with confidence scores

---

### Phase 5 — Matching + multi-frame confidence

**Goal:** End-to-end identification: hold a card up, get a card ID back with confidence.

**Sub-tasks**
1. SQLite wrapper (probably **GRDB.swift** — type-safe, mature, good ergonomics).
2. Indexed lookups for `(set, collector_number, language)` and `name`.
3. Fuzzy name matching for partial OCR (Levenshtein or FTS5 trigram).
4. **Bayesian posterior accumulator**: Swift class with `func update(observation: OCRResult)` and `var posterior: [CardID: Double]`.
5. Identification event when posterior threshold reached.
6. Card-change detection → reset.

**Educational thread**
- **Bayesian inference in code** — the math we'll implement explicitly
- **Log-space arithmetic for numerical stability** — when you multiply many small probabilities, you lose precision; add log-likelihoods instead
- **Prior calibration** — where does the initial prior come from? Uniform isn't always right
- **When to reset state in a streaming system** — the change-point detection problem in microcosm
- **GRDB.swift as a case study** — how a well-designed Swift wrapper over a C library works (pattern useful when interfacing with PyTorch C++ or ONNX runtime later in your career)

**Deliverable:** Functioning identification pipeline; ≥90% accuracy on a test set of 50 hand-collected card photos

---

### Phase 6 — Disambiguator framework

**Goal:** Resolve ambiguities Tier 1/Tier 2 can't (e.g., foil vs non-foil of the same printing).

**Sub-tasks**
1. Swift protocol `Disambiguator`:
   ```swift
   protocol Disambiguator {
       static var name: String { get }
       func update(observation: CardObservation, candidates: [CardID]) -> [CardID: LogLikelihood]
   }
   ```
2. Registry + lookup by name (Phase 1 populated the `disambiguator_flags` table).
3. **First concrete disambiguator: `IsFoilDetector`**
   - Modern cards: rule-based detection of the holofoil star in the collector-info region
   - Older cards: small CNN classifier trained on foil vs non-foil crops
4. PyTorch training pipeline for `IsFoilDetector`:
   - Collect training data (Scryfall provides foil indicators in the JSON)
   - Augmentation: glare simulation, brightness/contrast, slight rotation
   - Small MobileNetV3-Small or even a custom 4-layer CNN — we want it tiny
   - Train, validate, export to `.mlpackage` via `coremltools.convert(...)`
5. iOS integration: wrap the `.mlpackage` in a Swift class implementing `Disambiguator`
6. Integration tests on cards with known foil/non-foil pairs

**Educational thread** — *This is the meatiest ML deployment phase. Pay attention here for ML engineering job prep.*
- **End-to-end model deployment workflow** — collect data → train → validate → export → integrate → benchmark → ship
- **Train/val/test split discipline** for classification with class imbalance
- **Data augmentation strategy** — what to augment (lighting, angle, glare), what *not* to (foil appearance!)
- **Model architecture choice for mobile** — when to use MobileNet, when a custom tiny CNN, when distillation
- **Exporting PyTorch → Core ML via coremltools** — every quirk explained
- **Quantization** — int8 vs fp16 vs fp32, the accuracy/size/speed tradeoffs
- **Benchmarking on-device latency** — measuring P50 and P95 on real hardware (not just simulator)
- **Model size budget** — every disambiguator adds to app size; we'll set and enforce a budget
- **Why the disambiguator is per-card-flagged** — the cost-aware engineering pattern: only load the heavy model when actually needed

**Deliverable:** `IsFoilDetector.mlpackage` integrated, functional disambiguator framework, documented training pipeline

---

### Phase 7 — Inner segmentation model (robustness fallback)

**Goal:** Handle non-template frames (special art treatments, partial occlusion) where the rule-based region extractor fails.

**Sub-tasks**
1. **Synthetic training data pipeline**:
   - Pull Scryfall card images (the 'normal' size ~488×680)
   - Generate ground-truth segmentation masks programmatically (we know the layout!)
   - Augmentation: perspective distortion, lighting, glare, partial occlusion, motion blur
   - 100K+ synthetic training examples, near-free
2. Model: lightweight semantic segmentation — DeepLabv3 with MobileNetV3 backbone, or a small U-Net
3. PyTorch training loop with TensorBoard logging, checkpointing, LR scheduling
4. Export to Core ML
5. iOS integration as fallback when `FrameStyleClassifier` returns "unknown"
6. On-device benchmarks: latency <50 ms on iPhone 15+, model size <5 MB

**Educational thread**
- **Synthetic data pipelines** — when synthetic > real, when not (we know layout exactly, so synthetic is gold here)
- **Augmentation strategy as engineering** — augmentation is the difference between a model that works in the lab and a model that ships
- **Segmentation loss design** — Cross-Entropy vs Dice vs Tversky; class imbalance handling
- **Picking metrics that match deployment** — pixel accuracy lies; IoU per class doesn't
- **Quantization-aware training** vs **post-training quantization**
- **Profiling on real hardware** via Xcode Instruments — what to look for

**Deliverable:** Segmentation model that improves identification rate on non-standard frames

---

### Phase 8 — Collection storage + sync

**Goal:** Persistent, iCloud-synced personal collection.

**Sub-tasks**
1. SwiftData models:
   - `CollectionEntry`: card_id, quantity, condition, foil, language, acquired_date, notes
   - `Tag` (many-to-many with CollectionEntry)
   - Maybe `Deck` (deferred, but schema-aware)
2. CloudKit container setup, app entitlements, iCloud capability
3. Background sync handling
4. UI: collection list, search, filter by set/color/type/rarity
5. "Add to collection" action plumbed into the scan-confirmation flow

**Educational thread**
- **SwiftData vs Core Data** — why SwiftData is the new way; what changed
- **CloudKit sync mechanics** — record zones, push notifications, conflict resolution
- **iCloud capability + entitlements file** — what these XML files actually do
- **Offline-first thinking** — design for "the user is on a plane right now"

**Deliverable:** Working collection that syncs across user's Apple devices

---

### Phase 9 — Scanning UX

**Goal:** Production-quality scanning experience.

**Sub-tasks**
1. Live camera view with on-screen reticle
2. Real-time corner overlay drawn from detection results
3. Confidence indicator (progress ring as posterior accumulates)
4. Confirmation sheet: large card image (Scryfall CDN), card details, quantity stepper, condition picker, foil toggle
5. Continuous mode: confirm and immediately resume scanning
6. Undo / manual edit / manual override
7. Haptic feedback on successful identification

**Educational thread**
- SwiftUI animation primitives, state management at scale
- Accessibility (VoiceOver) — non-negotiable in modern iOS dev
- Camera permission UX — what good first-launch flow looks like

**Deliverable:** Polished scanner that feels like a finished product

---

### Phase 10 — Polish

**Goal:** Ship-ready for personal use.

**Sub-tasks**
1. First-launch onboarding (DB download progress, camera permission, iCloud sign-in prompt)
2. Settings screen
3. Error handling + offline graceful degradation
4. Localization stubs (English-only at launch but structured for future)
5. App icon, launch screen
6. Sideload re-signing workflow documented (free Apple ID = 7-day cycle)

**Deliverable:** App you use daily

---

## 6. Cross-phase teaching curriculum

Concepts that will be explicitly taught as we encounter them.

### iOS / Swift fundamentals (for a Python developer)
- Xcode project structure: targets, schemes, signing identities, Info.plist, capabilities, entitlements
- Swift basics: optionals (`?` and `!`), value types (struct) vs reference types (class), protocols, generics, `actor` for concurrency
- SwiftUI declarative model: `View` as a value, `@State` / `@Binding` / `@Environment` / `@Observable`
- iOS app lifecycle, app states, background execution
- Swift Concurrency: `async`/`await`, structured concurrency, `Task`, `TaskGroup`, actors

### Apple ML stack
- **Vision framework:** built-in pre-trained models for rectangles, text, faces, body pose, etc.
- **VisionKit:** higher-level scanning UI components (DataScanner, DocumentCamera)
- **Core ML:** Apple's on-device inference engine; consumes models from PyTorch, TensorFlow, ONNX, scikit-learn
- **Create ML:** Apple's no-code training tool — fine for simple classifiers/object detectors, ceiling lower than PyTorch
- **coremltools:** Python library that converts trained models to `.mlmodel` / `.mlpackage`
- **Core ML model formats:** `.mlmodel` (legacy, ML Program), `.mlpackage` (newer container with metadata + weights + ops)

### ML engineering practice (directly transferable to a job)
- **Reproducible training pipelines:** data versioning, model versioning, deterministic seeds
- **Train/val/test discipline:** how to split for streaming/temporal data, leakage prevention
- **Loss design:** classification vs segmentation vs detection losses; class imbalance handling
- **Model size optimization:** quantization (8-bit, 4-bit), pruning, distillation
- **Deployment metrics that matter beyond accuracy:** latency, memory footprint, energy, P95 vs P50
- **Inference profiling on real hardware**
- **A/B comparison of model versions in production**
- **Failure mode analysis** — building and maintaining a "regression" test set of past failures
- **Cost-aware engineering** — every byte of model and every millisecond of latency costs the user something

### Bayesian inference + streaming systems
- The math behind the multi-frame posterior accumulator
- Log-space arithmetic for numerical stability
- Prior calibration
- When and how to reset state (change-point detection)

---

## 7. Open items

| Item | Status |
|---|---|
| iOS deployment target | iOS 26 (user is on 26.5) ✅ |
| Bundle ID | Tentative `com.cgerrity.MTGScanner` |
| App display name | TBD |
| PyTorch vs Create ML for disambiguators | Defer until Phase 6 |
| Set symbol classifier (visual vs OCR set code) | Defer; explore in Phase 4 |

---

## 8. Risks & watch-items

- **Free Apple ID sideload expires every 7 days.** App must be re-signed periodically. Document the re-sign workflow in Phase 10.
- **OCR on small collector text** — may need aggressive pre-upscaling; validate in Phase 4.
- **DB size growth** — Scryfall keeps growing as new sets release. Recheck size annually.
- **CloudKit complexity** — sync is harder than it looks. Plan a full Phase 8 for it; don't tack it on.
- **Model bloat** — Core ML models compound; budget total app size from the start.
- **Privacy** — camera access requires `NSCameraUsageDescription` in Info.plist with a user-readable reason.

---

## 9. References

| Topic | Link |
|---|---|
| Scryfall API | https://scryfall.com/docs/api |
| Scryfall bulk data | https://scryfall.com/docs/api/bulk-data |
| Apple Vision framework | https://developer.apple.com/documentation/vision |
| VisionKit | https://developer.apple.com/documentation/visionkit |
| Core ML | https://developer.apple.com/documentation/coreml |
| coremltools | https://apple.github.io/coremltools/ |
| SwiftData | https://developer.apple.com/documentation/swiftdata |
| CloudKit | https://developer.apple.com/documentation/cloudkit |
| WWDC sessions on Vision/Core ML | https://developer.apple.com/videos/ |
| GRDB.swift | https://github.com/groue/GRDB.swift |

---

## 10. Current status

**2026-06-05** — Planning conversation complete. Repo contains only this plan, `CLAUDE.md`, `HANDOFF.md`, and `.claude/`. No code yet.

**Next concrete step:** Confirm with the user, then begin **Phase 1 — Foundation + data pipeline** in the `training/` directory.
