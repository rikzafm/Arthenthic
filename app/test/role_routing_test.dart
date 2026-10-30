import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:app/features/home/home_screen.dart';
import 'package:app/features/auth/login_screen.dart';
import 'package:app/services/api_client.dart';
import 'package:app/services/app_lock_service.dart';

void main() {
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    appLockService.isGuest = false;
    apiClient.currentUser = null;
  });

  testWidgets('Role routing - Guest entry displays guest banner and public actions', (WidgetTester tester) async {
    appLockService.isGuest = true;

    await tester.pumpWidget(MaterialApp(
      home: HomeScreen(onTabSelected: (_) {}),
    ));
    await tester.pumpAndSettle();

    // Guest banner
    expect(find.text('Sign in to save results and access accredited tools.'), findsOneWidget);
    expect(find.text('Sign In'), findsOneWidget);

    // Primary verify actions are available
    expect(find.text('Tap NFC chip'), findsOneWidget);
    expect(find.text('Scan surface'), findsOneWidget);

    // Accreditation application card is not visible for guest
    expect(find.text('Apply for Accreditation'), findsNothing);
  });

  testWidgets('Role routing - Collector sees Apply for Accreditation card', (WidgetTester tester) async {
    appLockService.isGuest = false;
    apiClient.currentUser = {
      "id": "col_1",
      "email": "collector@arthentic.io",
      "roles": ["Collector"],
    };

    await tester.pumpWidget(MaterialApp(
      home: HomeScreen(onTabSelected: (_) {}),
    ));
    await tester.pumpAndSettle();

    // Collector sees Apply for Accreditation
    expect(find.text('Apply for Accreditation'), findsOneWidget);
    expect(find.text('Apply'), findsOneWidget);

    // Tap Apply opens the accreditation modal
    await tester.ensureVisible(find.text('Apply'));
    await tester.tap(find.text('Apply'));
    await tester.pumpAndSettle();

    expect(find.text('Submit Application'), findsOneWidget);
    expect(find.text('Requested Role'), findsOneWidget);
  });

  testWidgets('Role routing - Multi-role user can switch roles and view per-role homes', (WidgetTester tester) async {
    appLockService.isGuest = false;
    apiClient.currentUser = {
      "id": "multi_1",
      "email": "multirole@arthentic.io",
      "roles": ["Artist", "Gallery", "Conservator", "Admin"],
    };

    await tester.pumpWidget(MaterialApp(
      home: HomeScreen(onTabSelected: (_) {}),
    ));
    await tester.pumpAndSettle();

    // Artist view is active: Register new artwork (genesis)
    expect(find.text('Register New Artwork'), findsOneWidget);
    expect(find.text('Start Genesis Capture'), findsOneWidget);

    // Switch to Gallery role
    await tester.tap(find.text('Gallery'));
    await tester.pumpAndSettle();

    // Gallery view displays Read-Only Verification Queue and Sign on Web banner
    expect(find.text('Read-Only Verification Queue'), findsOneWidget);
    expect(find.textContaining('Mobile is read-only. Multisig on-chain attestations must be signed on the Arthentic Web portal.'), findsOneWidget);

    // Switch to Conservator role
    await tester.tap(find.text('Conservator'));
    await tester.pumpAndSettle();

    // Conservator view displays Conservation Lab Ready
    expect(find.text('Conservation Lab Ready'), findsOneWidget);
    expect(find.textContaining('Record condition reports & update baselines post-restoration'), findsOneWidget);

    // Switch to Admin role
    await tester.tap(find.text('Admin'));
    await tester.pumpAndSettle();

    // Admin view displays Admin Accreditation Review
    expect(find.text('Admin Accreditation Review'), findsOneWidget);
  });

  testWidgets('Role routing - Login screen has guest entry', (WidgetTester tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: LoginScreen(),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Continue as guest'), findsOneWidget);
  });
}
