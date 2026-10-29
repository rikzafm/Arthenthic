import 'dart:convert';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SessionStore {
  final FlutterSecureStorage _storage;

  static const _keyAccessToken = 'auth_access_token';
  static const _keyRefreshToken = 'auth_refresh_token';
  static const _keyUser = 'auth_user_profile';
  static const _keyInstallId = 'auth_install_id';
  static const _keyActiveRole = 'auth_active_role';

  SessionStore({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              iOptions: IOSOptions(
                accessibility: KeychainAccessibility.passcode,
                synchronizable: false,
              ),
              mOptions: MacOsOptions(
                accessibility: KeychainAccessibility.first_unlock,
                usesDataProtectionKeychain: false,
                synchronizable: false,
              ),
            );

  Future<void> saveSession({
    required String accessToken,
    required String refreshToken,
    Map<String, dynamic>? user,
  }) async {
    await _storage.write(key: _keyAccessToken, value: accessToken);
    await _storage.write(key: _keyRefreshToken, value: refreshToken);
    if (user != null) {
      await _storage.write(key: _keyUser, value: jsonEncode(user));
    }
  }

  Future<void> updateTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    await _storage.write(key: _keyAccessToken, value: accessToken);
    await _storage.write(key: _keyRefreshToken, value: refreshToken);
  }

  Future<String?> getAccessToken() async {
    return await _storage.read(key: _keyAccessToken);
  }

  Future<String?> getRefreshToken() async {
    return await _storage.read(key: _keyRefreshToken);
  }

  Future<Map<String, dynamic>?> getUser() async {
    final raw = await _storage.read(key: _keyUser);
    if (raw == null) return null;
    try {
      return jsonDecode(raw) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  Future<bool> hasSession() async {
    final refresh = await getRefreshToken();
    return refresh != null && refresh.isNotEmpty;
  }

  Future<String?> getActiveRole() async {
    return await _storage.read(key: _keyActiveRole);
  }

  Future<void> setActiveRole(String role) async {
    await _storage.write(key: _keyActiveRole, value: role);
  }

  Future<void> clearSession() async {
    await _storage.delete(key: _keyAccessToken);
    await _storage.delete(key: _keyRefreshToken);
    await _storage.delete(key: _keyUser);
    await _storage.delete(key: _keyActiveRole);
  }

  Future<String> getOrCreateInstallId() async {
    var id = await _storage.read(key: _keyInstallId);
    if (id == null || id.isEmpty) {
      id = "inst_${DateTime.now().millisecondsSinceEpoch}_${(1000 + (DateTime.now().microsecond % 9000))}";
      await _storage.write(key: _keyInstallId, value: id);
    }
    return id;
  }
}

final sessionStore = SessionStore();

