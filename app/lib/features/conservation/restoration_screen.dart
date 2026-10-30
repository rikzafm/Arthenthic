import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme.dart';
import '../../services/wallet_service.dart';
import '../shared/artistic_background.dart';

/// UC-E Post-Sale Restoration & UC-F 3-of-3 Chip Replacement Screen (SD-07, SD-08).
class RestorationScreen extends StatefulWidget {
  final String tokenId;

  const RestorationScreen({super.key, this.tokenId = "101"});

  @override
  State<RestorationScreen> createState() => _RestorationScreenState();
}

class _RestorationScreenState extends State<RestorationScreen> with SingleTickerProviderStateMixin {
  late TabController _tabController;
  final TextEditingController _damageController = TextEditingController();

  bool _isSubmitting = false;
  String _chipStatus = "1 of 3 Signatures Collected";
  int _collectedSignatures = 1;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  void _submitRestorationRequest() async {
    setState(() => _isSubmitting = true);
    await Future.delayed(const Duration(milliseconds: 600));
    setState(() => _isSubmitting = false);

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          backgroundColor: AppTheme.brandDark,
          content: Text("Restoration request submitted (E-01). Conservator notified!"),
        ),
      );
      _damageController.clear();
    }
  }

  void _signOwnerConsent() {
    // E-07* / ADR-03 EIP-712 Owner Consent
    walletService.recordSignature("OwnerConsent (E-07* / ADR-03: Token #${widget.tokenId})");
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          backgroundColor: AppTheme.brandDark,
          content: Text("Owner consent signed via MetaMask (E-07* / ADR-03). Ready for updateCondition()!"),
        ),
      );
    }
  }

  void _signChipReplacement() {
    // F-05: 3-of-3 Multi-Approval
    setState(() {
      if (_collectedSignatures < 3) {
        _collectedSignatures++;
        _chipStatus = "$_collectedSignatures of 3 Signatures Collected";
      }
    });

    walletService.recordSignature("ChipReplacementApproval (F-05: $_collectedSignatures/3)");
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: AppTheme.brandDark,
          content: Text(
            _collectedSignatures == 3
                ? "3-of-3 Approvals Complete! Executing replaceChip() on Base L2..."
                : "Approval signed! ($_collectedSignatures/3)",
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bgLight,
      appBar: AppBar(
        title: Text(
          "Restoration & Chip Governance",
          style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700, color: AppTheme.textPrimary),
        ),
        backgroundColor: Colors.white,
        elevation: 0,
        centerTitle: true,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, size: 18, color: AppTheme.textPrimary),
          onPressed: () => Navigator.pop(context),
        ),
        bottom: TabBar(
          controller: _tabController,
          labelColor: AppTheme.brandBlue,
          unselectedLabelColor: AppTheme.textSecondary,
          indicatorColor: AppTheme.brandBlue,
          indicatorWeight: 2.5,
          labelStyle: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w700),
          unselectedLabelStyle: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w500),
          tabs: const [
            Tab(text: "Restoration (E-01..07)"),
            Tab(text: "Chip Swap (F-05 3-of-3)"),
          ],
        ),
      ),
      body: ArtisticBackground(
        child: TabBarView(
          controller: _tabController,
          children: [
            // Tab 1: Post-Sale Restoration Lifecycle
            SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text("Restoration Lifecycle", style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w800, color: AppTheme.textPrimary)),
                  const SizedBox(height: 6),
                  Text("Request repairs, review treatment dossiers, and sign EIP-712 owner consent (ADR-03).", style: GoogleFonts.inter(fontSize: 13, color: AppTheme.textSecondary)),
                  const SizedBox(height: 20),

                  // Request Box
                  Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(color: AppTheme.borderLight),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text("E-01: Create Restoration Request", style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700)),
                        const SizedBox(height: 12),
                        TextField(
                          controller: _damageController,
                          maxLines: 3,
                          decoration: InputDecoration(
                            hintText: "Describe physical canvas wear, craquelure, or pigment fading...",
                            hintStyle: GoogleFonts.inter(fontSize: 13, color: AppTheme.textMuted),
                            filled: true,
                            fillColor: const Color(0xFFF8FAFC),
                            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppTheme.borderLight)),
                          ),
                        ),
                        const SizedBox(height: 14),
                        SizedBox(
                          width: double.infinity,
                          height: 46,
                          child: ElevatedButton(
                            onPressed: _isSubmitting ? null : _submitRestorationRequest,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: AppTheme.brandBlue,
                              foregroundColor: Colors.white,
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                            ),
                            child: Text("Submit Request to Conservator", style: GoogleFonts.inter(fontWeight: FontWeight.w600)),
                          ),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 20),

                  // Consent Gate Box
                  Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      color: const Color(0xFFEFF6FF),
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(color: const Color(0xFFBFDBFE)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            const Icon(Icons.security_rounded, color: AppTheme.brandBlue, size: 20),
                            const SizedBox(width: 8),
                            Text("E-07* / ADR-03: Collector Consent Gate", style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700, color: AppTheme.brandBlue)),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          "Conservators cannot mutate condition baselines on Base L2 without on-chain signature verification of the current NFT owner (ADR-03).",
                          style: GoogleFonts.inter(fontSize: 12, color: const Color(0xFF1E3A8A)),
                        ),
                        const SizedBox(height: 14),
                        SizedBox(
                          width: double.infinity,
                          height: 44,
                          child: ElevatedButton.icon(
                            onPressed: _signOwnerConsent,
                            icon: const Icon(Icons.gesture_rounded, size: 18),
                            label: Text("Sign Owner Consent (MetaMask)", style: GoogleFonts.inter(fontWeight: FontWeight.w600)),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: AppTheme.brandBlue,
                              foregroundColor: Colors.white,
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),

            // Tab 2: 3-of-3 Damaged Chip Replacement Tracker
            SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text("F-05: 3-of-3 Chip Replacement", style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w800, color: AppTheme.textPrimary)),
                  const SizedBox(height: 6),
                  Text("When a physical NFC tag is damaged, 3 distinct actors must co-sign to bind a new chip.", style: GoogleFonts.inter(fontSize: 13, color: AppTheme.textSecondary)),
                  const SizedBox(height: 20),

                  Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(color: AppTheme.borderLight),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text("Approval Progress", style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700)),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                              decoration: BoxDecoration(
                                color: _collectedSignatures == 3 ? const Color(0xFFECFDF5) : const Color(0xFFFEF3C7),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Text(
                                _chipStatus,
                                style: GoogleFonts.inter(
                                  fontSize: 11,
                                  fontWeight: FontWeight.w700,
                                  color: _collectedSignatures == 3 ? const Color(0xFF065F46) : const Color(0xFF92400E),
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        _buildApprovalStep(1, "Collector (Current Owner)", _collectedSignatures >= 1),
                        _buildApprovalStep(2, "Artist (Original Creator)", _collectedSignatures >= 2),
                        _buildApprovalStep(3, "Verifier (Accredited Gallery Safe)", _collectedSignatures >= 3),
                        const SizedBox(height: 16),
                        SizedBox(
                          width: double.infinity,
                          height: 46,
                          child: ElevatedButton.icon(
                            onPressed: _collectedSignatures == 3 ? null : _signChipReplacement,
                            icon: const Icon(Icons.fingerprint_rounded, size: 20),
                            label: Text(
                              _collectedSignatures == 3 ? "All Approvals Recorded ✓" : "Sign Approval as Next Actor",
                              style: GoogleFonts.inter(fontWeight: FontWeight.w600),
                            ),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: AppTheme.brandBlue,
                              foregroundColor: Colors.white,
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildApprovalStep(int step, String title, bool isDone) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Container(
            width: 26,
            height: 26,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isDone ? const Color(0xFF059669) : const Color(0xFFE5E7EB),
            ),
            child: Icon(
              isDone ? Icons.check : Icons.circle_outlined,
              size: 16,
              color: Colors.white,
            ),
          ),
          const SizedBox(width: 12),
          Text(title, style: GoogleFonts.inter(fontSize: 13, fontWeight: isDone ? FontWeight.w700 : FontWeight.w500)),
        ],
      ),
    );
  }
}

