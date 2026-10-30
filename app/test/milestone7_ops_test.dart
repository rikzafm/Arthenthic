import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:app/contracts/contract_config.dart';
import 'package:app/features/web_consoles/admin_incident_console.dart';

void main() {
  group('Wave 3 Milestone 7 - Production Ops, Multi-Region KMS & SLA Rollout Governor Tests', () {
    test('ArthenticContractConfig exposes Multi-Region KMS Cluster endpoints and regions', () {
      final cluster = ArthenticContractConfig.multiRegionKmsClusterConfig();
      expect(cluster['primaryRegion'], equals('us-east-1'));
      expect(cluster['secondaryRegion'], equals('eu-west-1'));
      expect(cluster['tertiaryRegion'], equals('ap-southeast-1'));
      expect(cluster['regions'], contains('us-east-1'));
      expect(cluster['regions'], contains('eu-west-1'));
      expect(cluster['regions'], contains('ap-southeast-1'));
      expect(ArthenticContractConfig.isMultiRegionClusterEnabled(), isTrue);
    });

    test('ArthenticContractConfig exposes on-chain governance decentralization manifest', () {
      final gov = ArthenticContractConfig.governanceDecentralizationManifest();
      expect(gov['isDecentralized'], isTrue);
      expect(gov['safeThreshold'], equals('3-of-5'));
      expect(gov['timelockDelayHours'], equals(48));
      expect(gov['adminSafeAddress'].startsWith('0x'), isTrue);
      expect(gov['timelockAddress'].startsWith('0x'), isTrue);
      expect(gov['deployerAdminRevoked'], isTrue);
    });

    test('ArthenticContractConfig defines SLA monitoring thresholds and Edge CDN manifest', () {
      final sla = ArthenticContractConfig.slaMonitoringThresholds;
      expect(sla['maxLoginFailureRatePct'], equals(2.5));
      expect(sla['maxRefreshFailureRatePct'], equals(0.8));
      expect(sla['maxP0TamperAlerts'], equals(0));
      expect(sla['maxP0TokenReuseAlerts'], equals(0));

      final cdn = ArthenticContractConfig.edgeCdnManifest();
      expect(cdn['edgeVerifyBaseUrl'], equals('https://verify.arthentic.io'));
      expect(cdn['staticAssetTtlSeconds'], equals(86400));
      expect(cdn['dynamicVerifyTtlSeconds'], equals(0));
    });

    testWidgets('AdminIncidentConsole displays Multi-Region KMS and SLA Rollout controls', (tester) async {
      await tester.binding.setSurfaceSize(const Size(1280, 900));

      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: AdminIncidentConsole(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Check for Admin Console headers and Milestone 7 sections
      expect(find.text('Security Incident & Governance Console'), findsOneWidget);
      expect(find.text('Multi-Region KMS Cluster & Rollout Governor (M7)'), findsOneWidget);
      expect(find.text('US-East-1 (Primary)'), findsOneWidget);
      expect(find.text('EU-West-1 (Failover)'), findsOneWidget);
      expect(find.text('AP-Southeast-1 (Tertiary)'), findsOneWidget);
      expect(find.text('Staged Rollout Governor'), findsOneWidget);
    });
  });
}
