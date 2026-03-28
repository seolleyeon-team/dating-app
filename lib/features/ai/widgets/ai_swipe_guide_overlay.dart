// =============================================================================
// AI 스와이프 가이드 오버레이 (카드 위에 표시되는 스와이프 안내)
// 경로: lib/features/ai/widgets/ai_swipe_guide_overlay.dart
//
// 사용 예시:
// Stack(
//   children: [
//     ProfileCard(...),
//     const AiSwipeGuideOverlay(),
//   ],
// );
// =============================================================================

import 'package:flutter/cupertino.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF5E8A);
  static const Color pink200 = Color(0xFFFBCFE8);
}

// =============================================================================
// 메인 오버레이
// =============================================================================
class AiSwipeGuideOverlay extends StatefulWidget {
  const AiSwipeGuideOverlay({super.key});

  @override
  State<AiSwipeGuideOverlay> createState() => _AiSwipeGuideOverlayState();
}

class _AiSwipeGuideOverlayState extends State<AiSwipeGuideOverlay>
    with TickerProviderStateMixin {
  late AnimationController _pulseController;
  late AnimationController _arrowController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      duration: const Duration(seconds: 3),
      vsync: this,
    )..repeat(reverse: true);

    _arrowController = AnimationController(
      duration: const Duration(milliseconds: 2500),
      vsync: this,
    )..repeat();
  }

  @override
  void dispose() {
    _pulseController.dispose();
    _arrowController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Positioned.fill(
      child: IgnorePointer(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // 스와이프 화살표
            _SwipeArrows(
              pulseController: _pulseController,
              arrowController: _arrowController,
            ),
            const SizedBox(height: 8),
            // 액션 버튼 힌트
            const _ActionButtonHints(),
            const SizedBox(height: 24),
            // 스와이프 텍스트
            const _SwipeHintText(),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 스와이프 화살표
// =============================================================================
class _SwipeArrows extends StatelessWidget {
  final AnimationController pulseController;
  final AnimationController arrowController;

  const _SwipeArrows({
    required this.pulseController,
    required this.arrowController,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: pulseController,
      builder: (_, child) {
        final scale = 0.95 + (0.05 * pulseController.value);
        final opacity = 0.6 + (0.4 * pulseController.value);
        return Opacity(
          opacity: opacity,
          child: Transform.scale(scale: scale, child: child),
        );
      },
      child: SizedBox(
        width: 128,
        height: 64,
        child: Stack(
          alignment: Alignment.center,
          children: [
            // 왼쪽 화살표
            AnimatedBuilder(
              animation: arrowController,
              builder: (_, child) {
                // 0~0.35: 왼쪽으로, 0.35~0.65: 중앙, 0.65~1: 오른쪽으로
                double offset = 0;
                if (arrowController.value < 0.35) {
                  offset = -8 * (arrowController.value / 0.35);
                } else if (arrowController.value < 0.65) {
                  offset = -8 + (8 * ((arrowController.value - 0.35) / 0.3));
                } else {
                  offset = 8 * ((arrowController.value - 0.65) / 0.35);
                }
                return Transform.translate(
                  offset: Offset(offset, 0),
                  child: child,
                );
              },
              child: const Positioned(
                left: 0,
                child: Icon(
                  CupertinoIcons.chevron_left,
                  size: 32,
                  color: _AppColors.pink200,
                ),
              ),
            ),
            // 중앙 라인
            Container(
              width: 48,
              height: 1,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    _AppColors.pink200.withValues(alpha: 0),
                    _AppColors.pink200.withValues(alpha: 0.8),
                    _AppColors.pink200.withValues(alpha: 0),
                  ],
                ),
              ),
            ),
            // 중앙 도트
            Container(
              width: 6,
              height: 6,
              decoration: BoxDecoration(
                color: CupertinoColors.white,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: CupertinoColors.white.withValues(alpha: 0.9),
                    blurRadius: 15,
                  ),
                ],
              ),
            ),
            // 오른쪽 화살표
            AnimatedBuilder(
              animation: arrowController,
              builder: (_, child) {
                double offset = 0;
                if (arrowController.value < 0.35) {
                  offset = -8 * (arrowController.value / 0.35);
                } else if (arrowController.value < 0.65) {
                  offset = -8 + (8 * ((arrowController.value - 0.35) / 0.3));
                } else {
                  offset = 8 * ((arrowController.value - 0.65) / 0.35);
                }
                return Transform.translate(
                  offset: Offset(offset, 0),
                  child: child,
                );
              },
              child: const Positioned(
                right: 0,
                child: Icon(
                  CupertinoIcons.chevron_right,
                  size: 32,
                  color: _AppColors.pink200,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 액션 버튼 힌트
// =============================================================================
class _ActionButtonHints extends StatelessWidget {
  const _ActionButtonHints();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // X 버튼
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: CupertinoColors.white.withValues(alpha: 0.1),
              shape: BoxShape.circle,
              border: Border.all(
                color: CupertinoColors.white.withValues(alpha: 0.2),
              ),
            ),
            child: const Icon(
              CupertinoIcons.xmark,
              size: 24,
              color: CupertinoColors.white,
            ),
          ),
          // 하트 버튼
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: _AppColors.primary.withValues(alpha: 0.4),
              shape: BoxShape.circle,
              border: Border.all(
                color: CupertinoColors.white.withValues(alpha: 0.2),
              ),
            ),
            child: const Icon(
              CupertinoIcons.heart_fill,
              size: 24,
              color: CupertinoColors.white,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 스와이프 힌트 텍스트
// =============================================================================
class _SwipeHintText extends StatelessWidget {
  const _SwipeHintText();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10),
      decoration: BoxDecoration(
        color: CupertinoColors.black.withValues(alpha: 0.3),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: CupertinoColors.white.withValues(alpha: 0.1)),
      ),
      child: const Text(
        'SWIPE LEFT OR RIGHT',
        style: TextStyle(
          fontFamily: 'Pretendard',
          fontSize: 11,
          fontWeight: FontWeight.w300,
          letterSpacing: 3,
          color: CupertinoColors.white,
        ),
      ),
    );
  }
}
