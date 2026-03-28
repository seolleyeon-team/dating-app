// =============================================================================
// 대나무숲 튜토리얼 오버레이 (스포트라이트 마스크)
// 경로: lib/features/tutorial/widgets/bamboo_forest_tutorial_overlay.dart
//
// 사용 예시:
// showDialog(
//   context: context,
//   barrierColor: Colors.transparent,
//   builder: (_) => BambooForestTutorialOverlay(
//     onNext: () => Navigator.pop(context),
//     onSkip: () => Navigator.pop(context),
//     currentStep: 1,
//     totalSteps: 6,
//   ),
// );
// =============================================================================

import 'dart:ui';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFF43F85);
  static const Color overlayDark = Color(0xCC1F1F1F); // 80% opacity
}

// =============================================================================
// 메인 오버레이
// =============================================================================
class BambooForestTutorialOverlay extends StatefulWidget {
  final VoidCallback onNext;
  final VoidCallback? onSkip;
  final int currentStep;
  final int totalSteps;
  final Offset? spotlightCenter;
  final double spotlightRadius;

  const BambooForestTutorialOverlay({
    super.key,
    required this.onNext,
    this.onSkip,
    this.currentStep = 1,
    this.totalSteps = 6,
    this.spotlightCenter,
    this.spotlightRadius = 60,
  });

  @override
  State<BambooForestTutorialOverlay> createState() =>
      _BambooForestTutorialOverlayState();
}

class _BambooForestTutorialOverlayState
    extends State<BambooForestTutorialOverlay>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    _fadeAnimation = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOut,
    );
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

  void _onSkip() {
    HapticFeedback.lightImpact();
    widget.onSkip?.call();
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    // 기본 스포트라이트 위치 (하단 네비게이션 중앙)
    final spotlightCenter =
        widget.spotlightCenter ?? Offset(size.width * 0.28, size.height - 60);

    return FadeTransition(
      opacity: _fadeAnimation,
      child: Stack(
        children: [
          // 스포트라이트 마스크 오버레이
          CustomPaint(
            size: size,
            painter: _SpotlightPainter(
              center: spotlightCenter,
              radius: widget.spotlightRadius,
              overlayColor: _AppColors.overlayDark,
            ),
          ),
          // 스포트라이트 링
          Positioned(
            left: spotlightCenter.dx - widget.spotlightRadius - 5,
            top: spotlightCenter.dy - widget.spotlightRadius - 5,
            child: _PulsingRing(radius: widget.spotlightRadius + 5),
          ),
          // 콘텐츠
          SafeArea(
            child: Column(
              children: [
                // 상단 Skip 버튼
                Padding(
                  padding: const EdgeInsets.fromLTRB(0, 8, 24, 0),
                  child: Align(
                    alignment: Alignment.topRight,
                    child: CupertinoButton(
                      padding: EdgeInsets.zero,
                      onPressed: _onSkip,
                      child: Text(
                        'Skip',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                          color: CupertinoColors.white.withValues(alpha: 0.8),
                        ),
                      ),
                    ),
                  ),
                ),
                // 중앙 콘텐츠
                Expanded(child: Center(child: _TutorialCard())),
                // 하단 버튼 & 인디케이터
                Padding(
                  padding: EdgeInsets.fromLTRB(24, 0, 24, bottomPadding + 40),
                  child: Column(
                    children: [
                      // 도트 인디케이터
                      _DotIndicator(
                        currentStep: widget.currentStep,
                        totalSteps: widget.totalSteps,
                      ),
                      const SizedBox(height: 24),
                      // 다음 버튼
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: _onNext,
                        child: Container(
                          width: double.infinity,
                          height: 56,
                          decoration: BoxDecoration(
                            color: _AppColors.primary,
                            borderRadius: BorderRadius.circular(14),
                            boxShadow: [
                              BoxShadow(
                                color: _AppColors.primary.withValues(
                                  alpha: 0.3,
                                ),
                                blurRadius: 20,
                                spreadRadius: 0,
                              ),
                            ],
                          ),
                          child: const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(
                                '다음으로',
                                style: TextStyle(
                                  fontFamily: 'Pretendard',
                                  fontSize: 16,
                                  fontWeight: FontWeight.w700,
                                  color: CupertinoColors.white,
                                ),
                              ),
                              SizedBox(width: 6),
                              Icon(
                                CupertinoIcons.arrow_right,
                                size: 16,
                                color: CupertinoColors.white,
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                      // 스텝 텍스트
                      Text(
                        '${widget.currentStep} / ${widget.totalSteps}',
                        style: TextStyle(
                          fontFamily: 'Pretendard',
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                          letterSpacing: 2,
                          color: CupertinoColors.white.withValues(alpha: 0.4),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 스포트라이트 페인터
// =============================================================================
class _SpotlightPainter extends CustomPainter {
  final Offset center;
  final double radius;
  final Color overlayColor;

  _SpotlightPainter({
    required this.center,
    required this.radius,
    required this.overlayColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = overlayColor;

    // 전체 영역 경로
    final fullRect = Path()
      ..addRect(Rect.fromLTWH(0, 0, size.width, size.height));

    // 스포트라이트 원 경로
    final spotlight = Path()
      ..addOval(Rect.fromCircle(center: center, radius: radius));

    // 차집합 (전체 - 원)
    final maskedPath = Path.combine(
      PathOperation.difference,
      fullRect,
      spotlight,
    );

    canvas.drawPath(maskedPath, paint);
  }

  @override
  bool shouldRepaint(covariant _SpotlightPainter oldDelegate) =>
      center != oldDelegate.center ||
      radius != oldDelegate.radius ||
      overlayColor != oldDelegate.overlayColor;
}

// =============================================================================
// 펄싱 링
// =============================================================================
class _PulsingRing extends StatefulWidget {
  final double radius;

  const _PulsingRing({required this.radius});

  @override
  State<_PulsingRing> createState() => _PulsingRingState();
}

class _PulsingRingState extends State<_PulsingRing>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (_, __) {
        return Container(
          width: widget.radius * 2 + 10,
          height: widget.radius * 2 + 10,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(
              color: _AppColors.primary.withValues(
                alpha: 0.8 - (_controller.value * 0.6),
              ),
              width: 2,
            ),
            boxShadow: [
              BoxShadow(
                color: _AppColors.primary.withValues(
                  alpha: 0.8 - (_controller.value * 0.6),
                ),
                blurRadius: 15,
                spreadRadius: 0,
              ),
            ],
          ),
        );
      },
    );
  }
}

// =============================================================================
// 튜토리얼 카드
// =============================================================================
class _TutorialCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(20),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 32),
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: CupertinoColors.white.withValues(alpha: 0.1),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: CupertinoColors.white.withValues(alpha: 0.2),
            ),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // 타이틀
              const Text(
                '대나무숲에 오신걸\n환영해요! 🎋',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 24,
                  fontWeight: FontWeight.w700,
                  height: 1.3,
                  color: CupertinoColors.white,
                ),
              ),
              const SizedBox(height: 16),
              // 설명
              RichText(
                textAlign: TextAlign.center,
                text: TextSpan(
                  style: TextStyle(
                    fontFamily: 'Pretendard',
                    fontSize: 14,
                    height: 1.6,
                    color: CupertinoColors.white.withValues(alpha: 0.8),
                  ),
                  children: const [
                    TextSpan(text: '대나무숲은 익명으로\n연애 썰/고민/성공후기를 나누는\n'),
                    TextSpan(
                      text: '비밀스러운 공간',
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        color: _AppColors.primary,
                      ),
                    ),
                    TextSpan(text: '이에요.'),
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
// 도트 인디케이터
// =============================================================================
class _DotIndicator extends StatelessWidget {
  final int currentStep;
  final int totalSteps;

  const _DotIndicator({required this.currentStep, required this.totalSteps});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(totalSteps, (index) {
        final isActive = index < currentStep;
        return Container(
          width: 8,
          height: 8,
          margin: const EdgeInsets.symmetric(horizontal: 4),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: isActive
                ? _AppColors.primary
                : CupertinoColors.white.withValues(alpha: 0.3),
          ),
        );
      }),
    );
  }
}

// =============================================================================
// 헬퍼 함수 - 오버레이 표시
// =============================================================================
Future<void> showBambooForestTutorial(
  BuildContext context, {
  int currentStep = 1,
  int totalSteps = 6,
  Offset? spotlightCenter,
  double spotlightRadius = 60,
}) {
  return showCupertinoDialog(
    context: context,
    barrierDismissible: false,
    builder: (_) => BambooForestTutorialOverlay(
      onNext: () => Navigator.of(context).pop(),
      onSkip: () => Navigator.of(context).pop(),
      currentStep: currentStep,
      totalSteps: totalSteps,
      spotlightCenter: spotlightCenter,
      spotlightRadius: spotlightRadius,
    ),
  );
}
