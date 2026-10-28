import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:app/core/models.dart';
import 'package:app/features/scan/scan_screen.dart';

void main() {
  testWidgets('ScanScreen starts at Point 1 of 8 with spatial guidance and quality gating', (WidgetTester tester) async {
    final artwork = ArtworkInfo.mock();

    await tester.pumpWidget(
      MaterialApp(
        home: ScanScreen(artwork: artwork, selectedRole: 'Collector'),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    // 1. Should start at Point 1 of 8
    expect(find.text('Point 1 of 8'), findsOneWidget);

    // 2. Spatial guidance label for Point 1
    expect(find.textContaining('Top-Left', findRichText: true), findsWidgets);

    // 3. Telemetry HUD: Distance, Focus, Steadiness
    expect(find.text('Distance'), findsOneWidget);
    expect(find.text('Focus'), findsOneWidget);
    expect(find.text('Steadiness'), findsOneWidget);

    // 4. Shutter button is present
    final shutterFinder = find.byKey(const Key('shutter_button'));
    expect(shutterFinder, findsOneWidget);
  });
}
