import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppTheme {
  static const Color bgLight = Color(0xFFF6F7FB);
  static const Color brandBlue = Color(0xFF2344E8);
  static const Color brandDark = Color(0xFF131525);
  static const Color bubbleYellow = Color(0xFFFFB800);
  static const Color bubbleBlue = Color(0xFF2547E8);
  static const Color bubbleCoral = Color(0xFFE84A36);
  static const Color cardBg = Colors.white;
  static const Color borderLight = Color(0xFFE5E7EB);
  static const Color textPrimary = Color(0xFF111827);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color textMuted = Color(0xFF9CA3AF);
  static const Color goldBadgeBg = Color(0xFFFEF3C7);
  static const Color goldBadgeText = Color(0xFFB45309);
  static const Color softLavender = Color(0xFFEEF0F8);

  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: bgLight,
      colorScheme: ColorScheme.fromSeed(
        seedColor: brandBlue,
        primary: brandBlue,
        surface: cardBg,
      ),
      textTheme: GoogleFonts.interTextTheme().copyWith(
        headlineLarge: GoogleFonts.newsreader(
          fontSize: 34,
          fontWeight: FontWeight.w600,
          fontStyle: FontStyle.italic,
          color: textPrimary,
          letterSpacing: -0.5,
        ),
        headlineMedium: GoogleFonts.newsreader(
          fontSize: 30,
          fontWeight: FontWeight.w600,
          fontStyle: FontStyle.italic,
          color: textPrimary,
        ),
        headlineSmall: GoogleFonts.newsreader(
          fontSize: 24,
          fontWeight: FontWeight.w600,
          fontStyle: FontStyle.italic,
          color: textPrimary,
        ),
        titleLarge: GoogleFonts.inter(
          fontSize: 18,
          fontWeight: FontWeight.w700,
          color: textPrimary,
        ),
        titleMedium: GoogleFonts.inter(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: textPrimary,
        ),
        bodyLarge: GoogleFonts.inter(
          fontSize: 15,
          color: textPrimary,
        ),
        bodyMedium: GoogleFonts.inter(
          fontSize: 13,
          color: textSecondary,
        ),
      ),
    );
  }
}
