# Xcode Project Anatomy

**TL;DR:** An Xcode project is *a directory pretending to be a file*. The `.xcodeproj` you see in Finder is actually a folder containing build configuration, file references, and (sometimes) user-specific state. Understanding the **project / target / scheme** triad demystifies most Xcode confusion.

---

## What it is

When you click "Create New Project" in Xcode, you get a `.xcodeproj`. In Finder this looks like a file. It's not — `right-click → Show Package Contents` reveals a directory:

```
MTGScanner.xcodeproj/
├── project.pbxproj          ← THE project file: build settings, file refs, etc.
├── xcshareddata/            ← shared across the team
│   └── xcschemes/           ← shared schemes (commit these)
└── xcuserdata/              ← USER-specific state (do not commit)
    └── cgerrity.xcuserdatad/
```

`project.pbxproj` is a JSON-like ASCII property list. It contains:

- Every source file's reference
- Every target's build phases (compile, link, copy resources)
- Build settings per target per configuration (Debug / Release)
- Project-level settings (version, organization name)
- Group structure (the folder hierarchy shown in the Navigator)

It's text — so you can read it. But **don't edit it by hand**; Xcode's UI is the path of least pain.

---

## Why it matters

**For the project:** Understanding the layout helps you debug "why doesn't this file appear?" (it's not added to the target) or "why isn't this build setting taking effect?" (target overrides project).

**For ML engineering jobs:** You won't ship iOS apps in most ML eng roles. But understanding **build system models** (object/code-coupled config like Xcode's, vs declarative like Bazel/CMake) is transferable to thinking about ML training pipelines, dependency graphs, and reproducible build systems.

---

## The four concepts to know

### Project

The umbrella. Owns shared build settings and file references. One per `.xcodeproj`.

### Target

What gets built. A `.app`, a framework, a test bundle, an app extension. **A project usually has 3 targets at minimum:**

- `MTGScanner` — the app itself
- `MTGScannerTests` — unit tests
- `MTGScannerUITests` — UI tests

Each target has its **own** build settings, which **inherit from** and can **override** the project's. Targets compile their own files, may link different libraries, ship different Info.plists.

### Scheme

A *plan* for what to do with targets. Says "for action `build`, use target X; for action `test`, also include target Y; for action `run`, launch with these arguments." A scheme is essentially an Xcode-specific concept that wraps `target × action × configuration`.

Schemes can be:
- **Shared** (in `xcshareddata/xcschemes/`) — committed to git
- **User** (in `xcuserdata/.../xcschemes/`) — local only, gitignored

### Workspace

A `.xcworkspace` aggregates *multiple* projects. Used when you have an app + library + framework split, or when you use CocoaPods (Pods.xcodeproj added alongside yours). For our single-project use case, we don't need one. Open the `.xcodeproj` directly.

---

## Anatomy of our MTGScanner project

```
ios/MTGScanner/
├── MTGScanner.xcodeproj/                        ← the project bundle
│   ├── project.pbxproj                          ← TEXT — the actual project definition
│   ├── xcshareddata/xcschemes/                  ← shared schemes (commit)
│   └── xcuserdata/cgerrity.xcuserdatad/         ← user state (gitignored)
│       └── xcschemes/xcschememanagement.plist   ← which schemes show in your dropdown
│
├── MTGScanner/                                   ← source files for the app target
│   ├── MTGScannerApp.swift                       ← @main attribute lives here
│   ├── ContentView.swift                         ← initial SwiftUI view
│   ├── Item.swift                                ← sample SwiftData model
│   ├── Assets.xcassets/                          ← bundled images, colors
│   │   ├── AppIcon.appiconset/
│   │   └── AccentColor.colorset/
│   └── Preview Content/                          ← test data for SwiftUI #Preview
│       └── Preview Assets.xcassets/
│
├── MTGScannerTests/                              ← unit test target source
│   └── MTGScannerTests.swift
│
└── MTGScannerUITests/                            ← UI test target source
    ├── MTGScannerUITests.swift
    └── MTGScannerUITestsLaunchTests.swift
```

Key things to notice:

- **`MTGScannerApp.swift` has no Info.plist next to it.** Xcode 13+ moved Info.plist data into the project's build settings — there is no longer a physical Info.plist file by default. You edit it from `Project > Target > Info` tab.
- **No `main.swift`.** SwiftUI apps use the `@main` attribute on a `App`-conforming type to declare the entry point.
- **`@main` is a Swift language feature** (not Xcode-specific) — like Python's `if __name__ == "__main__"` block, it says "this type is the program entry point."

---

## What to commit, what to ignore

Already in our root `.gitignore`:

```
*.xcuserstate
xcuserdata/
*.swiftpm/configuration/
ios/build/
ios/DerivedData/
DerivedData/
```

| Path | Commit? | Why |
|---|---|---|
| `project.pbxproj` | **Yes** | The project definition |
| `xcshareddata/` | **Yes** | Shared schemes |
| `xcuserdata/` | **No** | User-specific cursor positions, window state, breakpoints |
| `Source files (.swift, .xib, .storyboard, .json)` | **Yes** | Your code |
| `Assets.xcassets/` | **Yes** | App resources |
| `Info.plist` (if it exists as a file) | **Yes** | App metadata |
| `*.entitlements` | **Yes** | Capabilities config |
| `DerivedData/` | **No** | Build artifacts; huge; regenerates on every build |

Merge conflicts in `project.pbxproj` are a notorious iOS-team pain — multiple devs adding files at once produces ugly diffs. Tools like **xcodegen** and **tuist** generate `.xcodeproj` from declarative config files (YAML / Swift) to sidestep this. Useful at team scale; overkill for solo work.

---

## Important per-target concepts

### Info.plist (and its modern equivalent)

The Info.plist describes the app to iOS: bundle ID, version, supported orientations, required capabilities, and usage descriptions (camera, location, microphone).

Xcode 13+ stores most of this in build settings (`INFOPLIST_KEY_*`) instead of a file. You edit them via:

```
Project Navigator → Target → Info tab
```

You add a key like `NSCameraUsageDescription` ("Privacy - Camera Usage Description" in the UI), give it a user-facing string, and iOS prompts the user the first time the app accesses the camera. **Without that key, the system silently denies access** — common cause of "my code can't open the camera."

### Capabilities

Apple gates certain features behind explicit "capabilities" that have to be enabled in the project AND in your provisioning profile:

- CloudKit
- iCloud Drive
- Push Notifications
- Background Modes
- HealthKit
- Sign in with Apple

Add via `Target → Signing & Capabilities → + Capability`. Xcode writes the corresponding settings into a `.entitlements` file and updates the provisioning profile.

For Phase 8 we'll enable **CloudKit** + **iCloud (Key-Value Storage)** for collection sync.

### Build settings

A dictionary of (key, value) pairs that drive the compiler, linker, and code-signing tools. There are *hundreds* of them. The ones you actually touch:

- `IPHONEOS_DEPLOYMENT_TARGET` — minimum iOS version (we set `26.0`)
- `MARKETING_VERSION` — your "v1.2.3" string
- `CURRENT_PROJECT_VERSION` — your "build 47" number
- `CODE_SIGN_STYLE` — Automatic or Manual
- `DEVELOPMENT_TEAM` — your Apple Developer team ID
- `SWIFT_VERSION` — `5` for current Swift

Inheritance: target settings inherit from project settings inherit from default settings. Override at the level closest to the target if you can.

### Schemes

A scheme defines what `⌘R` (Run), `⌘U` (Test), `⌘B` (Build), `⌘+I` (Profile), `⌘+Shift+I` (Analyze) do. Each action picks a target and a configuration.

For our project, the default scheme runs MTGScannerApp on simulator with Debug config. We'll likely never touch the scheme until we add a separate "training models" workflow.

---

## Code signing in a nutshell

To install an app on an iPhone, the binary must be signed with a certificate trusted by iOS. The certificate is tied to your Apple Developer team.

- **Free Apple ID:** signs with a "Personal Team" certificate. Apps expire **after 7 days** unless re-signed. 3 apps per device at a time.
- **Paid Apple Developer Program ($99/yr):** signs with a full Developer certificate. Apps don't expire on devices. App Store distribution requires this.

Xcode's "Automatic" signing mode handles all this for you — it picks the right provisioning profile, refreshes it, signs the build. **Almost always the right choice** unless you have CI infrastructure that needs Manual signing.

---

## Common confusions

- **"Why doesn't my file appear in the build?"** It's added to the project (visible in Navigator) but not added to the **target**. Click the file, look at the right-hand inspector → **Target Membership** → tick the target.
- **"Why don't my changes affect anything?"** Wrong target selected when adding a build setting. Settings cascade: project → target. Check both.
- **"Xcode says the build succeeded but the app didn't update."** DerivedData cache is stale. Product → Clean Build Folder (`⌘+Shift+K`), then rebuild.
- **"Why can't I commit my changes?"** Could be xcuserdata being modified. Make sure it's gitignored.

---

## See also

- [Bundle identifiers](bundle-identifiers.md)
- iOS app lifecycle (to be written)
- AVFoundation camera basics (Phase 2)

---

## Interview angle

iOS-specific so it doesn't come up in pure ML eng interviews much. But the **build-system mental model** — target dependencies, configuration inheritance, codependent capability declarations — does come up when:

- Discussing CI/CD ("how do you cache build artifacts?")
- Discussing reproducible ML training ("how does your training Docker image relate to your inference Docker image?")
- Discussing dependency management ("what happens when you change a transitive dependency?")

Treat Xcode's model as one instance of a general pattern. Bazel, CMake, Make, and even pip-tools share variants of it.
