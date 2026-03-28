// =============================================================================
// AI 스와이프 튜토리얼 오버레이 (좌우 스와이프 안내)
// 경로: lib/features/tutorial/widgets/swipe_tutorial_overlay.dart
//
// 사용 예시:
// showDialog(
//   context: context,
//   barrierColor: Colors.transparent,
//   builder: (_) => SwipeTutorialOverlay(
//     onSkip: () => Navigator.pop(context),
//     onNext: () => Navigator.pop(context),
//     currentStep: 2,
//     totalSteps: 4,
//   ),
// );
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF4458);
  static const Color overlayDark = Color(0xB3000000); // 70% black
}

// =============================================================================
// 메인 오버레이
// =============================================================================
class SwipeTutorialOverlay extends StatefulWidget {
  final VoidCallback onSkip;
  final VoidCallback onNext;
  final int currentStep;
  final int totalSteps;

  const SwipeTutorialOverlay({
    super.key,
    required this.onSkip,
    required this.onNext,
    this.currentStep = 2,
    this.totalSteps = 4,
  });

  @override
  State<SwipeTutorialOverlay> createState() => _SwipeTutorialOverlayState();
}

class _SwipeTutorialOverlayState extends State<SwipeTutorialOverlay>
    with TickerProviderStateMixin {
  late AnimationController _bounceLeftController;
  late AnimationController _bounceRightController;
  late AnimationController _pingController;

  @override
  void initState() {
    super.initState();
    _bounceLeftController = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    )..repeat(reverse: true);

    _bounceRightController = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    )..repeat(reverse: true);

    _pingController = AnimationController(
      duration: const Duration(seconds: 2),
      vsync: this,
    )..repeat();
  }

  @override
  void dispose() {
    _bounceLeftController.dispose();
    _bounceRightController.dispose();
    _pingController.dispose();
    super.dispose();
  }

  void _onSkip() {
    HapticFeedback.lightImpact();
    widget.onSkip();
  }

  void _onNext() {
    HapticFeedback.mediumImpact();
    widget.onNext();
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return Container(
      color: _AppColors.overlayDark,
      child: SafeArea(
        child: Column(
          children: [
            const Spacer(flex: 2),
            // 스와이프 방향 안내
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 32),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  // 왼쪽 (PASS)
                  _SwipeDirection(
                    controller: _bounceLeftController,
                    icon: CupertinoIcons.arrow_left,
                    label: 'PASS',
                    iconColor: CupertinoColors.white,
                    isLeft: true,
                  ),
                  // 오른쪽 (LIKE)
                  _SwipeDirection(
                    controller: _bounceRightController,
                    icon: CupertinoIcons.arrow_right,
                    label: 'LIKE',
                    iconColor: _AppColors.primary,
                    isLeft: false,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 32),
            // 터치 아이콘
            _TouchIndicator(controller: _pingController),
            const SizedBox(height: 24),
            // 설명 텍스트
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 48),
              child: Text(
                '오른쪽은 좋아요, 왼쪽은 패스.\n간단하게 넘겨주세요.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  height: 1.4,
                  color: CupertinoColors.white,
                ),
              ),
            ),
            const SizedBox(height: 32),
            // 스텝 인디케이터
            _StepIndicator(
              currentStep: widget.currentStep,
              totalSteps: widget.totalSteps,
            ),
            const Spacer(flex: 3),
            // 하단 버튼
            Padding(
              padding: EdgeInsets.fromLTRB(32, 0, 32, bottomPadding + 24),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: _onSkip,
                    child: Text(
                      '건너뛰기',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                        color: CupertinoColors.white.withValues(alpha: 0.6),
                      ),
                    ),
                  ),
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: _onNext,
                    child: Text(
                      '다음',
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                        color: CupertinoColors.white.withValues(alpha: 0.6),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// =============================================================================
// 스와이프 방향 안내
// =============================================================================
class _SwipeDirection extends StatelessWidget {
  final AnimationController controller;
  final IconData icon;
  final String label;
  final Color iconColor;
  final bool isLeft;

  const _SwipeDirection({
    required this.controller,
    required this.icon,
    required this.label,
    required this.iconColor,
    required this.isLeft,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (_, child) {
        final offset = isLeft ? -10 * controller.value : 10 * controller.value;
        return Transform.translate(offset: Offset(offset, 0), child: child);
      },
      child: Column(
        children: [
          if (isLeft) ...[
            Icon(icon, size: 48, color: iconColor),
            const SizedBox(height: 8),
            Text(
              label,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 12,
                fontWeight: FontWeight.w500,
                letterSpacing: 2,
                color: CupertinoColors.white.withValues(alpha: 0.8),
              ),
            ),
          ] else ...[
            Text(
              label,
              style: TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 12,
                fontWeight: FontWeight.w500,
                letterSpacing: 2,
                color: CupertinoColors.white.withValues(alpha: 0.8),
              ),
            ),
            const SizedBox(height: 8),
            Icon(icon, size: 48, color: iconColor),
          ],
        ],
      ),
    );
  }
}

// =============================================================================
// 터치 인디케이터
// =============================================================================
class _TouchIndicator extends StatelessWidget {
  final AnimationController controller;

  const _TouchIndicator({required this.controller});

  @override
  Widget build(BuildContext context) {
    return Stack(
      alignment: Alignment.center,
      children: [
        // 핑 효과
        AnimatedBuilder(
          animation: controller,
          builder: (_, __) {
            return Container(
              width: 64 + (20 * controller.value),
              height: 64 + (20 * controller.value),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: CupertinoColors.white.withValues(
                  alpha: 0.1 * (1 - controller.value),
                ),
              ),
            );
          },
        ),
        // 터치 아이콘
        Transform.rotate(
          angle: 0.2,
          child: const Icon(
            CupertinoIcons.hand_point_right_fill,
            size: 48,
            color: CupertinoColors.white,
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 스텝 인디케이터
// =============================================================================
class _StepIndicator extends StatelessWidget {
  final int currentStep;
  final int totalSteps;

  const _StepIndicator({required this.currentStep, required this.totalSteps});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(totalSteps, (index) {
        final isActive = index + 1 == currentStep;
        return Container(
          width: isActive ? 24 : 8,
          height: 8,
          margin: const EdgeInsets.symmetric(horizontal: 4),
          decoration: BoxDecoration(
            color: isActive
                ? _AppColors.primary
                : CupertinoColors.white.withValues(alpha: 0.3),
            borderRadius: BorderRadius.circular(4),
          ),
        );
      }),
    );
  }
}

// =============================================================================
// 헬퍼 함수 - 오버레이 표시
// =============================================================================
Future<void> showSwipeTutorial(
  BuildContext context, {
  int currentStep = 2,
  int totalSteps = 4,
}) {
  return showCupertinoDialog(
    context: context,
    barrierDismissible: false,
    builder: (_) => SwipeTutorialOverlay(
      onSkip: () => Navigator.of(context).pop(),
      onNext: () => Navigator.of(context).pop(),
      currentStep: currentStep,
      totalSteps: totalSteps,
    ),
  );
}
