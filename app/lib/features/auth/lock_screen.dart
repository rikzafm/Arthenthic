import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme.dart';
import '../../main.dart';
import '../../services/api_client.dart';
import '../../services/app_lock_service.dart';
import '../shared/artistic_background.dart';
import 'widgets/pin_pad_sheet.dart';
import 'welcome_screen.dart';

class LockScreen extends StatefulWidget {
  final bool autoPrompt;
  final VoidCallback? onUnlocked;
  final AppLockService? lockService;

  const LockScreen({
    super.key,
    this.autoPrompt = true,
    this.onUnlocked,
    this.lockService,
  });

  @override
  State<LockScreen> createState() => _LockScreenState();
}

class _LockScreenState extends State<LockScreen> {
  String? _statusMessage;
  bool _isPrompting = false;
  BiometricKind _biometricKind = BiometricKind.genericBiometric;

  AppLockService get _service => widget.lockService ?? appLockService;

  @override
  void initState() {
    super.initState();
    _checkBiometricKind();
    if (widget.autoPrompt) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _promptBiometric();
      });
    }
  }

  Future<void> _checkBiometricKind() async {
    final kind = await _service.getBiometricKind();
    if (mounted) {
      setState(() {
        _biometricKind = kind;
      });
    }
  }

  String get _biometricTitleSuffix {
    switch (_biometricKind) {
      case BiometricKind.touchId:
        return 'Touch ID';
      case BiometricKind.faceId:
        return 'Face ID';
      case BiometricKind.genericBiometric:
      default:
        return 'Face ID or Touch ID';
    }
  }

  String get _biometricTitle {
    switch (_biometricKind) {
      case BiometricKind.touchId:
        return 'Unlock with Touch ID';
      case BiometricKind.faceId:
        return 'Unlock with Face ID';
      case BiometricKind.genericBiometric:
      default:
        return 'Unlock with Face ID or Touch ID';
    }
  }

  String get _biometricSubtitle {
    switch (_biometricKind) {
      case BiometricKind.touchId:
        return 'Authenticate with Touch ID or your device passcode to access your authenticated session.';
      case BiometricKind.faceId:
        return 'Authenticate with Face ID or your device passcode to access your authenticated session.';
      case BiometricKind.genericBiometric:
      default:
        return 'Authenticate with Face ID, Touch ID, or your device passcode to access your authenticated session.';
    }
  }

  IconData get _biometricIcon {
    switch (_biometricKind) {
      case BiometricKind.touchId:
        return Icons.fingerprint_rounded;
      case BiometricKind.faceId:
        return Icons.face_unlock_outlined;
      case BiometricKind.genericBiometric:
      default:
        return Icons.fingerprint_rounded;
    }
  }

  void _handleUnlockSuccess() {
    _service.unlock();
    if (widget.onUnlocked != null) {
      widget.onUnlocked!();
    } else if (mounted) {
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const MainTabShell()),
      );
    }
  }

  Future<void> _promptBiometric({bool passcodeFallback = false}) async {
    if (passcodeFallback) {
      PinPadBottomSheet.show(
        context,
        lockService: _service,
        onSuccess: _handleUnlockSuccess,
      );
      return;
    }

    if (_isPrompting) return;
    setState(() {
      _isPrompting = true;
      _statusMessage = null;
    });

    try {
      final success = await _service.authenticate(
        reason: 'Unlock Arthentic with $_biometricTitleSuffix',
        biometricOnly: false,
      );

      if (!mounted) return;

      if (success) {
        _handleUnlockSuccess();
      } else {
        setState(() {
          _statusMessage = 'Authentication required. Tap to try again or use passcode.';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _isPrompting = false;
        });
      }
    }
  }

  Future<void> _handleSignOut() async {
    await apiClient.logout();
    _service.unlock();
    _service.isGuest = true;
    if (!mounted) return;

    Navigator.pushAndRemoveUntil(
      context,
      MaterialPageRoute(builder: (_) => const WelcomeScreen()),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bgLight,
      body: ArtisticBackground(
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 28.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Spacer(),

                // Face ID / Shield Icon
                Container(
                  width: 90,
                  height: 90,
                  decoration: BoxDecoration(
                    color: Colors.white,
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: AppTheme.brandBlue.withOpacity(0.12),
                        blurRadius: 24,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                  child: Center(
                    child: Icon(
                      _biometricKind == BiometricKind.touchId
                          ? Icons.fingerprint_rounded
                          : (_biometricKind == BiometricKind.faceId
                              ? Icons.face_unlock_outlined
                              : Icons.lock_outline_rounded),
                      size: 44,
                      color: AppTheme.brandBlue,
                    ),
                  ),
                ),
                const SizedBox(height: 28),

                // Title
                Text(
                  'Arthentic is Locked.',
                  style: GoogleFonts.newsreader(
                    fontSize: 34,
                    fontWeight: FontWeight.w600,
                    fontStyle: FontStyle.italic,
                    color: AppTheme.textPrimary,
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  _biometricSubtitle,
                  textAlign: TextAlign.center,
                  style: GoogleFonts.inter(
                    fontSize: 14,
                    color: AppTheme.textSecondary,
                    height: 1.4,
                  ),
                ),
                const SizedBox(height: 24),

                // Error / Status Badge
                if (_statusMessage != null) ...[
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                    decoration: BoxDecoration(
                      color: AppTheme.goldBadgeBg,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: AppTheme.goldBadgeText.withOpacity(0.3)),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.info_outline, size: 16, color: AppTheme.goldBadgeText),
                        const SizedBox(width: 8),
                        Flexible(
                          child: Text(
                            _statusMessage!,
                            style: GoogleFonts.inter(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                              color: AppTheme.goldBadgeText,
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),
                ],

                const Spacer(),

                // Unlock Button
                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: ElevatedButton(
                    key: const Key('lock_unlock_button'),
                    onPressed: _isPrompting ? null : () => _promptBiometric(passcodeFallback: false),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.brandBlue,
                      foregroundColor: Colors.white,
                      elevation: 0,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                    child: _isPrompting
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(
                              strokeWidth: 2.5,
                              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                            ),
                          )
                        : Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(_biometricIcon, size: 20),
                              const SizedBox(width: 8),
                              Text(
                                _biometricTitle,
                                style: GoogleFonts.inter(
                                  fontSize: 15,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          ),
                  ),
                ),
                const SizedBox(height: 12),

                // Passcode fallback button
                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: OutlinedButton(
                    key: const Key('lock_passcode_button'),
                    onPressed: _isPrompting ? null : () => _promptBiometric(passcodeFallback: true),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppTheme.textPrimary,
                      side: const BorderSide(color: AppTheme.borderLight, width: 1.2),
                      backgroundColor: Colors.white,
                      elevation: 0,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                    child: Text(
                      'Use device passcode',
                      style: GoogleFonts.inter(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 16),

                // Debug Simulator Bypass
                if (kDebugMode) ...[
                  TextButton.icon(
                    key: const Key('lock_dev_simulate_button'),
                    onPressed: () {
                      _service.devSimulateUnlock();
                      _handleUnlockSuccess();
                    },
                    icon: const Icon(Icons.developer_mode, size: 16, color: AppTheme.brandBlue),
                    label: Text(
                      'Simulate Biometric Unlock (Dev)',
                      style: GoogleFonts.inter(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: AppTheme.brandBlue,
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                ],

                // Sign Out
                TextButton(
                  key: const Key('lock_signout_button'),
                  onPressed: _handleSignOut,
                  child: Text(
                    'Sign out',
                    style: GoogleFonts.inter(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: const Color(0xFFDC2626),
                      decoration: TextDecoration.underline,
                    ),
                  ),
                ),
                const SizedBox(height: 28),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
