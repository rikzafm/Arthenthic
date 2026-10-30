import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme.dart';

/// Portal 2: Conservator Studio Console (CONSERVATOR_ROLE).
/// Optimized for Desktop Browser workstations (Part III, Section 4.3).
class ConservatorStudioConsole extends StatefulWidget {
  const ConservatorStudioConsole({super.key});

  @override
  State<ConservatorStudioConsole> createState() => _ConservatorStudioConsoleState();
}

class _ConservatorStudioConsoleState extends State<ConservatorStudioConsole> {
  final TextEditingController _notesController = TextEditingController();
  bool _isUploadingToArweave = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      body: Row(
        children: [
          // Sub-nav sidebar
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
                        color: const Color(0xFFFDF2F8),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(Icons.biotech_outlined, color: Color(0xFFDB2777), size: 18),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        "Conservator Lab",
                        style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w800, color: AppTheme.textPrimary),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 24),
                _buildNavItem("Restoration Requests (E-01)", Icons.assignment_outlined, true),
                _buildNavItem("Treatment Reports (E-04)", Icons.description_outlined, false),
                _buildNavItem("Owner Consent Gate (E-07*)", Icons.verified_user_outlined, false),
                _buildNavItem("Condition Update (E-03)", Icons.update_rounded, false),
              ],
            ),
          ),
          const VerticalDivider(width: 1, color: Color(0xFFE2E8F0)),

          // Main Workspace
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text("Conservation Studio Workspace", style: GoogleFonts.inter(fontSize: 24, fontWeight: FontWeight.w800, color: AppTheme.textPrimary)),
                  const SizedBox(height: 4),
                  Text("CONSERVATOR_ROLE · Permanent Arweave Treatment Archive & E-07* Consent Gate", style: GoogleFonts.inter(fontSize: 13, color: AppTheme.textSecondary)),
                  const SizedBox(height: 28),

                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.all(24),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(color: const Color(0xFFE2E8F0)),
                      ),
                      child: SingleChildScrollView(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text("Treatment Dossier Builder (E-04)", style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700)),
                            const SizedBox(height: 14),
                            TextField(
                              controller: _notesController,
                              maxLines: 4,
                              decoration: InputDecoration(
                                hintText: "Enter microscopic Pigment Relining, Craquelure Consolidation notes & solvents used...",
                                hintStyle: GoogleFonts.inter(fontSize: 13, color: AppTheme.textMuted),
                                filled: true,
                                fillColor: const Color(0xFFF8FAFC),
                                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppTheme.borderLight)),
                              ),
                            ),
                            const SizedBox(height: 16),
                            Row(
                              children: [
                                Flexible(
                                  child: ElevatedButton.icon(
                                    onPressed: () {
                                      setState(() => _isUploadingToArweave = true);
                                      Future.delayed(const Duration(seconds: 1), () {
                                        if (mounted) {
                                          setState(() => _isUploadingToArweave = false);
                                          ScaffoldMessenger.of(context).showSnackBar(
                                            const SnackBar(
                                              backgroundColor: AppTheme.brandDark,
                                              content: Text("Dossier uploaded to Arweave: ar://7a9b...f012 · Hash verified!"),
                                            ),
                                          );
                                        }
                                      });
                                    },
                                    icon: _isUploadingToArweave
                                        ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                                        : const Icon(Icons.cloud_upload_outlined, size: 16),
                                    label: Text("Upload Dossier to Arweave (B-04/E-04)", style: GoogleFonts.inter(fontWeight: FontWeight.w600)),
                                    style: ElevatedButton.styleFrom(
                                      backgroundColor: AppTheme.brandBlue,
                                      foregroundColor: Colors.white,
                                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildNavItem(String label, IconData icon, bool isSelected) {
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: isSelected ? const Color(0xFFFDF2F8) : Colors.transparent,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Icon(icon, size: 18, color: isSelected ? const Color(0xFFDB2777) : const Color(0xFF64748B)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              label,
              style: GoogleFonts.inter(
                fontSize: 13,
                fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                color: isSelected ? const Color(0xFFDB2777) : const Color(0xFF334155),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

