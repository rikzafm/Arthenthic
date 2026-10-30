import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:app/contracts/contract_config.dart';
import 'package:app/core/models.dart';
import 'package:app/features/shared/status_badge_widget.dart';
import 'package:app/features/verify/field_calibration_sheet.dart';

void main() {
  group('Wave 3 Milestone 5 - Field Calibration & Testnet Hardware Tests', () {
    test('ArthenticContractConfig validates Base Sepolia & Eth Sepolia addresses', () {
      expect(ArthenticContractConfig.baseSepoliaChainId, equals(84532));
      expect(ArthenticContractConfig.ethereumSepoliaChainId, equals(11155111));
      expect(ArthenticContractConfig.arthenticNftAddress.startsWith('0x'), isTrue);
      expect(ArthenticContractConfig.arthenticEscrowAddress.startsWith('0x'), isTrue);
      expect(ArthenticContractConfig.merkleAnchorAddress.startsWith('0x'), isTrue);

      final manifest = ArthenticContractConfig.activeNetworkManifest();
      expect(manifest['baseSepolia']['chainId'], equals(84532));
      expect(manifest['ethereumSepolia']['chainId'], equals(11155111));
      expect(ArthenticContractConfig.isLiveSepoliaConfigured(), isTrue);
    });

    test('SunParams supports tamperStatus and detects broken loop', () {
      final intactParams = SunParams(
        uid: '04A1B2C3D4E588',
        ctr: 101,
        cmac: 'A9E38F107B5C2D44',
        tamperStatus: 'TAMPER_OK',
      );
      expect(intactParams.isTampered, isFalse);

      final brokenParams = SunParams(
        uid: '04A1B2C3D4E588',
        ctr: 102,
        cmac: 'A9E38F107B5C2D44',
        tamperStatus: 'TAMPER_PERM_OPEN',
      );
      expect(brokenParams.isTampered, isTrue);
    });

    testWidgets('FieldCalibrationSheet renders substrate options and LiDAR metrics',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: FieldCalibrationSheet(
              measuredRoughnessMm: 0.45,
              lidarSnrDb: 18.5,
              onSubstrateSelected: (substrate) {},
            ),
          ),
        ),
      );

      // Verify titles and substrate chips
      expect(find.text('Field Sensor Calibration'), findsOneWidget);
      expect(find.text('Linen Canvas'), findsOneWidget);
      expect(find.text('Wood Panel'), findsOneWidget);
      expect(find.text('Impasto Oil'), findsOneWidget);
      expect(find.text('Watercolor'), findsOneWidget);

      // Verify LiDAR telemetry readouts
      expect(find.textContaining('18.5 dB'), findsOneWidget);
      expect(find.textContaining('0.45 mm'), findsOneWidget);

      // Select Impasto Oil and verify adaptive threshold indicator
      await tester.tap(find.text('Impasto Oil'));
      await tester.pumpAndSettle();
      expect(find.textContaining('8500 bps'), findsOneWidget);
    });

    testWidgets('StatusBadgeWidget properly handles FLAGGED tamper tag',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: StatusBadgeWidget(
              status: ArtworkStatus.FLAGGED,
              tamperDetected: true,
            ),
          ),
        ),
      );

      expect(find.text('FLAGGED'), findsOneWidget);
      expect(find.textContaining('TAMPER'), findsOneWidget);
    });
  });
}
