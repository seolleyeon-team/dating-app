import 'dart:ui';

import 'package:flutter/cupertino.dart';

class ProfilePhotoBlur extends StatelessWidget {
  final Widget child;
  final bool enabled;
  final double sigma;
  final String? badgeText;

  const ProfilePhotoBlur({
    super.key,
    required this.child,
    required this.enabled,
    this.sigma = 7,
    this.badgeText,
  });

  @override
  Widget build(BuildContext context) {
    if (!enabled) {
      return child;
    }

    return ClipRect(
      child: Stack(
        fit: StackFit.expand,
        children: [
          ImageFiltered(
            imageFilter: ImageFilter.blur(sigmaX: sigma, sigmaY: sigma),
            child: child,
          ),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    CupertinoColors.black.withValues(alpha: 0.06),
                    CupertinoColors.black.withValues(alpha: 0.12),
                  ],
                ),
              ),
            ),
          ),
          if (badgeText != null && badgeText!.trim().isNotEmpty)
            Positioned(
              top: 14,
              right: 14,
              child: SafeArea(
                minimum: EdgeInsets.zero,
                child: Container(
                  constraints: const BoxConstraints(maxWidth: 250),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 10,
                  ),
                  decoration: BoxDecoration(
                    color: CupertinoColors.white.withValues(alpha: 0.92),
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(
                      color: CupertinoColors.white.withValues(alpha: 0.98),
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: CupertinoColors.black.withValues(alpha: 0.14),
                        blurRadius: 14,
                        offset: const Offset(0, 5),
                      ),
                    ],
                  ),
                  child: Text(
                    badgeText!,
                    textAlign: TextAlign.right,
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF1E1A1C),
                      height: 1.2,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
