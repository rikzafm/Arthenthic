import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme.dart';
import '../../contracts/contract_config.dart';

/// Portal 1: Gallery & Verifier Institutional Console (VERIFIER_ROLE + Gnosis Safe).
/// Optimized for Desktop Browser / Safe{Wallet} App View (Part III, Section 4.2).
class GallerySafeConsole extends StatefulWidget {
  const GallerySafeConsole({super.key});

  @override
  State<GallerySafeConsole> createState() => _GallerySafeConsoleState();
}

class _GallerySafeConsoleState extends State<GallerySafeConsole> {
  int _selectedTab = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      body: Row(
        children: [
          // Sub-navigation sidebar for Gallery Safe
          Container(
            width: 240,
            color: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        color: const Color(0xFFEFF6FF),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(Icons.account_balance_outlined, color: AppTheme.brandBlue, size: 18),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        "Gallery Safe",
                        style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w800, color: AppTheme.textPrimary),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 24),
                _buildNavItem(0, "Intake Dossier Queue", Icons.inbox_outlined),
                _buildNavItem(1, "Safe Mint Queue (B-08)", Icons.fingerprint_rounded),
                _buildNavItem(2, "3-of-3 Chip Swap (F-05)", Icons.sync_alt_rounded),
                _buildNavItem(3, "Batch Collection Verifier", Icons.checklist_rounded),
              ],
            ),
          ),
          const VerticalDivider(width: 1, color: Color(0xFFE2E8F0)),

          // Main Workspace View
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: _buildWorkspace(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildNavItem(int index, String label, IconData icon) {
    final isSelected = _selectedTab == index;
    return InkWell(
      onTap: () => setState(() => _selectedTab = index),
      borderRadius: BorderRadius.circular(10),
      child: Container(
        margin: const EdgeInsets.only(bottom: 6),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: isSelected ? AppTheme.brandBlue.withOpacity(0.08) : Colors.transparent,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          children: [
            Icon(icon, size: 18, color: isSelected ? AppTheme.brandBlue : const Color(0xFF64748B)),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                label,
                style: GoogleFonts.inter(
                  fontSize: 13,
                  fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                  color: isSelected ? AppTheme.brandBlue : const Color(0xFF334155),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildWorkspace() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    "Institutional Verifier Console",
                    style: GoogleFonts.inter(fontSize: 24, fontWeight: FontWeight.w800, color: AppTheme.textPrimary),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    "VERIFIER_ROLE · Safe{Wallet} Multisig (2-of-3) · ${ArthenticContractConfig.baseSepoliaNetworkName} (${ArthenticContractConfig.shortAddress(ArthenticContractConfig.arthenticNftAddress)})",
                    style: GoogleFonts.inter(fontSize: 13, color: AppTheme.textSecondary),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            ElevatedButton.icon(
              onPressed: () {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    backgroundColor: AppTheme.brandDark,
                    content: Text("Connected to Gnosis Safe: 0xGallerySafeBasel000000000000000000000002"),
                  ),
                );
              },
              icon: const Icon(Icons.shield_outlined, size: 16),
              label: Text("Safe Connected", style: GoogleFonts.inter(fontWeight: FontWeight.w700)),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF0F172A),
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              ),
            ),
          ],
        ),
        const SizedBox(height: 28),

        // Table / Content
        Expanded(
          child: Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: const Color(0xFFE2E8F0)),
            ),
            child: ListView(
              children: [
                Text("Pending Safe Actions", style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700)),
                const SizedBox(height: 16),
                _buildActionRow(
                  title: "genesisMint() — Untitled #42 (Blue Period)",
                  tag: "B-08 SAFE MINT",
                  artist: "Studio Arthentic",
                  coSignStatus: "Artist Co-Signed ✓ (ADR-02)",
                  buttonText: "Propose Safe Tx (2-of-3)",
                ),
                _buildActionRow(
                  title: "replaceChip() — Nocturne in Gold & Raw Umber",
                  tag: "F-05 3-OF-3 CHIP",
                  artist: "Hendra Gunawan Estate",
                  coSignStatus: "2 of 3 Signatures Collected",
                  buttonText: "Sign 3/3 as Verifier",
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildActionRow({
    required String title,
    required String tag,
    required String artist,
    required String coSignStatus,
    required String buttonText,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFF8FAFC),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE2E8F0)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700)),
                const SizedBox(height: 4),
                Text("$tag · $artist · $coSignStatus", style: GoogleFonts.inter(fontSize: 12, color: AppTheme.textSecondary)),
              ],
            ),
          ),
          ElevatedButton(
            onPressed: () {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(backgroundColor: AppTheme.brandDark, content: Text("Action '$buttonText' queued in Safe!")),
              );
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: AppTheme.brandBlue,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
            child: Text(buttonText, style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }
}

