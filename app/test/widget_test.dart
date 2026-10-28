import 'package:flutter_test/flutter_test.dart';
import 'package:app/main.dart';

void main() {
  testWidgets('Arthentic App smoke test - Verify screen and Navigation', (WidgetTester tester) async {
    await tester.pumpWidget(const ArthenticApp());
    await tester.pumpAndSettle();

    // Verify Brand & Hero Tagline on Home Screen
    expect(find.text('Arthentic'), findsOneWidget);
    expect(find.text('Every canvas\nhas a fingerprint.'), findsOneWidget);

    // Verify Roles
    expect(find.text('Collector'), findsOneWidget);
    expect(find.text('Verifier'), findsOneWidget);
    expect(find.text('Conservator'), findsOneWidget);

    // Verify Primary Action Buttons
    expect(find.text('Tap NFC chip'), findsOneWidget);
    expect(find.text('Scan surface'), findsOneWidget);
    expect(find.text('Debug: simulate NFC tap'), findsOneWidget);

    // Test Navigation to Provenance
    await tester.tap(find.text('Provenance'));
    await tester.pumpAndSettle();
    expect(find.text('Provenance.'), findsOneWidget);

    // Test Navigation to Wallet
    await tester.tap(find.text('Wallet'));
    await tester.pumpAndSettle();
    expect(find.text('Your wallet.'), findsOneWidget);
    expect(find.text('Smart wallet address'), findsOneWidget);
    expect(find.text('Base Sepolia'), findsOneWidget);

    // Return to Verify tab
    await tester.tap(find.text('Verify'));
    await tester.pumpAndSettle();

    // Test Navigation to Scan Surface Screen
    await tester.tap(find.text('Scan surface'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    // Verify Scan Screen elements
    expect(find.text('Point 1 of 8'), findsOneWidget);
    expect(find.text('Distance'), findsOneWidget);
    expect(find.text('Focus'), findsOneWidget);
    expect(find.text('Steadiness'), findsOneWidget);
    expect(find.textContaining('Top-Left Corner', findRichText: true), findsWidgets);

    // Cancel back to Home
    await tester.tap(find.text('Cancel'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Scan surface'), findsOneWidget);
  });
}
