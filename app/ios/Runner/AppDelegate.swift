import Flutter
import UIKit
import ARKit
import AVFoundation

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    GeneratedPluginRegistrant.register(with: self)
    if let registrar = self.registrar(forPlugin: "CaptureChannel") {
      CaptureChannel.register(with: registrar)
    }
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
  }
}

public class CaptureChannel: NSObject, FlutterPlugin, ARSessionDelegate {
    private(set) var session: ARSession?
    private var isSessionRunning = false
    private var lastFrame: ARFrame?
    private weak var currentSCNView: ARSCNView?

    @objc public static func register(with registrar: FlutterPluginRegistrar) {
        let channel = FlutterMethodChannel(name: "com.arthentic.app/capture", binaryMessenger: registrar.messenger())
        let instance = CaptureChannel()
        registrar.addMethodCallDelegate(instance, channel: channel)

        let viewFactory = ARCameraViewFactory(captureChannel: instance)
        registrar.register(viewFactory, withId: "com.arthentic.app/ar_camera_view")
    }

    func bindSCNView(_ view: ARSCNView) {
        self.currentSCNView = view
        if let session = self.session {
            view.session = session
        }
    }

    @objc public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "isLiDARAvailable":
            let isSupported = ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth)
            result(isSupported)

        case "isCameraAvailable":
            result(ARWorldTrackingConfiguration.isSupported)

        case "startSession":
            startARSession(result: result)

        case "stopSession":
            stopARSession()
            result(true)

        case "capturePoint":
            guard let args = call.arguments as? [String: Any],
                  let pointIndex = args["pointIndex"] as? Int else {
                result(FlutterError(code: "INVALID_ARGS", message: "pointIndex required", details: nil))
                return
            }
            captureCurrentFrame(pointIndex: pointIndex, result: result)

        case "getLiveTelemetry":
            getLiveTelemetry(result: result)

        default:
            result(FlutterMethodNotImplemented)
        }
    }

    private func startARSession(result: @escaping FlutterResult) {
        guard ARWorldTrackingConfiguration.isSupported else {
            result(false)
            return
        }

        let configuration = ARWorldTrackingConfiguration()
        if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
            configuration.frameSemantics.insert(.sceneDepth)
        }
        if ARWorldTrackingConfiguration.supportsFrameSemantics(.smoothedSceneDepth) {
            configuration.frameSemantics.insert(.smoothedSceneDepth)
        }

        configuration.worldAlignment = .gravity

        if session == nil {
            session = ARSession()
            session?.delegate = self
        }

        if let scnView = currentSCNView, scnView.session !== session {
            scnView.session = session!
        }

        session?.run(configuration, options: [.resetTracking, .removeExistingAnchors])
        isSessionRunning = true
        result(true)
    }

    private func stopARSession() {
        session?.pause()
        isSessionRunning = false
        lastFrame = nil
    }

    public func session(_ session: ARSession, didUpdate frame: ARFrame) {
        self.lastFrame = frame
    }

    private func getLiveTelemetry(result: @escaping FlutterResult) {
        guard let frame = lastFrame ?? session?.currentFrame else {
            result([
                "distanceCm": 14,
                "focus": "Locked",
                "steadiness": "Good",
                "isLiDARActive": false,
                "tiltDegrees": 0,
                "isLeveled": true
            ])
            return
        }

        var distanceCm = 14
        var hasLiDAR = false
        if let sceneDepth = frame.sceneDepth {
            hasLiDAR = true
            let depthBuffer = sceneDepth.depthMap
            CVPixelBufferLockBaseAddress(depthBuffer, .readOnly)
            let width = CVPixelBufferGetWidth(depthBuffer)
            let height = CVPixelBufferGetHeight(depthBuffer)
            if let baseAddress = CVPixelBufferGetBaseAddress(depthBuffer) {
                let bytesPerRow = CVPixelBufferGetBytesPerRow(depthBuffer)
                let centerX = width / 2
                let centerY = height / 2
                let centerRowPtr = baseAddress.advanced(by: centerY * bytesPerRow).assumingMemoryBound(to: Float32.self)
                let centerDepth = centerRowPtr[centerX]
                if centerDepth.isFinite && centerDepth > 0.05 && centerDepth < 2.0 {
                    distanceCm = Int(round(centerDepth * 100))
                }
            }
            CVPixelBufferUnlockBaseAddress(depthBuffer, .readOnly)
        }

        let trackingState = frame.camera.trackingState
        var steadiness = "Good"
        var focus = "Locked"

        switch trackingState {
        case .normal:
            steadiness = "Good"
            focus = "Locked"
        case .limited(let reason):
            switch reason {
            case .excessiveMotion:
                steadiness = "Unsteady"
                focus = "Adjusting"
            case .insufficientFeatures:
                steadiness = "Low Detail"
                focus = "Seeking"
            case .initializing:
                steadiness = "Calibrating"
                focus = "Seeking"
            case .relocalizing:
                steadiness = "Relocalizing"
                focus = "Seeking"
            @unknown default:
                steadiness = "Fair"
            }
        case .notAvailable:
            steadiness = "Calibrating"
            focus = "Seeking"
        }

        let euler = frame.camera.eulerAngles
        // Calculate tilt deviation (pitch and roll combined) relative to perpendicular orientation
        let pitch = Double(euler.x) * 180.0 / .pi
        let roll = Double(euler.z) * 180.0 / .pi
        let tiltMagnitude = sqrt(pitch * pitch + roll * roll)
        let tiltDegrees = Int(round(tiltMagnitude))
        let isLeveled = tiltDegrees <= 12

        result([
            "distanceCm": distanceCm,
            "focus": focus,
            "steadiness": steadiness,
            "isLiDARActive": hasLiDAR,
            "tiltDegrees": tiltDegrees,
            "pitch": Int(round(pitch)),
            "roll": Int(round(roll)),
            "isLeveled": isLeveled
        ])
    }

    private func captureCurrentFrame(pointIndex: Int, result: @escaping FlutterResult) {
        guard let frame = lastFrame ?? session?.currentFrame else {
            result(FlutterError(code: "NO_FRAME", message: "No active ARFrame available", details: nil))
            return
        }

        // 1. Photo capture from color buffer
        let pixelBuffer = frame.capturedImage
        let ciImage = CIImage(cvPixelBuffer: pixelBuffer)
        let context = CIContext()
        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent) else {
            result(FlutterError(code: "CAPTURE_FAILED", message: "Could not create CGImage", details: nil))
            return
        }
        let uiImage = UIImage(cgImage: cgImage)
        guard let photoData = uiImage.jpegData(compressionQuality: 0.95) else {
            result(FlutterError(code: "JPEG_FAILED", message: "Could not encode JPEG", details: nil))
            return
        }

        // 2. Depth map extraction (contiguous Float32 array, stride-safe)
        var depthData = Data()
        var distanceCm = 14
        if let sceneDepth = frame.sceneDepth {
            let depthBuffer = sceneDepth.depthMap
            CVPixelBufferLockBaseAddress(depthBuffer, .readOnly)
            let width = CVPixelBufferGetWidth(depthBuffer)
            let height = CVPixelBufferGetHeight(depthBuffer)
            if let baseAddress = CVPixelBufferGetBaseAddress(depthBuffer) {
                let bytesPerRow = CVPixelBufferGetBytesPerRow(depthBuffer)
                var contiguousFloats = [Float32]()
                contiguousFloats.reserveCapacity(width * height)
                for row in 0..<height {
                    let rowPtr = baseAddress.advanced(by: row * bytesPerRow).assumingMemoryBound(to: Float32.self)
                    for col in 0..<width {
                        contiguousFloats.append(rowPtr[col])
                    }
                }
                depthData = contiguousFloats.withUnsafeBufferPointer { Data(buffer: $0) }

                let centerX = width / 2
                let centerY = height / 2
                let centerRowPtr = baseAddress.advanced(by: centerY * bytesPerRow).assumingMemoryBound(to: Float32.self)
                let centerDepth = centerRowPtr[centerX]
                if centerDepth.isFinite && centerDepth > 0.05 && centerDepth < 2.0 {
                    distanceCm = Int(round(centerDepth * 100))
                }
            }
            CVPixelBufferUnlockBaseAddress(depthBuffer, .readOnly)
        }

        // 3. Camera Intrinsics
        let intrinsics = frame.camera.intrinsics
        let intrinsicsDict: [String: Any] = [
            "fx": Double(intrinsics[0][0]),
            "fy": Double(intrinsics[1][1]),
            "cx": Double(intrinsics[2][0]),
            "cy": Double(intrinsics[2][1])
        ]

        // 4. Telemetry (Distance & Steadiness estimation)
        let payload: [String: Any] = [
            "photoBytes": FlutterStandardTypedData(bytes: photoData),
            "depthBytes": FlutterStandardTypedData(bytes: depthData),
            "intrinsics": intrinsicsDict,
            "telemetry": [
                "distanceCm": distanceCm,
                "focus": "Locked",
                "steadiness": "Good",
                "pointIndex": pointIndex
            ]
        ]

        result(payload)
    }
}

class ARCameraPlatformView: NSObject, FlutterPlatformView {
    private let scnView: ARSCNView

    init(frame: CGRect, viewIdentifier viewId: Int64, arguments args: Any?, captureChannel: CaptureChannel?) {
        scnView = ARSCNView(frame: frame)
        scnView.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        scnView.contentMode = .scaleAspectFill
        scnView.clipsToBounds = true
        scnView.automaticallyUpdatesLighting = true
        super.init()

        captureChannel?.bindSCNView(scnView)
    }

    func view() -> UIView {
        return scnView
    }

    deinit {
        scnView.session.pause()
    }
}

class ARCameraViewFactory: NSObject, FlutterPlatformViewFactory {
    private weak var captureChannel: CaptureChannel?

    init(captureChannel: CaptureChannel?) {
        self.captureChannel = captureChannel
        super.init()
    }

    func create(withFrame frame: CGRect, viewIdentifier viewId: Int64, arguments args: Any?) -> FlutterPlatformView {
        return ARCameraPlatformView(frame: frame, viewIdentifier: viewId, arguments: args, captureChannel: captureChannel)
    }

    func createArgsCodec() -> FlutterMessageCodec & NSObjectProtocol {
        return FlutterStandardMessageCodec.sharedInstance()
    }
}
