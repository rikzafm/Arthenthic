import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import '../core/models.dart';

abstract class NfcService {
  Future<SunParams> readSunTag();
  Future<Map<String, dynamic>> provisionSdmTag({
    required String chipUid,
    required String tokenId,
    String keySlot = '01',
  });
}

class SimulatedNfcService implements NfcService {
  static const MethodChannel _nfcChannel = MethodChannel('com.arthentic.app/nfc');
  final String serverBaseUrl;
  int _localCounter = 65;

  SimulatedNfcService({this.serverBaseUrl = "http://127.0.0.1:8000"});

  static bool get _isNativeIOs => !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS;

  @override
  Future<SunParams> readSunTag() async {
    if (_isNativeIOs) {
      try {
        final Map<dynamic, dynamic>? nativeRes =
            await _nfcChannel.invokeMethod('readSunTag');
        if (nativeRes != null) {
          return SunParams.fromJson(Map<String, dynamic>.from(nativeRes));
        }
      } catch (_) {
        // Fallback to HTTP or offline simulation
      }
    }

    try {
      final uri = Uri.parse("$serverBaseUrl/v1/verify/simulate-sun");
      final response = await http.get(uri).timeout(const Duration(seconds: 3));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return SunParams.fromJson(data);
      }
    } catch (_) {
      // Offline fallback
    }

    _localCounter++;
    return SunParams(
      uid: "04A1B2C3D4E5F6",
      ctr: _localCounter,
      cmac: "A9E38F107B5C2D44",
    );
  }

  @override
  Future<Map<String, dynamic>> provisionSdmTag({
    required String chipUid,
    required String tokenId,
    String keySlot = '01',
  }) async {
    final normUid = chipUid.trim().toUpperCase();
    if (_isNativeIOs) {
      try {
        final Map<dynamic, dynamic>? nativeRes =
            await _nfcChannel.invokeMethod('provisionSdmTag', {
          'chipUid': normUid,
          'tokenId': tokenId,
          'keySlot': keySlot,
        });
        if (nativeRes != null) {
          return Map<String, dynamic>.from(nativeRes);
        }
      } catch (_) {}
    }

    final sdmUrl =
        'https://verify.arthentic.io/?uid=$normUid&ctr=000001&cmac=A9E38F107B5C2D44';
    final hexTail = normUid.padRight(64, '0').substring(0, 64).toLowerCase();
    return {
      'success': true,
      'feature_code': 'B-05',
      'chipUid': normUid,
      'chipIdHash': '0x$hexTail',
      'tokenId': tokenId,
      'keySlot': keySlot,
      'sdmUrlTemplate': sdmUrl,
      'aes128SlotConfigured': true,
    };
  }
}

final nfcService = SimulatedNfcService();
