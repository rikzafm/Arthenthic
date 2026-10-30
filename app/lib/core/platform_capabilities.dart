import 'package:flutter/foundation.dart' show kIsWeb, defaultTargetPlatform, TargetPlatform;

/// Platform Capability Abstraction (Part IV, Section 5.2).
/// Isolates hardware-dependent APIs (ARKit Pro LiDAR, CoreNFC NTAG 424 DNA)
/// behind clean capability checks, allowing the codebase to compile and run
/// seamlessly on both physical iOS devices and Web / Desktop consoles.
class PlatformCapabilities {
  static bool get isWeb => kIsWeb;
  static bool get isIOS => !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS;
  static bool get isAndroid => !kIsWeb && defaultTargetPlatform == TargetPlatform.android;
  static bool get isDesktop => !kIsWeb && (
    defaultTargetPlatform == TargetPlatform.macOS ||
    defaultTargetPlatform == TargetPlatform.windows ||
    defaultTargetPlatform == TargetPlatform.linux
  );

  /// True only on physical iOS devices with ARKit / Pro LiDAR support (ADR-06)
  static bool get supportsLidarScan => isIOS;

  /// True on iOS devices with CoreNFC NTAG 424 DNA reader/writer support
  static bool get supportsHardwareNfc => isIOS;

  /// True on Desktop/Web layouts (>= 900px width) for Gallery Safe & Admin Consoles
  static bool isDesktopConsole(double screenWidth) => kIsWeb || isDesktop || screenWidth >= 900;
}

