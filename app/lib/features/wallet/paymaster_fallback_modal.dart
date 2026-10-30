import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme.dart';

/// K-04 ERC-4337 Paymaster Self-Pay Gas Fallback Sheet.
/// Displayed when sponsorship is declined (quota exhausted or low treasury).
/// Allows 1-tap direct settlement on Base L2 (~$0.01 gas).
class PaymasterFallbackModal extends StatelessWidget {
  final String methodName;
  final String reason;
  final double estimatedGasUsd;
  final String estimatedGasEth;
  final VoidCallback onConfirmSelfPay;

  const PaymasterFallbackModal({
    super.key,
    required this.methodName,
    required this.reason,
    this.estimatedGasUsd = 0.012,
    this.estimatedGasEth = "0.000005",
    required this.onConfirmSelfPay,
  });

  static void show(
    BuildContext context, {
    required String methodName,
    required String reason,
    required VoidCallback onConfirmSelfPay,
  }) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => PaymasterFallbackModal(
        methodName: methodName,
        reason: reason,
        onConfirmSelfPay: () {
          Navigator.pop(ctx);
          onConfirmSelfPay();
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: const Color(0xFFFEF3C7),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.local_gas_station_outlined, color: Color(0xFFB45309), size: 20),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        "Gas Sponsorship Fallback",
                        style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700, color: AppTheme.textPrimary),
                      ),
                      Text(
                        "K-04 Self-Pay Modal",
                        style: GoogleFonts.inter(fontSize: 12, color: AppTheme.textSecondary),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFFF8FAFC),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppTheme.borderLight),
              ),
              child: Text(
                reason,
                style: GoogleFonts.inter(fontSize: 12, color: AppTheme.textSecondary, height: 1.4),
              ),
            ),
            const SizedBox(height: 14),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text("Estimated Base L2 Gas:", style: GoogleFonts.inter(fontSize: 13, color: AppTheme.textSecondary)),
                Text(
                  "~$estimatedGasEth ETH (\$$estimatedGasUsd)",
                  style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w700, color: AppTheme.textPrimary),
                ),
              ],
            ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              height: 48,
              child: ElevatedButton(
                onPressed: onConfirmSelfPay,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.brandBlue,
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                ),
                child: Text("Pay Gas Directly via MetaMask", style: GoogleFonts.inter(fontWeight: FontWeight.w700)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

