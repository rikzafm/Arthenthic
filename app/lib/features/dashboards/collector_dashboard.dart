import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme.dart';
import '../shared/artistic_background.dart';
import '../shared/status_badge_widget.dart';

/// L-09 Collector Portfolio & Active Escrow Deliveries Dashboard.
/// Tracks owned artworks, in-transit escrows with countdown to expiry (1-tap refund),
/// and restoration history.
class CollectorDashboardScreen extends StatelessWidget {
  const CollectorDashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bgLight,
      appBar: AppBar(
        title: Text(
          "Collector Portfolio",
          style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700, color: AppTheme.textPrimary),
        ),
        backgroundColor: Colors.white,
        elevation: 0,
        centerTitle: true,
      ),
      body: ArtisticBackground(
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text("L-09: Collector Vault", style: GoogleFonts.inter(fontSize: 22, fontWeight: FontWeight.w800, color: AppTheme.textPrimary)),
                const SizedBox(height: 6),
                Text("Authenticated physical collection, active escrows & condition records.", style: GoogleFonts.inter(fontSize: 13, color: AppTheme.textSecondary)),
                const SizedBox(height: 20),

                // Portfolio Summary
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [Color(0xFF1E293B), Color(0xFF0F172A)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(20),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.08),
                        blurRadius: 16,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text("Total Portfolio Valuation", style: GoogleFonts.inter(fontSize: 12, color: const Color(0xFF94A3B8))),
                      const SizedBox(height: 8),
                      Text("\$54,200 USD", style: GoogleFonts.inter(fontSize: 28, fontWeight: FontWeight.w800, color: Colors.white)),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          const Icon(Icons.verified, color: AppTheme.bubbleYellow, size: 16),
                          const SizedBox(width: 6),
                          Text("3 Works 100% Cryptographically Verified", style: GoogleFonts.inter(fontSize: 12, color: const Color(0xFFCBD5E1))),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 24),

                Text("In-Transit Escrow Deliveries", style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700, color: AppTheme.textPrimary)),
                const SizedBox(height: 12),

                // In-Transit Escrow Card with Countdown
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
                          Text("Untitled #42 (Blue Period)", style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w700)),
                          const StatusBadgeWidget(status: "CLEAR", compact: true),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text("Escrow ID: esc_042 · 12,500 USDC locked", style: GoogleFonts.inter(fontSize: 12, color: AppTheme.textSecondary)),
                      const SizedBox(height: 14),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        decoration: BoxDecoration(
                          color: const Color(0xFFFEF3C7),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.timer_outlined, color: Color(0xFFB45309), size: 16),
                            const SizedBox(width: 8),
                            Text("11 Days Remaining until Auto-Refund (C-12)", style: GoogleFonts.inter(fontSize: 12, color: const Color(0xFF92400E), fontWeight: FontWeight.w600)),
                          ],
                        ),
                      ),
                      const SizedBox(height: 14),
                      Row(
                        children: [
                          Expanded(
                            child: OutlinedButton(
                              onPressed: () {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(content: Text("Refund enabled once delivery window expires (C-12)")),
                                );
                              },
                              style: OutlinedButton.styleFrom(
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                              ),
                              child: const Text("Refund (C-12)"),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: ElevatedButton(
                              onPressed: () {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    backgroundColor: AppTheme.brandDark,
                                    content: Text("Tap physical NFC tag on canvas to confirm delivery (C-06)!"),
                                  ),
                                );
                              },
                              style: ElevatedButton.styleFrom(
                                backgroundColor: AppTheme.brandBlue,
                                foregroundColor: Colors.white,
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                              ),
                              child: const Text("Tap Claim"),
                            ),
                          ),
                        ],
                      ),
                    ],
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

