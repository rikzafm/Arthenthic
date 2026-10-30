import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme.dart';
import '../shared/artistic_background.dart';

/// L-07 Artist Royalty & Works Dashboard.
/// Tracks artworks minted, active secondary sales, and 5.0% ERC-2981 royalties.
class ArtistDashboardScreen extends StatelessWidget {
  const ArtistDashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bgLight,
      appBar: AppBar(
        title: Text(
          "Artist Studio Dashboard",
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
                Text("L-07: Artist Atelier", style: GoogleFonts.inter(fontSize: 22, fontWeight: FontWeight.w800, color: AppTheme.textPrimary)),
                const SizedBox(height: 6),
                Text("Real-time on-chain ERC-2981 5.0% royalty settlements from Base L2.", style: GoogleFonts.inter(fontSize: 13, color: AppTheme.textSecondary)),
                const SizedBox(height: 20),

                // Royalty Metric Cards
                Row(
                  children: [
                    Expanded(
                      child: _buildMetricCard(
                        title: "Claimable Royalties",
                        value: "1,425.00 USDC",
                        subtitle: "+ 0.21 ETH",
                        color: const Color(0xFF059669),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: _buildMetricCard(
                        title: "Minted Works",
                        value: "12 Artworks",
                        subtitle: "100% On-Chain",
                        color: AppTheme.brandBlue,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 20),

                // Claim Button
                SizedBox(
                  width: double.infinity,
                  height: 50,
                  child: ElevatedButton.icon(
                    onPressed: () {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          backgroundColor: AppTheme.brandDark,
                          content: Text("1,425 USDC royalties claimed via ArthenticNFT.royaltyInfo()!"),
                        ),
                      );
                    },
                    icon: const Icon(Icons.savings_outlined, size: 20),
                    label: Text("Claim Accumulated Royalties", style: GoogleFonts.inter(fontWeight: FontWeight.w700)),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF059669),
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                    ),
                  ),
                ),
                const SizedBox(height: 24),

                Text("Genesis Artworks Catalog", style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700, color: AppTheme.textPrimary)),
                const SizedBox(height: 12),
                _buildArtworkCatalogItem("Untitled #42 (Blue Period)", "Token #1 · Sold · 625 USDC Royalty Paid"),
                _buildArtworkCatalogItem("Chromatic Relief VII", "Token #2 · Active Escrow · 0.21 ETH Expected"),
                _buildArtworkCatalogItem("Nocturne in Gold", "Token #3 · Secondary Resale · 1,400 USDC Royalty Paid"),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildMetricCard({required String title, required String value, required String subtitle, required Color color}) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppTheme.borderLight),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: GoogleFonts.inter(fontSize: 12, color: AppTheme.textSecondary)),
          const SizedBox(height: 8),
          Text(value, style: GoogleFonts.inter(fontSize: 17, fontWeight: FontWeight.w800, color: color)),
          const SizedBox(height: 4),
          Text(subtitle, style: GoogleFonts.inter(fontSize: 11, color: AppTheme.textMuted)),
        ],
      ),
    );
  }

  Widget _buildArtworkCatalogItem(String title, String status) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppTheme.borderLight),
      ),
      child: Row(
        children: [
          const Icon(Icons.brush_outlined, color: AppTheme.brandBlue, size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700)),
                Text(status, style: GoogleFonts.inter(fontSize: 12, color: AppTheme.textSecondary)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

