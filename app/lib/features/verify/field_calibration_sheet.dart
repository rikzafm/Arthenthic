import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Wave 3 Milestone 5: Physical Hardware Field Sensor Calibration Sheet.
/// Allows field engineers on iOS TestFlight builds to calibrate 8-point 256x192 LiDAR
/// and macro camera thresholds across Linen Canvas, Wood Panel, Impasto Oil, and Watercolor.
class FieldCalibrationSheet extends StatefulWidget {
  final double measuredRoughnessMm;
  final double lidarSnrDb;
  final ValueChanged<String>? onSubstrateSelected;

  const FieldCalibrationSheet({
    super.key,
    this.measuredRoughnessMm = 0.45,
    this.lidarSnrDb = 18.5,
    this.onSubstrateSelected,
  });

  @override
  State<FieldCalibrationSheet> createState() => _FieldCalibrationSheetState();
}

class _FieldCalibrationSheetState extends State<FieldCalibrationSheet> {
  String _selectedSubstrate = 'Linen Canvas';

  static const Map<String, int> _thresholds = {
    'Linen Canvas': 8800,
    'Wood Panel': 9000,
    'Impasto Oil': 8500,
    'Watercolor': 8900,
  };

  static const Map<String, String> _descriptions = {
    'Linen Canvas': 'Standard fine linen canvas weave. Balanced 70/30 photo-relief ratio.',
    'Wood Panel': 'Smooth gesso on hardboard/panel. Tight tolerance with 90.0% gate.',
    'Impasto Oil': 'High 3D relief palette-knife impasto with 40% depth weighting.',
    'Watercolor': 'Cotton rag matte paper. Presentation attack flat-print protection.',
  };

  @override
  Widget build(BuildContext context) {
    final thresholdBps = _thresholds[_selectedSubstrate] ?? 8800;
    final description = _descriptions[_selectedSubstrate] ?? '';

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: const BoxDecoration(
        color: Color(0xFF161618),
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.tune_rounded, color: Color(0xFFD4AF37), size: 24),
              const SizedBox(width: 10),
              Text(
                'Field Sensor Calibration',
                style: GoogleFonts.cinzel(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Calibrate iPhone 15/16 Pro LiDAR 256x192 mesh and substrate tolerance.',
            style: GoogleFonts.inter(fontSize: 12, color: Colors.white60),
          ),
          const SizedBox(height: 16),
          // Sensor Telemetry Cards
          Row(
            children: [
              Expanded(
                child: _buildMetricCard(
                  title: 'LiDAR Mesh SNR',
                  value: '${widget.lidarSnrDb.toStringAsFixed(1)} dB',
                  icon: Icons.graphic_eq_rounded,
                  isGood: widget.lidarSnrDb >= 12.0,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _buildMetricCard(
                  title: 'Relief Roughness',
                  value: '${widget.measuredRoughnessMm.toStringAsFixed(2)} mm',
                  icon: Icons.layers_rounded,
                  isGood: widget.measuredRoughnessMm >= 0.20,
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Text(
            'Artwork Substrate',
            style: GoogleFonts.inter(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: const Color(0xFFD4AF37),
            ),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              'Linen Canvas',
              'Wood Panel',
              'Impasto Oil',
              'Watercolor',
            ].map((substrate) {
              final isSelected = _selectedSubstrate == substrate;
              return ChoiceChip(
                label: Text(substrate),
                selected: isSelected,
                selectedColor: const Color(0xFFD4AF37).withOpacity(0.25),
                backgroundColor: const Color(0xFF242426),
                labelStyle: GoogleFonts.inter(
                  fontSize: 12,
                  fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
                  color: isSelected ? const Color(0xFFD4AF37) : Colors.white70,
                ),
                side: BorderSide(
                  color: isSelected ? const Color(0xFFD4AF37) : Colors.white12,
                ),
                onSelected: (selected) {
                  if (selected) {
                    setState(() {
                      _selectedSubstrate = substrate;
                    });
                    widget.onSubstrateSelected?.call(substrate);
                  }
                },
              );
            }).toList(),
          ),
          const SizedBox(height: 14),
          // Calibration Details Card
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFF1E1E22),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.white10),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      'Adaptive Gate Threshold:',
                      style: GoogleFonts.inter(fontSize: 12, color: Colors.white70),
                    ),
                    Text(
                      '$thresholdBps bps (${(thresholdBps / 100).toStringAsFixed(1)}%)',
                      style: GoogleFonts.inter(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: const Color(0xFFD4AF37),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  description,
                  style: GoogleFonts.inter(fontSize: 11, color: Colors.white54),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMetricCard({
    required String title,
    required String value,
    required IconData icon,
    required bool isGood,
  }) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: isGood ? const Color(0xFF10B981).withOpacity(0.3) : Colors.white10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 14, color: isGood ? const Color(0xFF10B981) : Colors.white54),
              const SizedBox(width: 4),
              Text(
                title,
                style: GoogleFonts.inter(fontSize: 11, color: Colors.white60),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            value,
            style: GoogleFonts.inter(
              fontSize: 16,
              fontWeight: FontWeight.bold,
              color: isGood ? const Color(0xFF10B981) : Colors.white,
            ),
          ),
        ],
      ),
    );
  }
}
