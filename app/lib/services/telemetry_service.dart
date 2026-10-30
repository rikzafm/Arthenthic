/// Telemetry and Crash Reporting Service for Arthentic Mobile.
/// Enforces zero-PII logging: scrubs emails, passwords, bearer tokens,
/// IP addresses, and private cryptographic keys before transmitting or persisting.
class TelemetryService {
  static final TelemetryService _instance = TelemetryService._internal();
  factory TelemetryService() => _instance;
  TelemetryService._internal();

  final List<Map<String, dynamic>> _buffer = [];
  bool enabled = true;

  List<Map<String, dynamic>> get bufferedLogs => List.unmodifiable(_buffer);

  void clear() => _buffer.clear();

  /// Regex patterns for scrubbing sensitive values
  static final RegExp _emailRegex = RegExp(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
  );

  static final RegExp _jwtRegex = RegExp(
    r'ey[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.[A-Za-z0-9-_.+/=]+',
  );

  static final RegExp _bearerRegex = RegExp(
    r'(Bearer\s+)[A-Za-z0-9\-._~+/]+=*',
    caseSensitive: false,
  );

  static final RegExp _ipv4Regex = RegExp(
    r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
  );

  static final RegExp _privateKeyRegex = RegExp(
    r'0x[a-fA-F0-9]{64}',
  );

  /// Scrubs sensitive PII from a single string.
  String sanitize(String input) {
    String output = input;

    // 1. Scrub JWT tokens
    output = output.replaceAll(_jwtRegex, '[REDACTED_JWT]');

    // 2. Scrub Bearer auth headers
    output = output.replaceAllMapped(_bearerRegex, (m) => '${m[1]}[REDACTED_TOKEN]');

    // 3. Scrub private keys
    output = output.replaceAll(_privateKeyRegex, '[REDACTED_PRIVATE_KEY]');

    // 4. Scrub email addresses (anonymize keeping domain or redact)
    output = output.replaceAllMapped(_emailRegex, (match) {
      final email = match.group(0)!;
      final parts = email.split('@');
      if (parts.length == 2 && parts[0].isNotEmpty) {
        final obscured = '${parts[0][0]}***@${parts[1]}';
        return obscured;
      }
      return '[REDACTED_EMAIL]';
    });

    // 5. Scrub/Zero out last octet of IPv4 addresses
    output = output.replaceAllMapped(_ipv4Regex, (match) {
      final ip = match.group(0)!;
      final segments = ip.split('.');
      if (segments.length == 4) {
        return '${segments[0]}.${segments[1]}.${segments[2]}.0';
      }
      return '[REDACTED_IP]';
    });

    return output;
  }

  /// Recursively scrubs sensitive fields in Maps and JSON payloads.
  dynamic sanitizePayload(dynamic data) {
    if (data is String) {
      return sanitize(data);
    } else if (data is Map) {
      final result = <String, dynamic>{};
      data.forEach((key, value) {
        final keyLower = key.toString().toLowerCase();
        if (keyLower.contains('password') ||
            keyLower.contains('secret') ||
            keyLower.contains('passcode') ||
            keyLower.contains('refresh_token') ||
            keyLower.contains('id_token')) {
          result[key.toString()] = '[REDACTED]';
        } else {
          result[key.toString()] = sanitizePayload(value);
        }
      });
      return result;
    } else if (data is List) {
      return data.map((item) => sanitizePayload(item)).toList();
    }
    return data;
  }

  /// Logs a non-PII telemetry event.
  void logEvent(String name, {Map<String, dynamic>? parameters}) {
    if (!enabled) return;
    final sanitizedParams = parameters != null ? sanitizePayload(parameters) as Map<String, dynamic> : null;
    final entry = {
      'type': 'event',
      'name': sanitize(name),
      if (sanitizedParams != null) 'parameters': sanitizedParams,
      'timestamp': DateTime.now().toUtc().toIso8601String(),
    };
    _buffer.add(entry);
    if (_buffer.length > 200) _buffer.removeAt(0);
  }

  /// Records a non-PII error/crash event.
  void recordError(
    dynamic error, {
    StackTrace? stackTrace,
    Map<String, dynamic>? context,
  }) {
    if (!enabled) return;
    final sanitizedContext = context != null ? sanitizePayload(context) as Map<String, dynamic> : null;
    final entry = {
      'type': 'error',
      'error': sanitize(error.toString()),
      if (stackTrace != null) 'stackTrace': sanitize(stackTrace.toString()),
      if (sanitizedContext != null) 'context': sanitizedContext,
      'timestamp': DateTime.now().toUtc().toIso8601String(),
    };
    _buffer.add(entry);
    if (_buffer.length > 200) _buffer.removeAt(0);
  }
}

final telemetryService = TelemetryService();

