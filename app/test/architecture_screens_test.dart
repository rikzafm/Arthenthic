import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:app/core/platform_capabilities.dart';
import 'package:app/contracts/contract_config.dart';
import 'package:app/features/shared/status_badge_widget.dart';
import 'package:app/features/dashboards/artist_dashboard.dart';
import 'package:app/features/dashboards/collector_dashboard.dart';
import 'package:app/features/genesis/genesis_intake_screen.dart';
import 'package:app/features/genesis/coa_screen.dart';
import 'package:app/features/conservation/restoration_screen.dart';
import 'package:app/features/wallet/paymaster_fallback_modal.dart';
import 'package:app/features/web_consoles/gallery_safe_console.dart';
import 'package:app/features/web_consoles/conservator_console.dart';
import 'package:app/features/web_consoles/admin_incident_console.dart';
import 'package:app/capture/capture_channel.dart';
import 'package:app/services/nfc_service.dart';
import 'package:app/services/wallet_service.dart';
import 'package:app/main.dart';

void main() {
  group('Wave 1 & Wave 2 Milestone 2 Architecture Widgets & Contract Config', () {
    test('PlatformCapabilities desktop breakpoint detection works', () {
      expect(PlatformCapabilities.isDesktopConsole(1200), isTrue);
      expect(PlatformCapabilities.isDesktopConsole(400), isFalse);
    });

    test('ArthenticContractConfig exposes Base Sepolia (84532) and Ethereum Sepolia (11155111) addresses', () {
      expect(ArthenticContractConfig.baseSepoliaChainId, 84532);
      expect(ArthenticContractConfig.ethereumSepoliaChainId, 11155111);
      expect(ArthenticContractConfig.arthenticNftAddress.startsWith('0x'), isTrue);
      expect(ArthenticContractConfig.arthenticEscrowAddress.startsWith('0x'), isTrue);
      expect(ArthenticContractConfig.merkleAnchorAddress.startsWith('0x'), isTrue);
      expect(
        ArthenticContractConfig.basescanContractUrl(ArthenticContractConfig.arthenticNftAddress),
        contains('sepolia.basescan.org/address/'),
      );
    });

    testWidgets('StatusBadgeWidget and StatusWarningBanner render all 5 D-15* badge states', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: Column(
                children: [
                  StatusBadgeWidget(status: 'CLEAR'),
                  StatusBadgeWidget(status: 'CHIP_REPLACED'),
                  StatusBadgeWidget(status: 'UNSYNCHRONIZED_OWNERSHIP'),
                  StatusBadgeWidget(status: 'FLAGGED'),
                  StatusBadgeWidget(status: 'DESTROYED'),
                  StatusWarningBanner(status: 'UNSYNCHRONIZED_OWNERSHIP'),
                  StatusWarningBanner(status: 'FLAGGED'),
                ],
              ),
            ),
          ),
        ),
      );

      expect(find.textContaining('CLEAR'), findsOneWidget);
      expect(find.textContaining('CHIP REPLACED'), findsOneWidget);
      expect(find.textContaining('UNSYNCHRONIZED OWNERSHIP'), findsWidgets);
      expect(find.textContaining('FLAGGED'), findsWidgets);
      expect(find.textContaining('DESTROYED'), findsOneWidget);
    });

    testWidgets('ArtistDashboardScreen (L-07) and CollectorDashboardScreen (L-09) render', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: ArtistDashboardScreen(),
        ),
      );
      expect(find.text('Artist Studio Dashboard'), findsOneWidget);
      expect(find.textContaining('5.0%'), findsWidgets);

      await tester.pumpWidget(
        const MaterialApp(
          home: CollectorDashboardScreen(),
        ),
      );
      expect(find.text('Collector Portfolio'), findsOneWidget);
      expect(find.textContaining('L-09: Collector Vault'), findsOneWidget);
      expect(find.textContaining('Auto-Refund (C-12)'), findsOneWidget);
    });

    testWidgets('GenesisIntakeScreen renders 3-stage intake wizard (B-01..B-08) & Base Sepolia config', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: GenesisIntakeScreen(),
        ),
      );
      expect(find.text('3-Stage Genesis Intake (UC-B)'), findsOneWidget);
      expect(
        find.text('Stage 1: Gallery Intake Dossier & NTAG 424 DNA Binding'),
        findsOneWidget,
      );
      expect(find.textContaining('Base Sepolia'), findsWidgets);
    });

    testWidgets('CertificateOfAuthenticityScreen (B-12) renders CoA after loading', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: CertificateOfAuthenticityScreen(tokenId: '101'),
        ),
      );
      await tester.pump(const Duration(seconds: 6));
      expect(find.text('Certificate of Authenticity'), findsWidgets);
      expect(find.textContaining('Cryptographic Integrity'), findsOneWidget);
    });

    testWidgets('RestorationScreen (E-01..07*, F-05) supports tab switch and 3-of-3 chip progression', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: RestorationScreen(tokenId: '101'),
        ),
      );
      expect(find.text('Restoration & Chip Governance'), findsOneWidget);
      expect(find.textContaining('E-07* / ADR-03: Collector Consent Gate'), findsOneWidget);

      // Switch to Tab 2: Chip Swap (F-05 3-of-3)
      await tester.tap(find.text('Chip Swap (F-05 3-of-3)'));
      await tester.pumpAndSettle();

      expect(find.text('1 of 3 Signatures Collected'), findsOneWidget);
      await tester.tap(find.text('Sign Approval as Next Actor'));
      await tester.pump();
      expect(find.text('2 of 3 Signatures Collected'), findsOneWidget);

      await tester.tap(find.text('Sign Approval as Next Actor'));
      await tester.pump();
      expect(find.text('3 of 3 Signatures Collected'), findsOneWidget);
    });

    testWidgets('PaymasterFallbackModal (K-04) renders gas breakdown and triggers callback', (tester) async {
      var confirmed = false;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PaymasterFallbackModal(
              methodName: 'claim',
              reason: 'Monthly T1 quota (10/10) exhausted for wallet.',
              onConfirmSelfPay: () {
                confirmed = true;
              },
            ),
          ),
        ),
      );

      expect(find.text('Gas Sponsorship Fallback'), findsOneWidget);
      expect(find.text('K-04 Self-Pay Modal'), findsOneWidget);
      await tester.tap(find.text('Pay Gas Directly via MetaMask'));
      await tester.pump();
      expect(confirmed, isTrue);
    });

    testWidgets('Institutional Desktop Web Consoles render (Gallery, Conservator, Admin)', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: GallerySafeConsole(),
        ),
      );
      expect(find.text('Institutional Verifier Console'), findsOneWidget);
      expect(find.textContaining('Base Sepolia'), findsWidgets);

      await tester.pumpWidget(
        const MaterialApp(
          home: ConservatorStudioConsole(),
        ),
      );
      expect(find.text('Conservation Studio Workspace'), findsOneWidget);

      await tester.pumpWidget(
        const MaterialApp(
          home: AdminIncidentConsole(),
        ),
      );
      expect(find.text('Security Incident & Governance Console'), findsOneWidget);
      expect(find.text('Emergency Pause (J-01)'), findsOneWidget);
    });

    test('CoreNFC SDM Writer Bridge (B-05) provisions NTAG 424 DNA SDM URL template and AES-128 key slot', () async {
      final res = await nfcService.provisionSdmTag(
        chipUid: '04A1B2C3D4E580',
        tokenId: '101',
        keySlot: '01',
      );
      expect(res['success'], isTrue);
      expect(res['feature_code'], 'B-05');
      expect(res['sdmUrlTemplate'], contains('verify.arthentic.io'));
      expect(res['aes128SlotConfigured'], isTrue);
      expect(res['chipIdHash'].toString().startsWith('0x'), isTrue);
    });

    test('ARKit SceneDepth LiDAR Bridge (B-02 / D-05) extracts 256x192 Float32 depth maps and 8-point mesh', () async {
      final point = await CaptureChannel.capturePoint(1);
      expect(point['depthWidth'], 256);
      expect(point['depthHeight'], 192);
      // 256 * 192 * 4 bytes per Float32 = 196608 bytes
      expect((point['depthBytes'] as List<int>).length, 256 * 192 * 4);

      final mesh = await CaptureChannel.captureEightPointMesh();
      expect(mesh['pointsCount'], 8);
      expect((mesh['captures'] as List).length, 8);
      expect(mesh['feature_code'], 'D-05');
    });

    test('Browser EIP-1193 eth_signTypedData_v4 & Gnosis Safe SDK Interop (B6.2) sign and propose Safe txs', () async {
      final eip712Res = await walletService.signTypedDataV4(
        primaryType: 'GenesisDossier',
        domain: {'name': 'ArthenticNFT', 'version': '1', 'chainId': 84532},
        message: {'artist': walletService.address, 'royaltyBps': 500},
      );
      expect(eip712Res['signature'].toString().startsWith('0x'), isTrue);
      expect(eip712Res['method'], 'eth_signTypedData_v4');

      final safeRes = await walletService.proposeSafeMultisigTransaction(
        toContract: ArthenticContractConfig.arthenticNftAddress,
        functionName: 'genesisMint',
        dataHex: '0x12345678',
      );
      expect(safeRes['safeTxHash'].toString().startsWith('0x'), isTrue);
      expect(safeRes['threshold'], '2-of-3');
    });

    testWidgets('D-14* Standalone Deep-Link Route renders Zero-Install Public NFC Tap Web Viewer', (tester) async {
      await tester.pumpWidget(
        const ArthenticApp(
          initialRoute: '/verify?uid=04A1B2C3D4E580&ctr=77&cmac=A9E38F107B5C2D44',
        ),
      );
      await tester.pump(const Duration(seconds: 4));
      expect(find.textContaining('Public NFC Tap Verification'), findsOneWidget);
      expect(find.textContaining('04A1B2C3D4E580'), findsOneWidget);
    });

    testWidgets('Milestone 4 Web Routing resolves /coa, /verify, and Institutional Consoles', (tester) async {
      await tester.pumpWidget(
        const ArthenticApp(
          initialRoute: '/coa?tokenId=101',
        ),
      );
      await tester.pump(const Duration(seconds: 6));
      expect(find.text('Certificate of Authenticity'), findsWidgets);

      await tester.pumpWidget(
        const ArthenticApp(
          initialRoute: '/console/gallery',
        ),
      );
      await tester.pump();
      expect(find.text('Institutional Verifier Console'), findsOneWidget);

      await tester.pumpWidget(
        const ArthenticApp(
          initialRoute: '/console/conservator',
        ),
      );
      await tester.pump();
      expect(find.text('Conservation Studio Workspace'), findsOneWidget);

      await tester.pumpWidget(
        const ArthenticApp(
          initialRoute: '/console/admin',
        ),
      );
      await tester.pump();
      expect(find.text('Security Incident & Governance Console'), findsOneWidget);
    });

    testWidgets('Milestone 4 Responsive Shell switches between Mobile BottomNav (<900px) and Desktop NavigationRail (>=900px)', (tester) async {
      tester.view.physicalSize = const Size(1440, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });

      await tester.pumpWidget(
        const MaterialApp(
          home: MainTabShell(),
        ),
      );
      await tester.pump();
      expect(find.byType(NavigationRail), findsOneWidget);
      expect(find.text('Gallery Safe'), findsOneWidget);
      expect(find.text('Conservator'), findsOneWidget);
      expect(find.text('Governance'), findsOneWidget);
    });
  });
}
