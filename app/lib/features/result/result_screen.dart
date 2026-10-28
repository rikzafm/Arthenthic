import 'dart:async';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme.dart';
import '../../core/models.dart';
import '../../services/wallet_service.dart';
import '../shared/artistic_background.dart';

class ResultScreen extends StatefulWidget {
  final ArtworkInfo artwork;
  final Level2Result result;

  const ResultScreen({
    super.key,
    required this.artwork,
    required this.result,
  });

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  int _secondsRemaining = 272; // 04:32
  Timer? _countdownTimer;
  bool _isRecordedOnChain = false;

  @override
  void initState() {
    super.initState();
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted && _secondsRemaining > 0) {
        setState(() => _secondsRemaining--);
      }
    });
  }

  @override
  void dispose() {
    _countdownTimer?.cancel();
    super.dispose();
  }

  String get _formattedTime {
    final m = (_secondsRemaining ~/ 60).toString().padLeft(2, '0');
    final s = (_secondsRemaining % 60).toString().padLeft(2, '0');
    return "$m:$s";
  }

  void _recordOnChain() {
    setState(() => _isRecordedOnChain = true);
    walletService.recordSignature("recordVerification (Base Sepolia tx: 0x8f3c...b12a)");

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        backgroundColor: AppTheme.brandDark,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        content: Row(
          children: const [
            Icon(Icons.verified, color: AppTheme.bubbleYellow),
            SizedBox(width: 12),
            Expanded(
              child: Text(
                "Attestation recorded on Base Sepolia! Gas sponsored.",
                style: TextStyle(color: Colors.white, fontSize: 13),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scorePct = widget.result.similarityBps ~/ 100;
    final thresholdPct = widget.result.thresholdBps ~/ 100;
    final isAuthentic = widget.result.isAuthentic;

    return Scaffold(
      backgroundColor: AppTheme.bgLight,
      body: ArtisticBackground(
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 16),
                // Headline (Serif Italic)
                Text(
                  isAuthentic ? "Authentic." : "Not Authentic.",
                  style: GoogleFonts.newsreader(
                    fontSize: 42,
                    fontWeight: FontWeight.w600,
                    fontStyle: FontStyle.italic,
                    color: AppTheme.textPrimary,
                  ),
                ),
                const SizedBox(height: 20),

                // Card 1: Score & Threshold Card
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 26),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(color: AppTheme.borderLight),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.03),
                        blurRadius: 12,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: Row(
                    children: [
                      // Circular Progress Ring
                      SizedBox(
                        width: 104,
                        height: 104,
                        child: Stack(
                          alignment: Alignment.center,
                          children: [
                            SizedBox(
                              width: 104,
                              height: 104,
                              child: CircularProgressIndicator(
                                value: scorePct / 100.0,
                                strokeWidth: 9,
                                backgroundColor: const Color(0xFFE5E7EB),
                                color: AppTheme.brandBlue,
                              ),
                            ),
                            Text(
                              "$scorePct%",
                              style: GoogleFonts.inter(
                                fontSize: 24,
                                fontWeight: FontWeight.w800,
                                color: AppTheme.textPrimary,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 24),
                      // Details Column
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
                              decoration: BoxDecoration(
                                color: isAuthentic ? AppTheme.goldBadgeBg : const Color(0xFFFEE2E2),
                                borderRadius: BorderRadius.circular(16),
                              ),
                              child: Text(
                                isAuthentic ? "Authentic" : "Unverified",
                                style: GoogleFonts.inter(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w700,
                                  color: isAuthentic ? AppTheme.goldBadgeText : const Color(0xFFB91C1C),
                                ),
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              "Threshold $thresholdPct%",
                              style: GoogleFonts.inter(
                                fontSize: 14,
                                color: AppTheme.textSecondary,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              "Sample data",
                              style: GoogleFonts.inter(
                                fontSize: 13,
                                color: AppTheme.textMuted,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),

                // Card 2: Breakdown Table
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
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
                  child: Column(
                    children: [
                      _buildBreakdownRow("NFC chip (SUN)", "valid · ctr 66"),
                      _buildRowDivider(),
                      if (widget.result.pointsPassed != null) ...[
                        _buildBreakdownRow(
                          "Spatial points",
                          "${widget.result.pointsPassed} of ${widget.result.totalPoints ?? 8} verified",
                        ),
                        _buildRowDivider(),
                      ],
                      _buildBreakdownRow(
                        "Photo texture",
                        "${widget.result.branches.photoTexturePct}%",
                      ),
                      _buildRowDivider(),
                      _buildBreakdownRow(
                        "LiDAR relief",
                        "${widget.result.branches.lidarReliefPct}%",
                      ),
                      _buildRowDivider(),
                      _buildBreakdownRow(
                        "Flat-print check",
                        widget.result.branches.flatPrintPassed ? "pass" : "fail",
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),

                // Card 3: Signed Attestation Box
                Container(
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF0F3FA),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        "Signed attestation",
                        style: GoogleFonts.inter(
                          fontSize: 13,
                          color: AppTheme.textSecondary,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        "0x9c41…e07a · expires in $_formattedTime",
                        style: GoogleFonts.sourceCodePro(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: AppTheme.textPrimary,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 24),

                // CTA: Record on-chain Button
                SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: ElevatedButton(
                    onPressed: _isRecordedOnChain ? null : _recordOnChain,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.brandBlue,
                      disabledBackgroundColor: AppTheme.brandBlue.withOpacity(0.5),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                      elevation: 0,
                    ),
                    child: Text(
                      _isRecordedOnChain ? "Recorded on-chain ✓" : "Record on-chain",
                      style: GoogleFonts.inter(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: Colors.white,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 14),

                // Secondary Action: Scan again
                Center(
                  child: TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: Text(
                      "Scan again",
                      style: GoogleFonts.inter(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        color: AppTheme.textPrimary,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 30),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildBreakdownRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 14),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: GoogleFonts.inter(
              fontSize: 15,
              color: AppTheme.textPrimary,
            ),
          ),
          Text(
            value,
            style: GoogleFonts.inter(
              fontSize: 15,
              fontWeight: FontWeight.w600,
              color: AppTheme.textPrimary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRowDivider() {
    return Container(
      height: 1,
      color: AppTheme.borderLight,
    );
  }
}

