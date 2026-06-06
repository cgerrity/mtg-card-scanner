//
//  ContentView.swift
//  MTGScanner
//
//  Phase 2 — live camera + Vision rectangle detection.
//  Single-file deliberately; we refactor into per-concern files in a later turn.
//
//  See `learning/apple-ios/avfoundation-camera-pipeline.md`,
//      `learning/apple-ios/swiftui-uikit-bridging.md`,
//      `learning/apple-ios/coordinate-spaces.md`.
//

import SwiftUI
import AVFoundation
import Vision
import Observation

// MARK: - Top-level view

struct ContentView: View {
    // @State holds the detector across SwiftUI re-renders. Without this, SwiftUI
    // would create a new CardDetectionService every render — and a new
    // AVCaptureSession with it.
    @State private var detector = CardDetectionService()

    var body: some View {
        ZStack {
            CameraPreviewView(session: detector.session)
                .ignoresSafeArea()

            CardCornerOverlay(quad: detector.detectedQuad)
                .ignoresSafeArea()

            VStack {
                Spacer()
                StatusBubble(text: statusText)
                    .padding(.bottom, 32)
            }
        }
        .task {
            // .task launches on view appear, cancels on disappear.
            await detector.start()
        }
    }

    private var statusText: String {
        switch detector.sessionState {
        case .idle:        return "Starting…"
        case .configuring: return "Configuring camera…"
        case .running:     return detector.detectedQuad == nil
                                ? "Looking for a card…"
                                : "Card detected"
        case .denied:      return "Camera access denied. Enable in Settings."
        case .failed(let msg): return "Error: \(msg)"
        }
    }
}

// MARK: - Camera preview (SwiftUI bridge to AVCaptureVideoPreviewLayer)

/// Wraps a `UIView` that hosts an `AVCaptureVideoPreviewLayer` as its root
/// layer. The preview layer renders the live camera feed directly — no
/// per-frame work on our part.
struct CameraPreviewView: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> PreviewUIView {
        let view = PreviewUIView()
        view.previewLayer.session = session
        view.previewLayer.videoGravity = .resizeAspectFill
        // Portrait orientation for the preview layer's connection.
        if let conn = view.previewLayer.connection,
           conn.isVideoRotationAngleSupported(90) {
            conn.videoRotationAngle = 90
        }
        return view
    }

    func updateUIView(_ uiView: PreviewUIView, context: Context) {
        // The session is shared by reference; nothing to sync on each render.
    }
}

/// Overriding `layerClass` makes the view's root layer an
/// `AVCaptureVideoPreviewLayer` — much cheaper than adding it as a sublayer.
final class PreviewUIView: UIView {
    override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
    var previewLayer: AVCaptureVideoPreviewLayer {
        // swiftlint:disable:next force_cast
        layer as! AVCaptureVideoPreviewLayer
    }
}

// MARK: - Overlay: draws the detected card's 4-corner quad

struct CardCornerOverlay: View {
    let quad: CardQuad?

    var body: some View {
        GeometryReader { geo in
            if let q = quad {
                Path { path in
                    let tl = q.topLeft.toSwiftUI(in: geo.size)
                    let tr = q.topRight.toSwiftUI(in: geo.size)
                    let br = q.bottomRight.toSwiftUI(in: geo.size)
                    let bl = q.bottomLeft.toSwiftUI(in: geo.size)
                    path.move(to: tl)
                    path.addLine(to: tr)
                    path.addLine(to: br)
                    path.addLine(to: bl)
                    path.closeSubpath()
                }
                .stroke(Color.green, lineWidth: 3)
                .shadow(color: .green.opacity(0.6), radius: 2)
            }
        }
    }
}

// MARK: - Status bubble

struct StatusBubble: View {
    let text: String
    var body: some View {
        Text(text)
            .font(.callout.weight(.medium))
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(.thinMaterial, in: Capsule())
    }
}

// MARK: - Coordinate model

/// A 4-corner quad in Vision's normalized coordinate space:
/// origin at the lower-left of the source image, units in `0...1`.
struct CardQuad: Equatable {
    let topLeft: CGPoint
    let topRight: CGPoint
    let bottomLeft: CGPoint
    let bottomRight: CGPoint

    init(observation: VNRectangleObservation) {
        self.topLeft     = observation.topLeft
        self.topRight    = observation.topRight
        self.bottomLeft  = observation.bottomLeft
        self.bottomRight = observation.bottomRight
    }
}

extension CGPoint {
    /// Convert Vision space (origin lower-left, normalized 0...1) to
    /// SwiftUI space (origin upper-left, points).
    func toSwiftUI(in size: CGSize) -> CGPoint {
        CGPoint(x: x * size.width, y: (1 - y) * size.height)
    }
}

// MARK: - Detection service

/// Owns the AVCaptureSession, runs `VNDetectRectanglesRequest` on each
/// camera frame, and publishes the most-recent detected card quad.
@Observable
final class CardDetectionService: NSObject {
    /// The shared session — the SwiftUI preview view also points at this.
    let session = AVCaptureSession()

    private let videoOutput = AVCaptureVideoDataOutput()
    private let processingQueue = DispatchQueue(
        label: "com.cgerrity.MTGScanner.processing",
        qos: .userInitiated
    )

    /// Most-recent detected card quad; nil if no card visible.
    var detectedQuad: CardQuad?

    /// Lifecycle state for the status UI.
    var sessionState: SessionState = .idle

    enum SessionState: Equatable {
        case idle
        case configuring
        case running
        case denied
        case failed(String)
    }

    func start() async {
        guard await ensurePermission() else {
            await MainActor.run { self.sessionState = .denied }
            return
        }
        await MainActor.run { self.sessionState = .configuring }

        // Configuration + startRunning are slow; do them off-main.
        await Task.detached(priority: .userInitiated) { [weak self] in
            self?.configureSession()
        }.value

        await Task.detached(priority: .userInitiated) { [weak self] in
            self?.session.startRunning()
        }.value

        await MainActor.run { self.sessionState = .running }
    }

    private func ensurePermission() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:    return true
        case .notDetermined: return await AVCaptureDevice.requestAccess(for: .video)
        case .denied, .restricted: return false
        @unknown default:    return false
        }
    }

    private func configureSession() {
        session.beginConfiguration()
        defer { session.commitConfiguration() }

        session.sessionPreset = .hd1920x1080

        guard let device = AVCaptureDevice.default(
            .builtInWideAngleCamera, for: .video, position: .back
        ) else {
            failOnMain("No back camera available")
            return
        }
        guard let input = try? AVCaptureDeviceInput(device: device),
              session.canAddInput(input) else {
            failOnMain("Could not open camera input")
            return
        }
        session.addInput(input)

        videoOutput.alwaysDiscardsLateVideoFrames = true
        videoOutput.videoSettings = [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA
        ]
        videoOutput.setSampleBufferDelegate(self, queue: processingQueue)
        guard session.canAddOutput(videoOutput) else {
            failOnMain("Could not add video output")
            return
        }
        session.addOutput(videoOutput)

        // Rotate the data-output buffer to portrait so Vision can use .up.
        if let conn = videoOutput.connection(with: .video),
           conn.isVideoRotationAngleSupported(90) {
            conn.videoRotationAngle = 90
        }
    }

    private func failOnMain(_ message: String) {
        DispatchQueue.main.async { self.sessionState = .failed(message) }
    }
}

// MARK: - Per-frame Vision rectangle detection

extension CardDetectionService: AVCaptureVideoDataOutputSampleBufferDelegate {

    func captureOutput(_ output: AVCaptureOutput,
                       didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        detectRectangles(in: pixelBuffer)
    }

    private func detectRectangles(in pixelBuffer: CVPixelBuffer) {
        // Buffer is already in portrait (videoRotationAngle = 90) so .up is correct.
        let handler = VNImageRequestHandler(cvPixelBuffer: pixelBuffer, orientation: .up)

        let request = VNDetectRectanglesRequest { [weak self] req, _ in
            guard let self else { return }
            let observation = (req.results as? [VNRectangleObservation])?.first
            let quad = observation.map { CardQuad(observation: $0) }
            DispatchQueue.main.async {
                self.detectedQuad = quad
            }
        }

        // MTG card aspect ratio is 63:88 ≈ 0.716 (width:height, both orderings).
        // VNDetectRectanglesRequest's aspect range is min/max ratio = short side ÷ long side ∈ [0, 1].
        request.minimumAspectRatio  = 0.65
        request.maximumAspectRatio  = 0.80
        request.minimumSize         = 0.25      // card occupies ≥ 25% of the smaller dim
        request.minimumConfidence   = 0.7
        request.maximumObservations = 1         // most-prominent rectangle only

        try? handler.perform([request])
    }
}

// MARK: - Preview

#Preview {
    ContentView()
}
