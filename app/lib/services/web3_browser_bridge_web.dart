import 'dart:js_interop';
import 'dart:js_interop_unsafe';

/// Flutter Web (kIsWeb) EIP-1193 (window.ethereum) & Gnosis Safe Apps SDK interop (Phase B6.2).
class Web3BrowserBridge {
  static bool get isEthereumAvailable => globalContext.has('ethereum');
  static bool get isSafeAppContext => globalContext.has('safeAppsSdk');

  static Future<String?> requestEthereumAccount() async {
    if (!isEthereumAvailable) return null;
    try {
      final ethereum = globalContext['ethereum'] as JSObject?;
      if (ethereum == null) return null;
      final reqObj = JSObject();
      reqObj['method'] = 'eth_requestAccounts'.toJS;
      final promise = ethereum.callMethod<JSPromise<JSAny?>>('request'.toJS, reqObj);
      final res = await promise.toDart;
      return res?.toString();
    } catch (_) {
      return null;
    }
  }

  static Future<String?> signTypedDataV4({
    required String address,
    required String typedDataJson,
  }) async {
    if (!isEthereumAvailable) return null;
    try {
      final ethereum = globalContext['ethereum'] as JSObject?;
      if (ethereum == null) return null;
      final reqObj = JSObject();
      reqObj['method'] = 'eth_signTypedData_v4'.toJS;
      reqObj['params'] = <JSAny?>[address.toJS, typedDataJson.toJS].toJS;
      final promise = ethereum.callMethod<JSPromise<JSAny?>>('request'.toJS, reqObj);
      final res = await promise.toDart;
      return res?.toString();
    } catch (_) {
      return null;
    }
  }

  static Future<String?> proposeSafeTransaction({
    required String to,
    required String value,
    required String data,
  }) async {
    if (!isSafeAppContext) return null;
    try {
      final safeSdk = globalContext['safeAppsSdk'] as JSObject?;
      if (safeSdk == null) return null;
      final txs = safeSdk['txs'] as JSObject?;
      if (txs == null) return null;
      final txItem = JSObject();
      txItem['to'] = to.toJS;
      txItem['value'] = value.toJS;
      txItem['data'] = data.toJS;
      final payload = JSObject();
      payload['txs'] = <JSAny?>[txItem].toJS;
      final promise = txs.callMethod<JSPromise<JSAny?>>('send'.toJS, payload);
      final res = await promise.toDart;
      return res?.toString();
    } catch (_) {
      return null;
    }
  }
}

