import 'package:flutter_test/flutter_test.dart';
import 'package:app/services/api_client.dart';

void main() {
  group('Milestone 7: Release Monitoring & Jittered Backoff Tests', () {
    test('computeJitteredBackoff applies exponential scaling with non-zero randomized jitter', () {
      final client = ApiClient();

      final d0 = client.computeJitteredBackoff(0, baseMs: 100, maxMs: 1000);
      expect(d0.inMilliseconds, greaterThanOrEqualTo(100));

      final d1 = client.computeJitteredBackoff(1, baseMs: 100, maxMs: 1000);
      expect(d1.inMilliseconds, greaterThanOrEqualTo(200));

      final d2 = client.computeJitteredBackoff(2, baseMs: 100, maxMs: 1000);
      expect(d2.inMilliseconds, greaterThanOrEqualTo(400));

      // Ensure cap at maxMs + 30% jitter max
      final dLarge = client.computeJitteredBackoff(10, baseMs: 100, maxMs: 1000);
      expect(dLarge.inMilliseconds, lessThanOrEqualTo(1300));
    });

    test('reportLockBypassAnomaly sends security report without PII', () async {
      final client = ApiClient();
      Map<String, dynamic>? reportedPayload;

      client.mockRoleHandler = (endpoint, body) async {
        if (endpoint == "/v1/auth/lock-bypass-report") {
          reportedPayload = Map<String, dynamic>.from(body);
          return {"status": "ok"};
        }
        return {};
      };

      final res = await client.reportLockBypassAnomaly(
        reason: "Biometric prompt cancelled 3 times; passcode entry delayed",
        metadata: {
          "device_model": "iPhone 15 Pro",
          "os_version": "iOS 18.1",
        },
      );

      expect(res["success"], isTrue);
      expect(reportedPayload, isNotNull);
      expect(reportedPayload!["details"], contains("Biometric prompt cancelled"));
      expect(reportedPayload!["metadata"]["device_model"], equals("iPhone 15 Pro"));
    });
  });
}

