import 'dart:ui';
import 'package:flutter/material.dart';
import '../../core/theme.dart';
import '../../services/app_lock_service.dart';
import 'lock_screen.dart';

class AppLockGate extends StatefulWidget {
  final Widget child;
  final bool enableLock;

  const AppLockGate({
    super.key,
    required this.child,
    this.enableLock = true,
  });

  @override
  State<AppLockGate> createState() => _AppLockGateState();
}

class _AppLockGateState extends State<AppLockGate> with WidgetsBindingObserver {
  bool _isBackgrounded = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    appLockService.addListener(_onLockChanged);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    appLockService.removeListener(_onLockChanged);
    super.dispose();
  }

  void _onLockChanged() {
    if (mounted) setState(() {});
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!widget.enableLock || appLockService.isGuest) return;

    if (state == AppLifecycleState.inactive || state == AppLifecycleState.paused) {
      setState(() => _isBackgrounded = true);
      appLockService.handleAppLifecycle(state);
    } else if (state == AppLifecycleState.resumed) {
      setState(() => _isBackgrounded = false);
      appLockService.handleAppLifecycle(state);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        widget.child,

        // Privacy Blur Shield for App-Switcher snapshot
        if (_isBackgrounded && !appLockService.isGuest)
          Positioned.fill(
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
              child: Container(
                color: AppTheme.brandDark.withOpacity(0.85),
                child: const Center(
                  child: Icon(
                    Icons.fingerprint,
                    size: 64,
                    color: Colors.white70,
                  ),
                ),
              ),
            ),
          ),

        // Lock Screen Overlay when app is locked
        if (appLockService.isLocked && !appLockService.isGuest)
          Positioned.fill(
            child: LockScreen(
              autoPrompt: true,
              onUnlocked: () {
                appLockService.unlock();
              },
            ),
          ),
      ],
    );
  }
}

