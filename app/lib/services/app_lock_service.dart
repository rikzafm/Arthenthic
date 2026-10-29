import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:local_auth/local_auth.dart';
import 'package:local_auth_darwin/local_auth_darwin.dart';

typedef AuthenticateCallback = Future<bool> Function({
  required String localizedReason,
  bool biometricOnly,
});

enum BiometricKind {
  faceId,
  touchId,
  genericBiometric,
  none,
}

class AppLockService extends ChangeNotifier {
  final LocalAuthentication _auth;
  AuthenticateCallback? customAuthenticate;
  Future<List<BiometricType>> Function()? customGetAvailableBiometrics;

  bool _isLocked = false;
  bool _isGuest = true;
  int gracePeriodSeconds = 30; // Default 30s grace period
  DateTime? _lastBackgroundedTime;
  bool _isAuthenticating = false;

  AppLockService({
    LocalAuthentication? auth,
    AuthenticateCallback? customAuthenticate,
    Future<List<BiometricType>> Function()? customGetAvailableBiometrics,
  })  : _auth = auth ?? LocalAuthentication(),
        customAuthenticate = customAuthenticate,
        customGetAvailableBiometrics = customGetAvailableBiometrics;

  bool get isLocked => _isLocked;
  bool get isGuest => _isGuest;
  bool get isAuthenticating => _isAuthenticating;
  DateTime? get lastBackgroundedTime => _lastBackgroundedTime;

  void setGracePeriod(int seconds) {
    gracePeriodSeconds = seconds;
    notifyListeners();
  }

  set isGuest(bool value) {
    _isGuest = value;
    if (_isGuest) {
      _isLocked = false;
    }
    notifyListeners();
  }

  void lock() {
    if (!_isGuest) {
      _isLocked = true;
      notifyListeners();
    }
  }

  void unlock() {
    _isLocked = false;
    _lastBackgroundedTime = null;
    notifyListeners();
  }

  static const String _defaultPin = '1234';
  static const String _storageKeyPin = 'arthentic_fallback_pin';
  final FlutterSecureStorage _storage = const FlutterSecureStorage();

  Future<String> getFallbackPin() async {
    try {
      final pin = await _storage.read(key: _storageKeyPin);
      if (pin != null && pin.isNotEmpty) {
        return pin;
      }
    } catch (_) {}
    return _defaultPin;
  }

  Future<bool> setFallbackPin(String newPin) async {
    if (newPin.length == 4 && int.tryParse(newPin) != null) {
      try {
        await _storage.write(key: _storageKeyPin, value: newPin);
        return true;
      } catch (_) {}
    }
    return false;
  }

  Future<bool> verifyFallbackPin(String enteredPin) async {
    final expectedPin = await getFallbackPin();
    if (enteredPin == expectedPin) {
      unlock();
      return true;
    }
    return false;
  }

  void devSimulateUnlock() {
    unlock();
  }

  Future<bool> isDeviceSecure() async {
    try {
      final supported = await _auth.isDeviceSupported();
      final canCheck = await _auth.canCheckBiometrics;
      return supported || canCheck;
    } catch (_) {
      return false;
    }
  }

  Future<List<BiometricType>> getAvailableBiometrics() async {
    try {
      if (customGetAvailableBiometrics != null) {
        return await customGetAvailableBiometrics!();
      }
      return await _auth.getAvailableBiometrics();
    } catch (_) {
      return [];
    }
  }

  Future<BiometricKind> getBiometricKind() async {
    try {
      final biometrics = await getAvailableBiometrics();
      if (biometrics.contains(BiometricType.face)) {
        return BiometricKind.faceId;
      } else if (biometrics.contains(BiometricType.fingerprint)) {
        return BiometricKind.touchId;
      } else if (biometrics.isNotEmpty) {
        return BiometricKind.genericBiometric;
      }
    } catch (_) {}
    return BiometricKind.genericBiometric;
  }

  Future<bool> authenticate({
    String reason = 'Authenticate with Face ID or Touch ID to unlock Arthentic',
    bool biometricOnly = false,
  }) async {
    if (_isAuthenticating) return false;
    _isAuthenticating = true;
    notifyListeners();

    try {
      if (customAuthenticate != null) {
        final result = await customAuthenticate!(
          localizedReason: reason,
          biometricOnly: biometricOnly,
        );
        if (result) {
          unlock();
        }
        return result;
      }

      final authenticated = await _auth.authenticate(
        localizedReason: reason,
        authMessages: const [
          IOSAuthMessages(
            cancelButton: 'Cancel',
            localizedFallbackTitle: 'Use Passcode',
          ),
        ],
        biometricOnly: biometricOnly,
        sensitiveTransaction: true,
        persistAcrossBackgrounding: false,
      );

      if (authenticated) {
        unlock();
      }
      return authenticated;
    } on PlatformException catch (e) {
      debugPrint('Biometric authentication error: ${e.message}');
      return false;
    } finally {
      _isAuthenticating = false;
      notifyListeners();
    }
  }

  void handleAppLifecycle(AppLifecycleState state) {
    if (_isGuest) return;

    if (state == AppLifecycleState.inactive || state == AppLifecycleState.paused) {
      _lastBackgroundedTime ??= DateTime.now();
    } else if (state == AppLifecycleState.resumed) {
      if (_lastBackgroundedTime != null) {
        final elapsed = DateTime.now().difference(_lastBackgroundedTime!).inSeconds;
        if (elapsed >= gracePeriodSeconds) {
          lock();
        }
      }
      _lastBackgroundedTime = null;
    }
  }

  @visibleForTesting
  void setLastBackgroundedTimeForTesting(DateTime time) {
    _lastBackgroundedTime = time;
  }
}

final appLockService = AppLockService();
