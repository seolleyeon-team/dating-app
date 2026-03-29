// =============================================================================
// 프로필 카드 액션 버튼 튜토리얼 오버레이
// 경로: lib/features/tutorial/widgets/action_buttons_tutorial_overlay.dart
//
// 사용 예시:
// showDialog(
//   context: context,
//   barrierColor: Colors.transparent,
//   builder: (_) => ActionButtonsTutorialOverlay(
//     onContinue: () => Navigator.pop(context),
//     currentStep: 3,
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
  static const Color overlayDark = Color(0xB3000000);
  static const Color pink100 = Color(0xFFFCE7F3);
  static const Color pink200 = Color(0xFFFBCFE8);
  static const Color pink500 = Color(0xFFEC4899);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray300 = Color(0xFFD1D5DB);
}

// =============================================================================
// 메인 오버레이
// =============================================================================
class ActionButtonsTutorialOverlay extends StatefulWidget {
  final VoidCallback onContinue;
  final int currentStep;
  final int totalSteps;

  const ActionButtonsTutorialOverlay({
    super.key,
    required this.onContinue,
    this.currentStep = 3,
    this.totalSteps = 4,
  });

  @override
  State<ActionButtonsTutorialOverlay> createState() =>
      _ActionButtonsTutorialOverlayState();
}

class _ActionButtonsTutorialOverlayState
    extends State<ActionButtonsTutorialOverlay>
    with SingleTickerProviderStateMixin {
  late AnimationController _bounceController;

  @override
  void initState() {
    super.initState();
    _bounceController = AnimationController(
      duration: const Duration(milliseconds: 1000),
      vsync: this,
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _bounceController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return GestureDetector(
      onTap: () {
        HapticFeedback.lightImpact();
        widget.onContinue();
      },
      child: Container(
        color: _AppColors.overlayDark,
        child: SafeArea(
          child: Stack(
            children: [
              // 상단 스텝 표시
              Positioned(
                top: 16,
                right: 24,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    color: CupertinoColors.white.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    '${widget.currentStep} / ${widget.totalSteps}',
                    style: const TextStyle(
                      fontFamily: 'Pretendard',
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      color: CupertinoColors.white,
                    ),
                  ),
                ),
              ),
              // 중앙 설명
              Positioned(
                left: 24,
                right: 24,
                bottom: 200,
                child: Column(
                  children: [
                    const Text(
                      '버튼으로도 선택할 수 있어요',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 20,
                        fontWeight: FontWeight.w700,
                        color: CupertinoColors.white,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      '판단이 빠를수록\n추천이 똑똑해져요.',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontFamily: 'Pretendard',
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                        height: 1.5,
                        color: CupertinoColors.white.withValues(alpha: 0.8),
                      ),
                    ),
                    const SizedBox(height: 16),
                    // 아래 화살표
                    AnimatedBuilder(
                      animation: _bounceController,
                      builder: (_, child) {
                        return Transform.translate(
                          offset: Offset(0, 8 * _bounceController.value),
                          child: child,
                        );
                      },
                      child: Icon(
                        CupertinoIcons.chevron_down,
                        size: 32,
                        color: CupertinoColors.white.withValues(alpha: 0.5),
                      ),
                    ),
                  ],
                ),
              ),
              // 하단 액션 버튼
              Positioned(
                left: 0,
                right: 0,
                bottom: bottomPadding + 24,
                child: const _ActionButtons(),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 액션 버튼
// =============================================================================
class _ActionButtons extends StatelessWidget {
  const _ActionButtons();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 48),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // 패스 버튼
          _ActionButton(
            icon: CupertinoIcons.xmark,
            iconColor: _AppColors.gray300,
            backgroundColor: CupertinoColors.white,
            borderColor: _AppColors.gray100,
            onTap: () {},
          ),
          const SizedBox(width: 40),
          // 좋아요 버튼
          _ActionButton(
            icon: CupertinoIcons.heart_fill,
            iconColor: _AppColors.pink500,
            backgroundColor: _AppColors.pink100,
            borderColor: _AppColors.pink200,
            onTap: () {},
          ),
        ],
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final Color backgroundColor;
  final Color borderColor;
  final VoidCallback onTap;

  const _ActionButton({
    required this.icon,
    required this.iconColor,
    required this.backgroundColor,
    required this.borderColor,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 72,
      height: 72,
      decoration: BoxDecoration(
        color: backgroundColor,
        shape: BoxShape.circle,
        border: Border.all(color: borderColor, width: 1),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.08),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Icon(icon, size: 36, color: iconColor),
    );
  }
}

// =============================================================================
// 헬퍼 함수 - 오버레이 표시
// =============================================================================
Future<void> showActionButtonsTutorial(
  BuildContext context, {
  int currentStep = 3,
  int totalSteps = 4,
}) {
  return showCupertinoDialog(
    context: context,
    barrierDismissible: false,
    builder: (_) => ActionButtonsTutorialOverlay(
      onContinue: () => Navigator.of(context).pop(),
      currentStep: currentStep,
      totalSteps: totalSteps,
    ),
  );
}
