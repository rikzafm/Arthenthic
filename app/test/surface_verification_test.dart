import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:app/core/models.dart';
import 'package:app/features/scan/scan_screen.dart';
import 'package:app/services/api_client.dart';

void main() {
  setUp(() {
    apiClient.mockRoleHandler = (endpoint, body) async {
      if (endpoint == "/v1/captures") {
        return {"captureId": "cap_test_${DateTime.now().millisecondsSinceEpoch}"};
      }
      return {};
    };
  });

  tearDown(() {
    apiClient.mockRoleHandler = null;
  });

  testWidgets('ScanScreen starts at Point 1 of 8 with spatial guidance, Tilt leveling, and quality gating', (WidgetTester tester) async {
    final artwork = ArtworkInfo.mock();

    await tester.pumpWidget(
      MaterialApp(
        home: ScanScreen(artwork: artwork, selectedRole: 'Collector'),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    // 1. Starts at Point 1 of 8
    expect(find.text('Point 1 of 8'), findsOneWidget);

    // 2. Spatial guidance label for Point 1
    expect(find.textContaining('Top-Left', findRichText: true), findsWidgets);

    // 3. Telemetry HUD: Distance, Tilt, Steadiness
    expect(find.text('Distance'), findsOneWidget);
    expect(find.text('Tilt'), findsOneWidget);
    expect(find.text('Steadiness'), findsOneWidget);

    // 4. Shutter button is present
    final shutterFinder = find.byKey(const Key('shutter_button'));
    expect(shutterFinder, findsOneWidget);

    // 5. Retake button should NOT be present on Point 1
    expect(find.byKey(const Key('retake_button')), findsNothing);
  });

  testWidgets('Manual shutter tap triggers capture and advances to Point 2 with cooldown and retake button', (WidgetTester tester) async {
    final artwork = ArtworkInfo.mock();

    await tester.pumpWidget(
      MaterialApp(
        home: ScanScreen(artwork: artwork, selectedRole: 'Collector'),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    // Tap shutter button
    final shutterFinder = find.byKey(const Key('shutter_button'));
    await tester.tap(shutterFinder);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    // Should advance to Point 2 of 8
    expect(find.text('Point 2 of 8'), findsOneWidget);

    // Should display cooldown prompt
    expect(find.textContaining('Point 1 captured! Move to Top-Center', findRichText: true), findsWidgets);

    // Retake button should now be visible
    expect(find.byKey(const Key('retake_button')), findsOneWidget);
    expect(find.text('Retake Pt 1'), findsOneWidget);
  });

  testWidgets('Retake button decrements point index and returns to prior point', (WidgetTester tester) async {
    final artwork = ArtworkInfo.mock();

    await tester.pumpWidget(
      MaterialApp(
        home: ScanScreen(artwork: artwork, selectedRole: 'Collector'),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    // Capture Point 1 manually
    await tester.tap(find.byKey(const Key('shutter_button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Point 2 of 8'), findsOneWidget);

    // Tap Retake Pt 1
    final retakeFinder = find.byKey(const Key('retake_button'));
    expect(retakeFinder, findsOneWidget);
    await tester.tap(retakeFinder);
    await tester.pump();

    // Should return to Point 1 of 8 and retake button disappears
    expect(find.text('Point 1 of 8'), findsOneWidget);
    expect(find.byKey(const Key('retake_button')), findsNothing);
  });

  testWidgets('Smart Auto-Capture executes after holding steady in sweet spot', (WidgetTester tester) async {
    final artwork = ArtworkInfo.mock();

    await tester.pumpWidget(
      MaterialApp(
        home: ScanScreen(artwork: artwork, selectedRole: 'Collector'),
      ),
    );
    await tester.pump();
    // Pump telemetry tick to arm auto-capture
    await tester.pump(const Duration(milliseconds: 400));
    // Pump countdown duration (800ms) + buffer to trigger capture
    await tester.pump(const Duration(milliseconds: 900));
    await tester.pump(const Duration(milliseconds: 200));

    // Auto-capture should have advanced to Point 2
    expect(find.text('Point 2 of 8'), findsOneWidget);
  });

  testWidgets('Upload failure displays retry banner and tapping Retry recovers', (WidgetTester tester) async {
    final artwork = ArtworkInfo.mock();
    bool shouldFail = true;

    apiClient.mockRoleHandler = (endpoint, body) async {
      if (endpoint == "/v1/captures") {
        if (shouldFail) {
          throw Exception("Network 503 Service Unavailable");
        }
        return {"captureId": "cap_retry_success"};
      }
      return {};
    };

    await tester.pumpWidget(
      MaterialApp(
        home: ScanScreen(artwork: artwork, selectedRole: 'Collector'),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    // Tap shutter button while network is failing
    await tester.tap(find.byKey(const Key('shutter_button')));
    // Wait for the backoff retries to exhaust
    await tester.pump(const Duration(milliseconds: 3000));
    await tester.pump();

    // Verify error banner is visible
    expect(find.byKey(const Key('upload_error_banner')), findsOneWidget);
    expect(find.byKey(const Key('retry_upload_button')), findsOneWidget);

    // Now restore network connection and tap Retry
    shouldFail = false;
    await tester.tap(find.byKey(const Key('retry_upload_button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    // Verify error banner is gone and advanced to Point 2
    expect(find.byKey(const Key('upload_error_banner')), findsNothing);
    expect(find.text('Point 2 of 8'), findsOneWidget);
  });
}
