# SwiftUI ↔ UIKit Bridging

**TL;DR:** SwiftUI doesn't have native equivalents for every UIKit/AVFoundation primitive. To embed UIKit content in SwiftUI you conform to `UIViewRepresentable` (for a `UIView`) or `UIViewControllerRepresentable` (for a `UIViewController`). The two required methods are `makeUI…` (create) and `updateUI…` (sync state changes).

---

## What it is

SwiftUI is declarative; UIKit is imperative. Apple ships SwiftUI on top of UIKit (and AppKit on macOS), so under the hood every SwiftUI view eventually becomes a UIKit one. When SwiftUI doesn't expose a native API for something — `AVCaptureVideoPreviewLayer`, `WKWebView`, `MKMapView`, etc. — you reach for a bridge protocol:

| Use this when... | Protocol |
|---|---|
| You have a UIView to embed | `UIViewRepresentable` |
| You have a UIViewController | `UIViewControllerRepresentable` |
| (macOS equivalents) | `NSViewRepresentable`, `NSViewControllerRepresentable` |

Both require two methods:

- `makeUI…(context:) -> UIView` — create the wrapped view ONCE
- `updateUI…(_ view:, context:)` — react to SwiftUI state changes

---

## Why it matters

**For the project:** Our `CameraPreviewView` is a `UIViewRepresentable` that wraps an `AVCaptureVideoPreviewLayer` (a `CALayer`, displayed inside a `UIView`).

**For ML engineering jobs:** Bridging declarative and imperative UI is a recurring pattern beyond iOS — React + canvas/WebGL, Flutter platform views, Compose interop, even Jupyter widgets in a notebook. Knowing the *shape* of the pattern means you can pick it up in any ecosystem.

---

## Minimal example

```swift
import SwiftUI
import AVFoundation

struct CameraPreviewView: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> PreviewUIView {
        let v = PreviewUIView()
        v.previewLayer.session = session
        v.previewLayer.videoGravity = .resizeAspectFill
        return v
    }

    func updateUIView(_ uiView: PreviewUIView, context: Context) {
        // Nothing to update — session is captured by reference and the
        // layer keeps drawing automatically as the session runs.
    }
}

final class PreviewUIView: UIView {
    override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
    var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }
}
```

Used in SwiftUI like any other view:

```swift
struct ScannerView: View {
    var body: some View {
        CameraPreviewView(session: detector.session)
            .ignoresSafeArea()
    }
}
```

---

## When SwiftUI state changes

`updateUIView` is called whenever SwiftUI re-renders this view. Use it to push state into the wrapped UIView:

```swift
struct StatusLabel: UIViewRepresentable {
    let text: String
    
    func makeUIView(context: Context) -> UILabel {
        let label = UILabel()
        label.numberOfLines = 0
        return label
    }
    
    func updateUIView(_ uiView: UILabel, context: Context) {
        uiView.text = text  // sync new text on every re-render
    }
}
```

For our `CameraPreviewView`, there's nothing to update — the AVCaptureSession is a class (reference), and changes to it (frame rate, focus, exposure) flow through automatically.

---

## Coordinators (when you need delegate callbacks)

If the wrapped UIKit class expects a delegate (`UITableView`, `MKMapView`, etc.), define a `Coordinator` class that implements the delegate protocol, and return it from `makeCoordinator()`:

```swift
struct MyMapView: UIViewRepresentable {
    @Binding var selectedAnnotation: Annotation?
    
    func makeCoordinator() -> Coordinator { Coordinator(parent: self) }
    
    func makeUIView(context: Context) -> MKMapView {
        let map = MKMapView()
        map.delegate = context.coordinator  // route delegate calls to Coordinator
        return map
    }
    
    func updateUIView(_ uiView: MKMapView, context: Context) { ... }
    
    final class Coordinator: NSObject, MKMapViewDelegate {
        var parent: MyMapView
        init(parent: MyMapView) { self.parent = parent }
        
        func mapView(_ mapView: MKMapView, didSelect annotation: MKAnnotation) {
            // Use parent.selectedAnnotation = ... to push state up to SwiftUI
        }
    }
}
```

Our `CameraPreviewView` doesn't need a Coordinator because the preview layer is a passive renderer with no delegate methods we care about. Our `CardDetectionService` plays the delegate role for `AVCaptureVideoDataOutput` directly.

---

## Watch out for

- **Don't recreate the wrapped view in `updateUIView`.** Create in `makeUIView` once. Modify in `updateUIView`.
- **`updateUIView` runs frequently.** Don't do expensive work there.
- **Reference identity matters for objects you pass in.** If you pass `let session = AVCaptureSession()` from a parent SwiftUI view, recreating that parent view recreates the session. Hold it in an `@Observable` class or `@State` to persist.
- **The wrapped UIView gets its parent's frame via Auto Layout.** If your camera preview is full-screen, `.ignoresSafeArea()` on the SwiftUI side does what you'd expect.
- **`#Preview` doesn't render real camera content.** SwiftUI previews are isolated; `AVCaptureSession.startRunning()` won't yield real frames. Plan for that.

---

## See also

- [AVFoundation camera pipeline](avfoundation-camera-pipeline.md) — what we wrap in this case
- [Xcode project anatomy](xcode-project-anatomy.md)

---

## Interview angle

iOS-specific but the concept generalizes:

> **"How do you embed a low-level imperative widget in a declarative UI framework?"**

The answer is always some variant of: a wrapper component with explicit lifecycle methods (`mount` + `update`), and an explicit boundary between "framework state" and "wrapped state." React has `useEffect` + refs, Flutter has `PlatformView`, Jetpack Compose has `AndroidView`. Same shape.

If the interviewer is digging into the *quality* of your bridging, talk about:

- Identity preservation (don't recreate expensive resources)
- Threading at the boundary (UIKit is main-thread only)
- State synchronization performance (avoid expensive `update*` work)
