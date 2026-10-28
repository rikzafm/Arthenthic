import 'package:flutter/material.dart';
import '../../core/theme.dart';

class ArtisticBackground extends StatelessWidget {
  final Widget child;
  final bool isDark;

  const ArtisticBackground({
    super.key,
    required this.child,
    this.isDark = false,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        if (!isDark) ...[
          // Large Yellow Circle (Top Right)
          Positioned(
            top: -60,
            right: -50,
            child: Container(
              width: 220,
              height: 220,
              decoration: const BoxDecoration(
                color: AppTheme.bubbleYellow,
                shape: BoxShape.circle,
              ),
            ),
          ),
          // Deep Blue Circle (Top Right offset)
          Positioned(
            top: 100,
            right: -40,
            child: Container(
              width: 140,
              height: 140,
              decoration: const BoxDecoration(
                color: AppTheme.bubbleBlue,
                shape: BoxShape.circle,
              ),
            ),
          ),
          // Small Blue Floating Dot
          Positioned(
            top: 155,
            right: 105,
            child: Container(
              width: 44,
              height: 44,
              decoration: const BoxDecoration(
                color: AppTheme.bubbleBlue,
                shape: BoxShape.circle,
              ),
            ),
          ),
          // Coral Circle (Left edge accent)
          Positioned(
            top: -100,
            left: -80,
            child: Container(
              width: 200,
              height: 200,
              decoration: const BoxDecoration(
                color: AppTheme.bubbleCoral,
                shape: BoxShape.circle,
              ),
            ),
          ),
        ] else ...[
          // Dark Mode Bubbles (Bottom of Scan screen)
          Positioned(
            bottom: -90,
            left: -50,
            child: Container(
              width: 220,
              height: 220,
              decoration: const BoxDecoration(
                color: AppTheme.bubbleCoral,
                shape: BoxShape.circle,
              ),
            ),
          ),
          Positioned(
            bottom: -80,
            right: -60,
            child: Container(
              width: 200,
              height: 200,
              decoration: const BoxDecoration(
                color: AppTheme.bubbleBlue,
                shape: BoxShape.circle,
              ),
            ),
          ),
          Positioned(
            bottom: 40,
            right: 30,
            child: Container(
              width: 36,
              height: 36,
              decoration: const BoxDecoration(
                color: AppTheme.bubbleYellow,
                shape: BoxShape.circle,
              ),
            ),
          ),
        ],
        child,
      ],
    );
  }
}

