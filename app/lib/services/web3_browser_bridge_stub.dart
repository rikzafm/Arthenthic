/// Native / VM fallback for Browser EIP-1193 & Gnosis Safe Apps SDK interop.
class Web3BrowserBridge {
  static bool get isEthereumAvailable => false;
  static bool get isSafeAppContext => false;

  static Future<String?> requestEthereumAccount() async => null;

  static Future<String?> signTypedDataV4({
    required String address,
    required String typedDataJson,
  }) async =>
      null;

  static Future<String?> proposeSafeTransaction({
    required String to,
    required String value,
    required String data,
  }) async =>
      null;
}

