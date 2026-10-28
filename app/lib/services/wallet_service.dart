import 'package:flutter/foundation.dart';
import 'package:intl/intl.dart';

class SignatureRecord {
  final String action;
  final String timestamp;

  SignatureRecord({required this.action, required this.timestamp});
}

class WalletService extends ChangeNotifier {
  // Default wallet address matching design artifact
  String _address = "0x7a3f1b2c9e44d0a85b6c3f7e21c9c91d";
  String _network = "Base Sepolia";
  String _gasStatus = "Sponsored";
  String _keyStorage = "iPhone Keychain";
  List<String> _roles = ["Collector", "Verifier"];

  final List<SignatureRecord> _recentSignatures = [
    SignatureRecord(action: "recordVerification", timestamp: "Today, 14:20"),
    SignatureRecord(action: "Sign in to server", timestamp: "Today, 09:15"),
  ];

  String get address => _address;
  String get shortAddress =>
      _address.length > 12 ? "${_address.substring(0, 6)}...${_address.substring(_address.length - 4)}" : _address;
  String get network => _network;
  String get gasStatus => _gasStatus;
  String get keyStorage => _keyStorage;
  List<String> get roles => _roles;
  List<SignatureRecord> get recentSignatures => List.unmodifiable(_recentSignatures);

  void recordSignature(String action) {
    final now = DateFormat('Today, HH:mm').format(DateTime.now());
    _recentSignatures.insert(0, SignatureRecord(action: action, timestamp: now));
    notifyListeners();
  }

  void setRoles(List<String> roles) {
    _roles = roles;
    notifyListeners();
  }

  Future<String> signMessage(String message) async {
    recordSignature("Sign in to server");
    // Return debug signature accepted by prototype server
    return "debug";
  }
}

final walletService = WalletService();

