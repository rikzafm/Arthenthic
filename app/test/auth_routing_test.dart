import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:app/main.dart';
import 'package:app/features/auth/welcome_screen.dart';
import 'package:app/features/auth/login_screen.dart';
import 'package:app/features/auth/signup_screen.dart';
import 'package:app/features/auth/splash_screen.dart';
import 'package:app/services/session_store.dart';
import 'package:app/services/api_client.dart';

void main() {
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });

  testWidgets('Launch routing - No session routes to WelcomeScreen and guest access works', (WidgetTester tester) async {
    // With empty secure storage
    FlutterSecureStorage.setMockInitialValues({});

    await tester.pumpWidget(const ArthenticApp(home: WelcomeScreen()));
    await tester.pumpAndSettle();

    // Verify Welcome elements
    expect(find.text('Arthentic'), findsOneWidget);
    expect(find.text('Every canvas\nhas a fingerprint.'), findsOneWidget);
    expect(find.text('Sign In'), findsOneWidget);
    expect(find.text('Create Account'), findsOneWidget);
    expect(find.text('Continue as guest'), findsOneWidget);

    // Tap "Continue as guest"
    await tester.tap(find.text('Continue as guest'));
    await tester.pumpAndSettle();

    // Verify routed to MainTabShell (guest mode)
    expect(find.text('Tap NFC chip'), findsOneWidget);
    expect(find.text('Scan surface'), findsOneWidget);
    expect(find.text('Provenance'), findsOneWidget);
    expect(find.text('Wallet'), findsOneWidget);
  });

  testWidgets('Launch routing - Welcome to Login screen and validation', (WidgetTester tester) async {
    await tester.pumpWidget(const ArthenticApp(home: WelcomeScreen()));
    await tester.pumpAndSettle();

    // Tap "Sign In"
    await tester.tap(find.text('Sign In'));
    await tester.pumpAndSettle();

    // Verify Login Screen
    expect(find.text('Welcome back.'), findsOneWidget);
    expect(find.byKey(const Key('login_email_field')), findsOneWidget);
    expect(find.byKey(const Key('login_password_field')), findsOneWidget);
    expect(find.byKey(const Key('login_submit_button')), findsOneWidget);

    // Submit empty fields -> shows validation error
    await tester.tap(find.byKey(const Key('login_submit_button')));
    await tester.pumpAndSettle();
    expect(find.text('Please enter both email and password.'), findsOneWidget);
  });

  testWidgets('Launch routing - Login to Sign Up screen and password strength validation', (WidgetTester tester) async {
    await tester.pumpWidget(const ArthenticApp(home: const LoginScreen()));
    await tester.pumpAndSettle();

    // Tap "Create one"
    await tester.ensureVisible(find.text('Create one'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Create one'));
    await tester.pumpAndSettle();

    // Verify Sign Up Screen
    expect(find.text('Create Account.'), findsOneWidget);
    expect(find.byKey(const Key('signup_name_field')), findsOneWidget);
    expect(find.byKey(const Key('signup_email_field')), findsOneWidget);
    expect(find.byKey(const Key('signup_password_field')), findsOneWidget);
    expect(find.text('8+ characters'), findsOneWidget);
    expect(find.text('1 letter'), findsOneWidget);
    expect(find.text('1 number'), findsOneWidget);

    // Enter weak password
    await tester.enterText(find.byKey(const Key('signup_password_field')), 'short');
    await tester.pumpAndSettle();

    // Check checklist state
    expect(find.byIcon(Icons.circle_outlined), findsWidgets);
  });

  testWidgets('Launch routing - Session expired shows notification banner on LoginScreen', (WidgetTester tester) async {
    await tester.pumpWidget(const ArthenticApp(home: LoginScreen(sessionExpired: true)));
    await tester.pumpAndSettle();

    expect(find.text('Session expired. Please sign in again.'), findsOneWidget);
    expect(find.text('Welcome back.'), findsOneWidget);
  });

  testWidgets('Launch routing - Forgot Password modal allows requesting reset token and updating password', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    bool forgotRequested = false;
    bool resetCompleted = false;

    apiClient.mockRoleHandler = (endpoint, body) async {
      if (endpoint == "/v1/auth/password/forgot") {
        forgotRequested = true;
        return {"success": true, "reset_token": "rst_token_12345"};
      } else if (endpoint == "/v1/auth/password/reset") {
        if (body["token"] == "rst_token_12345" && body["new_password"] == "BrandNewPass123!") {
          resetCompleted = true;
          return {"success": true, "message": "Password reset successfully"};
        }
        return {"success": false, "error": "Reset failed"};
      }
      return {};
    };

    await tester.pumpWidget(const ArthenticApp(home: LoginScreen()));
    await tester.pumpAndSettle();

    // Verify Forgot password button
    expect(find.byKey(const Key('forgot_password_button')), findsOneWidget);
    await tester.tap(find.byKey(const Key('forgot_password_button')));
    await tester.pumpAndSettle();

    // Reset password modal open
    expect(find.text('Reset Password'), findsOneWidget);
    expect(find.byKey(const Key('forgot_email_field')), findsOneWidget);

    // Enter email
    await tester.enterText(find.byKey(const Key('forgot_email_field')), 'artist@arthentic.io');
    await tester.tap(find.byKey(const Key('send_reset_code_button')));
    await tester.pumpAndSettle();

    expect(forgotRequested, isTrue);
    expect(find.byKey(const Key('reset_token_field')), findsOneWidget);
    expect(find.byKey(const Key('reset_new_password_field')), findsOneWidget);

    // Enter new password & confirm
    await tester.enterText(find.byKey(const Key('reset_new_password_field')), 'BrandNewPass123!');
    await tester.enterText(find.byKey(const Key('reset_confirm_password_field')), 'BrandNewPass123!');
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('submit_new_password_button')));
    await tester.pumpAndSettle();

    expect(resetCompleted, isTrue);
    expect(find.textContaining('Password reset successfully'), findsOneWidget);
  });
}

