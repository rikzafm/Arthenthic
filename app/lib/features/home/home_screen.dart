import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme.dart';
import '../../core/models.dart';
import '../../services/wallet_service.dart';
import '../../services/nfc_service.dart';
import '../../services/api_client.dart';
import '../../services/session_store.dart';
import '../../services/app_lock_service.dart';
import '../shared/artistic_background.dart';
import '../scan/scan_screen.dart';
import '../auth/login_screen.dart';
import '../settings/settings_screen.dart';

class HomeScreen extends StatefulWidget {
  final Function(int) onTabSelected;

  const HomeScreen({super.key, required this.onTabSelected});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  String _selectedRole = "Collector";
  List<String> _availableRoles = ["Collector"];
  bool _isGuest = false;
  ArtworkInfo _artwork = ArtworkInfo.mock();
  bool _isNfcLoading = false;

  List<dynamic> _myApplications = [];
  List<dynamic> _adminApplications = [];
  List<dynamic> _artistArtworks = [];
  List<dynamic> _conditionReports = [];

  @override
  void initState() {
    super.initState();
    _loadUserRoles();
  }

  Future<void> _loadUserRoles() async {
    final isGuest = appLockService.isGuest;
    List<String> roles = [];

    if (!isGuest && apiClient.currentUser != null) {
      roles = apiClient.userRoles;
    }

    if (roles.isEmpty) {
      final storedUser = await sessionStore.getUser();
      if (storedUser != null && storedUser["roles"] is List) {
        roles = (storedUser["roles"] as List).map((e) => e.toString()).toList();
      }
    }

    if (roles.isEmpty) {
      // Default roles for guest exploration and smoke test
      roles = ["Collector", "Verifier", "Conservator"];
    }

    final savedRole = await sessionStore.getActiveRole();
    if (mounted) {
      setState(() {
        _isGuest = isGuest;
        _availableRoles = roles;
        if (savedRole != null && roles.contains(savedRole)) {
          _selectedRole = savedRole;
        } else {
          _selectedRole = roles.first;
        }
      });
      _loadRoleSpecificData();
    }
  }

  Future<void> _loadRoleSpecificData() async {
    if (_isGuest) return;
    try {
      final role = _selectedRole.toLowerCase();
      if (role == "collector") {
        final apps = await apiClient.getMyApplications();
        if (mounted) setState(() => _myApplications = apps);
      } else if (role == "admin") {
        final apps = await apiClient.getAdminApplications();
        if (mounted) setState(() => _adminApplications = apps);
      } else if (role == "artist") {
        final works = await apiClient.getArtistArtworks();
        if (mounted) setState(() => _artistArtworks = works);
      } else if (role == "conservator") {
        final reps = await apiClient.getConditionReports();
        if (mounted) setState(() => _conditionReports = reps);
      }
    } catch (_) {}
  }

  void _onRoleChanged(String role) async {
    setState(() => _selectedRole = role);
    await sessionStore.setActiveRole(role);
    _loadRoleSpecificData();
  }

  void _showRoleSwitcher() {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      "Switch Active Role",
                      style: GoogleFonts.inter(
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                        color: AppTheme.textPrimary,
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close, size: 20),
                      onPressed: () => Navigator.pop(ctx),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  "Select the role profile you want to operate with on this device.",
                  style: GoogleFonts.inter(
                    fontSize: 13,
                    color: AppTheme.textSecondary,
                  ),
                ),
                const SizedBox(height: 16),
                ..._availableRoles.map((role) {
                  final isSelected = _selectedRole == role;
                  return InkWell(
                    onTap: () {
                      _onRoleChanged(role);
                      Navigator.pop(ctx);
                    },
                    borderRadius: BorderRadius.circular(14),
                    child: Container(
                      margin: const EdgeInsets.only(bottom: 10),
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                      decoration: BoxDecoration(
                        color: isSelected ? AppTheme.brandBlue.withOpacity(0.08) : Colors.white,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(
                          color: isSelected ? AppTheme.brandBlue : AppTheme.borderLight,
                          width: isSelected ? 1.5 : 1.0,
                        ),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            _getRoleIcon(role),
                            color: isSelected ? AppTheme.brandBlue : AppTheme.textSecondary,
                            size: 22,
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  role,
                                  style: GoogleFonts.inter(
                                    fontSize: 15,
                                    fontWeight: isSelected ? FontWeight.w700 : FontWeight.w600,
                                    color: isSelected ? AppTheme.brandBlue : AppTheme.textPrimary,
                                  ),
                                ),
                                Text(
                                  _getRoleDescription(role),
                                  style: GoogleFonts.inter(
                                    fontSize: 12,
                                    color: AppTheme.textSecondary,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          if (isSelected)
                            const Icon(Icons.check_circle_rounded, color: AppTheme.brandBlue, size: 20),
                        ],
                      ),
                    ),
                  );
                }).toList(),
              ],
            ),
          ),
        );
      },
    );
  }

  IconData _getRoleIcon(String role) {
    switch (role.toLowerCase()) {
      case "artist":
        return Icons.palette_outlined;
      case "gallery":
      case "verifier":
        return Icons.store_outlined;
      case "conservator":
        return Icons.biotech_outlined;
      case "admin":
        return Icons.admin_panel_settings_outlined;
      default:
        return Icons.account_balance_wallet_outlined;
    }
  }

  String _getRoleDescription(String role) {
    switch (role.toLowerCase()) {
      case "artist":
        return "Genesis capture & artwork baseline registration";
      case "gallery":
      case "verifier":
        return "Batch verification queue & reports (read-only)";
      case "conservator":
        return "Condition reports & post-restoration baselines";
      case "admin":
        return "Review applications & security audit log";
      default:
        return "Verify artwork, view certificates & apply for accreditation";
    }
  }

  void _showApplyAccreditationDialog() {
    String selectedRoleToApply = "Artist";
    final notesController = TextEditingController();
    final urlController = TextEditingController();
    final bioController = TextEditingController();
    bool hasAttachedDoc = false;

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
                          "Apply for Accreditation",
                          style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w700),
                        ),
                        IconButton(
                          icon: const Icon(Icons.close, size: 20),
                          onPressed: () => Navigator.pop(ctx),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(
                      "Submit credentials for manual Admin review. In v1, approval grants role access upon token refresh.",
                      style: GoogleFonts.inter(fontSize: 13, color: AppTheme.textSecondary),
                    ),
                    const SizedBox(height: 18),
                    Text("Requested Role", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 6),
                    DropdownButtonFormField<String>(
                      value: selectedRoleToApply,
                      decoration: InputDecoration(
                        filled: true,
                        fillColor: const Color(0xFFF8FAFC),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppTheme.borderLight),
                        ),
                      ),
                      items: const [
                        DropdownMenuItem(value: "Artist", child: Text("Artist")),
                        DropdownMenuItem(value: "Gallery", child: Text("Gallery (Verifier)")),
                        DropdownMenuItem(value: "Conservator", child: Text("Conservator")),
                      ],
                      onChanged: (val) {
                        if (val != null) setModalState(() => selectedRoleToApply = val);
                      },
                    ),
                    const SizedBox(height: 14),
                    Text("Portfolio / Website URL", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 6),
                    TextField(
                      controller: urlController,
                      decoration: InputDecoration(
                        hintText: "https://artist.com or org website",
                        hintStyle: GoogleFonts.inter(color: AppTheme.textMuted, fontSize: 13),
                        filled: true,
                        fillColor: const Color(0xFFF8FAFC),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppTheme.borderLight),
                        ),
                      ),
                    ),
                    const SizedBox(height: 14),
                    Text("Bio / Organization Affiliation", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 6),
                    TextField(
                      controller: bioController,
                      decoration: InputDecoration(
                        hintText: "Studio name, museum affiliation, or institution",
                        hintStyle: GoogleFonts.inter(color: AppTheme.textMuted, fontSize: 13),
                        filled: true,
                        fillColor: const Color(0xFFF8FAFC),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppTheme.borderLight),
                        ),
                      ),
                    ),
                    const SizedBox(height: 14),
                    Text("Verification Notes & Credentials", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 6),
                    TextField(
                      controller: notesController,
                      maxLines: 2,
                      decoration: InputDecoration(
                        hintText: "Brief summary of credentials or gallery association...",
                        hintStyle: GoogleFonts.inter(color: AppTheme.textMuted, fontSize: 13),
                        filled: true,
                        fillColor: const Color(0xFFF8FAFC),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppTheme.borderLight),
                        ),
                      ),
                    ),
                    const SizedBox(height: 14),
                    // Document Attachment Placeholder
                    InkWell(
                      onTap: () {
                        setModalState(() => hasAttachedDoc = !hasAttachedDoc);
                      },
                      child: Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: hasAttachedDoc ? const Color(0xFFEFF6FF) : const Color(0xFFF8FAFC),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: hasAttachedDoc ? AppTheme.brandBlue : AppTheme.borderLight,
                          ),
                        ),
                        child: Row(
                          children: [
                            Icon(
                              hasAttachedDoc ? Icons.check_circle : Icons.attach_file,
                              color: hasAttachedDoc ? AppTheme.brandBlue : AppTheme.textSecondary,
                              size: 20,
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                hasAttachedDoc
                                    ? "credentials_document.pdf attached"
                                    : "Attach proof of identity or diploma (PDF)",
                                style: GoogleFonts.inter(
                                  fontSize: 13,
                                  color: hasAttachedDoc ? AppTheme.brandBlue : AppTheme.textSecondary,
                                  fontWeight: hasAttachedDoc ? FontWeight.w600 : FontWeight.w500,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 20),
                    SizedBox(
                      width: double.infinity,
                      height: 48,
                      child: ElevatedButton(
                        onPressed: () async {
                          final docs = hasAttachedDoc
                              ? [
                                  {
                                    "storage_key": "accreditation/mock_cert.pdf",
                                    "filename": "credentials_document.pdf",
                                    "mime": "application/pdf",
                                    "sha256": "mock_hash_abc123",
                                  }
                                ]
                              : null;

                          final res = await apiClient.applyForRole(
                            role: selectedRoleToApply,
                            portfolioUrl: urlController.text.trim(),
                            bioOrOrg: bioController.text.trim(),
                            notes: notesController.text.trim(),
                            documents: docs,
                          );
                          if (mounted) {
                            Navigator.pop(ctx);
                            _loadRoleSpecificData();
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                backgroundColor: res["success"] == true ? AppTheme.brandDark : Colors.red.shade800,
                                content: Text(
                                  res["success"] == true
                                      ? "Application for $selectedRoleToApply submitted for Admin review!"
                                      : (res["error"] ?? "Application failed"),
                                ),
                              ),
                            );
                          }
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppTheme.brandBlue,
                          foregroundColor: Colors.white,
                          elevation: 0,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        ),
                        child: Text("Submit Application", style: GoogleFonts.inter(fontWeight: FontWeight.w600)),
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  void _showAdminReviewModal(Map<String, dynamic> app) {
    final noteController = TextEditingController();

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) {
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
                  Text("Review Application", style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w700)),
                  IconButton(icon: const Icon(Icons.close, size: 20), onPressed: () => Navigator.pop(ctx)),
                ],
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFFF8FAFC),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppTheme.borderLight),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text("Applicant: ${app['applicant_email'] ?? app['email']}", style: GoogleFonts.inter(fontWeight: FontWeight.w600)),
                    const SizedBox(height: 4),
                    Text("Requested Role: ${app['requested_role']}", style: GoogleFonts.inter(color: AppTheme.brandBlue, fontWeight: FontWeight.w700)),
                    if (app['payload']?['notes'] != null) ...[
                      const SizedBox(height: 4),
                      Text("Notes: ${app['payload']['notes']}", style: GoogleFonts.inter(fontSize: 12, color: AppTheme.textSecondary)),
                    ],
                  ],
                ),
              ),
              const SizedBox(height: 14),
              Text("Review Note / Feedback", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600)),
              const SizedBox(height: 6),
              TextField(
                controller: noteController,
                decoration: InputDecoration(
                  hintText: "Optional feedback for applicant...",
                  hintStyle: GoogleFonts.inter(color: AppTheme.textMuted, fontSize: 13),
                  filled: true,
                  fillColor: const Color(0xFFF8FAFC),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppTheme.borderLight)),
                ),
              ),
              const SizedBox(height: 18),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () async {
                        await apiClient.reviewApplication(app['id'], "reject", reviewNote: noteController.text.trim());
                        if (mounted) {
                          Navigator.pop(ctx);
                          _loadRoleSpecificData();
                        }
                      },
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Colors.red.shade700,
                        side: BorderSide(color: Colors.red.shade300),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                      child: const Text("Reject"),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () async {
                        await apiClient.reviewApplication(app['id'], "more_info", reviewNote: noteController.text.trim());
                        if (mounted) {
                          Navigator.pop(ctx);
                          _loadRoleSpecificData();
                        }
                      },
                      style: OutlinedButton.styleFrom(
                        foregroundColor: const Color(0xFFB45309),
                        side: const BorderSide(color: Color(0xFFFCD34D)),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                      child: const Text("Need Info"),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: ElevatedButton(
                      onPressed: () async {
                        await apiClient.reviewApplication(app['id'], "approve", reviewNote: noteController.text.trim());
                        if (mounted) {
                          Navigator.pop(ctx);
                          _loadRoleSpecificData();
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              backgroundColor: AppTheme.brandDark,
                              content: Text("Role ${app['requested_role']} granted to ${app['applicant_email'] ?? 'user'}!"),
                            ),
                          );
                        }
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppTheme.brandBlue,
                        foregroundColor: Colors.white,
                        elevation: 0,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                      child: const Text("Approve"),
                    ),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }

  void _showAddConditionReportDialog() {
    String grade = "Stable";
    final notesController = TextEditingController();
    final treatmentController = TextEditingController();

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
                      Text("Record Condition Report", style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w700)),
                      IconButton(icon: const Icon(Icons.close, size: 20), onPressed: () => Navigator.pop(ctx)),
                    ],
                  ),
                  const SizedBox(height: 14),
                  Text("Condition Grade", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 6),
                  DropdownButtonFormField<String>(
                    value: grade,
                    decoration: InputDecoration(
                      filled: true,
                      fillColor: const Color(0xFFF8FAFC),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppTheme.borderLight)),
                    ),
                    items: const [
                      DropdownMenuItem(value: "Stable", child: Text("Stable")),
                      DropdownMenuItem(value: "Excellent", child: Text("Excellent")),
                      DropdownMenuItem(value: "Minor Craquelure", child: Text("Minor Craquelure")),
                      DropdownMenuItem(value: "Restoration Required", child: Text("Restoration Required")),
                    ],
                    onChanged: (val) {
                      if (val != null) setModalState(() => grade = val);
                    },
                  ),
                  const SizedBox(height: 14),
                  Text("Condition Notes", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 6),
                  TextField(
                    controller: notesController,
                    maxLines: 2,
                    decoration: InputDecoration(
                      hintText: "Surface relief and pigment stability...",
                      hintStyle: GoogleFonts.inter(color: AppTheme.textMuted, fontSize: 13),
                      filled: true,
                      fillColor: const Color(0xFFF8FAFC),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppTheme.borderLight)),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Text("Treatment Performed", style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 6),
                  TextField(
                    controller: treatmentController,
                    decoration: InputDecoration(
                      hintText: "e.g. Dust removal with micro-suction",
                      hintStyle: GoogleFonts.inter(color: AppTheme.textMuted, fontSize: 13),
                      filled: true,
                      fillColor: const Color(0xFFF8FAFC),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppTheme.borderLight)),
                    ),
                  ),
                  const SizedBox(height: 18),
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: ElevatedButton(
                      onPressed: () async {
                        final res = await apiClient.submitConditionReport(
                          tokenId: _artwork.tokenId,
                          conditionGrade: grade,
                          notes: notesController.text.trim(),
                          treatmentPerformed: treatmentController.text.trim(),
                        );
                        if (mounted) {
                          Navigator.pop(ctx);
                          _loadRoleSpecificData();
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              backgroundColor: res["success"] == true ? AppTheme.brandDark : Colors.red.shade800,
                              content: Text(res["success"] == true ? "Condition report recorded on provenance!" : "Failed to record report"),
                            ),
                          );
                        }
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppTheme.brandBlue,
                        foregroundColor: Colors.white,
                        elevation: 0,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                      child: const Text("Record Report"),
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

  Future<void> _handleNfcTap({bool isDebug = false}) async {
    setState(() => _isNfcLoading = true);
    try {
      final sun = await nfcService.readSunTag();
      final attestation = await apiClient.verifyLevel1(sun, tokenId: _artwork.tokenId);
      walletService.recordSignature("verifyLevel1 (NFC SUN ctr ${sun.ctr})");

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: AppTheme.brandDark,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            content: Row(
              children: [
                const Icon(Icons.check_circle_rounded, color: AppTheme.bubbleYellow),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    "NFC SUN Tag Valid! Counter: ${sun.ctr}\nAttestation signed: ${attestation.signature.substring(0, 10)}...",
                    style: const TextStyle(color: Colors.white, fontSize: 13),
                  ),
                ),
              ],
            ),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: Colors.red.shade800,
            content: Text("NFC Verification error: $e"),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _isNfcLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bgLight,
      body: ArtisticBackground(
        child: SafeArea(
          bottom: false,
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 12),
                // Header Row: Brand + Role Pill / Wallet Pill
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      "Arthentic",
                      style: GoogleFonts.inter(
                        fontSize: 28,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.8,
                        color: AppTheme.textPrimary,
                      ),
                    ),
                    Row(
                      children: [
                        // Multi-role switcher icon
                        if (!_isGuest && _availableRoles.length > 1) ...[
                          GestureDetector(
                            onTap: _showRoleSwitcher,
                            child: Container(
                              margin: const EdgeInsets.only(right: 8),
                              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                              decoration: BoxDecoration(
                                color: AppTheme.brandBlue.withOpacity(0.1),
                                borderRadius: BorderRadius.circular(20),
                                border: Border.all(color: AppTheme.brandBlue.withOpacity(0.3)),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(_getRoleIcon(_selectedRole), size: 14, color: AppTheme.brandBlue),
                                  const SizedBox(width: 4),
                                  const Icon(Icons.unfold_more_rounded, size: 14, color: AppTheme.brandBlue),
                                ],
                              ),
                            ),
                          ),
                        ],
                        // Wallet Pill
                        GestureDetector(
                          onTap: () => widget.onTabSelected(2),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(24),
                              border: Border.all(color: AppTheme.borderLight),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.black.withOpacity(0.04),
                                  blurRadius: 8,
                                  offset: const Offset(0, 2),
                                ),
                              ],
                            ),
                            child: Text(
                              _isGuest ? "Guest" : walletService.shortAddress,
                              style: GoogleFonts.sourceCodePro(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                color: AppTheme.textPrimary,
                              ),
                            ),
                          ),
                        ),
                        if (!_isGuest) ...[
                          const SizedBox(width: 8),
                          GestureDetector(
                            onTap: () {
                              Navigator.push(
                                context,
                                MaterialPageRoute(builder: (_) => const SettingsScreen()),
                              );
                            },
                            child: Container(
                              padding: const EdgeInsets.all(8),
                              decoration: BoxDecoration(
                                color: Colors.white,
                                shape: BoxShape.circle,
                                border: Border.all(color: AppTheme.borderLight),
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withOpacity(0.04),
                                    blurRadius: 8,
                                    offset: const Offset(0, 2),
                                  ),
                                ],
                              ),
                              child: const Icon(Icons.settings_outlined, size: 18, color: AppTheme.textPrimary),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ],
                ),

                // Guest Banner
                if (_isGuest) ...[
                  const SizedBox(height: 16),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFEF3C7),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: const Color(0xFFF59E0B).withOpacity(0.4)),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.info_outline, size: 20, color: Color(0xFFB45309)),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            "Sign in to save results and access accredited tools.",
                            style: GoogleFonts.inter(
                              fontSize: 12.5,
                              fontWeight: FontWeight.w600,
                              color: const Color(0xFF92400E),
                            ),
                          ),
                        ),
                        TextButton(
                          onPressed: () {
                            Navigator.push(
                              context,
                              MaterialPageRoute(builder: (_) => const LoginScreen()),
                            );
                          },
                          style: TextButton.styleFrom(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                            minimumSize: Size.zero,
                            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                          child: Text(
                            "Sign In",
                            style: GoogleFonts.inter(
                              fontSize: 13,
                              fontWeight: FontWeight.w700,
                              color: AppTheme.brandBlue,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],

                const SizedBox(height: 24),

                // Hero Tagline
                Text(
                  "Every canvas\nhas a fingerprint.",
                  style: GoogleFonts.newsreader(
                    fontSize: 40,
                    height: 1.1,
                    fontWeight: FontWeight.w600,
                    fontStyle: FontStyle.italic,
                    color: AppTheme.textPrimary,
                    letterSpacing: -0.5,
                  ),
                ),
                const SizedBox(height: 18),

                // Role Selector Segment (if multiple roles available)
                if (_availableRoles.length > 1) ...[
                  Container(
                    padding: const EdgeInsets.all(4),
                    decoration: BoxDecoration(
                      color: const Color(0xFFE5E7F0).withOpacity(0.7),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Row(
                      children: _availableRoles.map((role) {
                        final isSelected = _selectedRole == role;
                        return Expanded(
                          child: GestureDetector(
                            onTap: () => _onRoleChanged(role),
                            child: AnimatedContainer(
                              duration: const Duration(milliseconds: 180),
                              padding: const EdgeInsets.symmetric(vertical: 9),
                              decoration: BoxDecoration(
                                color: isSelected ? Colors.white : Colors.transparent,
                                borderRadius: BorderRadius.circular(12),
                                boxShadow: isSelected
                                    ? [
                                        BoxShadow(
                                          color: Colors.black.withOpacity(0.06),
                                          blurRadius: 6,
                                          offset: const Offset(0, 2),
                                        ),
                                      ]
                                    : null,
                              ),
                              child: Center(
                                child: Text(
                                  role,
                                  style: GoogleFonts.inter(
                                    fontSize: 13,
                                    fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                                    color: isSelected ? AppTheme.textPrimary : AppTheme.textSecondary,
                                  ),
                                ),
                              ),
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                  ),
                  const SizedBox(height: 20),
                ],

                // Artwork Card
                _buildArtworkCard(),
                const SizedBox(height: 16),

                // Primary Action 1: Tap NFC Chip (Available across all roles & guest)
                InkWell(
                  onTap: _isNfcLoading ? null : () => _handleNfcTap(isDebug: false),
                  borderRadius: BorderRadius.circular(20),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 22),
                    decoration: BoxDecoration(
                      color: AppTheme.brandBlue,
                      borderRadius: BorderRadius.circular(20),
                      boxShadow: [
                        BoxShadow(
                          color: AppTheme.brandBlue.withOpacity(0.28),
                          blurRadius: 16,
                          offset: const Offset(0, 6),
                        ),
                      ],
                    ),
                    child: Row(
                      children: [
                        const Icon(
                          Icons.wifi_tethering_rounded,
                          color: Colors.white,
                          size: 32,
                        ),
                        const SizedBox(width: 18),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                "Tap NFC chip",
                                style: GoogleFonts.inter(
                                  fontSize: 17,
                                  fontWeight: FontWeight.w700,
                                  color: Colors.white,
                                ),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                "Level 1 · chip authenticity",
                                style: GoogleFonts.inter(
                                  fontSize: 13,
                                  color: Colors.white.withOpacity(0.85),
                                ),
                              ),
                            ],
                          ),
                        ),
                        if (_isNfcLoading)
                          const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2.5),
                          )
                        else
                          Icon(
                            Icons.arrow_forward_ios_rounded,
                            color: Colors.white.withOpacity(0.7),
                            size: 16,
                          ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 14),

                // Primary Action 2: Scan Surface (Level 2 LiDAR)
                InkWell(
                  onTap: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => ScanScreen(
                          artwork: _artwork,
                          selectedRole: _selectedRole,
                        ),
                      ),
                    );
                  },
                  borderRadius: BorderRadius.circular(20),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 22),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: AppTheme.borderLight),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.03),
                          blurRadius: 10,
                          offset: const Offset(0, 4),
                        ),
                      ],
                    ),
                    child: Row(
                      children: [
                        const Icon(
                          Icons.filter_center_focus_rounded,
                          color: AppTheme.textPrimary,
                          size: 30,
                        ),
                        const SizedBox(width: 18),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                "Scan surface",
                                style: GoogleFonts.inter(
                                  fontSize: 17,
                                  fontWeight: FontWeight.w700,
                                  color: AppTheme.textPrimary,
                                ),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                "Level 2 · camera + LiDAR fingerprint",
                                style: GoogleFonts.inter(
                                  fontSize: 13,
                                  color: AppTheme.textSecondary,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const Icon(
                          Icons.arrow_forward_ios_rounded,
                          color: AppTheme.textMuted,
                          size: 16,
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),

                // Role-Specific Home View Content
                _buildRoleHomeView(),

                const SizedBox(height: 16),

                // UC-C Physical-Confirmation Escrow Marketplace Entry Card
                InkWell(
                  onTap: () => widget.onTabSelected(3),
                  borderRadius: BorderRadius.circular(18),
                  child: Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(color: AppTheme.borderLight),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.02),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            color: const Color(0xFFFFF7ED),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Icon(Icons.storefront_rounded, color: Color(0xFFE65100), size: 24),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                "Escrow Marketplace (UC-C)",
                                style: GoogleFonts.inter(
                                  fontSize: 14.5,
                                  fontWeight: FontWeight.w700,
                                  color: AppTheme.textPrimary,
                                ),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                "USDC Permit2 & ETH Escrow · L1+L2 Physical Release · 93.5% / 5% / 1.5% Split",
                                style: GoogleFonts.inter(
                                  fontSize: 12,
                                  color: AppTheme.textSecondary,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const Icon(Icons.arrow_forward_ios_rounded, size: 15, color: AppTheme.textMuted),
                      ],
                    ),
                  ),
                ),

                const SizedBox(height: 16),

                // Debug: simulate NFC tap
                Center(
                  child: InkWell(
                    onTap: () => _handleNfcTap(isDebug: true),
                    borderRadius: BorderRadius.circular(24),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                      decoration: BoxDecoration(
                        color: Colors.transparent,
                        borderRadius: BorderRadius.circular(24),
                        border: Border.all(
                          color: const Color(0xFF94A3B8),
                          width: 1.2,
                        ),
                      ),
                      child: Text(
                        "Debug: simulate NFC tap",
                        style: GoogleFonts.inter(
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                          color: const Color(0xFF475569),
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 40),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// Builds role-specific home widget tree
  Widget _buildRoleHomeView() {
    switch (_selectedRole.toLowerCase()) {
      case "artist":
        return _buildArtistHome();
      case "gallery":
      case "verifier":
        return _buildGalleryHome();
      case "conservator":
        return _buildConservatorHome();
      case "admin":
        return _buildAdminHome();
      default:
        return _buildCollectorHome();
    }
  }

  /// 1. Collector Home: Status tracker for applications, Owned works, Apply for accreditation card
  Widget _buildCollectorHome() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Application Status Tracker (if user submitted an application)
        if (_myApplications.isNotEmpty) ...[
          ..._myApplications.map((app) {
            final statusStr = (app['status'] ?? 'pending').toString().toLowerCase();
            Color badgeBg = const Color(0xFFFEF3C7);
            Color badgeText = const Color(0xFF92400E);
            String label = "Pending Admin Review";

            if (statusStr == "approved") {
              badgeBg = const Color(0xFFD1FAE5);
              badgeText = const Color(0xFF065F46);
              label = "Approved (Refresh to activate)";
            } else if (statusStr == "rejected") {
              badgeBg = const Color(0xFFFEE2E2);
              badgeText = const Color(0xFF991B1B);
              label = "Application Rejected";
            } else if (statusStr == "more_info") {
              badgeBg = const Color(0xFFEDE9FE);
              badgeText = const Color(0xFF5B21B6);
              label = "More Info Requested";
            }

            return Container(
              margin: const EdgeInsets.only(bottom: 12),
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: AppTheme.borderLight),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        "${app['requested_role']} Application",
                        style: GoogleFonts.inter(fontWeight: FontWeight.w700, fontSize: 13),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(color: badgeBg, borderRadius: BorderRadius.circular(10)),
                        child: Text(label, style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w700, color: badgeText)),
                      ),
                    ],
                  ),
                  if (app['review_note'] != null && app['review_note'].toString().isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Text(
                      "Reviewer note: ${app['review_note']}",
                      style: GoogleFonts.inter(fontSize: 12, color: AppTheme.textSecondary),
                    ),
                  ],
                ],
              ),
            );
          }),
        ],

        // Apply for Accreditation Card
        if (!_isGuest) ...[
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: AppTheme.borderLight),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.02),
                  blurRadius: 8,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: AppTheme.brandBlue.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.badge_outlined, color: AppTheme.brandBlue, size: 24),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        "Apply for Accreditation",
                        style: GoogleFonts.inter(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: AppTheme.textPrimary,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        "Unlock Artist, Gallery, or Conservator privileges.",
                        style: GoogleFonts.inter(
                          fontSize: 12,
                          color: AppTheme.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                ElevatedButton(
                  onPressed: _showApplyAccreditationDialog,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.brandDark,
                    foregroundColor: Colors.white,
                    elevation: 0,
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                    minimumSize: Size.zero,
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                  child: Text("Apply", style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600)),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }

  /// 2. Artist Home: Register new artwork (genesis), My works, application status
  Widget _buildArtistHome() {
    return Column(
      children: [
        // Register New Artwork Action Banner
        Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF1E293B), Color(0xFF0F172A)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(20),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.12),
                blurRadius: 12,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppTheme.bubbleYellow.withOpacity(0.2),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(
                      "Artist Studio · Accredited",
                      style: GoogleFonts.inter(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: AppTheme.bubbleYellow,
                      ),
                    ),
                  ),
                  const Icon(Icons.verified_outlined, color: AppTheme.bubbleYellow, size: 20),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                "Register New Artwork",
                style: GoogleFonts.inter(
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                "Enroll physical micro-texture baseline and bind SUN cryptographic NFC chip.",
                style: GoogleFonts.inter(
                  fontSize: 13,
                  color: Colors.white.withOpacity(0.8),
                  height: 1.35,
                ),
              ),
              const SizedBox(height: 14),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => ScanScreen(
                          artwork: _artwork,
                          selectedRole: "Artist",
                        ),
                      ),
                    );
                  },
                  icon: const Icon(Icons.add_photo_alternate_outlined, size: 18),
                  label: Text("Start Genesis Capture", style: GoogleFonts.inter(fontWeight: FontWeight.w600)),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: AppTheme.textPrimary,
                    elevation: 0,
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  /// 3. Gallery Home: Batch verification queue, Sign on web explainer banner
  Widget _buildGalleryHome() {
    return Column(
      children: [
        // Web Signing Explainer Banner
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: const Color(0xFFEFF6FF),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: const Color(0xFF3B82F6).withOpacity(0.3)),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.laptop_mac_rounded, color: Color(0xFF2563EB), size: 22),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      "Read-Only Verification Queue",
                      style: GoogleFonts.inter(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: const Color(0xFF1E40AF),
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      "Mobile is read-only. Multisig on-chain attestations must be signed on the Arthentic Web portal.",
                      style: GoogleFonts.inter(
                        fontSize: 12.5,
                        color: const Color(0xFF1E3A8A),
                        height: 1.35,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  /// 4. Conservator Home: Condition reports list, record report button
  Widget _buildConservatorHome() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: const Color(0xFFF0FDF4),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: const Color(0xFF10B981).withOpacity(0.3)),
          ),
          child: Row(
            children: [
              const Icon(Icons.biotech_rounded, color: Color(0xFF059669), size: 24),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      "Conservation Lab Ready",
                      style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700, color: const Color(0xFF065F46)),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      "Record condition reports & update baselines post-restoration.",
                      style: GoogleFonts.inter(fontSize: 12.5, color: const Color(0xFF047857)),
                    ),
                  ],
                ),
              ),
              ElevatedButton(
                onPressed: _showAddConditionReportDialog,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF059669),
                  foregroundColor: Colors.white,
                  elevation: 0,
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                  minimumSize: Size.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                ),
                child: Text("Add Report", style: GoogleFonts.inter(fontSize: 11.5, fontWeight: FontWeight.w600)),
              ),
            ],
          ),
        ),
      ],
    );
  }

  /// 5. Admin Home: Review applications queue, role grants, audit log
  Widget _buildAdminHome() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: const Color(0xFFFEF2F2),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: const Color(0xFFEF4444).withOpacity(0.3)),
          ),
          child: Row(
            children: [
              const Icon(Icons.security_rounded, color: Color(0xFFDC2626), size: 24),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      "Admin Accreditation Review",
                      style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700, color: const Color(0xFF991B1B)),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      "Pending applications: ${_adminApplications.length}",
                      style: GoogleFonts.inter(fontSize: 12.5, color: const Color(0xFFB91C1C)),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        if (_adminApplications.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text(
            "Review Queue",
            style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700, color: AppTheme.textPrimary),
          ),
          const SizedBox(height: 8),
          ..._adminApplications.take(4).map((app) {
            return InkWell(
              onTap: () => _showAdminReviewModal(app),
              borderRadius: BorderRadius.circular(14),
              child: Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: AppTheme.borderLight),
                ),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: AppTheme.brandBlue.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        app['requested_role'] ?? 'Role',
                        style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w700, color: AppTheme.brandBlue),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            app['applicant_email'] ?? 'User',
                            style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600),
                          ),
                          Text(
                            "Status: ${app['status']}",
                            style: GoogleFonts.inter(fontSize: 11.5, color: AppTheme.textSecondary),
                          ),
                        ],
                      ),
                    ),
                    const Icon(Icons.arrow_forward_ios, size: 14, color: AppTheme.textMuted),
                  ],
                ),
              ),
            );
          }),
        ],
      ],
    );
  }

  Widget _buildArtworkCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppTheme.borderLight),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.03),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              color: const Color(0xFFDDE3F5),
              borderRadius: BorderRadius.circular(14),
            ),
            child: const Icon(
              Icons.palette_outlined,
              color: AppTheme.brandBlue,
              size: 28,
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _artwork.title,
                  style: GoogleFonts.inter(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: AppTheme.textPrimary,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  "${_artwork.artist} · Token #${_artwork.tokenId}",
                  style: GoogleFonts.inter(
                    fontSize: 13,
                    color: AppTheme.textSecondary,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  "Last verified ${_artwork.lastVerified}",
                  style: GoogleFonts.inter(
                    fontSize: 12,
                    color: AppTheme.textMuted,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
