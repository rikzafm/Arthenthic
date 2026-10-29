import 'package:flutter/foundation.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';
import 'api_client.dart';

typedef GoogleSignInHandler = Future<String?> Function();
typedef AppleSignInHandler = Future<String?> Function();

class OAuthService {
  final ApiClient _client;
  GoogleSignInHandler? customGoogleSignIn;
  AppleSignInHandler? customAppleSignIn;

  OAuthService({
    ApiClient? client,
    this.customGoogleSignIn,
    this.customAppleSignIn,
  }) : _client = client ?? apiClient;

  Future<Map<String, dynamic>> signInWithGoogle() async {
    try {
      String? idToken;
      if (customGoogleSignIn != null) {
        idToken = await customGoogleSignIn!();
        if (idToken == null) {
          return {"success": false, "cancelled": true};
        }
      } else {
        final account = await GoogleSignIn.instance.authenticate();
        idToken = account.authentication.idToken;
      }

      if (idToken == null || idToken.isEmpty) {
        return {"success": false, "error": "Unable to retrieve Google ID token."};
      }

      return await _client.loginWithGoogle(idToken: idToken);
    } on GoogleSignInException catch (e) {
      if (e.code == GoogleSignInExceptionCode.canceled) {
        return {"success": false, "cancelled": true};
      }
      return {"success": false, "error": "Google Sign-In failed: ${e.description ?? e.code.name}"};
    } catch (e) {
      debugPrint('Google Sign-In Error: $e');
      return {"success": false, "error": "Google Sign-In failed. Please try again."};
    }
  }

  Future<Map<String, dynamic>> signInWithApple() async {
    try {
      String? idToken;
      if (customAppleSignIn != null) {
        idToken = await customAppleSignIn!();
        if (idToken == null) {
          return {"success": false, "cancelled": true};
        }
      } else {
        final credential = await SignInWithApple.getAppleIDCredential(
          scopes: [
            AppleIDAuthorizationScopes.email,
            AppleIDAuthorizationScopes.fullName,
          ],
        );
        idToken = credential.identityToken;
      }

      if (idToken == null || idToken.isEmpty) {
        return {"success": false, "error": "Unable to retrieve Apple identity token."};
      }

      return await _client.loginWithApple(idToken: idToken);
    } on SignInWithAppleAuthorizationException catch (e) {
      if (e.code == AuthorizationErrorCode.canceled) {
        return {"success": false, "cancelled": true};
      }
      return {"success": false, "error": "Apple Sign-In failed: ${e.message}"};
    } catch (e) {
      debugPrint('Apple Sign-In Error: $e');
      return {"success": false, "error": "Apple Sign-In failed. Please try again."};
    }
  }
}

final oAuthService = OAuthService();
