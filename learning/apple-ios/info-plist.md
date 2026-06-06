# Info.plist

**TL;DR:** Info.plist is the metadata file iOS reads to decide how to load your app — bundle ID, version, supported orientations, **which permissions you intend to ask for and why**, required capabilities. Modern Xcode doesn't keep it as a physical file by default; the values live in build settings and Xcode synthesizes the plist at build time.

---

## What it is

A property list (`.plist`) is Apple's XML or binary serialization format for "structured config." Info.plist specifically holds app-level metadata:

- `CFBundleIdentifier` — your bundle ID (we covered this in [bundle-identifiers.md](bundle-identifiers.md))
- `CFBundleShortVersionString` — your marketing version, e.g. "1.2.3"
- `CFBundleVersion` — your build number, e.g. "47"
- `UISupportedInterfaceOrientations` — portrait, landscape-left, etc.
- `UIRequiredDeviceCapabilities` — only run on devices with camera, etc.
- `NSCameraUsageDescription` — what to tell the user when requesting camera access
- `NSLocationWhenInUseUsageDescription` — same for location
- `NSMicrophoneUsageDescription`, `NSPhotoLibraryUsageDescription`, ... — same for every other permission-gated capability

iOS reads this at app launch and uses it to populate the App Store listing, configure the App Sandbox, gate permission prompts, etc.

---

## Why it matters

**Critical for permissions:** iOS *silently denies* access to camera, location, microphone, etc. if your Info.plist doesn't carry the matching `Usage Description` key. The system never even prompts the user. Symptom: your code calls `AVCaptureDevice.requestAccess(for: .video)` and immediately receives "denied" with no permission dialog shown. **One of the most common iOS bugs new devs hit.**

**For ML eng jobs:** Info.plist itself isn't transferable, but the underlying concept — **declarative manifests of permissions/capabilities** — is. Every modern platform has its equivalent: AndroidManifest.xml, browser permission manifests, Kubernetes service accounts, AWS IAM roles. The pattern is: **declare what you need, the platform enforces it**.

---

## Modern Xcode and Info.plist

Pre-Xcode 13: every project had `Info.plist` as a physical file in the project.

Xcode 13+: by default, Xcode keeps Info.plist values as **build settings**. The synthesized Info.plist is built at compile time and embedded in the app bundle. You edit values via:

```
Project Navigator → Target → Info tab
```

That UI maps to underlying build settings prefixed `INFOPLIST_KEY_`:

| What you see in Info tab | Build setting |
|---|---|
| Bundle identifier | `PRODUCT_BUNDLE_IDENTIFIER` |
| Bundle name | `INFOPLIST_KEY_CFBundleName` |
| Privacy - Camera Usage Description | `INFOPLIST_KEY_NSCameraUsageDescription` |
| Required device capabilities → arm64 | `INFOPLIST_KEY_UIRequiredDeviceCapabilities` |

When the project is built, Xcode aggregates these into a temporary Info.plist and embeds it into `MTGScanner.app/Info.plist`. You can verify by inspecting the built app bundle.

---

## When you might want a physical Info.plist file

Some scenarios need a real file:

- **Adding custom keys** (e.g. third-party SDKs that read their own keys)
- **CI/CD that wants to grep or sed the plist**
- **Migrating an older project**

To convert: `Target → Build Settings → search "GENERATE_INFOPLIST_FILE"` and set to `No`, then specify `INFOPLIST_FILE` to point at a file path. Xcode will create the physical file on next build.

For our project, we stay with the build-setting style. Simpler.

---

## In our project

The build settings now include (because you added it via the Info tab):

```
INFOPLIST_KEY_NSCameraUsageDescription = "MTG Scanner uses the camera to identify Magic: The Gathering cards."
```

When the app first calls camera APIs, iOS shows the user a dialog with that exact string. The user taps Allow or Don't Allow. iOS remembers the choice forever (or until the user resets it in Settings).

If you forgot to add it, the camera call would return "denied" with no dialog — making debugging miserable. **Always check Info.plist permissions first when a permission-gated API misbehaves.**

---

## Watch out for

- **Permission usage strings are user-facing.** Apple's App Review checks them. Bad strings ("we need the camera") get rejected. Good strings explain the *why* in concrete user-facing terms.
- **iOS aggressively caches the first-prompt result.** During development, if you tap "Don't Allow" once, you have to reset privacy via Settings → General → Reset → Reset Location & Privacy. Or delete + reinstall the app.
- **The simulator behaves differently from device.** Sometimes simulator never shows the prompt (since simulator privacy is per-Mac-host). Test on device for permission flows.
- **Don't request permissions you don't use.** Apple flags this in review and users distrust apps that ask for the kitchen sink.
- **Some keys are required even if you don't use the capability** — e.g., older iOS versions required `NSPhotoLibraryUsageDescription` if your app *linked* (even unused) frameworks that could touch the photo library.

---

## See also

- [Bundle identifiers](bundle-identifiers.md)
- [Xcode project anatomy](xcode-project-anatomy.md)

---

## Interview angle

iOS-specific, doesn't usually come up in ML interviews. But if asked about iOS deployment ("we want to put an ML model on-device — what does that involve?"), mention:

- Code signing
- Capability/permission declarations (Info.plist)
- App size budgets
- On-device profiling
- Privacy considerations specifically for ML (model weights as PII proxies, on-device personalization)
