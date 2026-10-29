import 'package:flutter_test/flutter_test.dart';
import 'package:app/services/telemetry_service.dart';

void main() {
  group('TelemetryService - Zero-PII sanitization tests', () {
    late TelemetryService telemetry;

    setUp(() {
      telemetry = TelemetryService();
      telemetry.clear();
      telemetry.enabled = true;
    });

    test('Sanitizes email addresses to obscure identifier while preserving domain', () {
      const raw = 'User collector.specialist@arthentic.io reported an anomaly.';
      final sanitized = telemetry.sanitize(raw);
      expect(sanitized, contains('c***@arthentic.io'));
      expect(sanitized, isNot(contains('collector.specialist')));
    });

    test('Sanitizes JWT access and refresh tokens', () {
      const raw = 'Authorization failed for token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c';
      final sanitized = telemetry.sanitize(raw);
      expect(sanitized, contains('[REDACTED_JWT]'));
      expect(sanitized, isNot(contains('eyJhbGciOiJIUzI1Ni')));
    });

    test('Sanitizes Bearer authorization headers', () {
      const raw = 'Request header: Bearer a8f9bc1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0';
      final sanitized = telemetry.sanitize(raw);
      expect(sanitized, contains('Bearer [REDACTED_TOKEN]'));
      expect(sanitized, isNot(contains('a8f9bc1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0')));
    });

    test('Sanitizes Ethereum private keys and chip secrets', () {
      const raw = 'Key generated: 0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d';
      final sanitized = telemetry.sanitize(raw);
      expect(sanitized, contains('[REDACTED_PRIVATE_KEY]'));
      expect(sanitized, isNot(contains('4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d')));
    });

    test('Masks IPv4 address last octet for subnet-level geolocation without user identification', () {
      const raw = 'Connection established from 192.168.1.144:8000';
      final sanitized = telemetry.sanitize(raw);
      expect(sanitized, contains('192.168.1.0'));
      expect(sanitized, isNot(contains('192.168.1.144')));
    });

    test('Sanitizes nested dictionary payloads containing sensitive keys', () {
      final payload = {
        'event': 'login_failed',
        'email': 'artist@arthentic.io',
        'password': 'SuperSecretPassword123!',
        'metadata': {
          'refresh_token': 'opaque_refresh_token_string',
          'client_ip': '10.0.0.42',
        }
      };

      final sanitized = telemetry.sanitizePayload(payload) as Map<String, dynamic>;
      expect(sanitized['password'], equals('[REDACTED]'));
      expect(sanitized['email'], equals('a***@arthentic.io'));
      expect((sanitized['metadata'] as Map)['refresh_token'], equals('[REDACTED]'));
      expect((sanitized['metadata'] as Map)['client_ip'], equals('10.0.0.0'));
    });

    test('logEvent and recordError buffer non-PII entries', () {
      telemetry.logEvent('auth_screen_viewed', parameters: {
        'account': 'conservator@arthentic.io',
        'session_ip': '172.16.254.1',
      });

      telemetry.recordError(
        Exception('Network failure contacting verifier node at 10.1.2.3'),
        context: {'password_attempt': 'Pass123!'},
      );

      final logs = telemetry.bufferedLogs;
      expect(logs.length, equals(2));
      expect(logs[0]['name'], equals('auth_screen_viewed'));
      expect(logs[0]['parameters']['account'], equals('c***@arthentic.io'));
      expect(logs[0]['parameters']['session_ip'], equals('172.16.254.0'));

      expect(logs[1]['error'], contains('10.1.2.0'));
      expect(logs[1]['context']['password_attempt'], equals('[REDACTED]'));
    });
  });
}

