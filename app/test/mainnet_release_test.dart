import 'package:flutter_test/flutter_test.dart';
import 'package:app/contracts/contract_config.dart';

void main() {
  group('Wave 3 Milestone 6 - Mainnet Launch Readiness & Staged Rollout Tests', () {
    test('ArthenticContractConfig exposes Base Mainnet (8453) & Ethereum Mainnet (1) constants', () {
      expect(ArthenticContractConfig.baseMainnetChainId, equals(8453));
      expect(ArthenticContractConfig.ethereumMainnetChainId, equals(1));

      expect(ArthenticContractConfig.mainnetNftAddress.startsWith('0x'), isTrue);
      expect(ArthenticContractConfig.mainnetEscrowAddress.startsWith('0x'), isTrue);
      expect(ArthenticContractConfig.mainnetMerkleAnchorAddress.startsWith('0x'), isTrue);
      expect(ArthenticContractConfig.mainnetGnosisSafeAddress.startsWith('0x'), isTrue);
      expect(ArthenticContractConfig.mainnetTimelockAddress.startsWith('0x'), isTrue);
    });

    test('ArthenticContractConfig generates activeMainnetManifest and confirms live readiness', () {
      final manifest = ArthenticContractConfig.activeMainnetManifest();
      expect(manifest['baseMainnet']['chainId'], equals(8453));
      expect(manifest['ethereumMainnet']['chainId'], equals(1));
      expect(manifest['governance']['timelockDelayHours'], equals(48));
      expect(manifest['governance']['safeQuorum'], equals('3-of-5'));
      expect(ArthenticContractConfig.isLiveMainnetConfigured(), isTrue);
    });

    test('mainnetCdnVerifyUrl generates canonical CDN URL for Zero-Install NFC taps', () {
      final url = ArthenticContractConfig.mainnetCdnVerifyUrl('101');
      expect(url, equals('https://verify.arthentic.io/101'));

      final defaultUrl = ArthenticContractConfig.mainnetCdnVerifyUrl();
      expect(defaultUrl, equals('https://verify.arthentic.io'));
    });

    test('Staged rollout schedule defines exact 7-day phased percentages', () {
      final schedule = ArthenticContractConfig.stagedRolloutPercentages;
      expect(schedule[1], equals(1));
      expect(schedule[2], equals(2));
      expect(schedule[3], equals(5));
      expect(schedule[4], equals(10));
      expect(schedule[5], equals(20));
      expect(schedule[6], equals(50));
      expect(schedule[7], equals(100));
    });
  });
}

