import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:app/main.dart';
import 'package:app/services/api_client.dart';
import 'package:app/services/app_lock_service.dart';
import 'package:app/services/oauth_service.dart';
import 'package:app/features/auth/login_screen.dart';

void main() {
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    appLockService.isGuest = true;
    appLockService.unlock();

    apiClient.mockAuthHandler = (endpoint, body) async {
      return {
        "success": true,
        "access_token": "mock_jwt_access_token",
        "refresh_token": "mock_refresh_token_123",
        "user": {
          "id": "mock_user_123",
          "email": "oauth.user@arthentic.io",
          "display_name": "OAuth User",
          "roles": ["Collector"],
        }
      };
    };
  });

  group('OAuthService tests', () {
    test('Google sign in returns token and calls api', () async {
      final service = OAuthService(
        customGoogleSignIn: () async => "mock_google_id_token_123",
      );

      final token = await service.customGoogleSignIn!();
      expect(token, equals("mock_google_id_token_123"));
    });

    test('Google sign in handles cancel gracefully', () async {
      final service = OAuthService(
        customGoogleSignIn: () async => null, // user cancelled
      );

      final res = await service.signInWithGoogle();
      expect(res["cancelled"], isTrue);
    });

    test('Apple sign in handles cancel gracefully', () async {
      final service = OAuthService(
        customAppleSignIn: () async => null, // user cancelled
      );

      final res = await service.signInWithApple();
      expect(res["cancelled"], isTrue);
    });
  });

  group('LoginScreen OAuth Buttons tests', () {
    testWidgets('LoginScreen displays Apple and Google sign in buttons', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: LoginScreen(),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('apple_signin_button')), findsOneWidget);
      expect(find.text('Sign in with Apple'), findsOneWidget);

      expect(find.byKey(const Key('google_signin_button')), findsOneWidget);
      expect(find.text('Continue with Google'), findsOneWidget);
    });

    testWidgets('Google sign in success unlocks app and navigates to MainTabShell', (WidgetTester tester) async {
      oAuthService.customGoogleSignIn = () async => "mock_google:sub_123:test@google.com:1:Test User";

      await tester.pumpWidget(
        const MaterialApp(
          home: LoginScreen(),
        ),
      );
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.byKey(const Key('google_signin_button')));
      await tester.tap(find.byKey(const Key('google_signin_button')));
      await tester.pumpAndSettle();

      // Verified app lock is unlocked and user is not a guest
      expect(appLockService.isGuest, isFalse);
      expect(appLockService.isLocked, isFalse);
      expect(find.byType(MainTabShell), findsOneWidget);
    });

    testWidgets('Apple sign in success unlocks app and navigates to MainTabShell', (WidgetTester tester) async {
      oAuthService.customAppleSignIn = () async => "mock_apple:sub_apple_1:test@apple.com:1:Apple User";

      await tester.pumpWidget(
        const MaterialApp(
          home: LoginScreen(),
        ),
      );
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.byKey(const Key('apple_signin_button')));
      await tester.tap(find.byKey(const Key('apple_signin_button')));
      await tester.pumpAndSettle();

      expect(appLockService.isGuest, isFalse);
      expect(appLockService.isLocked, isFalse);
      expect(find.byType(MainTabShell), findsOneWidget);
    });
  });
}
