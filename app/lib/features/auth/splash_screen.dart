import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme.dart';
import '../../main.dart';
import '../../services/api_client.dart';
import '../../services/session_store.dart';
import '../../services/app_lock_service.dart';
import '../shared/artistic_background.dart';
import 'login_screen.dart';
import 'welcome_screen.dart';

class SplashScreen extends StatefulWidget {
  final bool autoRoute;

  const SplashScreen({super.key, this.autoRoute = true});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  @override
  void initState() {
    super.initState();
    if (widget.autoRoute) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _checkSession();
      });
    }
  }

  Future<void> _checkSession() async {
    if (!mounted) return;

    final hasStoredSession = await sessionStore.hasSession();
    if (!mounted) return;

    if (!hasStoredSession) {
      appLockService.isGuest = true;
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const WelcomeScreen()),
      );
      return;
    }

    final restored = await apiClient.restoreSession();
    if (!mounted) return;

    if (restored) {
      appLockService.isGuest = false;
      appLockService.lock();
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const MainTabShell()),
      );
    } else {
      appLockService.isGuest = true;
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => const LoginScreen(sessionExpired: true),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bgLight,
      body: ArtisticBackground(
        child: SafeArea(
          child: Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  width: 72,
                  height: 72,
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(20),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.06),
                        blurRadius: 16,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: const Center(
                    child: Icon(
                      Icons.fingerprint,
                      size: 40,
                      color: AppTheme.brandBlue,
                    ),
                  ),
                ),
                const SizedBox(height: 24),
                Text(
                  'Arthentic',
                  style: GoogleFonts.inter(
                    fontSize: 28,
                    fontWeight: FontWeight.w800,
                    color: AppTheme.textPrimary,
                    letterSpacing: -0.5,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Physical Canvas Verification',
                  style: GoogleFonts.inter(
                    fontSize: 14,
                    color: AppTheme.textSecondary,
                  ),
                ),
                const SizedBox(height: 36),
                const SizedBox(
                  width: 24,
                  height: 24,
                  child: CircularProgressIndicator(
                    strokeWidth: 2.5,
                    valueColor: AlwaysStoppedAnimation<Color>(AppTheme.brandBlue),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
