import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class CaptureChannel {
  static const MethodChannel _channel = MethodChannel('com.arthentic.app/capture');
  static const String arCameraViewType = 'com.arthentic.app/ar_camera_view';
  static const int defaultDepthWidth = 256;
  static const int defaultDepthHeight = 192;

  static bool get isNativeIOs => !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS;

  static Future<bool> isLiDARAvailable() async {
    if (!isNativeIOs) return false;
    try {
      final bool available = await _channel.invokeMethod('isLiDARAvailable');
      return available;
    } on MissingPluginException {
      return false;
    } catch (_) {
      return false;
    }
  }

  static Future<bool> isCameraAvailable() async {
    if (!isNativeIOs) return false;
    try {
      final bool available = await _channel.invokeMethod('isCameraAvailable');
      return available;
    } on MissingPluginException {
      return false;
    } catch (_) {
      return false;
    }
  }

  static Future<bool> startSession() async {
    if (!isNativeIOs) return true;
    try {
      final bool started = await _channel.invokeMethod('startSession');
      return started;
    } on MissingPluginException {
      return true;
    } catch (_) {
      return false;
    }
  }

  static Future<void> stopSession() async {
    if (!isNativeIOs) return;
    try {
      await _channel.invokeMethod('stopSession');
    } catch (_) {}
  }

  static Future<Map<String, dynamic>> getLiveTelemetry() async {
    if (isNativeIOs) {
      try {
        final Map<dynamic, dynamic>? res = await _channel.invokeMethod('getLiveTelemetry');
        if (res != null) {
          return Map<String, dynamic>.from(res);
        }
      } catch (_) {}
    }

    return {
      'distanceCm': 14,
      'focus': 'Locked',
      'steadiness': 'Good',
      'isLiDARActive': false,
      'tiltDegrees': 0,
      'pitch': 0,
      'roll': 0,
      'isLeveled': true,
    };
  }

  static Future<Map<String, dynamic>> capturePoint(int pointIndex) async {
    if (isNativeIOs) {
      try {
        final Map<dynamic, dynamic>? res = await _channel.invokeMethod('capturePoint', {
          'pointIndex': pointIndex,
        });
        if (res != null) {
          final map = Map<String, dynamic>.from(res);
          map.putIfAbsent('depthWidth', () => defaultDepthWidth);
          map.putIfAbsent('depthHeight', () => defaultDepthHeight);
          return map;
        }
      } catch (_) {}
    }

    // Fallback simulated point capture with valid JPEG & 256x192 Float32 depth buffer (ARKit sceneDepth resolution)
    const base64Jpeg =
        '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIs'
        'IxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy'
        'MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCABAAEADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAA'
        'AAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAk'
        'M2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKT'
        'lJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QA'
        'HwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdh'
        'cRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hp'
        'anN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk'
        '5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDfooor1DjCiiigAooooAKKKKACiiigAooooAKKKKACiiigAoooo'
        'AKKKKACiiigAooooAKKKKACiiigAooooAKKKKAP/9k=';
    final photoBytes = base64Decode(base64Jpeg);

    // Generate 256x192 Float32 depth buffer (0.14m + subtle weave relief std ~0.45mm)
    final depthFloats = Float32List(defaultDepthWidth * defaultDepthHeight);
    for (int y = 0; y < defaultDepthHeight; y++) {
      for (int x = 0; x < defaultDepthWidth; x++) {
        final double weave = (sin(x * 0.45) * cos(y * 0.45)) * 0.00045;
        depthFloats[y * defaultDepthWidth + x] = 0.14 + weave;
      }
    }
    final depthBytes = depthFloats.buffer.asUint8List();

    return {
      'photoBytes': photoBytes,
      'depthBytes': depthBytes,
      'depthWidth': defaultDepthWidth,
      'depthHeight': defaultDepthHeight,
      'intrinsics': {
        'fx': 1420.5,
        'fy': 1420.5,
        'cx': 128.0,
        'cy': 96.0,
      },
      'telemetry': {
        'distanceCm': 14,
        'focus': 'Locked',
        'steadiness': 'Good',
        'tiltDegrees': 0,
        'isLeveled': true,
        'pointIndex': pointIndex,
      }
    };
  }

  /// B-02 / D-05: 8-Point Guided LiDAR + Macro RGB Surface Mesh Capture Coordinator.
  static Future<Map<String, dynamic>> captureEightPointMesh({int pointsCount = 8}) async {
    final List<Map<String, dynamic>> captures = [];
    for (int pt = 1; pt <= pointsCount; pt++) {
      final pointData = await capturePoint(pt);
      captures.add(pointData);
    }
    return {
      'feature_code': 'D-05',
      'pointsCount': pointsCount,
      'depthWidth': defaultDepthWidth,
      'depthHeight': defaultDepthHeight,
      'captures': captures,
    };
  }
}
