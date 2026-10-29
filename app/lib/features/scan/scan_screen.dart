import 'dart:async';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme.dart';
import '../../core/models.dart';
import '../../capture/capture_channel.dart';
import '../../services/api_client.dart';
import '../../services/wallet_service.dart';
import '../result/result_screen.dart';

class ScanScreen extends StatefulWidget {
  final ArtworkInfo artwork;
  final String selectedRole;

  const ScanScreen({
    super.key,
    required this.artwork,
    this.selectedRole = "Collector",
  });

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> with SingleTickerProviderStateMixin {
  static const int totalPoints = 8;
  int currentPoint = 1; // Starts at Point 1 of 8
  int distanceCm = 14;
  int tiltDegrees = 0;
  int pitchDeg = 0;
  int rollDeg = 0;
  bool isLeveled = true;
  String focusStatus = "Locked";
  String steadinessStatus = "Good";
  bool isLiDAROn = true;
  bool isCapturing = false;
  bool isFlashing = false;
  bool hasLiveCamera = false;
  bool isCoolingDown = false;
  String? uploadErrorMsg;
  final List<String> _captureIds = [];

  static const Map<int, String> spatialPointNames = {
    1: "Top-Left Corner",
    2: "Top-Center",
    3: "Top-Right Corner",
    4: "Center-Left",
    5: "Center-Right",
    6: "Bottom-Left Corner",
    7: "Bottom-Center",
    8: "Bottom-Right Corner",
  };

  Timer? _telemetryTimer;
  Timer? _countdownTimer;
  Timer? _cooldownTimer;
  AnimationController? _simulatedCameraController;
  final GlobalKey _viewfinderKey = GlobalKey();
  Rect? _viewfinderRect;

  double countdownProgress = 0.0;
  int _countdownElapsedMs = 0;
  static const int countdownDurationMs = 800;
  static const int cooldownDurationMs = 1500;

  bool get isDistanceOptimal => distanceCm >= 12 && distanceCm <= 16;
  bool get isTiltOptimal => tiltDegrees <= 12;
  bool get isSteadinessOptimal => steadinessStatus == "Good";
  bool get isSweetSpot => isDistanceOptimal && isTiltOptimal && isSteadinessOptimal;
  bool get isReadyToCapture => isSweetSpot && !isCoolingDown && !isCapturing && uploadErrorMsg == null;

  @override
  void initState() {
    super.initState();
    // Only animate if not in headless unit test or dispose gracefully
    _simulatedCameraController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 4),
    );
    _simulatedCameraController?.repeat(reverse: true);

    _startSession();

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _updateViewfinderRect();
    });
  }

  void _updateViewfinderRect() {
    final renderBox = _viewfinderKey.currentContext?.findRenderObject() as RenderBox?;
    if (renderBox != null && renderBox.hasSize && mounted) {
      final size = renderBox.size;
      final offset = renderBox.localToGlobal(Offset.zero);
      final newRect = offset & size;
      if (_viewfinderRect != newRect) {
        setState(() {
          _viewfinderRect = newRect;
        });
      }
    }
  }

  Future<void> _startSession() async {
    final bool lidar = await CaptureChannel.isLiDARAvailable();
    final bool cam = await CaptureChannel.isCameraAvailable();
    final bool started = await CaptureChannel.startSession();

    if (mounted) {
      setState(() {
        isLiDAROn = lidar;
        hasLiveCamera = !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS && cam && started;
      });
    }

    // Telemetry polling: Live telemetry on iOS, simulated handheld fluctuations in mock mode
    _telemetryTimer = Timer.periodic(const Duration(milliseconds: 400), (_) async {
      if (!mounted) return;

      if (hasLiveCamera) {
        final telemetry = await CaptureChannel.getLiveTelemetry();
        if (mounted) {
          setState(() {
            distanceCm = telemetry['distanceCm'] ?? 14;
            tiltDegrees = telemetry['tiltDegrees'] ?? 0;
            pitchDeg = telemetry['pitch'] ?? 0;
            rollDeg = telemetry['roll'] ?? 0;
            isLeveled = telemetry['isLeveled'] ?? (tiltDegrees <= 12);
            focusStatus = telemetry['focus'] ?? "Locked";
            steadinessStatus = telemetry['steadiness'] ?? "Good";
            isLiDAROn = telemetry['isLiDARActive'] ?? true;
          });
          _checkAutoCapture();
        }
      } else {
        // Natural handheld slight fluctuation around optimal distance
        setState(() {
          distanceCm = 13 + Random().nextInt(3); // 13, 14, or 15 cm
          tiltDegrees = Random().nextInt(5); // 0..4 degrees
          pitchDeg = Random().nextInt(4) - 2;
          rollDeg = Random().nextInt(4) - 2;
          isLeveled = true;
          steadinessStatus = "Good";
          focusStatus = "Locked";
        });
        _checkAutoCapture();
      }
    });
  }

  void _checkAutoCapture() {
    if (!mounted) return;
    if (isReadyToCapture) {
      if (_countdownTimer == null) {
        _countdownElapsedMs = 0;
        _countdownTimer = Timer.periodic(const Duration(milliseconds: 50), (timer) {
          if (!mounted) {
            timer.cancel();
            return;
          }
          if (!isReadyToCapture) {
            _cancelCountdown();
            return;
          }
          _countdownElapsedMs += 50;
          setState(() {
            countdownProgress = (_countdownElapsedMs / countdownDurationMs).clamp(0.0, 1.0);
          });

          // Heartbeat haptic ticks at 250ms, 500ms, 750ms
          if (_countdownElapsedMs == 250 || _countdownElapsedMs == 500 || _countdownElapsedMs == 750) {
            HapticFeedback.selectionClick();
          }

          if (_countdownElapsedMs >= countdownDurationMs) {
            _cancelCountdown();
            _performCapture();
          }
        });
      }
    } else {
      _cancelCountdown();
    }
  }

  void _cancelCountdown() {
    _countdownTimer?.cancel();
    _countdownTimer = null;
    _countdownElapsedMs = 0;
    if (countdownProgress != 0.0 && mounted) {
      setState(() {
        countdownProgress = 0.0;
      });
    }
  }

  @override
  void dispose() {
    _telemetryTimer?.cancel();
    _countdownTimer?.cancel();
    _cooldownTimer?.cancel();
    _simulatedCameraController?.dispose();
    CaptureChannel.stopSession();
    super.dispose();
  }

  Future<String> _uploadWithRetry(Map<String, dynamic> cap) async {
    int attempt = 0;
    while (true) {
      try {
        final capId = await apiClient.uploadCapture(
          photoBytes: cap['photoBytes'],
          depthBytes: cap['depthBytes'],
          intrinsics: cap['intrinsics'],
          metadata: {
            ...Map<String, dynamic>.from(cap['telemetry'] ?? {}),
            'pointIndex': currentPoint,
            'spatialName': spatialPointNames[currentPoint],
          },
        );
        return capId;
      } catch (e) {
        attempt++;
        if (attempt >= 3) {
          rethrow;
        }
        await Future.delayed(Duration(milliseconds: 300 * (1 << attempt)));
      }
    }
  }

  Future<void> _performCapture() async {
    if (isCapturing) return;
    _cancelCountdown();

    HapticFeedback.mediumImpact();
    setState(() {
      isCapturing = true;
      isFlashing = true;
      uploadErrorMsg = null;
    });

    Future.delayed(const Duration(milliseconds: 120), () {
      if (mounted) {
        setState(() => isFlashing = false);
      }
    });

    try {
      final cap = await CaptureChannel.capturePoint(currentPoint);
      final capId = await _uploadWithRetry(cap);
      _captureIds.add(capId);

      if (currentPoint < totalPoints) {
        setState(() {
          currentPoint++;
          isCapturing = false;
          isCoolingDown = true;
        });

        // 1.5s transition cooldown before arming auto-capture again
        _cooldownTimer?.cancel();
        _cooldownTimer = Timer(const Duration(milliseconds: cooldownDurationMs), () {
          if (mounted) {
            setState(() {
              isCoolingDown = false;
            });
            _checkAutoCapture();
          }
        });
      } else {
        // Completed all 8 points: verify level 2 with multi-point capture IDs
        walletService.recordSignature("recordVerification (LiDAR surface scan)");
        final result = await apiClient.verifyLevel2(
          tokenId: widget.artwork.tokenId,
          captureIds: _captureIds,
        );

        if (mounted) {
          Navigator.of(context).pushReplacement(
            MaterialPageRoute(
              builder: (_) => ResultScreen(
                artwork: widget.artwork,
                result: result,
              ),
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          isCapturing = false;
          uploadErrorMsg = "Upload failed: Network timeout. Tap to retry.";
        });
      }
    }
  }

  void _onRetakePreviousPoint() {
    if (currentPoint <= 1 || isCapturing) return;
    _cancelCountdown();
    _cooldownTimer?.cancel();

    setState(() {
      if (_captureIds.isNotEmpty) {
        _captureIds.removeLast();
      }
      currentPoint--;
      isCoolingDown = false;
      uploadErrorMsg = null;
    });
    _checkAutoCapture();
  }

  Future<void> _onShutterTap() async {
    if (isCapturing) return;

    if (!isSweetSpot) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            distanceCm < 12
                ? "Too close: Move camera back to 12-16 cm."
                : (distanceCm > 16
                    ? "Too far: Move camera closer (12-16 cm)."
                    : (!isTiltOptimal
                        ? "Tilt camera flat to artwork surface."
                        : "Hold steady until focus locks.")),
          ),
          duration: const Duration(milliseconds: 1200),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }

    _performCapture();
  }

  @override
  Widget build(BuildContext context) {
    WidgetsBinding.instance.addPostFrameCallback((_) => _updateViewfinderRect());

    return Scaffold(
      backgroundColor: const Color(0xFF131427),
      body: LayoutBuilder(
        builder: (context, constraints) {
          final isCompact = constraints.maxHeight < 720;
          final double viewfinderSize = isCompact
              ? min(280.0, constraints.maxHeight * 0.32)
              : 280.0;

          return Stack(
            fit: StackFit.expand,
            children: [
              // 1. Live Camera feed or Simulated Macro Weave
              if (hasLiveCamera)
                const UiKitView(
                  viewType: CaptureChannel.arCameraViewType,
                  creationParamsCodec: StandardMessageCodec(),
                )
              else
                AnimatedBuilder(
                  animation: _simulatedCameraController ?? const AlwaysStoppedAnimation(0.0),
                  builder: (context, child) {
                    return SimulatedCameraView(
                      animationValue: _simulatedCameraController?.value ?? 0.0,
                    );
                  },
                ),

              // 2. Dimming scrim overlay with transparent cutout for viewfinder
              Positioned.fill(
                child: IgnorePointer(
                  child: CustomPaint(
                    painter: ViewfinderScrimPainter(cutoutRect: _viewfinderRect),
                  ),
                ),
              ),

              // 3. Ambient artistic accents (bottom corners)
              Positioned(
                bottom: -90,
                left: -50,
                child: IgnorePointer(
                  child: Container(
                    width: 200,
                    height: 200,
                    decoration: BoxDecoration(
                      color: AppTheme.bubbleCoral.withOpacity(0.35),
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
              ),
              Positioned(
                bottom: -80,
                right: -60,
                child: IgnorePointer(
                  child: Container(
                    width: 180,
                    height: 180,
                    decoration: BoxDecoration(
                      color: AppTheme.bubbleBlue.withOpacity(0.35),
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
              ),

              // 4. Foreground HUD & Interactive Controls
              SafeArea(
                child: Column(
                  children: [
                    // Top Bar: Cancel + Point Tracker + Retake Action
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          GestureDetector(
                            onTap: () => Navigator.of(context).pop(),
                            child: Text(
                              "Cancel",
                              style: GoogleFonts.inter(
                                fontSize: 16,
                                fontWeight: FontWeight.w600,
                                color: Colors.white,
                              ),
                            ),
                          ),
                          Text(
                            "Point $currentPoint of $totalPoints",
                            style: GoogleFonts.inter(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                              color: Colors.white.withOpacity(0.9),
                            ),
                          ),
                          if (currentPoint > 1)
                            GestureDetector(
                              key: const Key('retake_button'),
                              onTap: _onRetakePreviousPoint,
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                decoration: BoxDecoration(
                                  color: const Color(0xFF334155).withOpacity(0.85),
                                  borderRadius: BorderRadius.circular(12),
                                  border: Border.all(color: Colors.white24, width: 0.8),
                                ),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    const Icon(Icons.undo_rounded, size: 13, color: Colors.white70),
                                    const SizedBox(width: 4),
                                    Text(
                                      "Retake Pt ${currentPoint - 1}",
                                      style: GoogleFonts.inter(
                                        fontSize: 11,
                                        fontWeight: FontWeight.w600,
                                        color: Colors.white,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            )
                          else
                            const SizedBox(width: 50),
                        ],
                      ),
                    ),

                    // Segmented 8-dash Progress Bar
                    Padding(
                      padding: EdgeInsets.symmetric(
                        horizontal: 20,
                        vertical: isCompact ? 4 : 8,
                      ),
                      child: Row(
                        children: List.generate(totalPoints, (index) {
                          final isCompleted = index < currentPoint - 1;
                          final isCurrent = index == currentPoint - 1;
                          return Expanded(
                            child: Container(
                              height: 4,
                              margin: const EdgeInsets.symmetric(horizontal: 2),
                              decoration: BoxDecoration(
                                color: isCurrent
                                    ? AppTheme.bubbleYellow
                                    : (isCompleted
                                        ? const Color(0xFF4ADE80)
                                        : const Color(0xFF2C2E46)),
                                borderRadius: BorderRadius.circular(2),
                              ),
                            ),
                          );
                        }),
                      ),
                    ),

                    // Spatial Guidance Badge: Point location & LiDAR badge
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          // LiDAR Depth Status Badge
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
                            decoration: BoxDecoration(
                              color: Colors.black.withOpacity(0.4),
                              borderRadius: BorderRadius.circular(20),
                              border: Border.all(
                                color: AppTheme.bubbleYellow.withOpacity(0.7),
                                width: 1.2,
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Container(
                                  width: 7,
                                  height: 7,
                                  decoration: BoxDecoration(
                                    color: isLiDAROn ? const Color(0xFF4ADE80) : AppTheme.bubbleYellow,
                                    shape: BoxShape.circle,
                                  ),
                                ),
                                const SizedBox(width: 7),
                                Text(
                                  isLiDAROn ? "LiDAR depth ON" : "Camera Surface ON",
                                  style: GoogleFonts.inter(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w700,
                                    color: AppTheme.bubbleYellow,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 10),

                          // Active Spatial Point Name Badge
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
                            decoration: BoxDecoration(
                              color: const Color(0xFF1E293B).withOpacity(0.85),
                              borderRadius: BorderRadius.circular(20),
                              border: Border.all(
                                color: Colors.white.withOpacity(0.2),
                                width: 1.0,
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const Icon(
                                  Icons.place_rounded,
                                  size: 14,
                                  color: Color(0xFF60A5FA),
                                ),
                                const SizedBox(width: 4),
                                Text(
                                  spatialPointNames[currentPoint] ?? "Target",
                                  style: GoogleFonts.inter(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w600,
                                    color: Colors.white,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),

                    const Spacer(flex: 1),

                    // Center Viewfinder with Grid & Target Reticle + Canvas Mini-Map
                    Center(
                      child: Container(
                        key: _viewfinderKey,
                        width: viewfinderSize,
                        height: viewfinderSize,
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(
                            color: isSweetSpot
                                ? const Color(0xFF4ADE80).withOpacity(0.6)
                                : Colors.white.withOpacity(0.2),
                            width: isSweetSpot ? 2.0 : 1.0,
                          ),
                        ),
                        child: Stack(
                          children: [
                            // Reticle Grid lines & Corner brackets
                            CustomPaint(
                              size: Size(viewfinderSize, viewfinderSize),
                              painter: GridReticlePainter(isLocked: isSweetSpot),
                            ),

                            // Center Target Reticle with Countdown Progress & Leveling Bubble
                            Center(
                              child: SizedBox(
                                width: 56,
                                height: 56,
                                child: CustomPaint(
                                  painter: CountdownReticlePainter(
                                    progress: countdownProgress,
                                    isOptimal: isSweetSpot,
                                    tiltOffsetX: rollDeg.toDouble() * 1.2,
                                    tiltOffsetY: pitchDeg.toDouble() * 1.2,
                                  ),
                                ),
                              ),
                            ),

                            // Canvas Spatial Grid Mini-Map (top-right overlay inside viewfinder)
                            Positioned(
                              top: 10,
                              right: 10,
                              child: CanvasMiniMap(activePoint: currentPoint),
                            ),
                          ],
                        ),
                      ),
                    ),

                    const Spacer(flex: 1),

                    // Telemetry HUD Container
                    Container(
                      margin: const EdgeInsets.symmetric(horizontal: 20),
                      padding: EdgeInsets.symmetric(
                        vertical: isCompact ? 10 : 12,
                        horizontal: 16,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1C1E38).withOpacity(0.92),
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(
                          color: isSweetSpot
                              ? const Color(0xFF4ADE80).withOpacity(0.3)
                              : Colors.white.withOpacity(0.10),
                        ),
                      ),
                      child: Row(
                        children: [
                          _buildTelemetryColumn(
                            "Distance",
                            "$distanceCm cm",
                            isDistanceOptimal
                                ? const Color(0xFF4ADE80)
                                : AppTheme.bubbleYellow,
                          ),
                          _buildDivider(),
                          _buildTelemetryColumn(
                            "Tilt",
                            "$tiltDegrees°",
                            isTiltOptimal
                                ? const Color(0xFF4ADE80)
                                : AppTheme.bubbleYellow,
                          ),
                          _buildDivider(),
                          _buildTelemetryColumn(
                            "Steadiness",
                            steadinessStatus,
                            isSteadinessOptimal ? const Color(0xFF4ADE80) : AppTheme.bubbleYellow,
                          ),
                        ],
                      ),
                    ),

                    SizedBox(height: isCompact ? 8 : 14),

                    // Instruction Prompt or Error Banner
                    if (uploadErrorMsg != null)
                      Container(
                        key: const Key('upload_error_banner'),
                        margin: const EdgeInsets.symmetric(horizontal: 20),
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                        decoration: BoxDecoration(
                          color: const Color(0xFFEF4444).withOpacity(0.9),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.error_outline, color: Colors.white, size: 16),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                uploadErrorMsg!,
                                style: GoogleFonts.inter(
                                  fontSize: 12,
                                  fontWeight: FontWeight.w600,
                                  color: Colors.white,
                                ),
                              ),
                            ),
                            GestureDetector(
                              key: const Key('retry_upload_button'),
                              onTap: () {
                                setState(() => uploadErrorMsg = null);
                                _performCapture();
                              },
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                decoration: BoxDecoration(
                                  color: Colors.white,
                                  borderRadius: BorderRadius.circular(6),
                                ),
                                child: Text(
                                  "Retry",
                                  style: GoogleFonts.inter(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w700,
                                    color: const Color(0xFFEF4444),
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                      )
                    else
                      Text(
                        isCoolingDown
                            ? "Point ${currentPoint - 1} captured! Move to ${spatialPointNames[currentPoint]}..."
                            : (countdownProgress > 0
                                ? "Holding steady... Capturing (${(countdownProgress * 100).toInt()}%)"
                                : (distanceCm < 12
                                    ? "Too close ($distanceCm cm) · Move back to 12-16 cm."
                                    : (distanceCm > 16
                                        ? "Too far ($distanceCm cm) · Move closer to 12-16 cm."
                                        : (!isTiltOptimal
                                            ? "Tilt phone flat to surface ($tiltDegrees° / max 12°)"
                                            : (steadinessStatus != "Good"
                                                ? "Hold steady on ${spatialPointNames[currentPoint]}..."
                                                : "Steady on ${spatialPointNames[currentPoint]}. Ready to capture."))))),
                        style: GoogleFonts.inter(
                          fontSize: 13,
                          fontWeight: FontWeight.w500,
                          color: isSweetSpot
                              ? const Color(0xFF4ADE80)
                              : Colors.white.withOpacity(0.85),
                        ),
                      ),

                    SizedBox(height: isCompact ? 12 : 18),

                    // Large Shutter Button (Quality Gated with Auto/Manual Support)
                    GestureDetector(
                      key: const Key('shutter_button'),
                      onTap: _onShutterTap,
                      child: AnimatedOpacity(
                        duration: const Duration(milliseconds: 200),
                        opacity: isReadyToCapture ? 1.0 : 0.65,
                        child: Container(
                          width: isCompact ? 66 : 76,
                          height: isCompact ? 66 : 76,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: isReadyToCapture ? const Color(0xFF4ADE80) : Colors.white70,
                              width: 3.5,
                            ),
                          ),
                          padding: const EdgeInsets.all(5),
                          child: Container(
                            decoration: BoxDecoration(
                              color: isReadyToCapture
                                  ? AppTheme.bubbleYellow
                                  : const Color(0xFF94A3B8),
                              shape: BoxShape.circle,
                            ),
                            child: isCapturing
                                ? const Center(
                                    child: SizedBox(
                                      width: 24,
                                      height: 24,
                                      child: CircularProgressIndicator(
                                        color: Color(0xFF131427),
                                        strokeWidth: 3,
                                      ),
                                    ),
                                  )
                                : (countdownProgress > 0
                                    ? Center(
                                        child: Text(
                                          "${(countdownProgress * 100).toInt()}%",
                                          style: GoogleFonts.inter(
                                            fontSize: 11,
                                            fontWeight: FontWeight.w800,
                                            color: const Color(0xFF131427),
                                          ),
                                        ),
                                      )
                                    : null),
                          ),
                        ),
                      ),
                    ),

                    SizedBox(height: isCompact ? 16 : 30),
                  ],
                ),
              ),

              // 5. Camera Shutter Flash Overlay
              Positioned.fill(
                child: IgnorePointer(
                  child: AnimatedOpacity(
                    opacity: isFlashing ? 0.9 : 0.0,
                    duration: const Duration(milliseconds: 100),
                    child: Container(
                      color: Colors.white,
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildTelemetryColumn(String label, String value, Color valueColor) {
    return Expanded(
      child: Column(
        children: [
          Text(
            label,
            style: GoogleFonts.inter(
              fontSize: 12,
              color: Colors.white.withOpacity(0.55),
            ),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            style: GoogleFonts.inter(
              fontSize: 15,
              fontWeight: FontWeight.w700,
              color: valueColor,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDivider() {
    return Container(
      width: 1,
      height: 28,
      color: Colors.white.withOpacity(0.12),
    );
  }
}

class CanvasMiniMap extends StatelessWidget {
  final int activePoint;

  const CanvasMiniMap({super.key, required this.activePoint});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 58,
      height: 58,
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: const Color(0xCC0F172A),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white24, width: 0.8),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _buildDot(1),
              _buildDot(2),
              _buildDot(3),
            ],
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _buildDot(4),
              const SizedBox(width: 8, height: 8), // Center quadrant empty
              _buildDot(5),
            ],
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _buildDot(6),
              _buildDot(7),
              _buildDot(8),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildDot(int point) {
    final bool isActive = point == activePoint;
    final bool isDone = point < activePoint;

    return Container(
      width: 10,
      height: 10,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: isActive
            ? AppTheme.bubbleYellow
            : (isDone ? const Color(0xFF4ADE80) : const Color(0xFF334155)),
        border: isActive
            ? Border.all(color: Colors.white, width: 1.5)
            : null,
      ),
    );
  }
}

class ViewfinderScrimPainter extends CustomPainter {
  final Rect? cutoutRect;

  ViewfinderScrimPainter({this.cutoutRect});

  @override
  void paint(Canvas canvas, Size size) {
    final fullScreenRect = Rect.fromLTWH(0, 0, size.width, size.height);
    final backgroundPath = Path()..addRect(fullScreenRect);

    if (cutoutRect != null) {
      final cutoutPath = Path()
        ..addRRect(RRect.fromRectAndRadius(cutoutRect!, const Radius.circular(16)));
      final scrimPath = Path.combine(PathOperation.difference, backgroundPath, cutoutPath);
      final paint = Paint()
        ..color = const Color(0xB8101224) // Clean dark navy scrim outside viewfinder
        ..style = PaintingStyle.fill;
      canvas.drawPath(scrimPath, paint);
    } else {
      final paint = Paint()
        ..color = const Color(0xB8101224)
        ..style = PaintingStyle.fill;
      canvas.drawRect(fullScreenRect, paint);
    }
  }

  @override
  bool shouldRepaint(covariant ViewfinderScrimPainter oldDelegate) =>
      oldDelegate.cutoutRect != cutoutRect;
}

class SimulatedCameraView extends StatelessWidget {
  final double animationValue;

  const SimulatedCameraView({super.key, required this.animationValue});

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size.infinite,
      painter: CanvasWeaveSimulationPainter(animationValue: animationValue),
    );
  }
}

class CanvasWeaveSimulationPainter extends CustomPainter {
  final double animationValue;

  CanvasWeaveSimulationPainter({required this.animationValue});

  @override
  void paint(Canvas canvas, Size size) {
    final bgPaint = Paint()..color = const Color(0xFF222438);
    canvas.drawRect(Rect.fromLTWH(0, 0, size.width, size.height), bgPaint);

    final double driftX = sin(animationValue * 2 * pi) * 5.0;
    final double driftY = cos(animationValue * 2 * pi) * 3.5;

    const double step = 15.0;
    final warpPaint = Paint()
      ..color = const Color(0xFF2B2E49)
      ..strokeWidth = 5.5
      ..strokeCap = StrokeCap.round;

    final weftPaint = Paint()
      ..color = const Color(0xFF353856)
      ..strokeWidth = 5.0
      ..strokeCap = StrokeCap.round;

    final microFiberPaint = Paint()
      ..color = const Color(0xFF6B729E).withOpacity(0.35)
      ..strokeWidth = 1.2;

    canvas.save();
    canvas.translate(driftX, driftY);

    for (double x = -step; x < size.width + step * 2; x += step) {
      canvas.drawLine(Offset(x, -step), Offset(x, size.height + step), warpPaint);
    }

    for (double y = -step; y < size.height + step * 2; y += step) {
      canvas.drawLine(Offset(-step, y), Offset(size.width + step, y), weftPaint);
    }

    for (double x = -step; x < size.width + step * 2; x += step * 2) {
      for (double y = -step; y < size.height + step * 2; y += step * 2) {
        final double jitter = sin(x * 12.3 + y * 45.6) * 1.5;
        canvas.drawCircle(Offset(x + step / 2 + jitter, y + step / 2), 1.6, microFiberPaint);
      }
    }

    canvas.restore();

    final spotlightPaint = Paint()
      ..shader = RadialGradient(
        center: Alignment(driftX / 120, driftY / 120),
        radius: 0.85,
        colors: [
          Colors.transparent,
          const Color(0xFF131427).withOpacity(0.55),
          const Color(0xFF131427).withOpacity(0.92),
        ],
        stops: const [0.3, 0.7, 1.0],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height));

    canvas.drawRect(Rect.fromLTWH(0, 0, size.width, size.height), spotlightPaint);
  }

  @override
  bool shouldRepaint(covariant CanvasWeaveSimulationPainter oldDelegate) =>
      oldDelegate.animationValue != animationValue;
}

class GridReticlePainter extends CustomPainter {
  final bool isLocked;

  GridReticlePainter({this.isLocked = false});

  @override
  void paint(Canvas canvas, Size size) {
    final linePaint = Paint()
      ..color = Colors.white.withOpacity(0.08)
      ..strokeWidth = 1.0;

    // Grid lines (3x3)
    canvas.drawLine(Offset(size.width / 3, 0), Offset(size.width / 3, size.height), linePaint);
    canvas.drawLine(Offset(size.width * 2 / 3, 0), Offset(size.width * 2 / 3, size.height), linePaint);
    canvas.drawLine(Offset(0, size.height / 3), Offset(size.width, size.height / 3), linePaint);
    canvas.drawLine(Offset(0, size.height * 2 / 3), Offset(size.width, size.height * 2 / 3), linePaint);

    // Corner brackets
    final bracketPaint = Paint()
      ..color = isLocked ? const Color(0xFF4ADE80) : AppTheme.bubbleYellow
      ..strokeWidth = 2.5
      ..style = PaintingStyle.stroke;

    const corner = 28.0;
    const len = 34.0;

    // Top Left
    canvas.drawLine(const Offset(corner, corner), const Offset(corner + len, corner), bracketPaint);
    canvas.drawLine(const Offset(corner, corner), const Offset(corner, corner + len), bracketPaint);

    // Top Right
    canvas.drawLine(Offset(size.width - corner, corner), Offset(size.width - corner - len, corner), bracketPaint);
    canvas.drawLine(Offset(size.width - corner, corner), Offset(size.width - corner, corner + len), bracketPaint);

    // Bottom Left
    canvas.drawLine(Offset(corner, size.height - corner), Offset(corner + len, size.height - corner), bracketPaint);
    canvas.drawLine(Offset(corner, size.height - corner), Offset(corner, size.height - corner - len), bracketPaint);

    // Bottom Right
    canvas.drawLine(Offset(size.width - corner, size.height - corner), Offset(size.width - corner - len, size.height - corner), bracketPaint);
    canvas.drawLine(Offset(size.width - corner, size.height - corner), Offset(size.width - corner, corner + len), bracketPaint);
  }

  @override
  bool shouldRepaint(covariant GridReticlePainter oldDelegate) =>
      oldDelegate.isLocked != isLocked;
}

class CountdownReticlePainter extends CustomPainter {
  final double progress;
  final bool isOptimal;
  final double tiltOffsetX;
  final double tiltOffsetY;

  CountdownReticlePainter({
    required this.progress,
    required this.isOptimal,
    this.tiltOffsetX = 0.0,
    this.tiltOffsetY = 0.0,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2;

    // Outer target circle
    final outerPaint = Paint()
      ..color = isOptimal ? const Color(0xFF4ADE80) : Colors.white.withOpacity(0.85)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0;
    canvas.drawCircle(center, radius - 4, outerPaint);

    // Countdown progress arc (fills from -90 degrees)
    if (progress > 0.0) {
      final countdownPaint = Paint()
        ..color = const Color(0xFF4ADE80)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 4.5
        ..strokeCap = StrokeCap.round;

      final rect = Rect.fromCircle(center: center, radius: radius);
      canvas.drawArc(rect, -pi / 2, 2 * pi * progress, false, countdownPaint);
    }

    // Directional leveling bubble (offset by pitch/roll)
    final bubbleOffset = Offset(
      center.dx + tiltOffsetX.clamp(-14.0, 14.0),
      center.dy + tiltOffsetY.clamp(-14.0, 14.0),
    );

    final bubblePaint = Paint()
      ..color = isOptimal ? const Color(0xFF4ADE80) : AppTheme.bubbleYellow
      ..style = PaintingStyle.fill;
    canvas.drawCircle(bubbleOffset, 4.5, bubblePaint);

    // Bullseye center reticle
    final bullseyePaint = Paint()
      ..color = Colors.white.withOpacity(0.35)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.0;
    canvas.drawCircle(center, 7, bullseyePaint);
  }

  @override
  bool shouldRepaint(covariant CountdownReticlePainter oldDelegate) =>
      oldDelegate.progress != progress ||
      oldDelegate.isOptimal != isOptimal ||
      oldDelegate.tiltOffsetX != tiltOffsetX ||
      oldDelegate.tiltOffsetY != tiltOffsetY;
}
