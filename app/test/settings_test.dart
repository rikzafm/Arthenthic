import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:app/features/settings/settings_screen.dart';
import 'package:app/features/auth/welcome_screen.dart';
import 'package:app/services/api_client.dart';
import 'package:app/services/app_lock_service.dart';

void main() {
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    appLockService.isGuest = false;
    apiClient.currentUser = {
      "id": "usr_test_123",
      "email": "collector@arthentic.io",
      "display_name": "Test Collector",
      "email_verified_at": "2026-10-29T10:00:00Z",
      "roles": ["Collector"],
    };
    apiClient.mockRoleHandler = null;
    apiClient.mockAuthHandler = null;
  });

  testWidgets('Settings Screen - Displays profile, sessions, and allows session revoke', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    final sessions = [
      {
        "id": "sess_current",
        "device_name": "iPhone 15 Pro",
        "platform": "ios",
        "is_current": true,
        "is_active": true,
      },
      {
        "id": "sess_remote",
        "device_name": "iPad Pro",
        "platform": "ios",
        "is_current": false,
        "is_active": true,
      },
    ];

    String? revokedSessionId;

    apiClient.mockRoleHandler = (endpoint, body) async {
      if (endpoint == "/v1/auth/sessions") {
        return {"sessions": sessions};
      } else if (endpoint.contains("/revoke")) {
        revokedSessionId = endpoint.split('/')[4];
        final s = sessions.firstWhere((element) => element["id"] == revokedSessionId);
        s["is_active"] = false;
        return {"success": true};
      }
      return {};
    };

    await tester.pumpWidget(const MaterialApp(
      home: SettingsScreen(),
    ));
    await tester.pumpAndSettle();

    // 1. Verify profile info
    expect(find.text('Test Collector'), findsOneWidget);
    expect(find.text('collector@arthentic.io'), findsOneWidget);
    expect(find.text('Verified'), findsOneWidget);

    // 2. Verify sessions list
    expect(find.text('iPhone 15 Pro'), findsOneWidget);
    expect(find.text('This Device'), findsOneWidget);
    expect(find.text('iPad Pro'), findsOneWidget);
    expect(find.text('Revoke'), findsOneWidget);

    // 3. Tap Revoke on remote session
    await tester.ensureVisible(find.text('Revoke'));
    await tester.tap(find.text('Revoke'));
    await tester.pumpAndSettle();

    expect(revokedSessionId, equals("sess_remote"));
    expect(find.text('Revoked session'), findsOneWidget);
  });

  testWidgets('Settings Screen - Can change auto-lock grace period', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    apiClient.mockRoleHandler = (endpoint, body) async {
      return {"sessions": []};
    };

    await tester.pumpWidget(const MaterialApp(
      home: SettingsScreen(),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Auto-lock Grace Period'), findsOneWidget);
    expect(find.text('30 seconds'), findsOneWidget);

    // Open dropdown
    await tester.tap(find.text('30 seconds'));
    await tester.pumpAndSettle();

    // Select "Immediately"
    await tester.tap(find.text('Immediately').last);
    await tester.pumpAndSettle();

    expect(appLockService.gracePeriodSeconds, equals(0));
  });

  testWidgets('Settings Screen - Change password modal and validation', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    Map<String, dynamic>? changePayload;

    apiClient.mockRoleHandler = (endpoint, body) async {
      if (endpoint == "/v1/auth/sessions") {
        return {"sessions": []};
      } else if (endpoint == "/v1/auth/password/change") {
        changePayload = Map<String, dynamic>.from(body);
        return {"success": true, "message": "Password changed"};
      }
      return {};
    };

    await tester.pumpWidget(const MaterialApp(
      home: SettingsScreen(),
    ));
    await tester.pumpAndSettle();

    // Tap Change Password
    await tester.ensureVisible(find.text('Change Password'));
    await tester.tap(find.text('Change Password'));
    await tester.pumpAndSettle();

    // Modal is opened
    expect(find.text('Update Password'), findsOneWidget);

    // Enter passwords
    await tester.enterText(find.byType(TextField).at(0), 'OldPass123!');
    await tester.enterText(find.byType(TextField).at(1), 'NewPass123!');
    await tester.enterText(find.byType(TextField).at(2), 'NewPass123!');
    await tester.pumpAndSettle();

    await tester.tap(find.text('Update Password'));
    await tester.pumpAndSettle();

    expect(changePayload, isNotNull);
    expect(changePayload!["current_password"], equals("OldPass123!"));
    expect(changePayload!["new_password"], equals("NewPass123!"));
  });

  testWidgets('Settings Screen - Delete account confirmation (App Store 5.1.1(v)) routes to WelcomeScreen', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    bool deleteCalled = false;

    apiClient.mockRoleHandler = (endpoint, body) async {
      if (endpoint == "/v1/auth/sessions") {
        return {"sessions": []};
      } else if (endpoint == "/v1/auth/account") {
        deleteCalled = true;
        return {"success": true};
      }
      return {};
    };

    await tester.pumpWidget(const MaterialApp(
      home: SettingsScreen(),
    ));
    await tester.pumpAndSettle();

    // Tap Delete Account
    await tester.ensureVisible(find.text('Delete Account'));
    await tester.tap(find.text('Delete Account'));
    await tester.pumpAndSettle();

    // Verify warning dialog
    expect(find.text('Delete Account?'), findsOneWidget);
    expect(find.textContaining('This action is permanent and cannot be undone'), findsOneWidget);

    // Confirm deletion
    await tester.tap(find.text('Permanently Delete'));
    await tester.pumpAndSettle();

    expect(deleteCalled, isTrue);
    expect(find.byType(WelcomeScreen), findsOneWidget);
  });

  testWidgets('Settings Screen - Displays Connected Accounts (Apple and Google)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    apiClient.mockRoleHandler = (endpoint, body) async {
      return {"sessions": []};
    };

    await tester.pumpWidget(const MaterialApp(
      home: SettingsScreen(),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Connected Accounts'), findsOneWidget);
    expect(find.text('Sign in with Apple'), findsOneWidget);
    expect(find.text('Google Sign-In'), findsOneWidget);
  });

  testWidgets('Settings Screen - Email verification modal and confirmation updates state', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    apiClient.currentUser = {
      "id": "usr_unverified",
      "email": "newbie@arthentic.io",
      "display_name": "New User",
      "email_verified_at": null,
      "roles": ["Collector"],
    };

    bool emailRequested = false;
    bool emailConfirmed = false;

    apiClient.mockRoleHandler = (endpoint, body) async {
      if (endpoint == "/v1/auth/sessions") {
        return {"sessions": []};
      } else if (endpoint == "/v1/auth/verify-email/request") {
        emailRequested = true;
        return {"success": true, "verify_token": "verify_token_xyz"};
      } else if (endpoint == "/v1/auth/verify-email/confirm") {
        if (body["token"] == "verify_token_xyz") {
          emailConfirmed = true;
          return {"success": true, "message": "Email verified"};
        }
        return {"success": false, "error": "Invalid token"};
      }
      return {};
    };

    await tester.pumpWidget(const MaterialApp(
      home: SettingsScreen(),
    ));
    await tester.pumpAndSettle();

    // Verify unverified badge exists
    expect(find.text('Unverified'), findsOneWidget);

    // Tap Unverified badge
    await tester.tap(find.text('Unverified'));
    await tester.pumpAndSettle();

    // Verify modal is open
    expect(find.text('Verify Email Address'), findsOneWidget);
    expect(find.byKey(const Key('send_verification_email_button')), findsOneWidget);

    // Tap Send Verification Link
    await tester.tap(find.byKey(const Key('send_verification_email_button')));
    await tester.pumpAndSettle();

    expect(emailRequested, isTrue);
    expect(find.byKey(const Key('verify_token_field')), findsOneWidget);

    // Tap Confirm Verification
    await tester.tap(find.byKey(const Key('confirm_email_token_button')));
    await tester.pumpAndSettle();

    expect(emailConfirmed, isTrue);
    // Modal dismissed and badge now shows Verified
    expect(find.text('Verified'), findsOneWidget);
  });

  testWidgets('Settings Screen - Privacy & Data Retention policy sheet opens', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    apiClient.mockRoleHandler = (endpoint, body) async {
      return {"sessions": []};
    };

    await tester.pumpWidget(const MaterialApp(
      home: SettingsScreen(),
    ));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('Privacy & Data Policy'));
    await tester.tap(find.text('Privacy & Data Policy'));
    await tester.pumpAndSettle();

    expect(find.text('Privacy & Data Retention'), findsOneWidget);
    expect(find.textContaining('Zero-PII Architecture & App Store Compliance'), findsOneWidget);
    expect(find.textContaining('5.1.1(v)'), findsOneWidget);
  });
}

