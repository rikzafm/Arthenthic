import 'dart:convert';
import 'package:http/http.dart' as http;
import '../core/models.dart';

abstract class NfcService {
  Future<SunParams> readSunTag();
}

class SimulatedNfcService implements NfcService {
  final String serverBaseUrl;
  int _localCounter = 65;

  SimulatedNfcService({this.serverBaseUrl = "http://127.0.0.1:8000"});

  @override
  Future<SunParams> readSunTag() async {
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
}

final nfcService = SimulatedNfcService();

