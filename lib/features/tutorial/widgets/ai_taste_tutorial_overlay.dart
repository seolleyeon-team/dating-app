// =============================================================================
// AI 취향 튜토리얼 오버레이 (코칭 마크)
// 경로: lib/features/tutorial/widgets/ai_taste_tutorial_overlay.dart
//
// 사용 예시:
// showDialog(
//   context: context,
//   barrierColor: Colors.transparent,
//   builder: (_) => AiTasteTutorialOverlay(
//     onNext: () => Navigator.pop(context),
//     currentStep: 1,
//     totalSteps: 3,
//   ),
// );
// =============================================================================

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF4D7D);
  static const Color overlayDim = Color(0xBF000000); // rgba(0, 0, 0, 0.75)
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color textMain = Color(0xFF111827);
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color pink100 = Color(0xFFFCE7F3);
  static const Color purple100 = Color(0xFFF3E8FF);
}

// =============================================================================
// 메인 오버레이
// =============================================================================
class AiTasteTutorialOverlay extends StatefulWidget {
  final VoidCallback onNext;
  final VoidCallback? onSkip;
  final int currentStep;
  final int totalSteps;

  const AiTasteTutorialOverlay({
    super.key,
    required this.onNext,
    this.onSkip,
    this.currentStep = 1,
    this.totalSteps = 3,
  });

  @override
  State<AiTasteTutorialOverlay> createState() => _AiTasteTutorialOverlayState();
}

class _AiTasteTutorialOverlayState extends State<AiTasteTutorialOverlay>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 500),
      vsync: this,
    );
    _fadeAnimation = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOut,
    );
    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 0.1),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic));
    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onNext() {
    HapticFeedback.mediumImpact();
    widget.onNext();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _fadeAnimation,
      child: Container(
        color: _AppColors.overlayDim,
        child: SafeArea(
          child: Stack(
            children: [
              // 상단 하이라이트 버튼
              Positioned(top: 8, right: 16, child: _HighlightedButton()),
              // 화살표
              Positioned(top: 80, right: 80, child: _ArrowIndicator()),
              // 중앙 툴팁
              Center(
                child: SlideTransition(
                  position: _slideAnimation,
                  child: const _TutorialTooltip(),
                ),
              ),
              // 하단 버튼 & 인디케이터
              Positioned(
                left: 32,
                right: 32,
                bottom: 100,
                child: Column(
                  children: [
                    CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: _onNext,
                      child: Container(
                        width: double.infinity,
                        height: 52,
                        decoration: BoxDecoration(
                          color: _AppColors.primary,
                          borderRadius: BorderRadius.circular(14),
                          boxShadow: [
                            BoxShadow(
                              color: _AppColors.primary.withValues(alpha: 0.3),
                              blurRadius: 16,
                              offset: const Offset(0, 6),
                            ),
                          ],
                        ),
                        child: const Center(
                          child: Text(
                            '다음',
                            style: TextStyle(
                              fontFamily: 'Pretendard',
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                              color: CupertinoColors.white,
                            ),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    _StepIndicator(
                      currentStep: widget.currentStep,
                      totalSteps: widget.totalSteps,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 하이라이트 버튼
// =============================================================================
class _HighlightedButton extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [_AppColors.pink100, _AppColors.purple100],
        ),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: _AppColors.primary, width: 2),
        boxShadow: [
          BoxShadow(
            color: _AppColors.primary.withValues(alpha: 0.6),
            blurRadius: 30,
            spreadRadius: 0,
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(
            CupertinoIcons.sparkles,
            size: 14,
            color: _AppColors.primary,
          ),
          const SizedBox(width: 6),
          const Text(
            'AI에게 내 취향 알려주기',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: _AppColors.textMain,
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 화살표 인디케이터
// =============================================================================
class _ArrowIndicator extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Transform.rotate(
      angle: -0.2,
      child: SizedBox(
        width: 64,
        height: 64,
        child: CustomPaint(painter: _ArrowPainter()),
      ),
    );
  }
}

class _ArrowPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color =
          const Color(0xFFFBB6CE) // pink-300
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    final path = Path()
      ..moveTo(size.width * 0.2, size.height * 0.8)
      ..cubicTo(
        size.width * 0.2,
        size.height * 0.5,
        size.width * 0.6,
        size.height * 0.5,
        size.width * 0.8,
        size.height * 0.2,
      );

    canvas.drawPath(path, paint);

    // 화살표 머리
    final arrowPath = Path()
      ..moveTo(size.width * 0.7, size.height * 0.2)
      ..lineTo(size.width * 0.8, size.height * 0.2)
      ..lineTo(size.width * 0.8, size.height * 0.3);

    canvas.drawPath(arrowPath, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

// =============================================================================
// 튜토리얼 툴팁
// =============================================================================
class _TutorialTooltip extends StatelessWidget {
  const _TutorialTooltip();

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 32),
      padding: const EdgeInsets.all(24),
      constraints: const BoxConstraints(maxWidth: 300),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: CupertinoColors.black.withValues(alpha: 0.2),
            blurRadius: 20,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 아이콘
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: _AppColors.pink100,
              shape: BoxShape.circle,
            ),
            child: const Icon(
              CupertinoIcons.lightbulb,
              color: _AppColors.primary,
              size: 24,
            ),
          ),
          const SizedBox(height: 16),
          // 타이틀
          const Text(
            'AI에게 당신의 취향을\n학습시켜 보세요',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 18,
              fontWeight: FontWeight.w700,
              height: 1.3,
              color: _AppColors.textMain,
            ),
          ),
          const SizedBox(height: 8),
          // 설명
          const Text(
            '추천이 더 정확해집니다.',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 14,
              color: _AppColors.textSecondary,
            ),
          ),
        ],
      ),
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
      children: [
        Text(
          '$currentStep',
          style: const TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 14,
            fontWeight: FontWeight.w500,
            color: CupertinoColors.white,
          ),
        ),
        Text(
          ' / $totalSteps',
          style: TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 14,
            fontWeight: FontWeight.w500,
            color: CupertinoColors.white.withValues(alpha: 0.5),
          ),
        ),
      ],
    );
  }
}

// =============================================================================
// 헬퍼 함수 - 오버레이 표시
// =============================================================================
Future<void> showAiTasteTutorial(
  BuildContext context, {
  int currentStep = 1,
  int totalSteps = 3,
}) {
  return showCupertinoDialog(
    context: context,
    barrierDismissible: false,
    builder: (_) => AiTasteTutorialOverlay(
      onNext: () => Navigator.of(context).pop(),
      currentStep: currentStep,
      totalSteps: totalSteps,
    ),
  );
}
