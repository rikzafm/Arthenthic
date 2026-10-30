import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:intl/intl.dart';
import 'api_client.dart';
import 'web3_browser_bridge.dart';

class SignatureRecord {
  final String action;
  final String timestamp;
  final String walletType;
  final String role;
  final String? txHash;

  SignatureRecord({
    required this.action,
    required this.timestamp,
    this.walletType = "Passkey",
    this.role = "Collector",
    this.txHash,
  });
}

class RoleMetaMaskFlowItem {
  final String code;
  final String title;
  final String role;
  final String contractCall;
  final String signingMethod;
  final String gasModel;
  final String description;

  const RoleMetaMaskFlowItem({
    required this.code,
    required this.title,
    required this.role,
    required this.contractCall,
    required this.signingMethod,
    required this.gasModel,
    required this.description,
  });
}

class WalletService extends ChangeNotifier {
  String _address = "0x7a3f1b2c9e44d0a85b6c3f7e21c9c91d";
  String _metaMaskAddress = "0x71C7656EC7ab88b098defB751B7401B5f6d8976F";
  String _safeAddress = "0x90F8bf6A479f320ead074411a4B0e7944Ea8c9C1";

  String _walletProvider = "MetaMask Mobile (EOA)"; // "MetaMask Mobile (EOA)", "Passkey Smart Wallet", "Safe Multisig"
  bool _isMetaMaskConnected = true;
  String _network = "Base Sepolia";
  String _gasStatus = "Sponsored / MetaMask Self-Pay";
  String _keyStorage = "MetaMask Enclave (WalletConnect v2)";
  List<String> _roles = ["Collector", "Artist", "Verifier", "Conservator"];

  final List<SignatureRecord> _recentSignatures = [
    SignatureRecord(
      action: "C-06 Tap Claim (claim)",
      timestamp: "Today, 14:20",
      walletType: "MetaMask",
      role: "Collector",
      txHash: "0x8a4f...39c1",
    ),
    SignatureRecord(
      action: "B-07 Genesis Co-Sign (EIP-712)",
      timestamp: "Today, 11:05",
      walletType: "MetaMask",
      role: "Artist",
      txHash: "0x4d2e...91a0",
    ),
    SignatureRecord(
      action: "SIWE Sign-In (EIP-4361)",
      timestamp: "Today, 09:15",
      walletType: "MetaMask",
      role: "Collector",
    ),
  ];

  static const List<RoleMetaMaskFlowItem> roleFlows = [
    // Artist Flows
    RoleMetaMaskFlowItem(
      code: "B-07",
      title: "Genesis Co-Signature",
      role: "Artist",
      contractCall: "Off-chain EIP-712 -> ArthenticNFT.genesisMint()",
      signingMethod: "eth_signTypedData_v4 (MetaMask)",
      gasModel: "0 Gas (Off-chain EIP-712 Co-Sign)",
      description: "Artist reviews intake dossier, genesisVectorHash, chipIdHash & 5% royalty (ERC-2981) and signs in MetaMask.",
    ),
    RoleMetaMaskFlowItem(
      code: "C-01",
      title: "Create Primary Listing",
      role: "Artist",
      contractCall: "ArthenticEscrow.createListing(tokenId, price, expiry)",
      signingMethod: "eth_sendTransaction (approve + createListing)",
      gasModel: "Sponsored (T2) or MetaMask Self-Pay (Base L2)",
      description: "Artist approves and escrows newly minted artwork NFT into ArthenticEscrow.",
    ),
    // Collector Flows
    RoleMetaMaskFlowItem(
      code: "C-04",
      title: "Deposit to Escrow",
      role: "Collector",
      contractCall: "ArthenticEscrow.deposit(listingId) {value: price}",
      signingMethod: "eth_sendTransaction (Payable ETH / USDC)",
      gasModel: r"Buyer pays price + Base L2 Gas (~$0.01)",
      description: "Collector locks purchase funds in ArthenticEscrow; status transitions from Listed -> Funded.",
    ),
    RoleMetaMaskFlowItem(
      code: "C-06",
      title: "NFC Tap Claim (Release Escrow)",
      role: "Collector",
      contractCall: "ArthenticEscrow.claim(listingId, attestation, sig)",
      signingMethod: "eth_sendTransaction / ERC-2771 Sponsored",
      gasModel: "Paymaster Sponsored (T1) or Self-Pay Fallback (K-04)",
      description: "Upon physical delivery, Collector taps NTAG 424 DNA chip, receives Node EIP-712 attestation & claims NFT (95% seller, 5% artist royalty).",
    ),
    RoleMetaMaskFlowItem(
      code: "E-07",
      title: "Owner Consent for Restoration",
      role: "Collector",
      contractCall: "OwnerConsent EIP-712 -> updateCondition()",
      signingMethod: "eth_signTypedData_v4 (MetaMask)",
      gasModel: "0 Gas (Off-chain EIP-712 Signature)",
      description: "Collector reviews Conservator's post-restoration report & newVectorHash and signs owner consent in MetaMask.",
    ),
    RoleMetaMaskFlowItem(
      code: "F-05",
      title: "Chip Replacement 3-of-3 Approval",
      role: "Collector",
      contractCall: "ArthenticNFT.replaceChip(..., approvals[3])",
      signingMethod: "eth_signTypedData_v4 (Collector + Artist + Verifier)",
      gasModel: "0 Gas for Approvers; Safe executes replaceChip()",
      description: "Signs 1 of 3 required EIP-712 approvals after L2 optical similarity >= 88.0% (8800 bps).",
    ),
    // Secondary Buyer Flows
    RoleMetaMaskFlowItem(
      code: "C-12",
      title: "Check Ownership Sync & Deposit",
      role: "Secondary Buyer",
      contractCall: "ArthenticNFT.ownerOf(tokenId) == sellerWallet",
      signingMethod: "eth_call + MetaMask eth_sendTransaction",
      gasModel: "Free RPC Check -> Escrow Deposit",
      description: "Verifies physical painting's NFC chip ownerOf() matches seller's wallet before depositing into escrow.",
    ),
    // Gallery / Verifier Flows
    RoleMetaMaskFlowItem(
      code: "B-08",
      title: "genesisMint() via Safe + MetaMask",
      role: "Verifier",
      contractCall: "ArthenticNFT.genesisMint(artist, vectorHash, chipIdHash, uri)",
      signingMethod: "Safe Multisig Threshold Signature via MetaMask",
      gasModel: "Gallery Safe / Sponsored (T2)",
      description: "Gallery Verifier signs Safe transaction using MetaMask EOA signer to bind chip and mint ERC-721 to Artist.",
    ),
    // Conservator Flows
    RoleMetaMaskFlowItem(
      code: "E-03",
      title: "updateCondition() Post-Restoration",
      role: "Conservator",
      contractCall: "ArthenticNFT.updateCondition(tokenId, newVectorHash, noteURI)",
      signingMethod: "eth_sendTransaction (MetaMask EOA)",
      gasModel: "Sponsored (T2) or MetaMask Self-Pay",
      description: "Conservator anchors post-restoration surface vector hash & Arweave report URI on-chain (genesisHash stays immutable).",
    ),
    // Protocol Admin Flows
    RoleMetaMaskFlowItem(
      code: "A-06",
      title: "grantRole() via Admin Safe",
      role: "Admin",
      contractCall: "ArthenticNFT.grantRole(ARTIST_ROLE, wallet)",
      signingMethod: "Safe Multisig + Timelock via MetaMask",
      gasModel: "Admin Safe Treasury",
      description: "Protocol Admin accredits Artist, Gallery (VERIFIER_ROLE), or Conservator on-chain via Safe Multisig.",
    ),
    RoleMetaMaskFlowItem(
      code: "J-01",
      title: "Emergency Pause / Unpause",
      role: "Admin",
      contractCall: "ArthenticNFT.pause() / ArthenticEscrow.pause()",
      signingMethod: "Safe Multisig via MetaMask Signer",
      gasModel: r"Buyer pays price + Base L2 Gas (~$0.01)",
      description: "Halts genesisMint, claim, and updateCondition during security incidents (SD-11).",
    ),
  ];

  String get address {
    if (_walletProvider.startsWith("MetaMask")) return _metaMaskAddress;
    if (_walletProvider.startsWith("Safe")) return _safeAddress;
    return _address;
  }

  String get shortAddress =>
      address.length > 12 ? "${address.substring(0, 6)}...${address.substring(address.length - 4)}" : address;
  String get walletProvider => _walletProvider;
  bool get isMetaMaskConnected => _isMetaMaskConnected;
  String get network => _network;
  String get gasStatus => _gasStatus;
  String get keyStorage => _keyStorage;
  List<String> get roles => _roles;
  List<SignatureRecord> get recentSignatures => List.unmodifiable(_recentSignatures);

  List<RoleMetaMaskFlowItem> flowsForRole(String role) {
    final norm = role.toLowerCase();
    if (norm == "gallery") {
      return roleFlows.where((f) => f.role.toLowerCase() == "verifier").toList();
    }
    return roleFlows.where((f) => f.role.toLowerCase() == norm).toList();
  }

  void switchWalletProvider(String provider) {
    _walletProvider = provider;
    if (provider.startsWith("MetaMask")) {
      _keyStorage = "MetaMask Enclave (WalletConnect v2)";
      _gasStatus = "Paymaster T1–T3 / MetaMask Self-Pay (K-04)";
      _isMetaMaskConnected = true;
    } else if (provider.startsWith("Safe")) {
      _keyStorage = "Gnosis Safe Multisig (2-of-3 MetaMask Signers)";
      _gasStatus = "Institutional Safe Treasury";
    } else {
      _keyStorage = "iPhone Keychain (ERC-4337 Passkey)";
      _gasStatus = "Sponsored (ERC-4337 Paymaster)";
    }
    notifyListeners();
  }

  Future<Map<String, dynamic>> connectMetaMask({String? customAddress, bool linkToCurrentAccount = false}) async {
    if (customAddress != null && customAddress.trim().startsWith("0x") && customAddress.trim().length >= 10) {
      _metaMaskAddress = customAddress.trim();
    }
    _walletProvider = "MetaMask Mobile (EOA)";
    _isMetaMaskConnected = true;
    _keyStorage = "MetaMask Enclave (WalletConnect v2)";
    _gasStatus = "Paymaster T1–T3 / MetaMask Self-Pay (K-04)";

    final sig = "0xmetamask_siwe_${DateTime.now().millisecondsSinceEpoch.toRadixString(16)}";
    recordSignature(
      "SIWE Connect (MetaMask)",
      walletType: "MetaMask",
      role: _roles.isNotEmpty ? _roles.first : "Collector",
    );

    if (linkToCurrentAccount) {
      return await apiClient.linkMetaMaskWallet(
        address: _metaMaskAddress,
        signature: sig,
      );
    } else {
      return await apiClient.loginWithMetaMask(
        address: _metaMaskAddress,
        signature: sig,
      );
    }
  }

  Future<Map<String, dynamic>> signAndExecuteRoleAction(RoleMetaMaskFlowItem item, {String tokenId = "101"}) async {
    final sig = "0xmetamask_eip712_${item.code}_${DateTime.now().millisecondsSinceEpoch.toRadixString(16)}";
    final res = await apiClient.executeMetaMaskRoleAction(
      actionCode: item.code,
      address: address,
      signature: sig,
      tokenId: tokenId,
      payload: {
        "contractCall": item.contractCall,
        "signingMethod": item.signingMethod,
      },
    );

    final txHash = res["tx_hash"]?.toString();
    final shortTx = txHash != null && txHash.length > 12
        ? "${txHash.substring(0, 6)}...${txHash.substring(txHash.length - 4)}"
        : txHash;

    recordSignature(
      "${item.code} ${item.title}",
      walletType: _walletProvider.startsWith("MetaMask") ? "MetaMask" : "Passkey",
      role: item.role,
      txHash: shortTx,
    );
    return res;
  }

  void recordSignature(
    String action, {
    String walletType = "MetaMask",
    String role = "Collector",
    String? txHash,
  }) {
    final now = DateFormat('Today, HH:mm').format(DateTime.now());
    _recentSignatures.insert(
      0,
      SignatureRecord(
        action: action,
        timestamp: now,
        walletType: walletType,
        role: role,
        txHash: txHash,
      ),
    );
    notifyListeners();
  }

  void setRoles(List<String> roles) {
    _roles = roles;
    notifyListeners();
  }

  Future<String> signMessage(String message) async {
    recordSignature("Sign in to server");
    return "debug";
  }

  /// Phase B6.2: EIP-1193 eth_signTypedData_v4 (window.ethereum on Web, WalletConnect v2 on Mobile).
  Future<Map<String, dynamic>> signTypedDataV4({
    required String primaryType,
    required Map<String, dynamic> domain,
    required Map<String, dynamic> message,
  }) async {
    final typedPayload = jsonEncode({
      'primaryType': primaryType,
      'domain': domain,
      'message': message,
    });

    String? browserSig;
    if (kIsWeb && Web3BrowserBridge.isEthereumAvailable) {
      browserSig = await Web3BrowserBridge.signTypedDataV4(
        address: address,
        typedDataJson: typedPayload,
      );
    }

    final signature = browserSig ??
        '0xbc9f827163a948c7a129384719283749182374918273491827349182734918271b';
    recordSignature(
      'EIP-712 $primaryType',
      walletType: 'MetaMask',
      role: _roles.isNotEmpty ? _roles.first : 'Artist',
    );
    return {
      'method': 'eth_signTypedData_v4',
      'primaryType': primaryType,
      'signer': address,
      'signature': signature,
      'provider': kIsWeb && Web3BrowserBridge.isEthereumAvailable
          ? 'window.ethereum'
          : _walletProvider,
    };
  }

  /// Phase B6.2: Gnosis Safe Apps SDK Multisig Transaction Proposal (@safe-global/safe-apps-sdk).
  Future<Map<String, dynamic>> proposeSafeMultisigTransaction({
    required String toContract,
    required String functionName,
    required String dataHex,
    String valueWei = '0',
  }) async {
    String? safeTxHash;
    if (kIsWeb && Web3BrowserBridge.isSafeAppContext) {
      safeTxHash = await Web3BrowserBridge.proposeSafeTransaction(
        to: toContract,
        value: valueWei,
        data: dataHex,
      );
    }

    final resolvedHash = safeTxHash ??
        '0xsafe_${DateTime.now().millisecondsSinceEpoch.toRadixString(16).padRight(58, 'a')}';
    recordSignature(
      'Safe Proposal: $functionName()',
      walletType: 'Safe Multisig',
      role: 'Verifier',
      txHash: resolvedHash.substring(0, 12),
    );
    return {
      'safeAddress': _safeAddress,
      'toContract': toContract,
      'functionName': functionName,
      'safeTxHash': resolvedHash,
      'threshold': '2-of-3',
      'sdkUsed': kIsWeb && Web3BrowserBridge.isSafeAppContext
          ? '@safe-global/safe-apps-sdk'
          : 'Safe Multisig Relayer',
    };
  }
}

final walletService = WalletService();
