import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme.dart';
import '../../services/api_client.dart';
import '../../services/session_store.dart';
import '../../services/app_lock_service.dart';
import '../auth/welcome_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _isLoading = true;
  List<dynamic> _sessions = [];
  List<dynamic> _auditEvents = [];
  bool _emailVerified = false;
  String _userEmail = "";
  String _displayName = "";

  @override
  void initState() {
    super.initState();
    _loadSettingsData();
  }

  Future<void> _loadSettingsData() async {
    setState(() => _isLoading = true);
    try {
      final user = apiClient.currentUser;
      if (user != null) {
        _userEmail = user["email"] ?? "";
        _displayName = user["display_name"] ?? _userEmail.split('@').first;
        _emailVerified = user["email_verified_at"] != null;
      }

      final sessions = await apiClient.getSessions();
      if (mounted) {
        setState(() {
          _sessions = sessions;
          _isLoading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _handleRevokeSession(String sessionId) async {
    final res = await apiClient.revokeSession(sessionId);
    if (mounted) {
      if (res["success"] == true) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            backgroundColor: AppTheme.brandDark,
            content: Text("Session revoked successfully."),
          ),
        );
        _loadSettingsData();
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: Colors.red.shade800,
            content: Text(res["error"] ?? "Failed to revoke session"),
          ),
        );
      }
    }
  }

  void _showChangePasswordDialog() {
    final currentPassController = TextEditingController();
    final newPassController = TextEditingController();
    final confirmPassController = TextEditingController();
    String? errorText;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            return Padding(
              padding: EdgeInsets.only(
                left: 24,
                right: 24,
                top: 20,
                bottom: MediaQuery.of(context).viewInsets.bottom + 24,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        "Change Password",
                        style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w700),
                      ),
                      IconButton(
                        icon: const Icon(Icons.close, size: 20),
                        onPressed: () => Navigator.pop(ctx),
                      ),
                    ],
                  ),
                  if (errorText != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      errorText!,
                      style: GoogleFonts.inter(color: Colors.red.shade700, fontSize: 13, fontWeight: FontWeight.w600),
                    ),
                  ],
                  const SizedBox(height: 14),
                  Text("Current Password", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 6),
                  TextField(
                    controller: currentPassController,
                    obscureText: true,
                    decoration: InputDecoration(
                      hintText: "Enter current password",
                      filled: true,
                      fillColor: const Color(0xFFF8FAFC),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppTheme.borderLight)),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Text("New Password", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 6),
                  TextField(
                    controller: newPassController,
                    obscureText: true,
                    decoration: InputDecoration(
                      hintText: "At least 8 chars, 1 letter, 1 number",
                      filled: true,
                      fillColor: const Color(0xFFF8FAFC),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppTheme.borderLight)),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Text("Confirm New Password", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 6),
                  TextField(
                    controller: confirmPassController,
                    obscureText: true,
                    decoration: InputDecoration(
                      hintText: "Re-enter new password",
                      filled: true,
                      fillColor: const Color(0xFFF8FAFC),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppTheme.borderLight)),
                    ),
                  ),
                  const SizedBox(height: 20),
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: ElevatedButton(
                      onPressed: () async {
                        if (newPassController.text != confirmPassController.text) {
                          setModalState(() => errorText = "New passwords do not match.");
                          return;
                        }
                        final res = await apiClient.changePassword(
                          currentPassword: currentPassController.text.isNotEmpty ? currentPassController.text : null,
                          newPassword: newPassController.text,
                        );
                        if (mounted) {
                          if (res["success"] == true) {
                            Navigator.pop(ctx);
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                backgroundColor: AppTheme.brandDark,
                                content: Text("Password changed successfully! Other sessions revoked."),
                              ),
                            );
                          } else {
                            setModalState(() => errorText = res["error"] ?? "Password change failed.");
                          }
                        }
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppTheme.brandBlue,
                        foregroundColor: Colors.white,
                        elevation: 0,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                      child: Text("Update Password", style: GoogleFonts.inter(fontWeight: FontWeight.w600)),
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  void _showDeleteAccountConfirmation() {
    showDialog(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: Text("Delete Account?", style: GoogleFonts.inter(fontWeight: FontWeight.w700, color: Colors.red.shade900)),
          content: Text(
            "This action is permanent and cannot be undone. All active sessions will be terminated and your personal information will be completely anonymized.\n\nImmutable provenance events and blockchain records cannot be deleted per protocol design.",
            style: GoogleFonts.inter(fontSize: 13, color: AppTheme.textSecondary, height: 1.4),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: Text("Cancel", style: GoogleFonts.inter(color: AppTheme.textPrimary, fontWeight: FontWeight.w600)),
            ),
            ElevatedButton(
              onPressed: () async {
                Navigator.pop(ctx);
                final res = await apiClient.deleteAccount();
                if (mounted) {
                  if (res["success"] == true) {
                    appLockService.isGuest = true;
                    Navigator.pushAndRemoveUntil(
                      context,
                      MaterialPageRoute(builder: (_) => const WelcomeScreen()),
                      (route) => false,
                    );
                  } else {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        backgroundColor: Colors.red.shade800,
                        content: Text(res["error"] ?? "Account deletion failed"),
                      ),
                    );
                  }
                }
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.red.shade700,
                foregroundColor: Colors.white,
                elevation: 0,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              ),
              child: const Text("Permanently Delete"),
            ),
          ],
        );
      },
    );
  }

  Future<void> _handleSignOut() async {
    await apiClient.logout();
    await sessionStore.clearSession();
    appLockService.isGuest = true;
    if (mounted) {
      Navigator.pushAndRemoveUntil(
        context,
        MaterialPageRoute(builder: (_) => const WelcomeScreen()),
        (route) => false,
      );
    }
  }

  Future<void> _showAuditLogSheet() async {
    final events = await apiClient.getUserAuditLog();
    if (!mounted) return;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) {
        return Container(
          height: MediaQuery.of(context).size.height * 0.7,
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text("Security Activity Log", style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w700)),
                  IconButton(icon: const Icon(Icons.close, size: 20), onPressed: () => Navigator.pop(ctx)),
                ],
              ),
              const SizedBox(height: 12),
              Expanded(
                child: events.isEmpty
                    ? Center(child: Text("No security events recorded yet.", style: GoogleFonts.inter(color: AppTheme.textMuted)))
                    : ListView.separated(
                        itemCount: events.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (context, idx) {
                          final ev = events[idx];
                          return ListTile(
                            contentPadding: EdgeInsets.zero,
                            leading: Container(
                              padding: const EdgeInsets.all(8),
                              decoration: BoxDecoration(
                                color: AppTheme.brandBlue.withOpacity(0.1),
                                shape: BoxShape.circle,
                              ),
                              child: const Icon(Icons.shield_outlined, size: 18, color: AppTheme.brandBlue),
                            ),
                            title: Text(ev["action"] ?? "EVENT", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600)),
                            subtitle: Text("IP: ${ev['ip'] ?? 'unknown'}", style: GoogleFonts.inter(fontSize: 12, color: AppTheme.textSecondary)),
                            trailing: Text(
                              ev["created_at"] != null ? ev["created_at"].toString().split('T').first : "",
                              style: GoogleFonts.inter(fontSize: 11, color: AppTheme.textMuted),
                            ),
                          );
                        },
                      ),
              ),
            ],
          ),
        );
      },
    );
  }

  void _showEmailVerificationModal() {
    final tokenController = TextEditingController();
    bool codeSent = false;
    bool isSubmitting = false;
    String? errorText;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            return Padding(
              padding: EdgeInsets.only(
                left: 24,
                right: 24,
                top: 20,
                bottom: MediaQuery.of(context).viewInsets.bottom + 24,
              ),
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          "Verify Email Address",
                          style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w700),
                        ),
                        IconButton(
                          icon: const Icon(Icons.close, size: 20),
                          onPressed: () => Navigator.pop(ctx),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      codeSent
                          ? "Enter the verification code sent to $_userEmail:"
                          : "We will send a verification token to $_userEmail to confirm your ownership.",
                      style: GoogleFonts.inter(fontSize: 13, color: AppTheme.textSecondary),
                    ),
                    if (errorText != null) ...[
                      const SizedBox(height: 12),
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: const Color(0xFFFEE2E2),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          errorText!,
                          style: GoogleFonts.inter(color: Colors.red.shade800, fontSize: 13, fontWeight: FontWeight.w500),
                        ),
                      ),
                    ],
                    const SizedBox(height: 16),
                    if (!codeSent) ...[
                      SizedBox(
                        width: double.infinity,
                        height: 48,
                        child: ElevatedButton(
                          key: const Key('send_verification_email_button'),
                          onPressed: isSubmitting
                              ? null
                              : () async {
                                  setModalState(() {
                                    isSubmitting = true;
                                    errorText = null;
                                  });
                                  final res = await apiClient.requestEmailVerification();
                                  setModalState(() {
                                    isSubmitting = false;
                                    if (res["success"] == true) {
                                      codeSent = true;
                                      if (res["verify_token"] != null) {
                                        tokenController.text = res["verify_token"].toString();
                                      }
                                    } else {
                                      errorText = res["error"] ?? "Failed to send verification email.";
                                    }
                                  });
                                },
                          style: ElevatedButton.styleFrom(
                            backgroundColor: AppTheme.brandBlue,
                            foregroundColor: Colors.white,
                            elevation: 0,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                          ),
                          child: isSubmitting
                              ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, valueColor: AlwaysStoppedAnimation(Colors.white)))
                              : Text("Send Verification Link", style: GoogleFonts.inter(fontWeight: FontWeight.w600)),
                        ),
                      ),
                    ] else ...[
                      Text("Verification Token", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600)),
                      const SizedBox(height: 6),
                      TextField(
                        key: const Key('verify_token_field'),
                        controller: tokenController,
                        decoration: InputDecoration(
                          hintText: "Enter token from email",
                          filled: true,
                          fillColor: const Color(0xFFF8FAFC),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppTheme.borderLight)),
                        ),
                      ),
                      const SizedBox(height: 20),
                      SizedBox(
                        width: double.infinity,
                        height: 48,
                        child: ElevatedButton(
                          key: const Key('confirm_email_token_button'),
                          onPressed: isSubmitting
                              ? null
                              : () async {
                                  final token = tokenController.text.trim();
                                  if (token.isEmpty) {
                                    setModalState(() => errorText = "Token cannot be empty.");
                                    return;
                                  }
                                  setModalState(() {
                                    isSubmitting = true;
                                    errorText = null;
                                  });
                                  final res = await apiClient.confirmEmailVerification(token);
                                  if (mounted) {
                                    if (res["success"] == true) {
                                      setState(() => _emailVerified = true);
                                      Navigator.pop(ctx);
                                      ScaffoldMessenger.of(context).showSnackBar(
                                        const SnackBar(
                                          backgroundColor: AppTheme.brandDark,
                                          content: Text("Email successfully verified!"),
                                        ),
                                      );
                                    } else {
                                      setModalState(() {
                                        isSubmitting = false;
                                        errorText = res["error"] ?? "Invalid verification token.";
                                      });
                                    }
                                  }
                                },
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF059669),
                            foregroundColor: Colors.white,
                            elevation: 0,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                          ),
                          child: isSubmitting
                              ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, valueColor: AlwaysStoppedAnimation(Colors.white)))
                              : Text("Confirm Verification", style: GoogleFonts.inter(fontWeight: FontWeight.w600)),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  void _showPrivacyPolicyModal() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) {
        return Container(
          height: MediaQuery.of(context).size.height * 0.75,
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text("Privacy & Data Retention", style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w700)),
                  IconButton(icon: const Icon(Icons.close, size: 20), onPressed: () => Navigator.pop(ctx)),
                ],
              ),
              const SizedBox(height: 16),
              Expanded(
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text("Zero-PII Architecture & App Store Compliance", style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700, color: AppTheme.brandBlue)),
                      const SizedBox(height: 8),
                      Text(
                        "Arthentic Mobile is designed strictly around Apple App Store Guideline 5.1.1(v) for account deletion and user privacy:\n\n"
                        "• Local Biometrics: Face ID, Touch ID, and Passcode authentication execute entirely on-device within Apple's Secure Enclave. Biometric data is never transmitted to our servers.\n\n"
                        "• Account Anonymization: When you request account deletion, all personal data (email, name, password hash, OAuth links) is immediately and irreversibly wiped or anonymized. Active sessions are instantly revoked.\n\n"
                        "• Provenance & Cryptographic Immutability: Cryptographic hashes of artwork physical surface fingerprints, LiDAR depth vectors, and audit log IDs are preserved without personal identifiers to maintain decentralized artwork provenance integrity.\n\n"
                        "• No PII Crash Telemetry: Telemetry reports automatically scrub email addresses, access tokens, IP addresses, and private keys before leaving your device.",
                        style: GoogleFonts.inter(fontSize: 13, color: AppTheme.textSecondary, height: 1.5),
                      ),
                      const SizedBox(height: 24),
                      Text("Data Retention Schedule", style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700, color: AppTheme.textPrimary)),
                      const SizedBox(height: 8),
                      Text(
                        "• Refresh tokens: Automatically expired after 30 days absolute cap or revoked upon logout.\n"
                        "• Application documents: Encrypted at rest and purged following accreditation review.\n"
                        "• Audit logs: Retained for fraud detection and security investigations.",
                        style: GoogleFonts.inter(fontSize: 13, color: AppTheme.textSecondary, height: 1.5),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bgLight,
      appBar: AppBar(
        title: Text(
          "Settings & Security",
          style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w700, color: AppTheme.textPrimary),
        ),
        backgroundColor: Colors.white,
        elevation: 0,
        centerTitle: false,
        iconTheme: const IconThemeData(color: AppTheme.textPrimary),
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 1. Account Info Card
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(color: AppTheme.borderLight),
                    ),
                    child: Row(
                      children: [
                        CircleAvatar(
                          radius: 26,
                          backgroundColor: AppTheme.brandBlue.withOpacity(0.12),
                          child: Text(
                            _displayName.isNotEmpty ? _displayName[0].toUpperCase() : "U",
                            style: GoogleFonts.inter(fontSize: 20, fontWeight: FontWeight.w800, color: AppTheme.brandBlue),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                _displayName,
                                style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w700, color: AppTheme.textPrimary),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                _userEmail,
                                style: GoogleFonts.inter(fontSize: 13, color: AppTheme.textSecondary),
                              ),
                            ],
                          ),
                        ),
                        GestureDetector(
                          onTap: _emailVerified ? null : _showEmailVerificationModal,
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                            decoration: BoxDecoration(
                              color: _emailVerified ? const Color(0xFFD1FAE5) : const Color(0xFFFEF3C7),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  _emailVerified ? "Verified" : "Unverified",
                                  style: GoogleFonts.inter(
                                    fontSize: 11,
                                    fontWeight: FontWeight.w700,
                                    color: _emailVerified ? const Color(0xFF065F46) : const Color(0xFF92400E),
                                  ),
                                ),
                                if (!_emailVerified) ...[
                                  const SizedBox(width: 4),
                                  const Icon(Icons.arrow_forward_ios, size: 8, color: Color(0xFF92400E)),
                                ],
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),

                  // Connected Accounts (Section 3 Table)
                  const SizedBox(height: 20),
                  Text("Connected Accounts", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w700, color: AppTheme.textSecondary)),
                  const SizedBox(height: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(color: AppTheme.borderLight),
                    ),
                    child: Column(
                      children: [
                        Row(
                          children: [
                            const Icon(Icons.apple, size: 22, color: Colors.black),
                            const SizedBox(width: 12),
                            Text("Sign in with Apple", style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w600)),
                            const Spacer(),
                            Text("Supported", style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600, color: const Color(0xFF059669))),
                          ],
                        ),
                        const Divider(height: 20),
                        Row(
                          children: [
                            Container(
                              width: 20,
                              height: 20,
                              decoration: const BoxDecoration(shape: BoxShape.circle, color: Color(0xFF4285F4)),
                              child: const Center(child: Text("G", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 12))),
                            ),
                            const SizedBox(width: 12),
                            Text("Google Sign-In", style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w600)),
                            const Spacer(),
                            Text("Supported", style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600, color: const Color(0xFF059669))),
                          ],
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 20),
                  Text("App Lock & Biometrics", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w700, color: AppTheme.textSecondary)),
                  const SizedBox(height: 8),

                  // 2. Lock Timing Setting
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(color: AppTheme.borderLight),
                    ),
                    child: Column(
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Row(
                              children: [
                                const Icon(Icons.timer_outlined, size: 20, color: AppTheme.brandBlue),
                                const SizedBox(width: 10),
                                Text("Auto-lock Grace Period", style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w600)),
                              ],
                            ),
                            DropdownButton<int>(
                              value: appLockService.gracePeriodSeconds,
                              underline: const SizedBox(),
                              items: const [
                                DropdownMenuItem(value: 0, child: Text("Immediately")),
                                DropdownMenuItem(value: 15, child: Text("15 seconds")),
                                DropdownMenuItem(value: 30, child: Text("30 seconds")),
                                DropdownMenuItem(value: 60, child: Text("1 minute")),
                                DropdownMenuItem(value: 300, child: Text("5 minutes")),
                              ],
                              onChanged: (val) {
                                if (val != null) {
                                  setState(() => appLockService.setGracePeriod(val));
                                }
                              },
                            ),
                          ],
                        ),
                        const Divider(height: 20),
                        InkWell(
                          onTap: () {
                            appLockService.lock();
                            Navigator.pop(context);
                          },
                          child: Row(
                            children: [
                              const Icon(Icons.lock_outline, size: 20, color: AppTheme.brandDark),
                              const SizedBox(width: 10),
                              Text("Lock Arthentic Now", style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w600)),
                              const Spacer(),
                              const Icon(Icons.chevron_right, size: 18, color: AppTheme.textMuted),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 20),
                  Text("Password & Security", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w700, color: AppTheme.textSecondary)),
                  const SizedBox(height: 8),

                  // 3. Security Actions
                  Material(
                    color: Colors.white,
                    clipBehavior: Clip.antiAlias,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(18),
                      side: const BorderSide(color: AppTheme.borderLight),
                    ),
                    child: Column(
                      children: [
                        ListTile(
                          leading: const Icon(Icons.password_rounded, color: AppTheme.brandBlue),
                          title: Text("Change Password", style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w600)),
                          trailing: const Icon(Icons.chevron_right, size: 18, color: AppTheme.textMuted),
                          onTap: _showChangePasswordDialog,
                        ),
                        const Divider(height: 1),
                        ListTile(
                          leading: const Icon(Icons.history_rounded, color: AppTheme.brandBlue),
                          title: Text("Security Activity Log", style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w600)),
                          trailing: const Icon(Icons.chevron_right, size: 18, color: AppTheme.textMuted),
                          onTap: _showAuditLogSheet,
                        ),
                        const Divider(height: 1),
                        ListTile(
                          leading: const Icon(Icons.privacy_tip_outlined, color: AppTheme.brandBlue),
                          title: Text("Privacy & Data Policy", style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w600)),
                          trailing: const Icon(Icons.chevron_right, size: 18, color: AppTheme.textMuted),
                          onTap: _showPrivacyPolicyModal,
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 20),
                  Text("Active Devices & Sessions", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w700, color: AppTheme.textSecondary)),
                  const SizedBox(height: 8),

                  // 4. Active Sessions List
                  if (_sessions.isEmpty)
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(color: AppTheme.borderLight),
                      ),
                      child: Text("No active sessions found.", style: GoogleFonts.inter(color: AppTheme.textMuted)),
                    )
                  else
                    ..._sessions.map((sess) {
                      final isCurrent = sess["is_current"] == true;
                      final isActive = sess["is_active"] == true;
                      return Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: AppTheme.borderLight),
                        ),
                        child: Row(
                          children: [
                            Icon(
                              sess["platform"] == "ios" ? Icons.phone_iphone_rounded : Icons.devices_rounded,
                              color: isCurrent ? AppTheme.brandBlue : AppTheme.textSecondary,
                              size: 24,
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Text(
                                        sess["device_name"] ?? "Device",
                                        style: GoogleFonts.inter(fontSize: 13.5, fontWeight: FontWeight.w600),
                                      ),
                                      if (isCurrent) ...[
                                        const SizedBox(width: 6),
                                        Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                          decoration: BoxDecoration(
                                            color: AppTheme.brandBlue.withOpacity(0.12),
                                            borderRadius: BorderRadius.circular(6),
                                          ),
                                          child: Text(
                                            "This Device",
                                            style: GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w700, color: AppTheme.brandBlue),
                                          ),
                                        ),
                                      ],
                                    ],
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    isActive ? "Active session" : "Revoked session",
                                    style: GoogleFonts.inter(
                                      fontSize: 12,
                                      color: isActive ? const Color(0xFF059669) : Colors.red.shade700,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            if (!isCurrent && isActive)
                              TextButton(
                                onPressed: () => _handleRevokeSession(sess["id"]),
                                child: Text("Revoke", style: GoogleFonts.inter(color: Colors.red.shade700, fontWeight: FontWeight.w600, fontSize: 13)),
                              ),
                          ],
                        ),
                      );
                    }),

                  const SizedBox(height: 24),
                  // 5. Sign Out & Delete Account
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: OutlinedButton(
                      onPressed: _handleSignOut,
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppTheme.textPrimary,
                        side: const BorderSide(color: AppTheme.borderLight),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                      ),
                      child: Text("Sign Out", style: GoogleFonts.inter(fontWeight: FontWeight.w600)),
                    ),
                  ),

                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: TextButton(
                      onPressed: _showDeleteAccountConfirmation,
                      style: TextButton.styleFrom(
                        foregroundColor: Colors.red.shade700,
                      ),
                      child: Text("Delete Account", style: GoogleFonts.inter(fontWeight: FontWeight.w600)),
                    ),
                  ),
                  const SizedBox(height: 24),
                ],
              ),
            ),
    );
  }
}
