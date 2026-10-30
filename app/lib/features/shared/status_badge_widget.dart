import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// D-15* Deterministic Artwork Status Badge System.
/// Used on Scan Results, CoA, Marketplace Cards, and Provenance Timelines.
class StatusBadgeWidget extends StatelessWidget {
  final String status;
  final bool compact;
  final bool tamperDetected;

  const StatusBadgeWidget({
    super.key,
    required this.status,
    this.compact = false,
    this.tamperDetected = false,
  });

  @override
  Widget build(BuildContext context) {
    final s = status.toUpperCase().replaceAll(" ", "_");

    Color bg;
    Color text;
    Color border;
    IconData icon;
    String label;

    switch (s) {
      case "CLEAR":
        bg = const Color(0xFFECFDF5);
        text = const Color(0xFF065F46);
        border = const Color(0xFFA7F3D0);
        icon = Icons.verified_rounded;
        label = "CLEAR";
        break;
      case "CHIP_REPLACED":
        bg = const Color(0xFFEFF6FF);
        text = const Color(0xFF1E40AF);
        border = const Color(0xFFBFDBFE);
        icon = Icons.nfc_rounded;
        label = "CHIP REPLACED (3-OF-3)";
        break;
      case "UNSYNCHRONIZED_OWNERSHIP":
        bg = const Color(0xFFFEF3C7);
        text = const Color(0xFF92400E);
        border = const Color(0xFFFDE68A);
        icon = Icons.sync_problem_rounded;
        label = "UNSYNCHRONIZED OWNERSHIP";
        break;
      case "FLAGGED":
        bg = const Color(0xFFFFF7ED);
        text = const Color(0xFFC2410C);
        border = const Color(0xFFFED7AA);
        icon = Icons.flag_rounded;
        label = "FLAGGED";
        break;
      case "DESTROYED":
        bg = const Color(0xFFFEF2F2);
        text = const Color(0xFF991B1B);
        border = const Color(0xFFFECACA);
        icon = Icons.delete_forever_rounded;
        label = "DESTROYED ON-CHAIN";
        break;
      default:
        bg = const Color(0xFFF3F4F6);
        text = const Color(0xFF374151);
        border = const Color(0xFFE5E7EB);
        icon = Icons.info_outline_rounded;
        label = status.toUpperCase();
    }

    if (compact) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: border),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 12, color: text),
            const SizedBox(width: 4),
            Text(
              label,
              style: GoogleFonts.inter(
                fontSize: 10,
                fontWeight: FontWeight.w700,
                color: text,
                letterSpacing: 0.3,
              ),
            ),
            if (tamperDetected) ...[
              const SizedBox(width: 4),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
                decoration: BoxDecoration(
                  color: const Color(0xFFDC2626),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  'TAMPER',
                  style: GoogleFonts.inter(
                    fontSize: 8,
                    fontWeight: FontWeight.w800,
                    color: Colors.white,
                  ),
                ),
              ),
            ],
          ],
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: border, width: 1.2),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: text),
          const SizedBox(width: 6),
          Text(
            label,
            style: GoogleFonts.inter(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: text,
              letterSpacing: 0.4,
            ),
          ),
          if (tamperDetected) ...[
            const SizedBox(width: 6),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: const Color(0xFFDC2626),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                'TAMPER DETECTED',
                style: GoogleFonts.inter(
                  fontSize: 10,
                  fontWeight: FontWeight.w800,
                  color: Colors.white,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// D-15* Warning Banner displayed when an artwork is in a non-CLEAR state
/// (e.g., UNSYNCHRONIZED_OWNERSHIP, CHIP_REPLACED, FLAGGED, DESTROYED).
class StatusWarningBanner extends StatelessWidget {
  final String status;

  const StatusWarningBanner({
    super.key,
    required this.status,
  });

  @override
  Widget build(BuildContext context) {
    final s = status.toUpperCase().replaceAll(" ", "_");
    if (s == "CLEAR") {
      return const SizedBox.shrink();
    }

    String message;
    Color bg;
    Color text;
    IconData icon;

    switch (s) {
      case "UNSYNCHRONIZED_OWNERSHIP":
        message =
            "UNSYNCHRONIZED OWNERSHIP (C-12): Physical seller wallet does not match on-chain ArthenticNFT.ownerOf(tokenId). Escrow deposits are blocked until reconciled.";
        bg = const Color(0xFFFEF3C7);
        text = const Color(0xFF92400E);
        icon = Icons.sync_problem_rounded;
        break;
      case "CHIP_REPLACED":
        message =
            "CHIP REPLACED (F-05): Physical NTAG 424 DNA chip was rebound via 3-of-3 multi-approval (Collector + Artist + Verifier).";
        bg = const Color(0xFFEFF6FF);
        text = const Color(0xFF1E40AF);
        icon = Icons.nfc_rounded;
        break;
      case "FLAGGED":
        message =
            "FLAGGED FOR SECURITY REVIEW: Active governance alert or SUN counter anomaly under investigation.";
        bg = const Color(0xFFFFF7ED);
        text = const Color(0xFFC2410C);
        icon = Icons.flag_rounded;
        break;
      case "DESTROYED":
        message =
            "DESTROYED ON-CHAIN: This physical artwork has been permanently decommissioned.";
        bg = const Color(0xFFFEF2F2);
        text = const Color(0xFF991B1B);
        icon = Icons.delete_forever_rounded;
        break;
      default:
        message = "Status notice: $status";
        bg = const Color(0xFFF3F4F6);
        text = const Color(0xFF374151);
        icon = Icons.info_outline_rounded;
    }

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 6),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: text.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          Icon(icon, size: 18, color: text),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: GoogleFonts.inter(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: text,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

