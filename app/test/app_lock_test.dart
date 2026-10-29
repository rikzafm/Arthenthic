import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:local_auth/local_auth.dart';
import 'package:app/main.dart';
import 'package:app/services/app_lock_service.dart';
import 'package:app/features/auth/lock_screen.dart';
import 'package:app/features/auth/app_lock_gate.dart';
import 'package:app/features/auth/welcome_screen.dart';

void main() {
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    appLockService.isGuest = true;
    appLockService.unlock();
    appLockService.customAuthenticate = ({required localizedReason, bool? biometricOnly}) async => false;
  });

  group('AppLockService unit tests', () {
    test('Initial guest state is unlocked and lock is ignored for guest', () {
      final service = AppLockService();
      service.isGuest = true;
      expect(service.isLocked, isFalse);

      service.lock();
      // Guest cannot be locked
      expect(service.isLocked, isFalse);
    });

    test('Logged in user locks and unlocks correctly', () {
      final service = AppLockService();
      service.isGuest = false;
      expect(service.isLocked, isFalse);

      service.lock();
      expect(service.isLocked, isTrue);

      service.unlock();
      expect(service.isLocked, isFalse);
    });

    test('Grace period logic: within grace period remains unlocked', () {
      final service = AppLockService();
      service.isGuest = false;
      service.gracePeriodSeconds = 30;

      // App backgrounded 10 seconds ago
      service.setLastBackgroundedTimeForTesting(
        DateTime.now().subtract(const Duration(seconds: 10)),
      );

      service.handleAppLifecycle(AppLifecycleState.resumed);
      expect(service.isLocked, isFalse);
    });

    test('Grace period logic: past grace period locks the app', () {
      final service = AppLockService();
      service.isGuest = false;
      service.gracePeriodSeconds = 30;

      // App backgrounded 35 seconds ago
      service.setLastBackgroundedTimeForTesting(
        DateTime.now().subtract(const Duration(seconds: 35)),
      );

      service.handleAppLifecycle(AppLifecycleState.resumed);
      expect(service.isLocked, isTrue);
    });

    test('Guest is unaffected by background grace period', () {
      final service = AppLockService();
      service.isGuest = true;
      service.gracePeriodSeconds = 30;

      service.setLastBackgroundedTimeForTesting(
        DateTime.now().subtract(const Duration(seconds: 100)),
      );

      service.handleAppLifecycle(AppLifecycleState.resumed);
      expect(service.isLocked, isFalse);
    });

    test('Mock authenticate success unlocks service', () async {
      final service = AppLockService(
        customAuthenticate: ({required localizedReason, bool? biometricOnly}) async => true,
      );
      service.isGuest = false;
      service.lock();
      expect(service.isLocked, isTrue);

      final success = await service.authenticate();
      expect(success, isTrue);
      expect(service.isLocked, isFalse);
    });

    test('getBiometricKind detects Touch ID vs Face ID correctly', () async {
      final touchIdService = AppLockService(
        customGetAvailableBiometrics: () async => [BiometricType.fingerprint],
      );
      expect(await touchIdService.getBiometricKind(), BiometricKind.touchId);

      final faceIdService = AppLockService(
        customGetAvailableBiometrics: () async => [BiometricType.face],
      );
      expect(await faceIdService.getBiometricKind(), BiometricKind.faceId);

      final genericService = AppLockService(
        customGetAvailableBiometrics: () async => [BiometricType.iris],
      );
      expect(await genericService.getBiometricKind(), BiometricKind.genericBiometric);
    });

    test('Fallback PIN defaults to 1234 and verifies correctly', () async {
      final service = AppLockService();
      service.isGuest = false;
      service.lock();
      expect(service.isLocked, isTrue);

      expect(await service.getFallbackPin(), '1234');

      // Invalid PIN fails
      final wrong = await service.verifyFallbackPin('9999');
      expect(wrong, isFalse);
      expect(service.isLocked, isTrue);

      // Correct default PIN succeeds and unlocks
      final correct = await service.verifyFallbackPin('1234');
      expect(correct, isTrue);
      expect(service.isLocked, isFalse);
    });

    test('Update fallback PIN updates storage', () async {
      final service = AppLockService();
      final updated = await service.setFallbackPin('5678');
      expect(updated, isTrue);
      expect(await service.getFallbackPin(), '5678');
    });
  });

  group('LockScreen widget tests', () {
    testWidgets('Renders lock screen with action buttons', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: LockScreen(
            autoPrompt: false,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Arthentic is Locked.'), findsOneWidget);
      expect(find.byKey(const Key('lock_unlock_button')), findsOneWidget);
      expect(find.byKey(const Key('lock_passcode_button')), findsOneWidget);
      expect(find.byKey(const Key('lock_signout_button')), findsOneWidget);
    });

    testWidgets('Displays Touch ID styling and allows unlock with Touch ID', (WidgetTester tester) async {
      bool unlockInvoked = false;
      final touchIdService = AppLockService(
        customGetAvailableBiometrics: () async => [BiometricType.fingerprint],
        customAuthenticate: ({required localizedReason, bool? biometricOnly}) async {
          expect(localizedReason, contains('Touch ID'));
          unlockInvoked = true;
          return true;
        },
      );
      touchIdService.isGuest = false;
      touchIdService.lock();

      await tester.pumpWidget(
        MaterialApp(
          home: LockScreen(
            autoPrompt: false,
            lockService: touchIdService,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Renders Touch ID text and icon
      expect(find.text('Unlock with Touch ID'), findsOneWidget);
      expect(find.textContaining('Touch ID or your device passcode'), findsOneWidget);
      expect(find.byIcon(Icons.fingerprint_rounded), findsWidgets);

      // Tap unlock button
      await tester.tap(find.byKey(const Key('lock_unlock_button')));
      await tester.pumpAndSettle();

      expect(unlockInvoked, isTrue);
      expect(touchIdService.isLocked, isFalse);
    });

    testWidgets('Displays Face ID styling when Face ID is available', (WidgetTester tester) async {
      final faceIdService = AppLockService(
        customGetAvailableBiometrics: () async => [BiometricType.face],
      );

      await tester.pumpWidget(
        MaterialApp(
          home: LockScreen(
            autoPrompt: false,
            lockService: faceIdService,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Unlock with Face ID'), findsOneWidget);
      expect(find.textContaining('Face ID or your device passcode'), findsOneWidget);
      expect(find.byIcon(Icons.face_unlock_outlined), findsWidgets);
    });

    testWidgets('Unlock success calls onUnlocked callback via dev button', (WidgetTester tester) async {
      bool unlockedCalled = false;

      final testLockService = AppLockService();
      testLockService.isGuest = false;
      testLockService.lock();

      await tester.pumpWidget(
        MaterialApp(
          home: LockScreen(
            autoPrompt: false,
            lockService: testLockService,
            onUnlocked: () => unlockedCalled = true,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Trigger dev simulate button
      await tester.tap(find.byKey(const Key('lock_dev_simulate_button')));
      await tester.pumpAndSettle();

      expect(unlockedCalled, isTrue);
      expect(testLockService.isLocked, isFalse);
    });

    testWidgets('Passcode button opens PIN sheet and unlocks with PIN 1234', (WidgetTester tester) async {
      bool unlockedCalled = false;

      final testLockService = AppLockService();
      testLockService.isGuest = false;
      testLockService.lock();

      await tester.pumpWidget(
        MaterialApp(
          home: LockScreen(
            autoPrompt: false,
            lockService: testLockService,
            onUnlocked: () => unlockedCalled = true,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Tap passcode button to open bottom sheet
      await tester.tap(find.byKey(const Key('lock_passcode_button')));
      await tester.pumpAndSettle();

      expect(find.text('Enter Passcode'), findsOneWidget);

      // Tap digits 1, 2, 3, 4
      await tester.tap(find.byKey(const Key('pin_key_1')));
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(find.byKey(const Key('pin_key_2')));
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(find.byKey(const Key('pin_key_3')));
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(find.byKey(const Key('pin_key_4')));
      await tester.pumpAndSettle();

      expect(unlockedCalled, isTrue);
      expect(testLockService.isLocked, isFalse);
    });

    testWidgets('Sign out button clears session and navigates to WelcomeScreen', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: LockScreen(autoPrompt: false),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('lock_signout_button')));
      await tester.pumpAndSettle();

      // Navigated to WelcomeScreen
      expect(find.byType(WelcomeScreen), findsOneWidget);
    });
  });

  group('AppLockGate integration tests', () {
    testWidgets('AppLockGate shows lock overlay when locked', (WidgetTester tester) async {
      appLockService.isGuest = false;
      appLockService.lock();

      await tester.pumpWidget(
        MaterialApp(
          home: AppLockGate(
            child: const Scaffold(
              body: Text('Protected Content'),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Lock screen overlay is shown
      expect(find.text('Arthentic is Locked.'), findsOneWidget);

      // Unlock
      appLockService.unlock();
      await tester.pumpAndSettle();

      // Content now visible without lock overlay
      expect(find.text('Protected Content'), findsOneWidget);
      expect(find.text('Arthentic is Locked.'), findsNothing);
    });

    testWidgets('AppLockGate does not lock when in guest mode', (WidgetTester tester) async {
      appLockService.isGuest = true;
      appLockService.lock();

      await tester.pumpWidget(
        MaterialApp(
          home: AppLockGate(
            child: const Scaffold(
              body: Text('Guest Content'),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Guest Content'), findsOneWidget);
      expect(find.text('Arthentic is Locked.'), findsNothing);
    });
  });
}

