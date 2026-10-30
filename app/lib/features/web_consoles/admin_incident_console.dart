import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme.dart';

/// Portal 3: Protocol Admin Governance & Incident Console (DEFAULT_ADMIN_ROLE).
/// Real-time security alerts (J-05), 1-click Safe emergency pause (J-01),
/// Node key rotation (A-09), and Paymaster balance monitor (K-03).
class AdminIncidentConsole extends StatefulWidget {
  const AdminIncidentConsole({super.key});

  @override
  State<AdminIncidentConsole> createState() => _AdminIncidentConsoleState();
}

class _AdminIncidentConsoleState extends State<AdminIncidentConsole> {
  bool _isPaused = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      body: Row(
        children: [
          // Sub-nav sidebar
          Container(
            width: 250,
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
                        color: const Color(0xFFFEF2F2),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(Icons.shield_rounded, color: Color(0xFFDC2626), size: 18),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        "Protocol Governance",
                        style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w800, color: AppTheme.textPrimary),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 24),
                _buildNavItem("Real-Time Incident Stream (J-05)", Icons.crisis_alert_rounded, true),
                _buildNavItem("Emergency Circuit Breaker (J-01)", Icons.pause_circle_outline, false),
                _buildNavItem("KMS Node Key Rotation (A-09)", Icons.key_rounded, false),
                _buildNavItem("Paymaster Treasury (K-03)", Icons.account_balance_wallet_outlined, false),
                _buildNavItem("L1 Merkle Batcher (H-05)", Icons.layers_outlined, false),
              ],
            ),
          ),
          const VerticalDivider(width: 1, color: Color(0xFFE2E8F0)),

          // Main Content
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Column(
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
                              "Security Incident & Governance Console",
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: GoogleFonts.inter(fontSize: 20, fontWeight: FontWeight.w800, color: AppTheme.textPrimary),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              "DEFAULT_ADMIN_ROLE · Safe Multisig + Timelock Guard",
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: GoogleFonts.inter(fontSize: 12, color: AppTheme.textSecondary),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 12),

                      // Emergency Pause Button (J-01)
                      ElevatedButton.icon(
                        onPressed: () {
                          setState(() => _isPaused = !_isPaused);
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              backgroundColor: _isPaused ? Colors.red.shade900 : AppTheme.brandDark,
                              content: Text(_isPaused
                                  ? "EMERGENCY CIRCUIT BREAKER ACTIVATED (J-01): Protocol Paused!"
                                  : "Protocol unpaused. Normal operations restored."),
                            ),
                          );
                        },
                        icon: Icon(_isPaused ? Icons.play_arrow_rounded : Icons.emergency_rounded, size: 18),
                        label: Text(_isPaused ? "Unpause Protocol" : "Emergency Pause (J-01)", style: GoogleFonts.inter(fontWeight: FontWeight.w700)),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: _isPaused ? const Color(0xFF059669) : const Color(0xFFDC2626),
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 28),

                  // Stream & Alerts Table
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
                          // Wave 3 Milestone 7: Multi-Region KMS Cluster & Rollout Governor
                          Container(
                            padding: const EdgeInsets.all(16),
                            margin: const EdgeInsets.only(bottom: 20),
                            decoration: BoxDecoration(
                              color: const Color(0xFFF1F5F9),
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: const Color(0xFFCBD5E1)),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    Expanded(
                                      child: Text(
                                        "Multi-Region KMS Cluster & Rollout Governor (M7)",
                                        style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700, color: AppTheme.textPrimary),
                                      ),
                                    ),
                                    const SizedBox(width: 8),
                                    Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                      decoration: BoxDecoration(
                                        color: const Color(0xFFDCFCE7),
                                        borderRadius: BorderRadius.circular(6),
                                      ),
                                      child: Text(
                                        "3-of-5 Safe Quorum Active",
                                        style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w700, color: const Color(0xFF15803D)),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 12),
                                Wrap(
                                  spacing: 8,
                                  runSpacing: 8,
                                  children: [
                                    _buildRegionPill("US-East-1 (Primary)", true),
                                    _buildRegionPill("EU-West-1 (Failover)", false),
                                    _buildRegionPill("AP-Southeast-1 (Tertiary)", false),
                                  ],
                                ),
                                const SizedBox(height: 12),
                                const Divider(height: 1, color: Color(0xFFCBD5E1)),
                                const SizedBox(height: 12),
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            "Staged Rollout Governor",
                                            style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w700, color: AppTheme.textPrimary),
                                          ),
                                          Text(
                                            "Day 1 of 7 (1% Phased Release) · All SLA KPIs Healthy",
                                            style: GoogleFonts.inter(fontSize: 11, color: AppTheme.textSecondary),
                                          ),
                                        ],
                                      ),
                                    ),
                                    const SizedBox(width: 8),
                                    OutlinedButton(
                                          onPressed: () {},
                                          style: OutlinedButton.styleFrom(
                                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                            side: const BorderSide(color: Color(0xFFDC2626)),
                                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                          ),
                                          child: Text(
                                            "Pause Rollout",
                                            style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w700, color: const Color(0xFFDC2626)),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ],
                                ),
                              ),

                          Text("Real-Time Incident Stream (J-05 / SD-11)", style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700)),
                          const SizedBox(height: 16),
                          _buildIncidentRow(
                            severity: "INFO",
                            title: "Paymaster Deposit Gauge Healthy (K-03)",
                            details: "EntryPoint balance: 1.84 ETH on Base L2 · Tier T1-T3 quotas nominal.",
                            timestamp: "2 mins ago",
                          ),
                          _buildIncidentRow(
                            severity: "CLEAR",
                            title: "Ethereum L1 Merkle Anchor Root Settled (H-05)",
                            details: "Batch #104 (1,000 finalized events) anchored to Ethereum Sepolia L1.",
                            timestamp: "18 mins ago",
                          ),
                          _buildIncidentRow(
                            severity: "WARN",
                            title: "NFC SUN Counter Replay Intercepted (Key #1 / D-02)",
                            details: "Tag 04A1B2C3D4E580 counter #65 replayed from IP 194.26.29.112. Blocked in <1ms by Redis.",
                            timestamp: "1 hour ago",
                          ),
                        ],
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
        color: isSelected ? const Color(0xFFFEF2F2) : Colors.transparent,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Icon(icon, size: 18, color: isSelected ? const Color(0xFFDC2626) : const Color(0xFF64748B)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              label,
              style: GoogleFonts.inter(
                fontSize: 13,
                fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                color: isSelected ? const Color(0xFFDC2626) : const Color(0xFF334155),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildIncidentRow({
    required String severity,
    required String title,
    required String details,
    required String timestamp,
  }) {
    Color badgeColor;
    if (severity == "CLEAR" || severity == "INFO") {
      badgeColor = const Color(0xFF059669);
    } else {
      badgeColor = const Color(0xFFDC2626);
    }

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
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: badgeColor.withOpacity(0.12),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(severity, style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w800, color: badgeColor)),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700)),
                const SizedBox(height: 2),
                Text(details, style: GoogleFonts.inter(fontSize: 12, color: AppTheme.textSecondary)),
              ],
            ),
          ),
          Text(timestamp, style: GoogleFonts.inter(fontSize: 11, color: AppTheme.textMuted)),
        ],
      ),
    );
  }

  Widget _buildRegionPill(String label, bool isActive) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: isActive ? const Color(0xFFEFF6FF) : const Color(0xFFF8FAFC),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: isActive ? const Color(0xFF3B82F6) : const Color(0xFFE2E8F0)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              color: isActive ? const Color(0xFF2563EB) : const Color(0xFF94A3B8),
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 6),
          Text(
            label,
            style: GoogleFonts.inter(
              fontSize: 11,
              fontWeight: isActive ? FontWeight.w700 : FontWeight.w500,
              color: isActive ? const Color(0xFF1E40AF) : const Color(0xFF64748B),
            ),
          ),
        ],
      ),
    );
  }
}

